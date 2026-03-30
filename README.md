# NBA Analyst AI — Système RAG + SQL

Assistant virtuel intelligent pour l'analyse de statistiques NBA.
Combine un pipeline **RAG** (recherche sémantique) et un **Tool SQL** (requêtes exactes) pour répondre à tout type de question métier.

---

## Architecture cible

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SOURCES DE DONNÉES                          │
│                                                                     │
│   regular NBA.xlsx          Reddit 1-4.pdf                          │
│   (stats saison)            (analyses, débats)                      │
└──────────┬──────────────────────────┬──────────────────────────────┘
           │                          │
           ▼                          ▼
┌──────────────────┐       ┌──────────────────────┐
│  load_excel_to   │       │     indexer.py        │
│  _db.py          │       │  (chunking + embed.)  │
│  (Pydantic  )    │       │  (langchain-text-     │
│                  │       │   splitters + Mistral)│
└────────┬─────────┘       └──────────┬────────────┘
         │                            │
         ▼                            ▼
┌──────────────────┐       ┌──────────────────────┐
│  SQLite          │       │  FAISS Index          │
│  teams           │       │  (302 vecteurs)       │
│  players         │       │  vector_db/           │
│  player_stats    │       │                       │
└────────┬─────────┘       └──────────┬────────────┘
         │                            │
         └──────────┬─────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────┐
│              ROUTEUR LLM (Mistral)                │
│                                                   │
│   Question → SQL  ou  RAG  ?                      │
│   (classifier_question — max_tokens=5)            │
└──────────┬────────────────────┬──────────────────┘
           │                    │
           ▼                    ▼
┌──────────────────┐  ┌──────────────────────────┐
│  sql_tool.py     │  │  vector_store.py          │
│  Few-shot SQL    │  │  Recherche cosinus FAISS  │
│  → SQLite query  │  │  → top-K chunks           │
└────────┬─────────┘  └──────────┬────────────────┘
         │                       │
         └──────────┬────────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │  LLM Mistral        │
         │  Synthèse réponse   │
         │  (Pydantic AI )     │
         └──────────┬──────────┘
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
┌──────────────────┐  ┌──────────────────────┐
│  Streamlit UI    │  │  API REST (FastAPI)   │
│  MistralChat.py  │  │  api.py              │
│  :8501           │  │  :8000               │
└──────────────────┘  └──────────────────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │  evaluate_ragas.py  │
         │  RAGAS + Logfire    │
         │  Pydantic + Pydantic│
         │  AI                 │
         └─────────────────────┘
```

### Principe du routage hybride

| Type de question | Source choisie | Exemple |
|---|---|---|
| Stat précise, classement, top N | **SQL** (SQLite) | *"Qui a le plus de points ?"* |
| Définition, analyse, débat | **RAG** (FAISS) | *"C'est quoi le Net Rating ?"* |
| Hors-champ / bruité | **RAG** (fallback) | *"ki a le + de point seson?"* |

---

## Prérequis

- Python 3.10+
- Clé API Mistral — [console.mistral.ai](https://console.mistral.ai/)
- (Optionnel) Clé Logfire — [logfire.pydantic.dev](https://logfire.pydantic.dev) pour la traçabilité

---

## Installation et déploiement

### 1. Cloner le dépôt

```bash
git clone <url-du-repo>
cd P10_DSML
```

### 2. Créer l'environnement virtuel

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer les variables d'environnement

Créez un fichier `.env` à la racine :

```env
MISTRAL_API_KEY=votre_clé_mistral
LOGFIRE_TOKEN=votre_token_logfire   # optionnel
```

### 5. Placer les données sources

```
inputs/
├── regular NBA.xlsx    ← stats saison NBA (obligatoire)
├── Reddit 1.pdf        ← discussions Reddit (optionnel)
├── Reddit 2.pdf
├── Reddit 3.pdf
└── Reddit 4.pdf
```

### 6. Exécuter le pipeline d'initialisation

**Dans cet ordre :**

```bash
# Étape 1 — Construire l'index vectoriel FAISS (embedding des documents)
python indexer.py

# Étape 2 — Charger les données Excel dans la base SQLite
python utils/load_excel_to_db.py

# Vérification : 30 équipes, 569 joueurs, 569 stats insérées
```

---

## Lancement des interfaces

### Interface Streamlit (chat visuel)

```bash
streamlit run MistralChat.py
```

Accessible sur : `http://localhost:8501`

### API REST (FastAPI)

```bash
uvicorn api:app --reload --port 8000
```

Accessible sur : `http://localhost:8000`
Documentation interactive : `http://localhost:8000/docs`

---

## API REST — Référence complète

### `GET /health`

Vérifie que le système est opérationnel.

```bash
curl http://localhost:8000/health
```

Réponse :
```json
{
  "status": "ok",
  "faiss_index": "loaded (302 vecteurs)",
  "sql_database": "connected (569 joueurs)",
  "model": "mistral-small-latest"
}
```

---

### `GET /stats`

Statistiques de la base de données.

```bash
curl http://localhost:8000/stats
```

Réponse :
```json
{
  "total_players": 569,
  "total_teams": 30,
  "sample_leaders": {
    "#1": "Shai Gilgeous-Alexander (OKC) — 2485.0 pts",
    "#2": "Anthony Edwards (MIN) — 2180.0 pts",
    "#3": "Nikola Jokić (DEN) — 2072.0 pts"
  }
}
```

