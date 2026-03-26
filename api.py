# api.py
"""
API REST — NBA Analyst AI

Expose le pipeline RAG + SQL via des endpoints HTTP

Endpoints :
  GET  /health          -> état du système (index FAISS + base SQL)
  GET  /stats           -> statistiques de la base de données
  POST /query           -> question → réponse (routage SQL ou RAG automatique)
  POST /query/rag       -> force le mode RAG (FAISS uniquement)
  POST /query/sql       -> force le mode SQL

Lancement :
  uvicorn api:app --reload --port 8000

Exemples curl :
  curl http://localhost:8000/health
  curl -X POST http://localhost:8000/query \
       -H "Content-Type: application/json" \
       -d '{"question": "Qui a le plus de points cette saison ?"}'
"""

import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# MODÈLES PYDANTIC — Requêtes et Réponses de l'API

class QueryRequest(BaseModel):
    """Corps d'une requête POST /query"""
    question: str = Field(
        min_length=3,
        description="La question posée en langage naturel",
        examples=["Qui a le plus de points cette saison ?"]
    )
    k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Nombre de documents à récupérer (mode RAG uniquement)"
    )


class SourceDocument(BaseModel):
    """Un document source utilisé pour construire la réponse"""
    source: str
    score: Optional[float] = None
    excerpt: str


class QueryResponse(BaseModel):
    """Réponse complète d'une requête /query"""
    question: str
    answer: str
    mode: str              # "SQL" ou "RAG"
    sources: list[SourceDocument]
    sql_query_result: Optional[str] = None  # données brutes SQL si mode SQL


class HealthResponse(BaseModel):
    """Réponse du endpoint /health."""
    status: str            # "ok" ou "degraded"
    faiss_index: str       # "loaded (N vecteurs)" ou "not loaded"
    sql_database: str      # "connected (N joueurs)" ou "not connected"
    model: str


class StatsResponse(BaseModel):
    """Statistiques de la base de données"""
    total_players: int
    total_teams: int
    sample_leaders: dict   # top 3 scoreurs pour vérification rapide


# CHARGEMENT DES RESSOURCES AU DÉMARRAGE

# Le @asynccontextmanager lifespan charge les ressources lourdes
# (FAISS, clients Mistral) une seule fois au démarrage du serveur,
# évitant de les recharger à chaque requête

from utils.config import MISTRAL_API_KEY, MODEL_NAME, SEARCH_K, DATABASE_FILE
from utils.vector_store import VectorStoreManager
from utils.sql_tool import query_nba_database
from mistralai import Mistral

# Ressources globales (initialisées dans lifespan)
_vector_store: Optional[VectorStoreManager] = None
_mistral_client: Optional[Mistral] = None

ROUTING_PROMPT = """Tu es un routeur pour un assistant NBA.
Réponds UNIQUEMENT par SQL ou RAG, rien d'autre.

SQL  -> classements, top N, chiffres précis, comparaisons statistiques, moyennes par équipe.
RAG  -> définitions, analyses qualitatives, opinions, contexte historique.

Question : {question}
Réponse :"""

RAG_PROMPT = """Tu es NBA Analyst AI. Réponds à partir du contexte UNIQUEMENT.
Si le contexte ne contient pas la réponse, dis-le clairement.

CONTEXTE :
{context}

QUESTION : {question}

RÉPONSE :"""

SQL_PROMPT = """Tu es NBA Analyst AI. Synthétise ces données NBA en une réponse claire.

DONNÉES :
{data}

QUESTION : {question}

RÉPONSE :"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise les ressources au démarrage, les libère à l'arrêt"""
    global _vector_store, _mistral_client

    logging.info("Démarrage de l'API — chargement des ressources...")
    _mistral_client = Mistral(api_key=MISTRAL_API_KEY)
    _vector_store = VectorStoreManager()

    if _vector_store.index is None:
        logging.warning("Index FAISS non chargé. Mode RAG indisponible")
    else:
        logging.info(f"FAISS chargé : {_vector_store.index.ntotal} vecteurs")

    yield  # L'API tourne ici

    logging.info("Arrêt de l'API.")


