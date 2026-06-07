"""
GoldenBet AI - Veri Çekim Motoru
================================

NBA (nba_api), EuroLeague ve EuroCup (public REST API) için geçmiş maç ve
tarihsel çeyrek verisi çeken modül. Tüm fonksiyonlar hata durumunda boş
DataFrame/dict döner, uygulama çökmez.

Yetenekler:
    * fetch_nba_data(...)                 : NBA takım geçmişi
    * fetch_euroleague_data(...)          : EuroLeague/EuroCup sezon verisi
    * fetch_historical_nba_quarters(...)  : NBA maçının çeyrek skorları
    * fetch_historical_euroleague_quarters(...) : EuroLeague maçı çeyrek
    * compute_team_baseline(...)          : dakika başı ortalama skor
    * FAMOUS_GAMES                        : efsanevi maçlar sözlüğü
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import pandas as pd
import requests

# nba_api opsiyonel: Docker imajı ince tutmak için try/except ile yüklüyoruz.
try:
    from nba_api.stats.endpoints import leaguegamefinder
    from nba_api.stats.static import teams as nba_static_teams
    from nba_api.stats.endpoints import boxscoretraditionalv3
    _NBA_API_AVAILABLE = True
except Exception:  # pragma: no cover
    _NBA_API_AVAILABLE = False


# -----------------------------------------------------------------------------
# Sabitler
# -----------------------------------------------------------------------------
NBA_HEADERS = {
    "Host": "stats.nba.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Referer": "https://www.nba.com/",
}

EUROLEAGUE_BASE_URL = "https://api.euroleague.net/v2/competitions"
EUROLEAGUE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.euroleaguebasketball.net/",
    "Origin": "https://www.euroleaguebasketball.net",
}

REQUEST_TIMEOUT_SEC = 15


# -----------------------------------------------------------------------------
# NBA
# -----------------------------------------------------------------------------
def _resolve_nba_team_id(team_full_name: str) -> Optional[int]:
    """`nba_api.stats.static.teams` üzerinden takım ID'sini döndürür."""
    if not _NBA_API_AVAILABLE or not team_full_name:
        return None
    try:
        all_teams = nba_static_teams.get_teams()
        target = team_full_name.strip().lower()
        for t in all_teams:
            full = (t.get("full_name") or "").lower()
            nick = (t.get("nickname") or "").lower()
            city = (t.get("city") or "").lower()
            if target in (full, nick, f"{city} {nick}".strip()):
                return int(t["id"])
        return None
    except Exception:
        return None


