# rapport_comparatif.py
"""
Rapport comparatif AVANT / APRÈS enrichissement SQL


Ce script charge les deux fichiers de résultats RAGAS et produit :
  1. Tableau comparatif global (avant vs après)
  2. Tableau par catégorie (SIMPLE / COMPLEXE / BRUITÉ)
  3. Graphiques matplotlib (barres groupées + radar)
  4. Analyse critique des biais et limite
"""

import json
import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# 1. CHARGEMENT DES RÉSULTATS


RAG_FILE    = Path("outputs/ragas_results.json")
HYBRID_FILE = Path("outputs/ragas_results_hybrid.json")
OUTPUT_DIR  = Path("outputs")

METRICS = ["faithfulness", "context_recall", "context_precision"]
COLORS  = {"RAG seul":"#4C72B0", "SQL + RAG": "#DD8452"}


def load_results(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        print(f"[AVERTISSEMENT] Fichier introuvable : {path}")
        return pd.DataFrame()
    with open(path) as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df["mode"] = label
    return df


df_rag    = load_results(RAG_FILE,    "RAG seul")
df_hybrid = load_results(HYBRID_FILE, "SQL + RAG")

if df_rag.empty and df_hybrid.empty:
    print("Aucun fichier de résultats trouvé. Lance d'abord evaluate_ragas.py")
    sys.exit(1)

# Combiner les deux datasets
frames = [df for df in [df_rag, df_hybrid] if not df.empty]
df_all = pd.concat(frames, ignore_index=True)

# Colonnes disponibles dans les deux fichiers
available_metrics = [m for m in METRICS if m in df_all.columns]

# 2. TABLEAU COMPARATIF GLOBAL

def print_global_comparison():
    print("  RAPPORT COMPARATIF — NBA Analyst AI")
    print("  Avant (RAG seul) vs Après (SQL + RAG)")

    global_scores = df_all.groupby("mode")[available_metrics].mean().round(3)

    # Calcul de l'évolution
    if "RAG seul" in global_scores.index and "SQL + RAG" in global_scores.index:
        delta = (global_scores.loc["SQL + RAG"] - global_scores.loc["RAG seul"]).round(3)
        delta_pct = ((delta / global_scores.loc["RAG seul"].replace(0, 0.001)) * 100).round(1)

        print("\n  Scores globaux :")
        print(f"  {'Métrique':<25} {'RAG seul':>10} {'SQL+RAG':>10} {'Δ':>8} {'Δ%':>8}")
        print("  " + "-" * 65)
        for metric in available_metrics:
            rag_val = global_scores.loc["RAG seul", metric]
            hyb_val = global_scores.loc["SQL + RAG", metric]
            d       = delta[metric]
            d_pct   = delta_pct[metric]
            arrow   = "↑" if d > 0 else ("↓" if d < 0 else "=")
            print(f"  {metric:<25} {rag_val:>10.3f} {hyb_val:>10.3f} {arrow}{abs(d):>6.3f} {d_pct:>+7.1f}%")
    else:
        print(global_scores.to_string())

    print()


# 3. TABLEAU PAR CATÉGORIE

def print_category_comparison():
    print("  Scores par catégorie")

    for metric in available_metrics:
        print(f"\n  {metric} :")
        pivot = df_all.pivot_table(
            index="category", columns="mode", values=metric, aggfunc="mean"
        ).round(3)
        print(pivot.to_string())

    print()

# 4. ANALYSE CRITIQUE

def print_critical_analysis():
    print("  ANALYSE CRITIQUE — Biais et limites")

    analysis = """
  1. MAPPING NL -> SQL (Text-to-SQL)
  ──────────────────────────────────
  Le routeur LLM (classifier_question) peut mal classer certaines questions :
  - Questions "bruités" mal orthographiées -> le LLM peut hésiter entre SQL/RAG
  - Questions mixtes (ex: "quel est le style de Wembanyama et ses stats ?")
    nécessitent les deux sources mais le routeur n'en choisit qu'une
  - Limite : aucun fallback si la requête SQL retourne 0 résultat
    (le LLM reçoit un contexte vide et peut halluciner)

  2. COUVERTURE DES CAS SQL
  ─────────────────────────
  - Les données sont des TOTAUX/MOYENNES saison (pas de données par match)
  - Questions type "sur les 5 derniers matchs" -> impossibles à répondre
  - Filtres complexes multi-colonnes peuvent générer du SQL incorrect
  - Le few-shot couvre 8 patterns : les questions hors pattern sont moins précises

  3. ÉVALUATION RAGAS AVEC SQL
  ─────────────────────────────
  - Pour les questions SQL, "contexts" = résultat tabulaire formaté en texte
  - RAGAS utilise ce texte comme contexte -> context_recall peut rester bas
    si le résultat SQL est exact mais formulé différemment du ground_truth
  - faithfulness devrait augmenter car le LLM se base sur des données exactes

  4. BIAIS DU DATASET DE TEST
  ────────────────────────────
  - 25 questions sur 26 (B05 manquante dans les résultats)
  - SIMPLE (10q) majoritairement SQL -> fort gain attendu
  - COMPLEXE (10q) majoritairement SQL -> fort gain attendu
  - BRUITÉ (6q) mixte -> gain modéré (certaines sont hors-champ)
  - Toutes les ground_truth sont en français -> impact sur la similarité sémantique

  5. LIMITES DE L'ÉVALUATION LLM-AS-A-JUDGE
  ───────────────────────────────────────────
  - RAGAS utilise Mistral comme juge -> peut avoir les mêmes biais que le système évalué
  - context_recall dépend de la capacité du juge LLM à comparer sémantiquement
    le ground_truth avec les contextes SQL (texte structuré vs phrase naturelle)
"""
    print(analysis)


# 5. GRAPHIQUES

def generate_charts():
    modes_present = df_all["mode"].unique().tolist()
    if len(modes_present) < 2:
        print("  [INFO] Un seul mode disponible — graphique comparatif non généré")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Rapport comparatif RAGAS — NBA Analyst AI\nRAG seul vs SQL + RAG",
                 fontsize=13, fontweight="bold")

    # Graphique 1 : Barres groupées par catégorie 
    ax1 = axes[0]
    categories = sorted(df_all["category"].unique())
    x = np.arange(len(categories))
    bar_width = 0.35
    metric_to_show = "context_recall" if "context_recall" in available_metrics else available_metrics[0]

    for i, mode in enumerate(["RAG seul", "SQL + RAG"]):
        if mode not in df_all["mode"].values:
            continue
        vals = []
        for cat in categories:
            subset = df_all[(df_all["mode"] == mode) & (df_all["category"] == cat)]
            vals.append(subset[metric_to_show].mean() if not subset.empty else 0)
        offset = (i - 0.5) * bar_width
        bars = ax1.bar(x + offset, vals, bar_width,
                       label=mode, color=COLORS.get(mode, "gray"), alpha=0.85)
        for bar in bars:
            h = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width() / 2, h + 0.01,
                     f"{h:.2f}", ha="center", va="bottom", fontsize=8)

    ax1.set_title(f"{metric_to_show} par catégorie", fontsize=11)
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories)
    ax1.set_ylim(0, 1.15)
    ax1.set_ylabel("Score (0 → 1)")
    ax1.legend()
    ax1.grid(axis="y", alpha=0.3)

    # Graphique 2 : Barres groupées — scores globaux 
    ax2 = axes[1]
    x2 = np.arange(len(available_metrics))

    for i, mode in enumerate(["RAG seul", "SQL + RAG"]):
        if mode not in df_all["mode"].values:
            continue
        vals = [df_all[df_all["mode"] == mode][m].mean() for m in available_metrics]
        offset = (i - 0.5) * bar_width
        bars = ax2.bar(x2 + offset, vals, bar_width,
                       label=mode, color=COLORS.get(mode, "gray"), alpha=0.85)
        for bar in bars:
            h = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width() / 2, h + 0.01,
                     f"{h:.2f}", ha="center", va="bottom", fontsize=8)

    ax2.set_title("Scores globaux par métrique", fontsize=11)
    ax2.set_xticks(x2)
    ax2.set_xticklabels(
        [m.replace("_", "\n") for m in available_metrics],
        fontsize=9
    )
    ax2.set_ylim(0, 1.15)
    ax2.set_ylabel("Score moyen (0 → 1)")
    ax2.legend()
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    chart_path = OUTPUT_DIR / "rapport_comparatif.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.show()
    print(f"\n  Graphique sauvegardé : {chart_path}")


