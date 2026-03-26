# utils/evaluate_ragas.py
"""
 ÉVALUATION RAGAS — NBA Analyst AI

Ce script évalue la qualité du système RAG sur 3 catégories :
  - SIMPLE   : questions directes, une stat
  - COMPLEXE : agrégations, comparaisons multi-critères
  - BRUITÉ   : fautes de frappe, questions hors-champ

Architecture du script :
  1. Pydantic         : valider les flux entrée/sortie du pipeline
  2. Pydantic AI      : envelopper l'appel LLM avec sortie structurée
  3. Logfire          : tracer chaque étape (retrieval → génération → évaluation)
  4. RAGAS evaluate   : calculer les 4 métriques de qualité
  5. Tableau résultats : synthèse par catégorie

Métriques RAGAS utilisées :
  - answer_relevancy  : la réponse répond-elle à la question ?
  - faithfulness      : la réponse est-elle fidèle aux contextes récupérés ?
  - context_recall    : les bons contextes ont-ils été trouvés ?     
  - context_precision : les contextes récupérés sont-ils utiles ?    

"""

import os
import sys
import time
import logging
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

# 1. PYDANTIC — Modèles de validation des données

# Pydantic garantit que les données ont le bon format à chaque étape
# Si une question mal formée arrive, elle sera rejetée AVANT d'appeler le LLM
from pydantic import BaseModel, Field, field_validator


class QuestionInput(BaseModel):
    """Valide le format d'une question de test avant de l'envoyer au RAG"""
    id: str
    question: str = Field(min_length=5, description="La question posée au système")
    ground_truth: str = Field(min_length=1)
    category: str  # SIMPLE | COMPLEXE | BRUITÉ
    difficulty: int = Field(ge=1, le=3)
    context_needed: str

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        """Rejette les questions vides ou composées uniquement d'espaces"""
        if not v.strip():
            raise ValueError("La question ne peut pas être vide")
        return v.strip()

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str) -> str:
        allowed = {"SIMPLE", "COMPLEXE", "BRUITÉ"}
        if v not in allowed:
            raise ValueError(f"Catégorie invalide '{v}'. Attendu : {allowed}")
        return v


class RAGResult(BaseModel):
    """Valide la sortie du pipeline RAG avant de la passer à RAGAS"""
    answer: str = Field(min_length=1, description="Réponse générée par le LLM")
    contexts: list[str] = Field(min_length=1, description="Chunks récupérés par le retriever")
    num_contexts: int = Field(ge=0)

    @field_validator("contexts")
    @classmethod
    def remove_empty_contexts(cls, v: list[str]) -> list[str]:
        """Supprime les chunks vides qui pourraient fausser les métriques RAGAS"""
        cleaned = [c for c in v if c.strip()]
        return cleaned if cleaned else ["Aucun contexte pertinent trouvé"]


class EvaluationRow(BaseModel):
    """Une ligne complète pour le dataset RAGAS (les 4 colonnes + métadonnées)"""
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    category: str
    difficulty: int
    question_id: str


# 2. PYDANTIC AI — Agent LLM avec sortie structurée

# Pydantic AI garantit que la réponse du LLM est bien une string non vide

# ici l'agent valide automatiquement la sortie via le modèle Pydantic
from pydantic_ai import Agent
from pydantic_ai.models.mistral import MistralModel


class NBAAnswer(BaseModel):
    """Structure de la réponse attendue du LLM NBA"""
    answer: str = Field(min_length=1, description="Réponse factuelle basée sur le contexte")


# L'agent Pydantic AI utilise Mistral et force une sortie conforme à NBAAnswer
nba_agent = Agent(
    model=MistralModel("mistral-small-latest"),
    output_type=NBAAnswer,
    system_prompt=(
        "Tu es NBA Analyst AI, un expert NBA. "
        "Réponds à la question en te basant UNIQUEMENT sur le contexte fourni. "
        "Si le contexte ne contient pas la réponse, dis clairement que tu ne sais pas."
    ),
)



# 3. LOGFIRE — Configuration de l'observabilité
# Logfire trace chaque étape et les affiche dans un dashboard
import logfire

logfire.configure(
    token=os.getenv("LOGFIRE_TOKEN"),
    advanced=logfire.AdvancedOptions(
        base_url="https://logfire-eu.pydantic.dev"
    ),
    service_name="nba-rag-eval"
)