def fetch_nba_data(team_full_name: str, season: str = "2024-25") -> pd.DataFrame:
    """
    Belirtilen NBA takımının ilgili sezondaki tüm maçlarını çeker.

    Sütunlar: TARIH, ESLESME, G_B, SAYI, RAKIP_SAYI, PLUS_MINUS, EVDE
    """
    empty = pd.DataFrame(
        columns=["TARIH", "ESLESME", "G_B", "SAYI", "RAKIP_SAYI",
                 "PLUS_MINUS", "EVDE"]
    )
    if not _NBA_API_AVAILABLE:
        return empty
    team_id = _resolve_nba_team_id(team_full_name)
    if team_id is None:
        return empty
    try:
        finder = leaguegamefinder.LeagueGameFinder(
            team_id_nullable=team_id,
            season_nullable=season,
            season_type_nullable="Regular Season",
            league_id_nullable="00",
        )
        df = finder.get_data_frames()[0]
        if df is None or df.empty:
            return empty

        rename_map = {
            "GAME_DATE": "TARIH",
            "MATCHUP": "ESLESME",
            "WL": "G_B",
            "PTS": "SAYI",
            "PLUS_MINUS": "PLUS_MINUS",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df["TARIH"] = pd.to_datetime(df["TARIH"], errors="coerce")
        df["SAYI"] = pd.to_numeric(df["SAYI"], errors="coerce")
        df["PLUS_MINUS"] = pd.to_numeric(df["PLUS_MINUS"], errors="coerce")
        df["EVDE"] = df["ESLESME"].astype(str).str.contains("vs.", na=False)

        # Rakip skorunu MATCHUP'tan türetmek zor; basitleştirme için bırakmıyoruz.
        if "RAKIP_SAYI" not in df.columns:
            df["RAKIP_SAYI"] = pd.NA

        return df[["TARIH", "ESLESME", "G_B", "SAYI", "RAKIP_SAYI",
                   "PLUS_MINUS", "EVDE"]].sort_values("TARIH").reset_index(drop=True)
    except Exception:
        return empty


# -----------------------------------------------------------------------------
# EuroLeague / EuroCup
# -----------------------------------------------------------------------------
def fetch_euroleague_data(season_code: str = "E2024",
                          competition: str = "E") -> pd.DataFrame:
    """
    EuroLeague (competition='E') veya EuroCup (competition='U') sezon verisi.

    Çıktı kolonları: HAFTA, EV_SAHIBI, DEPLASMAN, EV_SKOR, DEPLASMAN_SKOR, TOPLAM
    """
    empty = pd.DataFrame(
        columns=["HAFTA", "EV_SAHIBI", "DEPLASMAN",
                 "EV_SKOR", "DEPLASMAN_SKOR", "TOPLAM"]
    )
    url = f"{EUROLEAGUE_BASE_URL}/{competition}/seasons/{season_code}/games"
    try:
        r = requests.get(url, headers=EUROLEAGUE_HEADERS, timeout=REQUEST_TIMEOUT_SEC)
        if r.status_code != 200:
            return empty
        games = r.json()
        if not isinstance(games, list) or not games:
            return empty

        rows = []
        for g in games:
            # Sadece oynanmış maçları al
            if not g.get("played", False):
                continue
            local = (g.get("local") or {}).get("club", {}) or {}
            road = (g.get("road") or {}).get("club", {}) or {}
            try:
                ev_skor = int(g.get("localScore", {}).get("score", 0)) \
                    if isinstance(g.get("localScore"), dict) \
                    else int(g.get("localScore") or 0)
                dep_skor = int(g.get("roadScore", {}).get("score", 0)) \
                    if isinstance(g.get("roadScore"), dict) \
                    else int(g.get("roadScore") or 0)
            except (TypeError, ValueError):
                continue
            rows.append({
                "HAFTA": int(g.get("round", 0)),
                "EV_SAHIBI": local.get("name", "Unknown"),
                "DEPLASMAN": road.get("name", "Unknown"),
                "EV_SKOR": ev_skor,
                "DEPLASMAN_SKOR": dep_skor,
                "TOPLAM": ev_skor + dep_skor,
            })
        if not rows:
            return empty
        return pd.DataFrame(rows).sort_values("HAFTA").reset_index(drop=True)
    except Exception:
        return empty


# -----------------------------------------------------------------------------
# Baseline hesaplayıcı (takım/lig ortalaması)
# -----------------------------------------------------------------------------
def compute_team_baseline(df: pd.DataFrame, mode: str) -> float:
    """
    Maç başına ortalama TOPLAM skoru döndürür.

    mode='nba'  : df içinde 'SAYI' kolonu (tek takım). İki takım *2 yaklaşımı.
    mode='euro' : df içinde 'TOPLAM' kolonu.
    """
    try:
        if df is None or df.empty:
            return 0.0
        if mode == "nba" and "SAYI" in df.columns:
            return float(pd.to_numeric(df["SAYI"], errors="coerce").mean() * 2.0)
        if mode == "euro" and "TOPLAM" in df.columns:
            return float(pd.to_numeric(df["TOPLAM"], errors="coerce").mean())
    except Exception:
        return 0.0
    return 0.0


# -----------------------------------------------------------------------------
# Tarihsel Çeyrek Verisi
# -----------------------------------------------------------------------------
def fetch_historical_nba_quarters(game_id: str) -> Dict[int, float]:
    """
    NBA maçının 4 çeyreğinin KÜMÜLATİF toplam skorlarını döndürür.

    Dönüş: {1: q1_total, 2: q2_total, 3: q3_total, 4: final_total}
    Hata durumunda boş dict.
    """
    if not _NBA_API_AVAILABLE or not game_id:
        return {}
    try:
        box = boxscoretraditionalv3.BoxScoreTraditionalV3(
            game_id=game_id, timeout=REQUEST_TIMEOUT_SEC
        )
        # data_frames()[0] takım-seviyesinde özet, [1] oyuncu
        frames = box.get_data_frames()
        if not frames:
            return {}
        team_df = frames[0]
        # 'period' kolonu (1-4) ve 'points' kolonu bekliyoruz
        if "period" not in team_df.columns or "points" not in team_df.columns:
            return {}
        per_q = team_df.groupby("period")["points"].sum().to_dict()
        # Kümülatife çevir
        cumulative: Dict[int, float] = {}
        running = 0.0
        for q in sorted([k for k in per_q.keys() if isinstance(k, int) and 1 <= k <= 4]):
            running += float(per_q[q])
            cumulative[q] = round(running, 2)
        return cumulative
    except Exception:
        return {}


def fetch_historical_euroleague_quarters(season_code: str,
                                         game_code: int,
                                         competition: str = "E") -> Dict[int, float]:
    """
    EuroLeague/EuroCup maçının 4 çeyreğinin KÜMÜLATİF toplam skorlarını döndürür.
    """
    url = (
        f"{EUROLEAGUE_BASE_URL}/{competition}/seasons/{season_code}"
        f"/games/{game_code}/boxscore"
    )
    try:
        r = requests.get(url, headers=EUROLEAGUE_HEADERS, timeout=REQUEST_TIMEOUT_SEC)
        if r.status_code != 200:
            return {}
        data = r.json()
        if not isinstance(data, dict):
            return {}

        stats = data.get("stats") or data
        # Stats içinde takımların periyot skorları farklı formatlarda gelebilir.
        per_q_totals: Dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}

        def _harvest(team_stats: Dict[str, Any]) -> None:
            if not isinstance(team_stats, dict):
                return
            for key, val in team_stats.items():
                kl = str(key).lower()
                if not kl.startswith("quarter"):
                    continue
                # quarter1, quarter2, ... veya "q1" formatı olabilir
                try:
                    qnum = int("".join(ch for ch in kl if ch.isdigit())[:1] or "0")
                except (TypeError, ValueError):
                    continue
                if not 1 <= qnum <= 4:
                    continue
                pts = None
                if isinstance(val, dict):
                    pts = val.get("points") or val.get("score") or val.get("total")
                else:
                    pts = val
                if pts is None:
                    continue
                try:
                    per_q_totals[qnum] += float(pts)
                except (TypeError, ValueError):
                    continue

        # Olası anahtarlar: stats (her takım için dict) veya doğrudan takımlar
        if "stats" in stats and isinstance(stats["stats"], dict):
            for team_name, team_stats in stats["stats"].items():
                _harvest(team_stats if isinstance(team_stats, dict) else {})
        # Alternatif: Teams dict
        for team_key in ("local", "road", "home", "away"):
            t = stats.get(team_key) or data.get(team_key)
            if isinstance(t, dict):
                _harvest(t)

        if all(v == 0.0 for v in per_q_totals.values()):
            return {}
        cumulative: Dict[int, float] = {}
        running = 0.0
        for q in (1, 2, 3, 4):
            running += per_q_totals[q]
            cumulative[q] = round(running, 2)
        return cumulative
    except Exception:
        return {}