# 6. TABLEAU DÉTAILLÉ PAR QUESTION

def print_question_detail():
    print("  Détail par question (évolution)")

    if "RAG seul" not in df_all["mode"].values or "SQL + RAG" not in df_all["mode"].values:
        print("  Un seul mode disponible - pas de comparaison possible")
        return

    df_rag_q    = df_all[df_all["mode"] == "RAG seul"].set_index("question_id")
    df_hybrid_q = df_all[df_all["mode"] == "SQL + RAG"].set_index("question_id")

    common_ids = df_rag_q.index.intersection(df_hybrid_q.index)

    print(f"\n  {'ID':<6} {'Cat':<9} {'Diff':>4}", end="")
    for m in available_metrics:
        short = m[:6]
        print(f"  {'RAG':>5}/{short+'H':>7}", end="")
    print()
    print("  " + "-" * 68)

    for qid in sorted(common_ids):
        cat  = df_rag_q.loc[qid, "category"]
        diff = df_rag_q.loc[qid, "difficulty"]
        print(f"  {qid:<6} {cat:<9} {diff:>4}", end="")
        for m in available_metrics:
            r = df_rag_q.loc[qid, m] if m in df_rag_q.columns else float("nan")
            h = df_hybrid_q.loc[qid, m] if m in df_hybrid_q.columns else float("nan")
            arrow = "↑" if h > r + 0.01 else ("↓" if h < r - 0.01 else "=")
            print(f"  {r:>5.2f}/{h:>5.2f}{arrow}", end="")
        print()
    print()

if __name__ == "__main__":
    print_global_comparison()
    print_category_comparison()
    print_question_detail()
    print_critical_analysis()
    generate_charts()

    print("  Rapport terminé")
    print(f"  Fichiers disponibles dans : {OUTPUT_DIR}/")
