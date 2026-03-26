"""
Jeu de questions de test pour l'évaluation RAGAS - SportSee Assistant IA
Saison NBA régulière

Catégories :
  - SIMPLE    : une seule stat directe, réponse non ambiguë
  - COMPLEXE  : agrégation, comparaison, multi-critères
  - BRUITÉ    : fautes de frappe, formulation floue, question hors-champ

Chaque entrée contient :
  - question         : la question posée à l'assistant
  - ground_truth     : la réponse attendue (référence pour RAGAS)
  - category         : SIMPLE | COMPLEXE | BRUITÉ
  - difficulty       : 1 (facile) -> 3 (difficile)
  - context_needed   : source de donnée principale attendue (SQL / RAG / BOTH)
"""

TEST_QUESTIONS = [

    # ──────────────────────────────────────────────
    # CATÉGORIE 1 : SIMPLE
    # ──────────────────────────────────────────────
    {
        "id": "S01",
        "question": "Quel joueur a marqué le plus de points sur la saison ?",
        "ground_truth": (
            "Shai Gilgeous-Alexander (OKC) est le meilleur marqueur de la saison "
            "avec 2 485 points au total."
        ),
        "category": "SIMPLE",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "S02",
        "question": "Quel joueur a le meilleur pourcentage de réussite à 3 points (minimum 100 tentatives) ?",
        "ground_truth": (
            "Seth Curry (CHA) affiche le meilleur pourcentage à 3 points avec 45,6 % "
            "sur 184 tentatives."
        ),
        "category": "SIMPLE",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "S03",
        "question": "Qui a capté le plus de rebonds cette saison ?",
        "ground_truth": (
            "Ivica Zubac (LAC) domine les rebonds avec 1 008 rebonds totaux sur la saison."
        ),
        "category": "SIMPLE",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "S04",
        "question": "Quel joueur a réalisé le plus de passes décisives ?",
        "ground_truth": (
            "Trae Young (ATL) mène la ligue en passes décisives avec 882 assists."
        ),
        "category": "SIMPLE",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "S05",
        "question": "Qui a réussi le plus d'interceptions cette saison ?",
        "ground_truth": (
            "Dyson Daniels (ATL) est le leader des interceptions avec 228 steals."
        ),
        "category": "SIMPLE",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "S06",
        "question": "Quel joueur a réalisé le plus de contres ?",
        "ground_truth": (
            "Victor Wembanyama (SAS) domine les contres avec 175 blocks sur la saison."
        ),
        "category": "SIMPLE",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "S07",
        "question": "Quel joueur a le meilleur pourcentage de lancers francs (minimum 50 matchs joués) ?",
        "ground_truth": (
            "Sam Hauser (BOS) affiche un pourcentage parfait de 100 % aux lancers francs."
        ),
        "category": "SIMPLE",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "S08",
        "question": "Quel joueur a joué le plus de matchs cette saison ?",
        "ground_truth": (
            "Jalen Green (HOU) a disputé le plus grand nombre de matchs avec 82 matchs joués."
        ),
        "category": "SIMPLE",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "S09",
        "question": "Quel joueur a le plus grand nombre de triple-doubles ?",
        "ground_truth": (
            "Nikola Jokić (DEN) est le leader des triple-doubles avec 34 triple-doubles."
        ),
        "category": "SIMPLE",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "S10",
        "question": "Quel joueur a le meilleur Net Rating parmi les joueurs ayant joué au moins 50 matchs ?",
        "ground_truth": (
            "Shai Gilgeous-Alexander (OKC) affiche le meilleur Net Rating avec +16,7."
        ),
        "category": "SIMPLE",
        "difficulty": 2,
        "context_needed": "SQL",
    },

    # ──────────────────────────────────────────────
    # CATÉGORIE 2 : COMPLEXE
    # ──────────────────────────────────────────────
    {
        "id": "C01",
        "question": (
            "Compare les statistiques moyennes de rebonds des joueurs de Boston (BOS) "
            "et de Milwaukee (MIL)."
        ),
        "ground_truth": (
            "Les joueurs de Boston (BOS) ont une moyenne de 219,0 rebonds par joueur "
            "contre 203,9 pour Milwaukee (MIL). Boston domine légèrement au rebond."
        ),
        "category": "COMPLEXE",
        "difficulty": 2,
        "context_needed": "SQL",
    },
    {
        "id": "C02",
        "question": (
            "Donne-moi le top 3 des joueurs ayant tenté le plus de tirs à 3 points, "
            "avec leur pourcentage de réussite."
        ),
        "ground_truth": (
            "1. Anthony Edwards (MIN) : 814 tentatives, 39,5 % de réussite. "
            "2. Malik Beasley (DET) : 320 tentatives, 41,6 % de réussite (saison partielle). "
            "3. Stephen Curry (GSW) : 308 tentatives, 39,7 % de réussite."
        ),
        "category": "COMPLEXE",
        "difficulty": 2,
        "context_needed": "SQL",
    },
    {
        "id": "C03",
        "question": (
            "Quels sont les 5 joueurs principaux d'OKC et leurs statistiques "
            "de points, rebonds et passes ?"
        ),
        "ground_truth": (
            "1. Shai Gilgeous-Alexander : 2 485 pts, 380 reb, 486 ast. "
            "2. Jalen Williams : 1 490 pts, 366 reb, 352 ast. "
            "3. Aaron Wiggins : 912 pts, 296 reb, 137 ast. "
            "4. Isaiah Joe : 755 pts, 192 reb, 118 ast. "
            "5. Luguentz Dort : 717 pts, 291 reb, 114 ast."
        ),
        "category": "COMPLEXE",
        "difficulty": 2,
        "context_needed": "SQL",
    },
    {
        "id": "C04",
        "question": (
            "Qui sont les 3 joueurs qui perdent le plus de balles (turnovers) "
            "et quel est leur ratio passes/pertes ?"
        ),
        "ground_truth": (
            "1. Trae Young (ATL) : 357 turnovers. "
            "2. James Harden (LAC) : 340 turnovers. "
            "3. Cade Cunningham (DET) : 308 turnovers."
        ),
        "category": "COMPLEXE",
        "difficulty": 2,
        "context_needed": "SQL",
    },
    {
        "id": "C05",
        "question": (
            "Quel joueur a le meilleur impact global sur le jeu selon le PIE "
            "(Player Impact Estimate), avec au moins 50 matchs joués ?"
        ),
        "ground_truth": (
            "Giannis Antetokounmpo (MIL) affiche le meilleur PIE avec 21,0 "
            "parmi les joueurs ayant disputé au moins 50 matchs."
        ),
        "category": "COMPLEXE",
        "difficulty": 2,
        "context_needed": "SQL",
    },
    {
        "id": "C06",
        "question": (
            "Quel joueur a le meilleur ratio passes décisives / pertes de balle "
            "(AST/TO) parmi ceux ayant joué 50 matchs ou plus ?"
        ),
        "ground_truth": (
            "Tyrese Haliburton (IND) possède le meilleur ratio AST/TO avec 5,61."
        ),
        "category": "COMPLEXE",
        "difficulty": 2,
        "context_needed": "SQL",
    },
    {
        "id": "C07",
        "question": (
            "Quel joueur a le taux d'utilisation (USG%) le plus élevé "
            "parmi les joueurs ayant joué au moins 50 matchs ?"
        ),
        "ground_truth": (
            "Giannis Antetokounmpo (MIL) a le taux d'utilisation le plus élevé avec 34,6 %."
        ),
        "category": "COMPLEXE",
        "difficulty": 2,
        "context_needed": "SQL",
    },
    {
        "id": "C08",
        "question": (
            "Quelles sont les statistiques de Victor Wembanyama cette saison "
            "et quel est son profil de joueur ?"
        ),
        "ground_truth": (
            "Victor Wembanyama (SAS) totalise 1 118 points, 175 contres et 506 rebonds. "
            "Il est le leader de la ligue aux contres, confirmant son profil de pivot "
            "défensif élite, alliant présence intérieure et capacité scoring."
        ),
        "category": "COMPLEXE",
        "difficulty": 3,
        "context_needed": "BOTH",
    },
    {
        "id": "C09",
        "question": (
            "Compare le True Shooting % (TS%) et l'Effective Field Goal % (EFG%) "
            "du meilleur joueur dans chaque catégorie."
        ),
        "ground_truth": (
            "Meilleur TS% : Jarrett Allen (CLE) avec 72,4 %. "
            "Meilleur EFG% : Jaxson Hayes (LAL) avec 72,2 %."
        ),
        "category": "COMPLEXE",
        "difficulty": 3,
        "context_needed": "SQL",
    },
    {
        "id": "C10",
        "question": (
            "Quelles équipes ont le roster le plus jeune en moyenne ?"
        ),
        "ground_truth": (
            "Les équipes avec les rosters les plus jeunes sont : "
            "1. Brooklyn Nets (BKN) : 24,0 ans de moyenne. "
            "2. Utah Jazz (UTA) : 24,2 ans. "
            "3. Portland Trail Blazers (POR) : 24,5 ans."
        ),
        "category": "COMPLEXE",
        "difficulty": 3,
        "context_needed": "SQL",
    },

    # ──────────────────────────────────────────────
    # CATÉGORIE 3 : BRUITÉ
    # ──────────────────────────────────────────────
    {
        "id": "B01",
        "question": "ki a le + de point cette seson ?",
        "ground_truth": (
            "Shai Gilgeous-Alexander (OKC) est le meilleur marqueur de la saison "
            "avec 2 485 points."
        ),
        "category": "BRUITÉ",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "B02",
        "question": "Donne moi les stats de Wembanyama… je crois qu'il joue à San Antonio ?",
        "ground_truth": (
            "Oui, Victor Wembanyama joue bien aux San Antonio Spurs (SAS). "
            "Il totalise 1 118 points, 506 rebonds et 175 contres cette saison."
        ),
        "category": "BRUITÉ",
        "difficulty": 1,
        "context_needed": "SQL",
    },
    {
        "id": "B03",
        "question": "Quel est le meilleur défenseur de la ligue selon les données ?",
        "ground_truth": (
            "Selon les données disponibles, Dyson Daniels (ATL) est le leader "
            "des interceptions avec 228 steals, et Victor Wembanyama (SAS) domine "
            "aux contres avec 175 blocks. Le meilleur défenseur dépend du critère "
            "retenu (interceptions, contres, DEFRTG)."
        ),
        "category": "BRUITÉ",
        "difficulty": 2,
        "context_needed": "SQL",
    },
    {
        "id": "B04",
        "question": "C'est quoi le NETRTG déjà ? Et qui a le pire ?",
        "ground_truth": (
            "Le Net Rating (NETRTG) mesure l'écart de points marqués vs encaissés "
            "par 100 possessions lorsque le joueur est sur le terrain. "
            "Le joueur avec le pire NETRTG parmi ceux ayant joué 50+ matchs "
            "est Cody Williams (UTA) avec -15,5."
        ),
        "category": "BRUITÉ",
        "difficulty": 2,
        "context_needed": "BOTH",
    },
    {
        "id": "B05",
        "question": "Est-ce que LeBron James a des bonnes stats cette saison ?",
        "ground_truth": (
            "LeBron James n'apparaît pas dans le jeu de données disponible pour "
            "cette saison. Il est possible qu'il n'ait pas disputé suffisamment "
            "de matchs ou que ses données ne soient pas incluses dans ce dataset."
        ),
        "category": "BRUITÉ",
        "difficulty": 2,
        "context_needed": "SQL",
    },
    {
        "id": "B06",
        "question": "Kobe Bryant est le meilleur non ?",
        "ground_truth": (
            "Kobe Bryant a pris sa retraite en 2016 et n'est pas présent dans "
            "les données de cette saison. Le meilleur marqueur de la saison actuelle "
            "est Shai Gilgeous-Alexander (OKC) avec 2 485 points."
        ),
        "category": "BRUITÉ",
        "difficulty": 1,
        "context_needed": "SQL",
    },
]


