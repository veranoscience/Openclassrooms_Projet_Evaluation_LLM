# utils/load_excel_to_db.py
"""
Pipeline d'ingestion : Excel -> Pydantic validation -> SQLite

Étapes :
  1. Lire les feuilles "Données NBA" et "Equipe" du fichier Excel
  2. Valider chaque ligne avec des modèles Pydantic (rejet des données invalides)
  3. Insérer dans la base SQLite (3 tables : teams, players, player_stats)

"""

import sys
import logging
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator, ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config import DATABASE_FILE, DATABASE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

EXCEL_FILE = "inputs/regular NBA.xlsx"

# 1. MODÈLES PYDANTIC — Validation des données avant insertion

# Chaque modèle correspond exactement à une table SQL
# Pydantic vérifie les types, les plages de valeurs et nettoie les données
# AVANT qu'elles arrivent dans la base — évite les données corrompues

class TeamRow(BaseModel):
    """Valide une ligne de la feuille 'Equipe'"""
    team_code: str = Field(min_length=2, max_length=3)
    team_name: str = Field(min_length=3)

    @field_validator("team_code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()


class PlayerRow(BaseModel):
    """Valide les informations d'identité d'un joueur"""
    name: str = Field(min_length=2)
    team_code: str = Field(min_length=2, max_length=3)
    age: int = Field(ge=18, le=45)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("team_code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()


class PlayerStatsRow(BaseModel):
    """
    Valide les statistiques saison d'un joueur
    Toutes les stats sont des totaux ou moyennes sur la saison régulière
    Optional[float] = peut être None si la donnée est manquante dans l'Excel
    """
    player_name: str  # clé de jointure temporaire
    # Présence terrain
    gp:  int   = Field(ge=0, le=82)    # Games Played
    w:   int   = Field(ge=0, le=82)    # Victoires
    l:   int   = Field(ge=0, le=82)    # Défaites
    min_total: Optional[float] = None  # Minutes totales
    # Stats offensives
    pts:  Optional[float] = None       # Points totaux
    fgm:  Optional[float] = None       # Tirs réussis
    fga:  Optional[float] = None       # Tirs tentés
    fg_pct:  Optional[float] = None    # % tirs (0-100)
    three_pa: Optional[float] = None   # Tirs à 3pts tentés
    three_pct: Optional[float] = None  # % à 3pts
    ftm:  Optional[float] = None       # Lancers francs réussis
    fta:  Optional[float] = None       # Lancers francs tentés
    ft_pct: Optional[float] = None     # % lancers francs
    # Stats défensives / polyvalence
    oreb: Optional[float] = None
    dreb: Optional[float] = None
    reb:  Optional[float] = None
    ast:  Optional[float] = None
    tov:  Optional[float] = None
    stl:  Optional[float] = None
    blk:  Optional[float] = None
    pf:   Optional[float] = None
    # Métriques avancées
    plus_minus: Optional[float] = None
    offrtg:    Optional[float] = None
    defrtg:    Optional[float] = None
    netrtg:    Optional[float] = None
    ast_pct:   Optional[float] = None
    ast_to:    Optional[float] = None
    oreb_pct:  Optional[float] = None
    dreb_pct:  Optional[float] = None
    reb_pct:   Optional[float] = None
    efg_pct:   Optional[float] = None
    ts_pct:    Optional[float] = None
    usg_pct:   Optional[float] = None
    pace:      Optional[float] = None
    pie:       Optional[float] = None
    poss:      Optional[float] = None
    # Double/Triple doubles
    dd2: Optional[int] = None
    td3: Optional[int] = None

    @field_validator("fg_pct", "three_pct", "ft_pct", mode="before")
    @classmethod
    def pct_range(cls, v):
        """Les pourcentages sont entre 0 et 100 dans l'Excel"""
        if v is None:
            return None
        try:
            val = float(v)
            if val < 0 or val > 100:
                return None  # valeur aberrante -> None
            return val
        except (TypeError, ValueError):
            return None


# 2. CRÉATION DES TABLES SQL


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS teams (
    team_code TEXT PRIMARY KEY,
    team_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    player_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    team_code   TEXT NOT NULL,
    age         INTEGER,
    FOREIGN KEY (team_code) REFERENCES teams(team_code)
);

CREATE TABLE IF NOT EXISTS player_stats (
    stat_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL,
    -- Présence terrain
    gp          INTEGER,
    w           INTEGER,
    l           INTEGER,
    min_total   REAL,
    -- Stats offensives
    pts         REAL,
    fgm         REAL,
    fga         REAL,
    fg_pct      REAL,
    three_pa    REAL,
    three_pct   REAL,
    ftm         REAL,
    fta         REAL,
    ft_pct      REAL,
    -- Stats classiques
    oreb        REAL,
    dreb        REAL,
    reb         REAL,
    ast         REAL,
    tov         REAL,
    stl         REAL,
    blk         REAL,
    pf          REAL,
    -- Métriques avancées
    plus_minus  REAL,
    offrtg      REAL,
    defrtg      REAL,
    netrtg      REAL,
    ast_pct     REAL,
    ast_to      REAL,
    oreb_pct    REAL,
    dreb_pct    REAL,
    reb_pct     REAL,
    efg_pct     REAL,
    ts_pct      REAL,
    usg_pct     REAL,
    pace        REAL,
    pie         REAL,
    poss        REAL,
    dd2         INTEGER,
    td3         INTEGER,
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);
"""


# 3. FONCTIONS D'INGESTION

def safe_float(val) -> Optional[float]:
    """Convertit une valeur en float, retourne None si impossible"""
    try:
        f = float(val)
        import math
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def safe_int(val) -> Optional[int]:
    """Convertit une valeur en int, retourne None si impossible"""
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def load_teams(conn: sqlite3.Connection, df_equipe: pd.DataFrame) -> int:
    """Charge la feuille 'Equipe' dans la table teams"""
    inserted = 0
    errors = 0
    for _, row in df_equipe.iterrows():
        try:
            team = TeamRow(
                team_code=str(row["Code"]),
                team_name=str(row["Nom complet de l'équipe"]),
            )
            conn.execute(
                "INSERT OR REPLACE INTO teams (team_code, team_name) VALUES (?, ?)",
                (team.team_code, team.team_name),
            )
            inserted += 1
        except ValidationError as e:
            logging.warning(f"Équipe ignorée (validation) : {row.to_dict()} — {e}")
            errors += 1
    conn.commit()
    logging.info(f"Teams : {inserted} insérées, {errors} rejetées.")
    return inserted


def load_players_and_stats(conn: sqlite3.Connection, df_nba: pd.DataFrame) -> tuple[int, int]:
    """Charge les joueurs et leurs stats depuis la feuille 'Données NBA'"""
    players_inserted = 0
    stats_inserted = 0
    errors = 0

    for _, row in df_nba.iterrows():
        # ── Validation du joueur ────────────────────────────────
        try:
            player = PlayerRow(
                name=str(row["Player"]),
                team_code=str(row["Team"]),
                age=safe_int(row["Age"]) or 0,
            )
        except ValidationError as e:
            logging.warning(f"Joueur ignoré : {row.get('Player', '?')} — {e}")
            errors += 1
            continue

        # ── Insertion du joueur ─────────────────────────────────
        cursor = conn.execute(
            "INSERT INTO players (name, team_code, age) VALUES (?, ?, ?)",
            (player.name, player.team_code, player.age),
        )
        player_id = cursor.lastrowid
        players_inserted += 1

        # ── Validation des stats ────────────────────────────────
        # La colonne "3P%" s'appelle datetime.time(15,0) à cause d'un bug Excel
        # On récupère la valeur par position (colonne index 10 = 3PM, 12 = 3PA, 13 = 3P%)
        cols = list(df_nba.columns)

        try:
            stats = PlayerStatsRow(
                player_name=player.name,
                gp=safe_int(row.get("GP", 0)) or 0,
                w=safe_int(row.get("W", 0)) or 0,
                l=safe_int(row.get("L", 0)) or 0,
                min_total=safe_float(row.get("Min")),
                pts=safe_float(row.get("PTS")),
                fgm=safe_float(row.get("FGM")),
                fga=safe_float(row.get("FGA")),
                fg_pct=safe_float(row.get("FG%")),
                # 3PA et 3P% — colonnes mal nommées dans l'Excel
                three_pa=safe_float(row.get("3PA")),
                three_pct=safe_float(row.get("3P%")),
                ftm=safe_float(row.get("FTM")),
                fta=safe_float(row.get("FTA")),
                ft_pct=safe_float(row.get("FT%")),
                oreb=safe_float(row.get("OREB")),
                dreb=safe_float(row.get("DREB")),
                reb=safe_float(row.get("REB")),
                ast=safe_float(row.get("AST")),
                tov=safe_float(row.get("TOV")),
                stl=safe_float(row.get("STL")),
                blk=safe_float(row.get("BLK")),
                pf=safe_float(row.get("PF")),
                plus_minus=safe_float(row.get("+/-")),
                offrtg=safe_float(row.get("OFFRTG")),
                defrtg=safe_float(row.get("DEFRTG")),
                netrtg=safe_float(row.get("NETRTG")),
                ast_pct=safe_float(row.get("AST%")),
                ast_to=safe_float(row.get("AST/TO")),
                oreb_pct=safe_float(row.get("OREB%")),
                dreb_pct=safe_float(row.get("DREB%")),
                reb_pct=safe_float(row.get("REB%")),
                efg_pct=safe_float(row.get("EFG%")),
                ts_pct=safe_float(row.get("TS%")),
                usg_pct=safe_float(row.get("USG%")),
                pace=safe_float(row.get("PACE")),
                pie=safe_float(row.get("PIE")),
                poss=safe_float(row.get("POSS")),
                dd2=safe_int(row.get("DD2")),
                td3=safe_int(row.get("TD3")),
            )
        except ValidationError as e:
            logging.warning(f"Stats ignorées pour {player.name} — {e}")
            errors += 1
            continue

        # ── Insertion des stats ─────────────────────────────────
        conn.execute("""
            INSERT INTO player_stats (
                player_id, gp, w, l, min_total,
                pts, fgm, fga, fg_pct,
                three_pa, three_pct,
                ftm, fta, ft_pct,
                oreb, dreb, reb, ast, tov, stl, blk, pf,
                plus_minus, offrtg, defrtg, netrtg,
                ast_pct, ast_to, oreb_pct, dreb_pct, reb_pct,
                efg_pct, ts_pct, usg_pct, pace, pie, poss,
                dd2, td3
            ) VALUES (
                ?,?,?,?,?,  ?,?,?,?,  ?,?,  ?,?,?,
                ?,?,?,?,?,?,?,?,
                ?,?,?,?,  ?,?,?,?,?,  ?,?,?,?,?,?,
                ?,?
            )
        """, (
            player_id,
            stats.gp, stats.w, stats.l, stats.min_total,
            stats.pts, stats.fgm, stats.fga, stats.fg_pct,
            stats.three_pa, stats.three_pct,
            stats.ftm, stats.fta, stats.ft_pct,
            stats.oreb, stats.dreb, stats.reb, stats.ast,
            stats.tov, stats.stl, stats.blk, stats.pf,
            stats.plus_minus, stats.offrtg, stats.defrtg, stats.netrtg,
            stats.ast_pct, stats.ast_to,
            stats.oreb_pct, stats.dreb_pct, stats.reb_pct,
            stats.efg_pct, stats.ts_pct, stats.usg_pct,
            stats.pace, stats.pie, stats.poss,
            stats.dd2, stats.td3,
        ))
        stats_inserted += 1

    conn.commit()
    logging.info(f"Players : {players_inserted} insérés.")
    logging.info(f"Stats   : {stats_inserted} insérées, {errors} rejetées.")
    return players_inserted, stats_inserted


def run():
    # Créer le dossier database si nécessaire
    Path(DATABASE_DIR).mkdir(parents=True, exist_ok=True)
    db_path = DATABASE_FILE

    logging.info(f"Base de données : {db_path}")
    logging.info(f"Fichier source  : {EXCEL_FILE}")

    # Lire l'Excel
    logging.info("Lecture du fichier Excel...")
    try:
        df_nba    = pd.read_excel(EXCEL_FILE, sheet_name="Données NBA", header=1)
        df_equipe = pd.read_excel(EXCEL_FILE, sheet_name="Equipe")
    except FileNotFoundError:
        logging.error(f"Fichier introuvable : {EXCEL_FILE}")
        sys.exit(1)

    # Nettoyer les colonnes sans nom (artefacts Excel)
    df_nba = df_nba.loc[:, ~df_nba.columns.astype(str).str.startswith("Unnamed")]
    # Supprimer les lignes entièrement vides
    df_nba = df_nba.dropna(how="all")
    logging.info(f"Données NBA : {len(df_nba)} lignes chargées")

    # Connexion SQLite
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # Créer les tables
    conn.executescript(CREATE_TABLES_SQL)
    logging.info("Tables créées (ou déjà existantes).")

    # Vider les tables existantes pour éviter les doublons si relancé
    conn.executescript("DELETE FROM player_stats; DELETE FROM players; DELETE FROM teams;")

    # Ingestion
    load_teams(conn, df_equipe)
    load_players_and_stats(conn, df_nba)

    # Vérification finale
    counts = {}
    for table in ("teams", "players", "player_stats"):
        (n,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[table] = n

    conn.close()

    logging.info("=" * 50)
    logging.info("Ingestion terminée :")
    for table, n in counts.items():
        logging.info(f"  {table:<15} : {n} lignes")
    logging.info("=" * 50)


if __name__ == "__main__":
    run()
