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

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import requests

# nba_api opsiyonel: Docker imajı ince tutmak için try/except ile yüklüyoruz.
try:
    from nba_api.live.nba.endpoints import boxscore as live_boxscore_lib
    from nba_api.live.nba.endpoints import scoreboard as live_scoreboard_lib
    from nba_api.stats.endpoints import boxscoretraditionalv3, leaguegamefinder
    from nba_api.stats.static import teams as nba_static_teams

    _NBA_API_AVAILABLE = True
except Exception:  # pragma: no cover
    _NBA_API_AVAILABLE = False

# Rate limiting — cache.rate_limit_check kullanır (Redis yoksa hep True)
cache_lib: Any | None = None
try:
    import cache as _cache_mod

    cache_lib = _cache_mod
except Exception:
    cache_lib = None


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
def _resolve_nba_team_id(team_full_name: str) -> int | None:
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
        columns=["TARIH", "ESLESME", "G_B", "SAYI", "RAKIP_SAYI", "PLUS_MINUS", "EVDE"]
    )
    if not _NBA_API_AVAILABLE:
        return empty
    team_id = _resolve_nba_team_id(team_full_name)
    if team_id is None:
        return empty
    if cache_lib and not cache_lib.rate_limit_check("nba_api", 30, 60):
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

        # Rakip skorunu PLUS_MINUS'dan türet: PLUS_MINUS = kendi_sayisi - rakip_sayisi
        df["RAKIP_SAYI"] = df["SAYI"] - df["PLUS_MINUS"]

        return (
            df[["TARIH", "ESLESME", "G_B", "SAYI", "RAKIP_SAYI", "PLUS_MINUS", "EVDE"]]
            .sort_values("TARIH")
            .reset_index(drop=True)
        )
    except Exception:
        return empty


# -----------------------------------------------------------------------------
# NBA Sezon Schedule (Tüm Maçlar)
# -----------------------------------------------------------------------------
def fetch_nba_season_schedule(
    season: str = "2024-25", season_type: str = "Regular Season"
) -> pd.DataFrame:
    """
    Belirtilen sezondaki NBA maçlarını tekilleştirilmiş şekilde döner.

    Parametreler
    ------------
    season      : "2024-25" formatında
    season_type : "Regular Season" | "Playoffs"

    Her maç tek satır: GAME_ID, GAME_DATE, HOME, AWAY, HOME_PTS, AWAY_PTS,
    TOTAL, WINNER. Backtest ve eşleşme seçimi için kullanılır.
    """
    empty = pd.DataFrame(
        columns=["GAME_ID", "GAME_DATE", "HOME", "AWAY", "HOME_PTS", "AWAY_PTS", "TOTAL", "WINNER"]
    )
    if not _NBA_API_AVAILABLE:
        return empty
    if cache_lib and not cache_lib.rate_limit_check("nba_api", 30, 60):
        return empty
    try:
        finder = leaguegamefinder.LeagueGameFinder(
            season_nullable=season, season_type_nullable=season_type, league_id_nullable="00"
        )
        df = finder.get_data_frames()[0]
        if df is None or df.empty:
            return empty

        rows: list[dict] = []
        for game_id, gdf in df.groupby("GAME_ID"):
            if len(gdf) < 2:
                continue
            home_row = gdf[gdf["MATCHUP"].astype(str).str.contains("vs.", na=False)]
            away_row = gdf[gdf["MATCHUP"].astype(str).str.contains("@", na=False)]
            if home_row.empty or away_row.empty:
                continue
            h = home_row.iloc[0]
            a = away_row.iloc[0]
            matchup = str(h["MATCHUP"])
            home_abbr = away_abbr = None
            for sep in [" vs. ", " @ "]:
                if sep in matchup:
                    parts = matchup.split(sep)
                    if len(parts) == 2:
                        home_abbr, away_abbr = parts
                        break
            if not home_abbr:
                continue
            try:
                home_pts = int(h["PTS"])
                away_pts = int(a["PTS"])
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "GAME_ID": game_id,
                    "GAME_DATE": pd.to_datetime(h["GAME_DATE"], errors="coerce"),
                    "HOME": home_abbr,
                    "AWAY": away_abbr,
                    "HOME_PTS": home_pts,
                    "AWAY_PTS": away_pts,
                    "TOTAL": home_pts + away_pts,
                    "WINNER": home_abbr if home_pts > away_pts else away_abbr,
                }
            )
        if not rows:
            return empty
        return pd.DataFrame(rows).sort_values("GAME_DATE").reset_index(drop=True)
    except Exception:
        return empty


