# utils/sql_tool.py
"""
Tool LangChain SQL pour l'agent NBA

Ce module expose une fonction get_sql_tool() qui retourne un Tool
que l'agent peut appeler pour répondre aux questions chiffrées

Fonctionnement :
  1. L'agent reçoit une question ("Top 3 rebondeurs ?")
  2. Il appelle ce Tool avec la question en texte libre
  3. Le Tool génère une requête SQL via few-shot + LLM
  4. Il exécute la requête sur SQLite
  5. Il retourne le résultat formaté en texte

Few-shot examples :
  Des exemples question -> SQL appris par le LLM pour améliorer la précision
  Sans few-shot, le LLM peut inventer des noms de colonnes qui n'existent pas
"""

import sys
import logging
from pathlib import Path

from langchain_core.tools import Tool

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config import MISTRAL_API_KEY, DATABASE_FILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 1. SCHÉMA DE RÉFÉRENCE (pour le LLM)

# On donne au LLM le schéma exact des tables pour qu'il génère
# des requêtes SQL correctes sans inventer des noms de colonnes

DB_SCHEMA = """
Tables disponibles dans la base NBA :

teams(team_code TEXT PK, team_name TEXT)

players(player_id INT PK, name TEXT, team_code TEXT FK, age INT)

player_stats(
  stat_id INT PK, player_id INT FK,
  gp INT,          -- matchs joués (Games Played)
  w INT,           -- victoires
  l INT,           -- défaites
  min_total REAL,  -- minutes totales
  pts REAL,        -- points totaux saison
  fgm REAL,        -- tirs réussis
  fga REAL,        -- tirs tentés
  fg_pct REAL,     -- % tirs (0-100)
  three_pa REAL,   -- tirs à 3pts tentés
  three_pct REAL,  -- % à 3pts (0-100)
  ftm REAL,        -- lancers francs réussis
  fta REAL,        -- lancers francs tentés
  ft_pct REAL,     -- % lancers francs (0-100)
  oreb REAL,       -- rebonds offensifs
  dreb REAL,       -- rebonds défensifs
  reb REAL,        -- rebonds totaux
  ast REAL,        -- passes décisives
  tov REAL,        -- balles perdues (turnovers)
  stl REAL,        -- interceptions (steals)
  blk REAL,        -- contres (blocks)
  pf REAL,         -- fautes personnelles
  plus_minus REAL, -- +/-
  offrtg REAL,     -- offensive rating
  defrtg REAL,     -- defensive rating
  netrtg REAL,     -- net rating = offrtg - defrtg
  ast_pct REAL,    -- % passes décisives
  ast_to REAL,     -- ratio passes/pertes
  oreb_pct REAL, dreb_pct REAL, reb_pct REAL,
  efg_pct REAL,    -- effective field goal %
  ts_pct REAL,     -- true shooting %
  usg_pct REAL,    -- usage rate %
  pace REAL,       -- rythme de jeu
  pie REAL,        -- player impact estimate
  poss REAL,       -- possessions totales
  dd2 INT,         -- double-doubles
  td3 INT          -- triple-doubles
)

Jointure type :
  SELECT p.name, t.team_name, s.*
  FROM players p
  JOIN player_stats s ON p.player_id = s.player_id
  JOIN teams t ON p.team_code = t.team_code
"""

# 2. FEW-SHOT EXAMPLES

# Ces exemples montrent au LLM le pattern question -> SQL à suivre
# Ils couvrent les cas les plus fréquents dans les questions de test

FEW_SHOT_EXAMPLES = [
    {
        "question": "Quel joueur a marqué le plus de points cette saison ?",
        "sql": (
            "SELECT p.name, p.team_code, s.pts "
            "FROM players p JOIN player_stats s ON p.player_id = s.player_id "
            "ORDER BY s.pts DESC LIMIT 1;"
        ),
    },
    {
        "question": "Top 5 des rebondeurs (minimum 50 matchs joués) ?",
        "sql": (
            "SELECT p.name, p.team_code, s.reb "
            "FROM players p JOIN player_stats s ON p.player_id = s.player_id "
            "WHERE s.gp >= 50 ORDER BY s.reb DESC LIMIT 5;"
        ),
    },
    {
        "question": "Quel joueur a le meilleur pourcentage à 3 points (minimum 100 tentatives) ?",
        "sql": (
            "SELECT p.name, p.team_code, s.three_pct, s.three_pa "
            "FROM players p JOIN player_stats s ON p.player_id = s.player_id "
            "WHERE s.three_pa >= 100 ORDER BY s.three_pct DESC LIMIT 1;"
        ),
    },
    {
        "question": "Compare les rebonds moyens des joueurs de Boston (BOS) et Milwaukee (MIL).",
        "sql": (
            "SELECT p.team_code, AVG(s.reb) AS avg_reb "
            "FROM players p JOIN player_stats s ON p.player_id = s.player_id "
            "WHERE p.team_code IN ('BOS', 'MIL') "
            "GROUP BY p.team_code;"
        ),
    },
    {
        "question": "Top 3 des joueurs avec le plus de turnovers et leur ratio AST/TO ?",
        "sql": (
            "SELECT p.name, p.team_code, s.tov, s.ast_to "
            "FROM players p JOIN player_stats s ON p.player_id = s.player_id "
            "ORDER BY s.tov DESC LIMIT 3;"
        ),
    },
    {
        "question": "Quel joueur a le meilleur Net Rating parmi ceux ayant joué 50 matchs ou plus ?",
        "sql": (
            "SELECT p.name, p.team_code, s.netrtg, s.gp "
            "FROM players p JOIN player_stats s ON p.player_id = s.player_id "
            "WHERE s.gp >= 50 ORDER BY s.netrtg DESC LIMIT 1;"
        ),
    },
    {
        "question": "Quelles équipes ont le roster le plus jeune en moyenne ?",
        "sql": (
            "SELECT p.team_code, t.team_name, AVG(p.age) AS avg_age "
            "FROM players p JOIN teams t ON p.team_code = t.team_code "
            "GROUP BY p.team_code ORDER BY avg_age ASC LIMIT 5;"
        ),
    },
    {
        "question": "Qui a le meilleur True Shooting % parmi les joueurs d'OKC ?",
        "sql": (
            "SELECT p.name, s.ts_pct "
            "FROM players p JOIN player_stats s ON p.player_id = s.player_id "
            "WHERE p.team_code = 'OKC' ORDER BY s.ts_pct DESC LIMIT 1;"
        ),
    },
]


