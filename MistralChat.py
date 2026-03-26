# MistralChat.py (version RAG + SQL)
import streamlit as st
import logging
from mistralai import Mistral
from dotenv import load_dotenv

load_dotenv()

# --- Importations depuis vos modules ---
try:
    from utils.config import (
        MISTRAL_API_KEY, MODEL_NAME, SEARCH_K,
        APP_TITLE, NAME
    )
    from utils.vector_store import VectorStoreManager
    from utils.sql_tool import query_nba_database
except ImportError as e:
    st.error(f"Erreur d'importation: {e}.")
    st.stop()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

api_key = MISTRAL_API_KEY
model = MODEL_NAME

if not api_key:
    st.error("Clé API Mistral non trouvée (MISTRAL_API_KEY). Définissez-la dans .env")
    st.stop()

try:
    client = Mistral(api_key=api_key)
except Exception as e:
    st.error(f"Erreur initialisation client Mistral : {e}")
    st.stop()


# CHARGEMENT DES RESSOURCES (mis en cache pour la session)

@st.cache_resource
def get_vector_store_manager():
    try:
        manager = VectorStoreManager()
        if manager.index is None or not manager.document_chunks:
            logging.error("Index FAISS non chargé")
            return None
        logging.info(f"VectorStoreManager chargé ({manager.index.ntotal} vecteurs)")
        return manager
    except Exception as e:
        logging.exception(f"Erreur chargement VectorStoreManager: {e}")
        return None

vector_store_manager = get_vector_store_manager()


# ROUTEUR : SQL ou RAG ?

# C'est le cerveau de l'agent hybride
# Le LLM analyse la question et décide quelle source de données utiliser
#
#   SQL  -> questions chiffrées, classements, comparaisons, filtres
#   RAG  -> analyses qualitatives, définitions, débats, contexte textuel

ROUTING_PROMPT = """Tu es un routeur pour un assistant NBA.
Ton unique rôle est de décider si une question nécessite SQL ou RAG.

SQL  -> questions avec des chiffres précis, classements, top N, comparaisons statistiques,
        filtres (minimum X matchs), moyennes par équipe.
RAG  -> définitions ("c'est quoi le NETRTG ?"), analyses qualitatives ("quel est le style de
        Wembanyama ?"), opinions, débats, contexte historique.

Réponds UNIQUEMENT par le mot SQL ou RAG, rien d'autre.

Question : {question}
Réponse :"""


def classifier_question(question: str) -> str:
    """
    Classe la question en 'SQL' ou 'RAG' via un appel LLM léger
    Retourne 'SQL' ou 'RAG'
    """
    try:
        response = client.chat.complete(
            model=model,
            messages=[{
                "role": "user",
                "content": ROUTING_PROMPT.format(question=question)
            }],
            temperature=0,      # déterministe
            max_tokens=5,       # on attend juste "SQL" ou "RAG"
        )
        decision = response.choices[0].message.content.strip().upper()
        # Sécurité : si la réponse n'est pas attendue, on utilise RAG par défaut
        return "SQL" if "SQL" in decision else "RAG"
    except Exception as e:
        logging.warning(f"Erreur routeur, fallback RAG : {e}")
        return "RAG"


# PROMPTS SYSTÈME

# Prompt RAG : répond à partir des chunks textuels
RAG_SYSTEM_PROMPT = """Tu es 'NBA Analyst AI', un expert NBA.
Réponds à la question en te basant UNIQUEMENT sur le contexte fourni ci-dessous.
Si le contexte ne contient pas la réponse, dis-le clairement.

CONTEXTE :
{context_str}

QUESTION : {question}

RÉPONSE :"""

# Prompt SQL : synthétise les données brutes retournées par la base
SQL_SYSTEM_PROMPT = """Tu es 'NBA Analyst AI', un expert NBA.
Les données suivantes viennent d'une requête SQL sur la base de statistiques NBA.
Synthétise ces données en une réponse claire et engageante pour un fan de basketball.

DONNÉES SQL :
{sql_result}

QUESTION : {question}

RÉPONSE :"""