# -----------------------------------------------------------------------------
# EuroLeague / EuroCup
# -----------------------------------------------------------------------------
def fetch_euroleague_data(season_code: str = "E2024", competition: str = "E") -> pd.DataFrame:
    """
    EuroLeague (competition='E') veya EuroCup (competition='U') sezon verisi.

    Çıktı kolonları: HAFTA, GAME_CODE, SEASON_CODE, GAME_DATE, STATUS,
    EV_SAHIBI, DEPLASMAN, EV_SKOR, DEPLASMAN_SKOR, TOPLAM

    STATUS: "final" (oynanmis), "live" (baslamis, devam), "planlandi"
    """
    empty = pd.DataFrame(
        columns=[
            "HAFTA",
            "GAME_CODE",
            "SEASON_CODE",
            "GAME_DATE",
            "STATUS",
            "EV_SAHIBI",
            "DEPLASMAN",
            "EV_SKOR",
            "DEPLASMAN_SKOR",
            "TOPLAM",
        ]
    )
    if cache_lib and not cache_lib.rate_limit_check("euroleague_api", 60, 60):
        return empty
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
            played = bool(g.get("played", False))
            started = bool(g.get("started", False))
            if played:
                status = "final"
            elif started:
                status = "live"
            else:
                status = "planlandi"

            local = (g.get("local") or {}).get("club", {}) or {}
            road = (g.get("road") or {}).get("club", {}) or {}
            try:
                ev_skor = (
                    int(g.get("localScore", {}).get("score", 0))
                    if isinstance(g.get("localScore"), dict)
                    else int(g.get("localScore") or 0)
                )
                dep_skor = (
                    int(g.get("roadScore", {}).get("score", 0))
                    if isinstance(g.get("roadScore"), dict)
                    else int(g.get("roadScore") or 0)
                )
            except (TypeError, ValueError):
                ev_skor = dep_skor = 0

            date_raw = g.get("date") or g.get("startTimeUTC") or ""
            game_date = pd.to_datetime(date_raw, errors="coerce")

            rows.append(
                {
                    "HAFTA": int(g.get("round", 0) or 0),
                    "GAME_CODE": int(g.get("code", 0) or 0),
                    "SEASON_CODE": season_code,
                    "GAME_DATE": game_date,
                    "STATUS": status,
                    "EV_SAHIBI": local.get("name", "Unknown"),
                    "DEPLASMAN": road.get("name", "Unknown"),
                    "EV_SKOR": ev_skor,
                    "DEPLASMAN_SKOR": dep_skor,
                    "TOPLAM": ev_skor + dep_skor,
                }
            )
        if not rows:
            return empty
        return (
            pd.DataFrame(rows)
            .sort_values(["GAME_DATE", "HAFTA"], na_position="last")
            .reset_index(drop=True)
        )
    except Exception:
        return empty


def fetch_euroleague_season_cached(season_code: str, competition: str) -> pd.DataFrame:
    """Sezon fikstürünü TTL cache ile çeker (API kotası dostu)."""
    key = f"goldenb:cache:euro:schedule:{competition}:{season_code}"
    if cache_lib:
        cached = cache_lib.cache_get(key)
        if cached is not None:
            try:
                df = pd.DataFrame(cached)
                if not df.empty:
                    return df
            except Exception:
                pass
    df = fetch_euroleague_data(season_code, competition)
    if cache_lib and not df.empty:
        cache_lib.cache_set(key, df.to_dict(orient="records"), ttl_seconds=1800)
    return df


def fetch_euroleague_today_games(season_code: str, competition: str = "E") -> pd.DataFrame:
    """Bugün oynanacak/oynanan EuroLeague/EuroCup maçlarını döner."""
    empty = pd.DataFrame(
        columns=[
            "HAFTA",
            "GAME_CODE",
            "SEASON_CODE",
            "GAME_DATE",
            "STATUS",
            "EV_SAHIBI",
            "DEPLASMAN",
            "EV_SKOR",
            "DEPLASMAN_SKOR",
            "TOPLAM",
        ]
    )
    df = fetch_euroleague_season_cached(season_code, competition)
    if df is None or df.empty or "GAME_DATE" not in df.columns:
        return empty
    today = pd.Timestamp.today().normalize()
    mask = pd.to_datetime(df["GAME_DATE"], errors="coerce").dt.normalize() == today
    return df[mask].reset_index(drop=True)


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