app = FastAPI(
    title="NBA Analyst AI — API REST",
    description=(
        "API REST exposant le pipeline hybride RAG + SQL. "
        "Chaque question est automatiquement routée vers la source "
        "la plus appropriée (base SQL pour les stats, FAISS pour l'analyse)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# FONCTIONS INTERNES

def _classify(question: str) -> str:
    """Classifie la question : SQL ou RAG"""
    try:
        r = _mistral_client.chat.complete(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": ROUTING_PROMPT.format(question=question)}],
            temperature=0,
            max_tokens=5,
        )
        decision = r.choices[0].message.content.strip().upper()
        return "SQL" if "SQL" in decision else "RAG"
    except Exception:
        return "RAG"


def _generate(prompt: str) -> str:
    """Appelle le LLM Mistral pour générer une réponse"""
    r = _mistral_client.chat.complete(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "Tu es un expert NBA. Réponds en français"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    return r.choices[0].message.content


def _run_rag(question: str, k: int) -> tuple[str, list[SourceDocument]]:
    """Exécute le pipeline RAG (FAISS + LLM)"""
    if _vector_store is None or _vector_store.index is None:
        raise HTTPException(status_code=503, detail="Index FAISS non disponible.")

    results = _vector_store.search(question, k=k)
    contexts = [r["text"] for r in results]
    sources = [
        SourceDocument(
            source=r["metadata"].get("source", "?"),
            score=round(r["score"], 2),
            excerpt=r["text"][:200] + "...",
        )
        for r in results
    ]

    context_str = "\n\n---\n\n".join(contexts) if contexts else "Aucun contexte trouvé"
    answer = _generate(RAG_PROMPT.format(context=context_str, question=question))
    return answer, sources


def _run_sql(question: str) -> tuple[str, list[SourceDocument], str]:
    """Exécute le pipeline SQL (Text-to-SQL + LLM)"""
    sql_result = query_nba_database(question)
    sources = [SourceDocument(source="SQLite — player_stats", score=None, excerpt=sql_result[:300])]
    answer = _generate(SQL_PROMPT.format(data=sql_result, question=question))
    return answer, sources, sql_result



# ENDPOINTS

@app.get("/health", response_model=HealthResponse, tags=["Système"])
def health():
    """
    Vérifie l'état du système
    Retourne le statut de l'index FAISS et de la base SQL
    """
    # Statut FAISS
    if _vector_store and _vector_store.index:
        faiss_status = f"loaded ({_vector_store.index.ntotal} vecteurs)"
    else:
        faiss_status = "not loaded"

    # Statut SQL
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        (n,) = conn.execute("SELECT COUNT(*) FROM players").fetchone()
        conn.close()
        sql_status = f"connected ({n} joueurs)"
    except Exception:
        sql_status = "not connected"

    overall = "ok" if "loaded" in faiss_status and "connected" in sql_status else "degraded"

    return HealthResponse(
        status=overall,
        faiss_index=faiss_status,
        sql_database=sql_status,
        model=MODEL_NAME,
    )


@app.get("/stats", response_model=StatsResponse, tags=["Système"])
def stats():
    """
    Retourne des statistiques sur la base de données
    Utile pour vérifier que l'ingestion Excel s'est bien passée
    """
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        (n_players,) = conn.execute("SELECT COUNT(*) FROM players").fetchone()
        (n_teams,) = conn.execute("SELECT COUNT(*) FROM teams").fetchone()
        top3 = conn.execute(
            "SELECT p.name, p.team_code, s.pts "
            "FROM players p JOIN player_stats s ON p.player_id = s.player_id "
            "ORDER BY s.pts DESC LIMIT 3"
        ).fetchall()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Base SQL inaccessible : {e}")

    return StatsResponse(
        total_players=n_players,
        total_teams=n_teams,
        sample_leaders={
            f"#{i+1}": f"{row[0]} ({row[1]}) — {row[2]} pts"
            for i, row in enumerate(top3)
        },
    )


@app.post("/query", response_model=QueryResponse, tags=["RAG"])
def query(request: QueryRequest):
    """
    Endpoint principal — routage automatique SQL ou RAG

    Le LLM analyse la question et choisit la source la plus adaptée :
    - **SQL** pour les questions chiffrées (classements, stats précises)
    - **RAG** pour les analyses qualitatives et définitions

    **Exemple de requête :**
    ```json
    {"question": "Qui a le plus de points cette saison ?", "k": 5}
    ```

    **Exemple de réponse :**
    ```json
    {
      "question": "Qui a le plus de points cette saison ?",
      "answer": "Shai Gilgeous-Alexander (OKC) avec 2485 points.",
      "mode": "SQL",
      "sources": [{"source": "SQLite — player_stats", ...}]
    }
    ```
    """
    logging.info(f"POST /query — '{request.question}'")
    mode = _classify(request.question)

    try:
        if mode == "SQL":
            answer, sources, sql_raw = _run_sql(request.question)
            return QueryResponse(
                question=request.question,
                answer=answer,
                mode="SQL",
                sources=sources,
                sql_query_result=sql_raw,
            )
        else:
            answer, sources = _run_rag(request.question, k=request.k)
            return QueryResponse(
                question=request.question,
                answer=answer,
                mode="RAG",
                sources=sources,
            )
    except HTTPException:
        raise
    except Exception as e:
        logging.exception(f"Erreur /query : {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/rag", response_model=QueryResponse, tags=["RAG"])
def query_rag(request: QueryRequest):
    """
    Force le mode RAG (FAISS) — ignore le routeur automatique
    Utile pour comparer RAG vs SQL sur une même question
    """
    logging.info(f"POST /query/rag — '{request.question}'")
    try:
        answer, sources = _run_rag(request.question, k=request.k)
        return QueryResponse(
            question=request.question,
            answer=answer,
            mode="RAG",
            sources=sources,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/sql", response_model=QueryResponse, tags=["RAG"])
def query_sql(request: QueryRequest):
    """
    Force le mode SQL — ignore le routeur automatique
    Utile pour tester la génération SQL sur des questions ambiguës
    """
    logging.info(f"POST /query/sql — '{request.question}'")
    try:
        answer, sources, sql_raw = _run_sql(request.question)
        return QueryResponse(
            question=request.question,
            answer=answer,
            mode="SQL",
            sources=sources,
            sql_query_result=sql_raw,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