---

### `POST /query` — Endpoint principal (routage automatique)

Le LLM choisit automatiquement SQL ou RAG selon la nature de la question.

```bash
curl -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -d '{"question": "Qui a le plus de points cette saison ?", "k": 5}'
```

Corps de la requête :

| Champ | Type | Description |
|---|---|---|
| `question` | string | Question en langage naturel (min 3 caractères) |
| `k` | integer | Nb de documents RAG à récupérer (défaut: 5, max: 20) |

Réponse :
```json
{
  "question": "Qui a le plus de points cette saison ?",
  "answer": "Shai Gilgeous-Alexander (OKC) est le meilleur marqueur avec 2485 points.",
  "mode": "SQL",
  "sources": [
    {
      "source": "SQLite — player_stats",
      "score": null,
      "excerpt": "name | team_code | pts\nShai Gilgeous-Alexander | OKC | 2485.0"
    }
  ],
  "sql_query_result": "name | team_code | pts\n...",
}
```

---

### `POST /query/rag` — Force le mode RAG

Ignore le routeur, utilise uniquement FAISS.

```bash
curl -X POST http://localhost:8000/query/rag \
     -H "Content-Type: application/json" \
     -d '{"question": "C est quoi le Net Rating ?"}'
```

---

### `POST /query/sql` — Force le mode SQL

Ignore le routeur, génère et exécute une requête SQL.

```bash
curl -X POST http://localhost:8000/query/sql \
     -H "Content-Type: application/json" \
     -d '{"question": "Top 5 rebondeurs minimum 50 matchs joués ?"}'
```

---

## Évaluation de la qualité (RAGAS)

### Lancer l'évaluation

```bash
# Mode baseline — RAG seul (FAISS)
python utils/evaluate_ragas.py --mode rag

# Mode enrichi — pipeline hybride SQL + RAG
python utils/evaluate_ragas.py --mode hybrid
```

### Générer le rapport comparatif

```bash
python rapport_comparatif.py
```

Produit dans `outputs/` :
- `ragas_results.csv / .json` — scores baseline
- `ragas_results_hybrid.csv / .json` — scores après enrichissement SQL
- `rapport_comparatif.png` — graphiques comparatifs

### Métriques RAGAS

| Métrique | Ce qu'elle mesure |
|---|---|
| `faithfulness` | La réponse est-elle ancrée dans les contextes ? (anti-hallucination) |
| `context_recall` | Les bons documents ont-ils été récupérés ? |
| `context_precision` | Les documents récupérés sont-ils tous pertinents ? |

---

## Structure complète du projet

```
P10_DSML/
│
├── api.py                      # API REST FastAPI (5 endpoints)
├── MistralChat.py              # Interface Streamlit (chat visuel)
├── indexer.py                  # Pipeline d'indexation FAISS
├── rapport_comparatif.py       # Rapport AVANT/APRÈS avec graphiques
│
├── utils/
│   ├── config.py               # Variables de configuration centralisées
│   ├── vector_store.py         # Index FAISS — chunking, embedding, recherche
│   ├── data_loader.py          # Chargement PDF, Excel, DOCX, CSV (avec OCR)
│   ├── load_excel_to_db.py     # Ingestion Excel → SQLite (validé par Pydantic)
│   ├── sql_tool.py             # Tool SQL — Text-to-SQL + few-shot examples
│   ├── evaluate_ragas.py       # Évaluation RAGAS (modes rag et hybrid)
│   └── questions.py            # Jeu de 26 questions test (SIMPLE/COMPLEXE/BRUITÉ)
│
├── inputs/                     # Documents sources (Excel + PDFs)
├── vector_db/                  # Index FAISS + chunks (généré par indexer.py)
├── database/                   # Base SQLite (générée par load_excel_to_db.py)
├── outputs/                    # Résultats RAGAS + graphiques
│
├── .env                        # Clés API (ne pas committer)
├── requirements.txt            # Dépendances Python
└── README.md                   # Ce fichier
```

---

## Récapitulatif des commandes

```bash
# 1. Installation
pip install -r requirements.txt

# 2. Initialisation (une seule fois)
python indexer.py
python utils/load_excel_to_db.py

# 3. Utilisation
streamlit run MistralChat.py        # Interface graphique
uvicorn api:app --reload            # API REST

# 4. Évaluation
python utils/evaluate_ragas.py --mode rag
python utils/evaluate_ragas.py --mode hybrid
python rapport_comparatif.py
```

---

## Technologies utilisées

| Couche | Technologie | Rôle |
|---|---|---|
| LLM | Mistral AI (`mistral-small-latest`) | Génération, routage, évaluation |
| Embeddings | `mistral-embed` | Vectorisation des documents |
| Recherche vectorielle | FAISS (`faiss-cpu`) | Similarité cosinus |
| Base de données | SQLite | Stats NBA structurées |
| Validation données | Pydantic + Pydantic AI | Sécurisation des flux |
| Tracing | Logfire | Observabilité pas à pas |
| Évaluation | RAGAS | Métriques de qualité RAG |
| Interface | Streamlit | Chat visuel |
| API | FastAPI + Uvicorn | Endpoints REST |