def compute_schedule_baseline(df: pd.DataFrame, league: str) -> float:
    """
    Sezon fikstüründen (tüm maçlar) maç başına ortalama TOPLAM skoru döndürür.

    NBA       : 'TOTAL' kolonu
    Euro*     : 'TOPLAM' kolonu
    Hata/boş ise 0.0 döner.
    """
    try:
        if df is None or df.empty:
            return 0.0
        col = "TOTAL" if league == "NBA" else "TOPLAM"
        if col not in df.columns:
            return 0.0
        val = float(pd.to_numeric(df[col], errors="coerce").mean())
        return val if val > 0 else 0.0
    except Exception:
        return 0.0


def compute_team_baselines(df: pd.DataFrame, league: str) -> tuple[float, float]:
    """
    Sezon fikstüründen Ev ve Deplasman ortalama skorlarini ayri dondurur.

    NBA       : HOME_PTS, AWAY_PTS kolonlari
    Euro*     : EV_SKOR, DEPLASMAN_SKOR kolonlari

    Donus: (home_baseline, away_baseline)
    Hata / bos durumda (0.0, 0.0).
    """
    try:
        if df is None or df.empty:
            return (0.0, 0.0)
        if league == "NBA":
            if "HOME_PTS" not in df.columns or "AWAY_PTS" not in df.columns:
                return (0.0, 0.0)
            home = float(pd.to_numeric(df["HOME_PTS"], errors="coerce").mean())
            away = float(pd.to_numeric(df["AWAY_PTS"], errors="coerce").mean())
        else:
            if "EV_SKOR" not in df.columns or "DEPLASMAN_SKOR" not in df.columns:
                return (0.0, 0.0)
            home = float(pd.to_numeric(df["EV_SKOR"], errors="coerce").mean())
            away = float(pd.to_numeric(df["DEPLASMAN_SKOR"], errors="coerce").mean())
        return (home if home > 0 else 0.0, away if away > 0 else 0.0)
    except Exception:
        return (0.0, 0.0)


# -----------------------------------------------------------------------------
# Tarihsel Çeyrek Verisi
# -----------------------------------------------------------------------------
def fetch_historical_nba_quarters(game_id: str) -> dict[int, float]:
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
        cumulative: dict[int, float] = {}
        running = 0.0
        for q in sorted([k for k in per_q if isinstance(k, int) and 1 <= k <= 4]):
            running += float(per_q[q])
            cumulative[q] = round(running, 2)
        return cumulative
    except Exception:
        return {}