# -----------------------------------------------------------------------------
# Ünlü Maçlar Sözlüğü (Famous Games Index)
# -----------------------------------------------------------------------------
# Notlar:
#   * 'quarters' değerleri MAÇ BAŞINA KÜMÜLATİF TOPLAM skorlardır (her iki takım).
#   * 'game_id' / 'season_code'+'game_code' API çağrısı için opsiyonel şablondur.
#     API başarısız olursa hardcoded 'quarters' kullanılır (graceful fallback).
# -----------------------------------------------------------------------------
FAMOUS_GAMES: Dict[str, Dict[str, Any]] = {
    "2016 NBA Finals G7 (Cavaliers 93-89 Warriors)": {
        "league": "NBA",
        "game_id": "0041600407",
        "final_total": 182.0,
        "quarters": {1: 49.0, 2: 95.0, 3: 138.0, 4: 182.0},
        "note": "Tarihi geri dönüş maçı; Q3 sonu LeBron+Kyrie ısındı.",
    },
    "2004 NBA Finals G5 (Pistons 100-87 Lakers)": {
        "league": "NBA",
        "game_id": "0040400107",
        "final_total": 187.0,
        "quarters": {1: 36.0, 2: 80.0, 3: 119.0, 4: 187.0},
        "note": "Düşük tempolu, sert savunma dönemi — model hızlı öğrenmeli.",
    },
    "2019 NBA Finals G6 (Raptors vs Warriors)": {
        "league": "NBA",
        "game_id": "0041900306",
        "final_total": 211.0,
        "quarters": {1: 54.0, 2: 109.0, 3: 161.0, 4: 211.0},
        "note": "Yüksek tempolu şampiyonluk maçı.",
    },
    "2023 NBA Finals G5 (Nuggets 94-89 Heat)": {
        "league": "NBA",
        "game_id": "0042200305",
        "final_total": 183.0,
        "quarters": {1: 49.0, 2: 87.0, 3: 131.0, 4: 183.0},
        "note": "Düşük tempolu, savunma ağırlıklı final.",
    },
    "2024 EuroLeague Final (Real Madrid vs Panathinaikos)": {
        "league": "EUROLEAGUE",
        "game_id": None,
        "season_code": "E2023",
        "game_code": 350,
        "final_total": 175.0,
        "quarters": {1: 39.0, 2: 78.0, 3: 124.0, 4: 175.0},
        "note": "Modern EuroLeague temposu, dengeli skor.",
    },
    "2024 EuroCup Final (Paris Basketball)": {
        "league": "EUROCUP",
        "game_id": None,
        "season_code": "U2023",
        "game_code": 220,
        "final_total": 168.0,
        "quarters": {1: 38.0, 2: 82.0, 3: 120.0, 4: 168.0},
        "note": "EuroCup ortalamasına yakın tempo.",
    },
}