logfire.info("test_logfire_connection")

logfire.instrument_pydantic_ai()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 4. INITIALISATION DES CLIENTS

from utils.config import MISTRAL_API_KEY, SEARCH_K
from utils.vector_store import VectorStoreManager
from utils.questions import TEST_QUESTIONS

# LLM évaluateur pour RAGAS (différent du LLM de génération ),pour "juger" les réponses générées
from langchain_mistralai import ChatMistralAI, MistralAIEmbeddings
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

evaluator_llm = LangchainLLMWrapper(
    ChatMistralAI(
        model="mistral-small-latest",
        mistral_api_key=MISTRAL_API_KEY,
        temperature=0,
    )
)

evaluator_embeddings = LangchainEmbeddingsWrapper(
    MistralAIEmbeddings(
        model="mistral-embed",
        mistral_api_key=MISTRAL_API_KEY,
    )
)

# index FAISS déjà construit par indexer.py
vector_store = VectorStoreManager()

if vector_store.index is None:
    logging.error("Index FAISS non chargé. Lance d'abord : python indexer.py")
    sys.exit(1)

# 5. PIPELINE RAG — Fonction autonome tracée par Logfire


def run_rag(question_input: QuestionInput) -> RAGResult:
    """
    Exécute le pipeline RAG complet pour une question
    Chaque sous-étape (retrieval, génération) est tracée par Logfire

    Retourne un RAGResult validé par Pydantic
    """
    with logfire.span(
        "rag_pipeline",
        question_id=question_input.id,
        category=question_input.category,
        difficulty=question_input.difficulty,
    ):
        # ÉTAPE R : Retrieval 
        # On interroge l'index FAISS pour récupérer les chunks pertinents
        with logfire.span("retrieval", question=question_input.question):
            search_results = vector_store.search(question_input.question, k=SEARCH_K)
            contexts = [r["text"] for r in search_results]
            logfire.info(
                "retrieval_complete",
                contexts_preview=contexts[:2],
                num_contexts=len(contexts),
                top_scores=[round(r["score"], 2) for r in search_results[:3]],
            )

        # ÉTAPE A : Augmentation 
        # On construit le prompt en injectant les contextes récupérés
        context_str = "\n\n---\n\n".join(contexts) if contexts else "Aucun contexte disponible."
        user_prompt = (
            f"Contexte :\n{context_str}\n\n"
            f"Question : {question_input.question}"
        )

        # ÉTAPE G : Generation
        # Pydantic AI appelle Mistral et valide que la sortie est bien un NBAAnswer
        with logfire.span("generation", question_id=question_input.id):
            result = nba_agent.run_sync(user_prompt)
            answer = result.output.answer  # Validé par Pydantic (NBAAnswer.answer)
            logfire.info("generation_complete", answer_length=len(answer))
            logfire.info(
                "rag_output",
                question=question_input.question,
                answer=answer,
                num_contexts=len(contexts),
)

        # Validation Pydantic de la sortie du pipeline
        return RAGResult(
            answer=answer,
            contexts=contexts if contexts else ["Aucun contexte trouvé"],
            num_contexts=len(contexts),
        )


# 6. BOUCLE D'ÉVALUATION


def collect_rag_results() -> list[EvaluationRow]:
    """Exécute le pipeline RAG sur toutes les questions du jeu de test"""
    rows: list[EvaluationRow] = []

    with logfire.span("evaluation_loop", total_questions=len(TEST_QUESTIONS)):
        for q_data in TEST_QUESTIONS:
            try:
                # Validation Pydantic de l'entrée — rejette les données malformées
                q = QuestionInput(**q_data)
                logfire.info("processing_question", id=q.id, category=q.category)

                rag_result = run_rag(q)

                row = EvaluationRow(
                    question=q.question,
                    answer=rag_result.answer,
                    contexts=rag_result.contexts,
                    ground_truth=q.ground_truth,
                    category=q.category,
                    difficulty=q.difficulty,
                    question_id=q.id,
                )
                rows.append(row)
                logging.info(f"[{q.id}] ✓ {q.category} — {len(rag_result.contexts)} contextes récupérés")
                time.sleep(5)

            except Exception as e:
                logfire.error("question_failed", id=q_data.get("id"), error=str(e))
                logging.error(f"Erreur pour {q_data.get('id')} : {e}")

    logging.info(f"\n{len(rows)}/{len(TEST_QUESTIONS)} questions traitées avec succès")
    return rows