# ──────────────────────────────────────────────────────────────────
# FORMAT RAGAS  (datasets compatible)
# ──────────────────────────────────────────────────────────────────
def to_ragas_dataset(questions: list[dict]) -> dict:
    """
    Convertit la liste en dictionnaire de listes prêt pour
    datasets.Dataset.from_dict() utilisé par RAGAS
    """
    return {
        "question":     [q["question"]     for q in questions],
        "ground_truth": [q["ground_truth"] for q in questions],
        "id":           [q["id"]           for q in questions],
        "category":     [q["category"]     for q in questions],
        "difficulty":   [q["difficulty"]   for q in questions],
        "context_needed": [q["context_needed"] for q in questions],
    }


if __name__ == "__main__":
    import json

    dataset = to_ragas_dataset(TEST_QUESTIONS)

    # Affichage résumé
    from collections import Counter
    cats = Counter(q["category"] for q in TEST_QUESTIONS)
    print("=" * 60)
    print(f"Total questions : {len(TEST_QUESTIONS)}")
    for cat, count in cats.items():
        print(f"  {cat:10s} : {count} questions")
    print("=" * 60)

    # Export JSON
    with open("ragas_questions.json", "w", encoding="utf-8") as f:
        json.dump(TEST_QUESTIONS, f, ensure_ascii=False, indent=2)
    print("Fichier ragas_questions.json généré avec succès")