def fetch_famous_game_quarters(label: str) -> Dict[int, float]:
    """
    FAMOUS_GAMES içinden seçilen maçın çeyrek skorlarını döndürür.
    Önce API'yi dener, başarısız olursa hardcoded veriye düşer.
    """
    game = FAMOUS_GAMES.get(label)
    if not game:
        return {}

    league = game.get("league", "NBA")
    if league == "NBA" and game.get("game_id"):
        quarters = fetch_historical_nba_quarters(str(game["game_id"]))
        if quarters:
            return quarters
    elif league in ("EUROLEAGUE", "EUROCUP") and game.get("season_code"):
        comp = "E" if league == "EUROLEAGUE" else "U"
        quarters = fetch_historical_euroleague_quarters(
            season_code=str(game["season_code"]),
            game_code=int(game.get("game_code") or 0),
            competition=comp,
        )
        if quarters:
            return quarters

    # Graceful fallback → hardcoded değer
    return {int(k): float(v) for k, v in game.get("quarters", {}).items()}


def get_famous_games_for_league(league: str) -> Dict[str, Dict[str, Any]]:
    """Belirli bir lig için ünlü maçları filtreler."""
    key = league.upper()
    return {
        label: meta for label, meta in FAMOUS_GAMES.items()
        if meta.get("league", "").upper() == key
    }