# 7. ÉVALUATION RAGAS

def run_ragas_evaluation(rows: list[EvaluationRow]) -> pd.DataFrame:
    """
    Lance l'évaluation RAGAS sur le dataset collecté
    """
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import AnswerRelevancy, Faithfulness, ContextRecall, ContextPrecision  # noqa: F401
    from ragas.run_config import RunConfig

    # Construction du dataset RAGAS (format HuggingFace Dataset)

    dataset = Dataset.from_dict({
        "user_input":         [r.question for r in rows],
        "response":           [r.answer for r in rows],
        "retrieved_contexts": [r.contexts for r in rows],
        "reference":          [r.ground_truth for r in rows],
    })

    logging.info(f"Lancement de l'évaluation RAGAS sur {len(rows)} échantillons...")

    with logfire.span("ragas_evaluation", num_samples=len(rows)):
        metrics = [
            # AnswerRelevancy incompatible avec LangchainLLMWrapper (bug RAGAS 0.4.x, dict += dict)
            Faithfulness(),       # La réponse est-elle ancrée dans les contextes ?
            ContextRecall(),      # Les contextes contiennent-ils la bonne réponse ?
            ContextPrecision(),   # Les contextes récupérés sont-ils tous utiles ?
        ]
        print(dataset.features)

        results = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=evaluator_llm,
            embeddings=evaluator_embeddings,
            run_config=RunConfig(max_workers=1, max_retries=5, max_wait=120),
        )

    # Convertir les scores en DataFrame
    df_scores = results.to_pandas()

    # Ajouter les métadonnées (catégorie, difficulté)
    df_meta = pd.DataFrame([{
        "question":    r.question,
        "question_id": r.question_id,
        "category":    r.category,
        "difficulty":  r.difficulty,
    } for r in rows])

    df_final = pd.merge(df_scores, df_meta, left_on="user_input", right_on="question", how="left")
    return df_final



# 8. Tableau comparatif des scores

METRIC_COLS = ["answer_relevancy", "faithfulness", "context_recall", "context_precision"]


def print_summary(df: pd.DataFrame) -> None:
    """
    Affiche le tableau comparatif des scores par catégorie
    """
    available = [c for c in METRIC_COLS if c in df.columns]

    print("\n" + "=" * 75)
    print("  TABLEAU COMPARATIF - Scores RAGAS par catégorie")
    print("=" * 75)

    # Scores par catégorie
    summary = df.groupby("category")[available].mean().round(3)
    print(summary.to_string())


# ─────────────────────────────────────────────────────────────────
# 9. PIPELINE HYBRIDE — SQL + RAG (mode enrichi)
# ─────────────────────────────────────────────────────────────────
# Ce pipeline est identique à ce que fait MistralChat.py :
#   1. Le LLM classifie la question → SQL ou RAG
#   2. SQL → query_nba_database() → contexte = résultat tabulaire
#   3. RAG → FAISS search → contexte = chunks textuels
# Cela permet de mesurer l'amélioration apportée par l'intégration SQL.

from mistralai import Mistral as _MistralDirect
from utils.sql_tool import query_nba_database

_direct_client = _MistralDirect(api_key=MISTRAL_API_KEY)

ROUTING_PROMPT = """Tu es un routeur pour un assistant NBA.
Réponds UNIQUEMENT par SQL ou RAG, rien d'autre.

SQL  → classements, top N, comparaisons de stats, filtres numériques, moyennes par équipe.
RAG  → définitions, analyses qualitatives, opinions, contexte historique.

Question : {question}
Réponse :"""


def _classify(question: str) -> str:
    """Classifie la question en SQL ou RAG (même logique que MistralChat.py)."""
    try:
        r = _direct_client.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": ROUTING_PROMPT.format(question=question)}],
            temperature=0,
            max_tokens=5,
        )
        decision = r.choices[0].message.content.strip().upper()
        return "SQL" if "SQL" in decision else "RAG"
    except Exception:
        return "RAG"