# GÉNÉRATION DE RÉPONSE

def generer_reponse(messages: list[dict]) -> str:
    try:
        response = client.chat.complete(
            model=model,
            messages=messages,
            temperature=0.1,
        )
        if response.choices:
            return response.choices[0].message.content
        return "Je n'ai pas pu générer de réponse"
    except Exception as e:
        logging.exception("Erreur API Mistral")
        return f"Erreur technique : {e}"


# INTERFACE STREAMLIT

st.title(APP_TITLE)
st.caption(f"Assistant virtuel NBA | Modèle : {model} | Sources : FAISS + SQLite")

# Historique de conversation
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": (
            f"Bonjour ! Je suis votre analyste IA NBA. "
            f"Posez-moi vos questions sur les joueurs, équipes et statistiques. "
            f"J'utilise à la fois une base de données SQL (stats précises) "
            f"et une base de connaissances textuelle (analyses, débats)."
        )
    }]

# Affichage de l'historique
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])


# TRAITEMENT D'UNE NOUVELLE QUESTION

if prompt := st.chat_input(f"Posez votre question sur la {NAME}..."):

    # 1. Afficher la question de l'utilisateur
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.text("Analyse de votre question...")

        # ÉTAPE 1 : Routing
        # Le LLM décide si la question nécessite SQL ou RAG
        mode = classifier_question(prompt)
        logging.info(f"Routing → {mode} pour : '{prompt}'")

        # ÉTAPE 2A : Mode SQL
        if mode == "SQL":
            placeholder.text("Interrogation de la base de données...")

            sql_result = query_nba_database(prompt)

            # Construire le prompt de synthèse
            messages_for_api = [
                {"role": "system", "content": "Tu es un expert NBA. Synthétise les données de manière engageante."},
                {"role": "user", "content": SQL_SYSTEM_PROMPT.format(
                    sql_result=sql_result,
                    question=prompt
                )}
            ]
            response_content = generer_reponse(messages_for_api)

            # Afficher avec badge SQL
            placeholder.empty()
            st.markdown("*Source : Base de données SQL*")
            with st.expander("Voir les données brutes SQL"):
                st.code(sql_result)
            st.write(response_content)

        # ÉTAPE 2B : Mode RAG
        else:
            placeholder.text("Recherche dans la base de connaissances...")

            if vector_store_manager is None:
                placeholder.error("Index FAISS non disponible. Lancez python indexer.py")
                st.stop()

            # Recherche vectorielle
            try:
                search_results = vector_store_manager.search(prompt, k=SEARCH_K)
            except Exception as e:
                logging.exception(f"Erreur FAISS search")
                search_results = []

            # Formater le contexte
            if search_results:
                context_str = "\n\n---\n\n".join([
                    f"Source : {r['metadata'].get('source', '?')} (Score : {r['score']:.1f}%)\n{r['text']}"
                    for r in search_results
                ])
            else:
                context_str = "Aucun document pertinent trouvé"

            messages_for_api = [
                {"role": "system", "content": "Tu es un expert NBA."},
                {"role": "user", "content": RAG_SYSTEM_PROMPT.format(
                    context_str=context_str,
                    question=prompt
                )}
            ]
            response_content = generer_reponse(messages_for_api)

            # Afficher avec badge RAG
            placeholder.empty()
            st.markdown("*Source : Base de connaissances (RAG)*")
            if search_results:
                with st.expander(f"Voir les {len(search_results)} documents sources"):
                    for i, r in enumerate(search_results, 1):
                        st.markdown(f"**{i}.** `{r['metadata'].get('source','?')}` — Score : {r['score']:.1f}%")
                        st.caption(r['text'][:200] + "...")
            st.write(response_content)

    # 3. Sauvegarder dans l'historique
    st.session_state.messages.append({"role": "assistant", "content": response_content})

st.markdown("---")
st.caption("Powered by Mistral AI · FAISS · SQLite | NBA Analyst AI")