def fetch_historical_euroleague_quarters(
    season_code: str, game_code: int, competition: str = "E"
) -> dict[int, float]:
    """
    EuroLeague/EuroCup maçının 4 çeyreğinin KÜMÜLATİF toplam skorlarını döndürür.
    """
    url = f"{EUROLEAGUE_BASE_URL}/{competition}/seasons/{season_code}/games/{game_code}/boxscore"
    try:
        r = requests.get(url, headers=EUROLEAGUE_HEADERS, timeout=REQUEST_TIMEOUT_SEC)
        if r.status_code != 200:
            return {}
        data = r.json()
        if not isinstance(data, dict):
            return {}

        stats = data.get("stats") or data
        # Stats içinde takımların periyot skorları farklı formatlarda gelebilir.
        per_q_totals: dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}

        def _harvest(team_stats: dict[str, Any]) -> None:
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
        cumulative: dict[int, float] = {}
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
FAMOUS_GAMES: dict[str, dict[str, Any]] = {
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


def fetch_famous_game_quarters(label: str) -> dict[int, float]:
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


def get_famous_games_for_league(league: str) -> dict[str, dict[str, Any]]:
    """Belirli bir lig için ünlü maçları filtreler."""
    key = league.upper()
    return {
        label: meta for label, meta in FAMOUS_GAMES.items() if meta.get("league", "").upper() == key
    }


def fetch_quarters_for_schedule_row(row: pd.Series, league: str) -> dict[int, float]:
    """
    Schedule satırından çeyrek skorlarını çeker (NBA veya Euro).

    NBA  : canlı/geriye dönüşlü liveData boxscore ile (game_id gerekir)
    Euro : Boxscore endpoint'i ile (season_code + game_code gerekir)

    Hata/boş durumda {} döner.
    """
    try:
        if league == "NBA":
            gid = str(row.get("GAME_ID", ""))
            if not gid:
                return {}
            team_quarters = fetch_nba_quarters_by_team(gid)
            return team_quarters.get("total", {})
        if league in ("EuroLeague", "EuroCup"):
            comp = "E" if league == "EuroLeague" else "U"
            season_code = str(row.get("SEASON_CODE", "") or "")
            game_code = int(row.get("GAME_CODE", 0) or 0)
            if not season_code or game_code <= 0:
                return {}
            team_quarters = fetch_euroleague_quarters_by_team(
                season_code=season_code, game_code=game_code, competition=comp
            )
            return team_quarters.get("total", {})
    except Exception:
        return {}
    return {}


# -----------------------------------------------------------------------------
# Takım Formu (Son N Maç Tabanlı Gerçek Baseline)
# -----------------------------------------------------------------------------
def _nba_cache_wrap(
    key: str, fetch_fn: Callable[[], pd.DataFrame], ttl_seconds: int = 21600
) -> pd.DataFrame:
    """NBA çekimlerini TTL cache'e sar (Redis yoksa doğrudan çalışır)."""
    if cache_lib:
        cached = cache_lib.cache_get(key)
        if cached is not None:
            try:
                df = pd.DataFrame(cached)
                if not df.empty:
                    return df
            except Exception:
                pass
    df = fetch_fn()
    if cache_lib and not df.empty:
        cache_lib.cache_set(key, df.to_dict(orient="records"), ttl_seconds=ttl_seconds)
    return df


def _fetch_nba_team_games_raw(team_full_name: str, season: str) -> pd.DataFrame:
    """Tek bir NBA takımın sezon maçlarını çeker (ham nba_api)."""
    empty = pd.DataFrame(columns=["GAME_DATE", "MATCHUP", "PTS", "IS_HOME"])
    if not _NBA_API_AVAILABLE or not team_full_name:
        return empty
    team_id = _resolve_nba_team_id(team_full_name)
    if team_id is None:
        return empty
    if cache_lib and not cache_lib.rate_limit_check("nba_api", 30, 60):
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
        df = df.rename(columns={"GAME_DATE": "GAME_DATE", "PTS": "PTS"})
        df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        df["PTS"] = pd.to_numeric(df["PTS"], errors="coerce")
        df["IS_HOME"] = df["MATCHUP"].astype(str).str.contains("vs.", na=False)
        return (
            df[["GAME_DATE", "MATCHUP", "PTS", "IS_HOME"]]
            .sort_values("GAME_DATE")
            .reset_index(drop=True)
        )
    except Exception:
        return empty


def _fetch_nba_team_games(team_full_name: str, season: str) -> pd.DataFrame:
    """Takım maçlarını 6 saat TTL cache ile çeker."""
    team_id = _resolve_nba_team_id(team_full_name) or 0
    return _nba_cache_wrap(
        f"goldenb:cache:nba:team:{team_id}:{season}",
        lambda: _fetch_nba_team_games_raw(team_full_name, season),
        ttl_seconds=21600,
    )


def _mean_ring(values: list[float], lookback: int) -> float:
    vals = [float(v) for v in values if pd.notna(v)]
    if not vals:
        return 0.0
    recent = vals[-max(1, lookback) :]
    return float(np.mean(recent))


def compute_team_form(
    home_team: str, away_team: str, league: str, season: str = "", lookback: int = 10
) -> tuple[float, float]:
    """
    SEÇİLEN MAÇA ÖZEL gerçek takım projeksiyonu.

    NBA       : Ev sahibinin son 'lookback' CANLI EVDE ATTĞI ortalama +
                deplasmanın son 'lookback' DEPLASMANDA attığı ortalama.
    Euro*     : Mevcut sezon fikstüründen aynı hesap (ekstra API çağrısı yok).

    Basarısız durumda (0.0, 0.0) döner — çağıran taraf lig ortalamasına düşer.
    """
    try:
        if league == "NBA":
            h_df = _fetch_nba_team_games(home_team, season)
            a_df = _fetch_nba_team_games(away_team, season)
            if h_df.empty or a_df.empty:
                return (0.0, 0.0)
            h_home_pts = h_df.loc[h_df["IS_HOME"] == True, "PTS"].tolist()  # noqa: E712
            h_all_pts = h_df["PTS"].tolist()
            a_away_pts = a_df.loc[a_df["IS_HOME"] == False, "PTS"].tolist()  # noqa: E712
            a_all_pts = a_df["PTS"].tolist()
            home_proj = _mean_ring(h_home_pts or h_all_pts, lookback)
            away_proj = _mean_ring(a_away_pts or a_all_pts, lookback)
            return (home_proj, away_proj)

        if league in ("EuroLeague", "EuroCup"):
            comp = "E" if league == "EuroLeague" else "U"
            sched = fetch_euroleague_season_cached(season, comp)
            if sched is None or sched.empty:
                return (0.0, 0.0)
            h_rows = sched[sched["EV_SAHIBI"] == home_team]
            a_rows = sched[sched["DEPLASMAN"] == away_team]
            home_proj = _mean_ring(h_rows["EV_SKOR"].tolist(), lookback)
            away_proj = _mean_ring(a_rows["DEPLASMAN_SKOR"].tolist(), lookback)
            if home_proj <= 0:
                home_proj = _mean_ring(
                    sched[sched["EV_SAHIBI"] == home_team]["EV_SKOR"].tolist(), lookback
                )
            if away_proj <= 0:
                away_proj = _mean_ring(
                    sched[sched["DEPLASMAN"] == away_team]["DEPLASMAN_SKOR"].tolist(), lookback
                )
            return (home_proj, away_proj)
    except Exception:
        return (0.0, 0.0)
    return (0.0, 0.0)


# -----------------------------------------------------------------------------
# NBA Canlı Feed (cdn.nba.com liveData — API anahtarı yok)
# -----------------------------------------------------------------------------
def _parse_team_periods(team_node: dict[str, Any], final_score: float) -> dict[int, float]:
    """
    liveData boxscore'daki bir takım node'undan ÇEYREK BAŞINA skorlar çıkarır.
    periodValue alanı periyot-bazlı iken (NBA) kümülatif gelen formatları da
    normalize eder. Dönüş {1..4: per-yarıyık skor}.
    """
    per_q: dict[int, float] = {}
    try:
        periods = team_node.get("periods") or []
        for p in periods:
            if not isinstance(p, dict):
                continue
            try:
                q = int(p.get("period", 0))
            except (TypeError, ValueError):
                continue
            if not 1 <= q <= 4:
                continue
            val = p.get("periodValue")
            if val is None:
                val = p.get("score")
            try:
                per_q[q] = float(val or 0)
            except (TypeError, ValueError):
                continue
    except Exception:
        return {}

    if not per_q:
        return {}
    total = sum(per_q.values())
    if final_score > 0 and abs(total - final_score) > 0.1:
        # Kümülatif gelmiş: farkları al per-yarıyıka çevir
        per: dict[int, float] = {}
        prev = 0.0
        for q in sorted(per_q):
            per[q] = max(0.0, per_q[q] - prev)
            prev = per_q[q]
        per_q = per
    return per_q


def _cumulative(per_q: dict[int, float]) -> dict[int, float]:
    out: dict[int, float] = {}
    running = 0.0
    for q in sorted(per_q):
        running += per_q[q]
        out[q] = round(running, 2)
    return out


def fetch_nba_live_state(game_id: str) -> dict[str, Any]:
    """
    Bir NBA maçının (oynanıyor veya bitmiş) canlı durumunu çeker.

    Dönüş dict:
        status, period, clock, home_score, away_score,
        home_periods: {q: per-quarter pts}, away_periods: aynı,
        finished: bool
    """
    out: dict[str, Any] = {
        "status": "",
        "period": 0,
        "clock": "",
        "home_score": 0.0,
        "away_score": 0.0,
        "home_periods": {},
        "away_periods": {},
        "finished": False,
    }
    if not _NBA_API_AVAILABLE or not game_id:
        return out
    try:
        box = live_boxscore_lib.BoxScore(game_id=str(game_id))
        game = (box.get_dict() or {}).get("game") or {}
        out["status"] = str(game.get("gameStatusText", "") or "")
        try:
            out["period"] = int(game.get("period", 0) or 0)
        except (TypeError, ValueError):
            out["period"] = 0
        out["clock"] = str(game.get("gameClock", "") or "")

        home = game.get("homeTeam") or {}
        away = game.get("awayTeam") or {}
        try:
            out["home_score"] = float(home.get("score", 0) or 0)
        except (TypeError, ValueError):
            out["home_score"] = 0.0
        try:
            out["away_score"] = float(away.get("score", 0) or 0)
        except (TypeError, ValueError):
            out["away_score"] = 0.0
        out["home_periods"] = _parse_team_periods(home, out["home_score"])
        out["away_periods"] = _parse_team_periods(away, out["away_score"])
        out["finished"] = out["status"].lower().endswith("final")
    except Exception:
        pass
    return out


def fetch_nba_quarters_by_team(game_id: str) -> dict[str, dict[int, float]]:
    """
    NBA maçının çeyrek kırılımlarını takım-bazlı KÜMÜLATİF döner.

    Dönüş: {"home": {q: cum_h}, "away": {q: cum_a}, "total": {q: cum_t}}
    Çeyrek verisi ayrışmıyorsa home/away boş, total dolu (fallback yolu).
    """
    out: dict[str, dict[int, float]] = {"home": {}, "away": {}, "total": {}}
    state = fetch_nba_live_state(game_id)
    hp, ap = state.get("home_periods") or {}, state.get("away_periods") or {}
    if hp and ap and len(hp) == len(ap) and len(hp) >= 1:
        cum_h, cum_a = _cumulative(hp), _cumulative(ap)
        out["home"] = cum_h
        out["away"] = cum_a
        out["total"] = {q: round(cum_h[q] + cum_a[q], 2) for q in sorted(set(cum_h) & set(cum_a))}
    else:
        out["total"] = fetch_quarters_combined_fallback(game_id)
    return out


def fetch_quarters_combined_fallback(game_id: str) -> dict[int, float]:
    """Takım ayrımı olmayan durumda toplam kümülatif çeyrek (eski yol)."""
    if not _NBA_API_AVAILABLE or not game_id:
        return {}
    try:
        box = boxscoretraditionalv3.BoxScoreTraditionalV3(
            game_id=game_id, timeout=REQUEST_TIMEOUT_SEC
        )
        frames = box.get_data_frames()
        if not frames:
            return {}
        team_df = frames[0]
        if "period" not in team_df.columns or "points" not in team_df.columns:
            return {}
        per_q = team_df.groupby("period")["points"].sum().to_dict()
        per: dict[int, float] = {}
        for k, v in per_q.items():
            try:
                q = int(k)
                if 1 <= q <= 4:
                    per[q] = float(v)
            except (TypeError, ValueError):
                continue
        return _cumulative(per)
    except Exception:
        return {}


def fetch_nba_today_games() -> pd.DataFrame:
    """
    Bugün oynanan NBA maçları (canlı + bitmiş + planlanmış).

    Kolonlar: GAME_ID, HOME, AWAY, HOME_SCORE, AWAY_SCORE, PERIOD, CLOCK,
              STATUS, GAME_TIME_UTC, HOME_FULL, AWAY_FULL
    """
    cols = [
        "GAME_ID",
        "HOME",
        "AWAY",
        "HOME_SCORE",
        "AWAY_SCORE",
        "PERIOD",
        "CLOCK",
        "STATUS",
        "GAME_TIME_UTC",
        "HOME_FULL",
        "AWAY_FULL",
    ]
    empty = pd.DataFrame(columns=cols)
    if not _NBA_API_AVAILABLE:
        return empty
    if cache_lib and not cache_lib.rate_limit_check("nba_live", 20, 60):
        return empty
    try:
        sb = live_scoreboard_lib.ScoreBoard()
        data = sb.get_dict() or {}
        games = (data.get("scoreboard") or {}).get("games") or []
        rows = []
        for g in games:
            if not isinstance(g, dict):
                continue
            home = g.get("homeTeam") or {}
            away = g.get("awayTeam") or {}
            try:
                per = int(g.get("period", 0) or 0)
            except (TypeError, ValueError):
                per = 0
            rows.append(
                {
                    "GAME_ID": str(g.get("gameId", "") or ""),
                    "HOME": str(home.get("teamAbbreviation", "") or ""),
                    "AWAY": str(away.get("teamAbbreviation", "") or ""),
                    "HOME_SCORE": float(home.get("score", 0) or 0),
                    "AWAY_SCORE": float(away.get("score", 0) or 0),
                    "PERIOD": per,
                    "CLOCK": str(g.get("gameClock", "") or ""),
                    "STATUS": str(g.get("gameStatus", 0) or 0),
                    "GAME_TIME_UTC": str(g.get("gameTimeUTC", "") or ""),
                    "HOME_FULL": f"{home.get('teamCity', '')} {home.get('teamName', '')}".strip(),
                    "AWAY_FULL": f"{away.get('teamCity', '')} {away.get('teamName', '')}".strip(),
                }
            )
        if not rows:
            return empty
        return pd.DataFrame(rows)[cols].sort_values("GAME_TIME_UTC").reset_index(drop=True)
    except Exception:
        return empty


def fetch_euroleague_quarters_by_team(
    season_code: str, game_code: int, competition: str = "E"
) -> dict[str, dict[int, float]]:
    """
    EuroLeague/EuroCup maçının çeyrek kırılımlarını takım-bazlı KÜMÜLATİF döner.

    API'nin olası farklı şemalarına bükülür (defensive parsing);
    ayrışamazsa {"home": {}, "away": {}, "total": {kümülatif}} döner.
    """
    out: dict[str, dict[int, float]] = {"home": {}, "away": {}, "total": {}}
    url = f"{EUROLEAGUE_BASE_URL}/{competition}/seasons/{season_code}/games/{game_code}/boxscore"
    try:
        r = requests.get(url, headers=EUROLEAGUE_HEADERS, timeout=REQUEST_TIMEOUT_SEC)
        if r.status_code != 200:
            return out
        data = r.json()
        if not isinstance(data, dict):
            return out
    except Exception:
        return out

    def _per_quarter_from_node(node: Any) -> dict[int, float]:
        per_q: dict[int, float] = {}
        if not isinstance(node, dict):
            return per_q
        for key, val in node.items():
            kl = str(key).lower()
            if not kl.startswith(("quarter", "q")):
                continue
            digits = "".join(ch for ch in kl if ch.isdigit())
            if not digits:
                continue
            try:
                qnum = int(digits[0])
            except (TypeError, ValueError):
                continue
            if not 1 <= qnum <= 4:
                continue
            pts = None
            if isinstance(val, dict):
                pts = val.get("points") or val.get("score") or val.get("total")
            else:
                pts = val
            if pts is not None:
                try:
                    per_q[qnum] = float(pts)
                except (TypeError, ValueError):
                    continue
        return per_q

    def _find_team_nodes(
        node: Any, labels: tuple[str, ...], depth: int = 0
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if depth > 6 or not isinstance(node, dict):
            return found
        for key, val in node.items():
            kl = str(key).lower()
            if any(lbl in kl for lbl in labels) and isinstance(val, dict):
                found.append(val)
            found.extend(_find_team_nodes(val, labels, depth + 1))
        return found

    containers = data.get("stats") or data
    stats_block = containers.get("stats") if isinstance(containers, dict) else None

    home_nodes = _find_team_nodes(stats_block or containers, ("local", "home"))
    away_nodes = _find_team_nodes(stats_block or containers, ("road", "visit", "away"))

    def _merge_periods(nodes: list[dict[str, Any]]) -> dict[int, float]:
        merged: dict[int, float] = {}
        for node in nodes:
            # {quarterN: value} seviyesindeyse direkt al
            cand = _per_quarter_from_node(node)
            if not cand and isinstance(node, dict):
                for sub in node.values():
                    if isinstance(sub, dict):
                        sub_c = _per_quarter_from_node(sub)
                        for q, v in sub_c.items():
                            if merged.get(q, 0) == 0:
                                merged[q] = v
                continue
            for q, v in cand.items():
                if merged.get(q, 0) == 0:
                    merged[q] = v
        return merged

    home_per = _merge_periods(home_nodes[:1] or [])
    away_per = _merge_periods(away_nodes[:1] or [])

    if home_per and away_per and len(home_per) == len(away_per):
        out["home"] = _cumulative(home_per)
        out["away"] = _cumulative(away_per)
        out["total"] = {q: round(out["home"][q] + out["away"][q], 2) for q in out["home"]}
        return out

    # Fallback: eski birleşik toplam üzerinden 50/50 tahmini bölünüm
    combined = fetch_historical_euroleague_quarters(season_code, game_code, competition)
    out["total"] = combined
    if combined:
        out["home"] = {q: round(v / 2.0, 2) for q, v in combined.items()}
        out["away"] = {q: round(v / 2.0, 2) for q, v in combined.items()}
    return out