def run_hybrid(question_input: QuestionInput) -> tuple[RAGResult, str]:
    """
    Pipeline hybride : route vers SQL ou RAG selon la nature de la question.
    Retourne (RAGResult, mode_utilisé).
    """
    with logfire.span(
        "hybrid_pipeline",
        question_id=question_input.id,
        category=question_input.category,
    ):
        mode = _classify(question_input.question)
        logfire.info("routing_decision", mode=mode, question_id=question_input.id)

        if mode == "SQL":
            # ── Branche SQL ──────────────────────────────────────
            with logfire.span("sql_query", question_id=question_input.id):
                sql_result = query_nba_database(question_input.question)
                logfire.info("sql_done", rows_preview=sql_result[:200])

            # Contexte = le résultat SQL formaté (RAGAS l'évaluera comme contexte)
            contexts = [sql_result]
            prompt = (
                f"Données issues de la base NBA :\n{sql_result}\n\n"
                f"Question : {question_input.question}"
            )
        else:
            # ── Branche RAG ──────────────────────────────────────
            with logfire.span("rag_retrieval", question_id=question_input.id):
                search_results = vector_store.search(question_input.question, k=SEARCH_K)
                contexts = [r["text"] for r in search_results]
                logfire.info("retrieval_done", num_contexts=len(contexts))

            context_str = "\n\n---\n\n".join(contexts) if contexts else "Aucun contexte."
            prompt = f"Contexte :\n{context_str}\n\nQuestion : {question_input.question}"

        # ── Génération (Pydantic AI) ──────────────────────────
        with logfire.span("hybrid_generation", question_id=question_input.id):
            result = nba_agent.run_sync(prompt)
            answer = result.output.answer

        return RAGResult(
            answer=answer,
            contexts=contexts if contexts else ["Aucun contexte trouvé."],
            num_contexts=len(contexts),
        ), mode


def collect_hybrid_results() -> list[EvaluationRow]:
    """Exécute le pipeline hybride (SQL+RAG) sur toutes les questions."""
    rows: list[EvaluationRow] = []

    with logfire.span("hybrid_evaluation_loop", total_questions=len(TEST_QUESTIONS)):
        for q_data in TEST_QUESTIONS:
            try:
                q = QuestionInput(**q_data)
                result, mode = run_hybrid(q)

                row = EvaluationRow(
                    question=q.question,
                    answer=result.answer,
                    contexts=result.contexts,
                    ground_truth=q.ground_truth,
                    category=q.category,
                    difficulty=q.difficulty,
                    question_id=q.id,
                )
                rows.append(row)
                logging.info(f"[{q.id}] ✓ {mode} — {q.category}")
                import time; time.sleep(3)

            except Exception as e:
                logfire.error("hybrid_question_failed", id=q_data.get("id"), error=str(e))
                logging.error(f"Erreur {q_data.get('id')} : {e}")

    logging.info(f"{len(rows)}/{len(TEST_QUESTIONS)} questions traitées.")
    return rows


if __name__ == "__main__":
    import argparse
    import traceback

    parser = argparse.ArgumentParser(description="Évaluation RAGAS — NBA Analyst AI")
    parser.add_argument(
        "--mode",
        choices=["rag", "hybrid"],
        default="rag",
        help="rag = baseline FAISS seul | hybrid = SQL + RAG (défaut: rag)",
    )
    args = parser.parse_args()

    try:
        logging.info(f"Démarrage évaluation RAGAS — mode : {args.mode.upper()}")

        # Collecte des résultats selon le mode
        if args.mode == "hybrid":
            rows = collect_hybrid_results()
            out_csv  = "outputs/ragas_results_hybrid.csv"
            out_json = "outputs/ragas_results_hybrid.json"
        else:
            rows = collect_rag_results()
            out_csv  = "outputs/ragas_results.csv"
            out_json = "outputs/ragas_results.json"

        if not rows:
            logging.error("Aucun résultat collecté.")
            sys.exit(1)

        # Évaluation RAGAS
        df_results = run_ragas_evaluation(rows)

        # Affichage
        print_summary(df_results)

        # Sauvegarde
        Path("outputs").mkdir(exist_ok=True)
        df_results.to_csv(out_csv, index=False, encoding="utf-8")
        df_results.to_json(out_json, orient="records", force_ascii=False, indent=2)
        logging.info(f"Résultats → {out_csv} et {out_json}")

    except Exception as e:
        print(f"\nERREUR : {e}")
        traceback.print_exc()
        sys.exit(1)