# 3. CONSTRUCTION DU PROMPT FEW-SHOT

def build_few_shot_prompt() -> str:
    """Construit le bloc few-shot à injecter dans le prompt SQL"""
    lines = ["Exemples de questions et leurs requêtes SQL correspondantes :\n"]
    for ex in FEW_SHOT_EXAMPLES:
        lines.append(f"Question : {ex['question']}")
        lines.append(f"SQL      : {ex['sql']}")
        lines.append("")
    return "\n".join(lines)



# 4. FONCTION PRINCIPALE : exécution SQL avec génération LLM


def query_nba_database(question: str) -> str:
    """
    Prend une question en langage naturel, génère le SQL, l'exécute et retourne le résultat

    C'est la fonction qui sera enveloppée dans un Tool LangChain
    """
    import sqlite3

    db_path = DATABASE_FILE
    few_shot_block = build_few_shot_prompt()

    # Prompt envoyé au LLM pour générer la requête SQL
    sql_generation_prompt = f"""Tu es un expert SQL spécialisé en statistiques NBA.
Tu dois générer une requête SQLite valide pour répondre à la question.

{DB_SCHEMA}

{few_shot_block}

Règles importantes :
- Utilise UNIQUEMENT les colonnes listées dans le schéma ci-dessus.
- Pour filtrer par équipe, utilise team_code (ex: 'OKC', 'BOS', 'MIL').
- Toujours faire la jointure players -> player_stats via player_id.
- Retourne UNIQUEMENT la requête SQL, sans explication, sans balises markdown.
- Termine toujours par un point-virgule.

Question : {question}
SQL :"""

    # Appel LLM pour générer la requête
    from mistralai import Mistral
    client = Mistral(api_key=MISTRAL_API_KEY)

    try:
        response = client.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": sql_generation_prompt}],
            temperature=0,  
        )
        sql_query = response.choices[0].message.content.strip()

        # Nettoyer les éventuelles balises markdown que le LLM pourrait ajouter
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()

        logging.info(f"SQL généré : {sql_query}")

    except Exception as e:
        return f"Erreur lors de la génération SQL : {e}"

    # Exécution de la requête sur SQLite
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql_query)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "Aucun résultat trouvé pour cette requête"

        # Formater les résultats en texte lisible
        col_names = rows[0].keys()
        lines = [" | ".join(col_names)]
        lines.append("-" * 60)
        for row in rows:
            lines.append(" | ".join(str(v) if v is not None else "N/A" for v in row))

        result = "\n".join(lines)
        logging.info(f"SQL résultat : {len(rows)} ligne(s) retournée(s)")
        return result

    except sqlite3.Error as e:
        logging.error(f"Erreur SQL : {e} - Requête : {sql_query}")
        return f"Erreur d'exécution SQL : {e}\nRequête tentée : {sql_query}"


# 5. CRÉATION DU TOOL LANGCHAIN


def get_sql_tool() -> Tool:
    """
    Retourne le Tool LangChain que l'agent utilisera pour les questions chiffrées

    L'agent appelle ce Tool quand il détecte une question nécessitant
    des données précises (classements, comparaisons, statistiques exactes)
    """
    return Tool(
        name="nba_sql_database",
        func=query_nba_database,
        description=(
            "Utilise ce tool pour répondre aux questions sur les statistiques NBA "
            "qui nécessitent des données précises : classements, comparaisons d'équipes, "
            "meilleur joueur par métrique, moyennes par équipe, etc. "
            "Entrée : une question en français sur les stats NBA. "
            "Sortie : les données exactes issues de la base de données."
        ),
    )


if __name__ == "__main__":
    test_questions = [
        "Quel joueur a marqué le plus de points cette saison ?",
        "Top 3 des rebondeurs avec minimum 50 matchs joués ?",
        "Quel joueur d'OKC a le meilleur Net Rating ?",
        "Compare les rebonds moyens de BOS et MIL.",
    ]

    
    print("TEST DU SQL TOOL")


    for q in test_questions:
        print(f"\nQuestion : {q}")
        print("-" * 40)
        result = query_nba_database(q)
        print(result)
        print()
