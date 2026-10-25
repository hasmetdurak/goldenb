"""
GoldenBet AI - Patron Komut Paneli
==================================

3-katmanli minimalist UI:
  1) Akordeon: Mac Kimligi & Kural Matrisi
  2) Dev Dijital Skor Tabelasi (Ev - Dep)
  3) 5 kart: Q1, Q2, 1H (vurgulu), Q3, Q4

Canli Veri Katmani:
  * NBA  : cdn.nba.com liveData (bugünkü maclar + canli skor, anahtar yok)
  * Euro : api.euroleague.net v2 (bugünkü maclar + durum)
  * Odds : The Odds API (ODDS_API_KEY) — gerçek bahisçi baraj + fiyat
"""

from __future__ import annotations

import re
import time
from typing import Any

import pandas as pd
import streamlit as st

import betting_ui as bui
import config as cfg
import data_fetcher as df_lib
import engine as eng
import odds_fetcher as of_lib

# -----------------------------------------------------------------------------
# Sayfa Konfigurasyonu
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="GoldenBet AI · Skor Tahmin Merkezi", layout="wide", initial_sidebar_state="expanded"
)


# -----------------------------------------------------------------------------
# CSS — Minimal Scoreboard UI
# -----------------------------------------------------------------------------
NEON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap');

.stApp {
    background: radial-gradient(ellipse at top, #0F172A 0%, #05080F 75%);
    font-family: 'JetBrains Mono', monospace;
}
.block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 0rem !important;
    max-width: 100% !important;
}
h1, h2, h3 {
    color: #00FF7F !important;
    font-weight: 800 !important;
    letter-spacing: 0.04em;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #0A0E1A;
    border-right: 1px solid #1F2937;
    padding: 0.8rem 0.8rem !important;
}
[data-testid="stSidebar"] h1 { font-size: 1.05rem !important; margin-bottom: 0.6rem; }
[data-testid="stSidebar"] h2 {
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #6B7280 !important;
    margin: 0.6rem 0 0.4rem 0 !important;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid #1F2937;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p {
    font-size: 0.74rem !important;
    color: #9CA3AF !important;
    margin-bottom: 0.15rem !important;
}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] select {
    font-size: 0.78rem !important;
    min-height: 30px !important;
}
[data-testid="stSidebar"] button {
    font-size: 0.75rem !important;
    padding: 0.3rem 0.5rem !important;
}

/* Metric karti */
.stMetric {
    background-color: #0d1117 !important;
    padding: 10px 12px !important;
    border-radius: 8px !important;
    border: 1px solid #21262d !important;
}
[data-testid="stMetricValue"] {
    color: #00FF7F !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 800 !important;
    font-size: 1.1rem !important;
}
[data-testid="stMetricLabel"] {
    color: #9CA3AF !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem !important;
}
div.stButton > button:first-child {
    width: 100%; font-weight: bold; border-radius: 6px;
}

/* --- SCOREBOARD --- */
.scoreboard {
    background: linear-gradient(180deg, #0d1117 0%, #010409 100%);
    border: 2px solid #30363d;
    border-radius: 16px;
    padding: clamp(20px, 4vw, 40px);
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 16px 0;
    box-shadow: 0 0 40px rgba(46, 160, 67, 0.12);
}
.score-side { text-align: center; flex: 1; min-width: 0; }
.team-name {
    color: #8b949e;
    font-size: clamp(0.8rem, 1.5vw, 1.1rem);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 8px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.score-number {
    color: #2ea043;
    font-size: clamp(2.8rem, 8vw, 5.5rem);
    font-weight: 900;
    font-family: 'JetBrains Mono', monospace;
    text-shadow: 0 0 20px rgba(46, 160, 67, 0.4);
    line-height: 1;
}
.score-dash {
    color: #FF1744;
    font-size: clamp(2rem, 5vw, 4rem);
    font-weight: 300;
    margin: 0 24px;
    flex-shrink: 0;
}
.scoreboard-sub {
    text-align: center;
    color: #c9d1d9;
    font-size: clamp(0.75rem, 1.3vw, 0.95rem);
    padding: 10px 16px;
    background: #0d1117;
    border-radius: 8px;
    border: 1px solid #21262d;
    margin-bottom: 12px;
}
.scoreboard-sub b { color: #2ea043; }

/* --- Quarter Cards --- */
.q-card {
    background: #0d1117;
    padding: clamp(10px, 1.5vw, 16px);
    border-radius: 10px;
    border: 1px solid #30363d;
    text-align: center;
    height: 100%;
    margin: 4px 0;
}
.q-card.half { border: 2px solid #238636; }
.q-label {
    color: #8b949e;
    font-size: clamp(0.6rem, 1vw, 0.72rem);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 6px;
}
.q-score {
    color: #f0f6fc;
    font-size: clamp(1.0rem, 2.2vw, 1.6rem);
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
}
.q-total {
    color: #2ea043;
    font-size: clamp(0.72rem, 1.2vw, 0.85rem);
    margin-top: 4px;
    font-weight: 700;
}

/* Odds paneli */
.odds-chip {
    display: inline-block;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 6px 12px;
    margin: 2px;
    font-family: 'JetBrains Mono', monospace;
}
.odds-chip b { color: #2ea043; }
.odds-ev-pos { color: #2ea043; font-weight: 800; }
.odds-ev-neg { color: #FF1744; }

/* Ogrenme Monitoru */
.mae-card {
    background-color: #0d1117;
    padding: clamp(14px, 2vw, 20px);
    border-radius: 12px;
    border: 1px solid #30363d;
    height: 100%;
}
.mae-card h3 { color: #f0f6fc !important; font-size: 0.95rem !important; margin: 0 0 8px 0 !important; }

/* Responsive */
@media (max-width: 768px) {
    .score-number { font-size: 2.5rem; }
    .score-dash { font-size: 1.6rem; margin: 0 10px; }
    .scoreboard { padding: 16px; }
}
@media (max-width: 480px) {
    .score-number { font-size: 1.8rem; }
    .scoreboard { padding: 12px; }
    .q-score { font-size: 0.9rem; }
}
</style>
"""
st.markdown(NEON_CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Session State Bootstrap
# -----------------------------------------------------------------------------
def _init_state() -> None:
    if "dual_engine" not in st.session_state:
        st.session_state.dual_engine = eng.DualTeamScoreEngine()
    if "mod" not in st.session_state:
        st.session_state.mod = "canli"
    if "league" not in st.session_state:
        st.session_state.league = "NBA"
    if "season" not in st.session_state:
        st.session_state.season = "2024-25"
    if "season_type" not in st.session_state:
        st.session_state.season_type = "Regular Season"
    if "home_score" not in st.session_state:
        st.session_state.home_score = 0
    if "away_score" not in st.session_state:
        st.session_state.away_score = 0
    if "current_minute" not in st.session_state:
        st.session_state.current_minute = 24
    if "total_minutes" not in st.session_state:
        st.session_state.total_minutes = 48
    if "schedule_df" not in st.session_state:
        st.session_state.schedule_df = pd.DataFrame()
    if "schedule_signature" not in st.session_state:
        st.session_state.schedule_signature = ""
    if "selected_match" not in st.session_state:
        st.session_state.selected_match = None
    if "baseline_avg" not in st.session_state:
        st.session_state.baseline_avg = 0.0
    if "home_baseline" not in st.session_state:
        st.session_state.home_baseline = 0.0
    if "away_baseline" not in st.session_state:
        st.session_state.away_baseline = 0.0
    if "baseline_source" not in st.session_state:
        st.session_state.baseline_source = "lig"
    if "context_tag" not in st.session_state:
        st.session_state.context_tag = "Normal_Season_Match"
    if "last_scoreboard" not in st.session_state:
        st.session_state.last_scoreboard = None
    if "historical_mode" not in st.session_state:
        st.session_state.historical_mode = False
    if "historical_quarters" not in st.session_state:
        st.session_state.historical_quarters = {}
    if "historical_team_quarters" not in st.session_state:
        st.session_state.historical_team_quarters = {}
    if "historical_scored_quarter" not in st.session_state:
        st.session_state.historical_scored_quarter = 0
    if "historical_label" not in st.session_state:
        st.session_state.historical_label = ""
    if "current_quarter" not in st.session_state:
        st.session_state.current_quarter = 0
    if "historical_running" not in st.session_state:
        st.session_state.historical_running = False
    # Canli feed + market
    if "live_game_id" not in st.session_state:
        st.session_state.live_game_id = ""
    if "live_state" not in st.session_state:
        st.session_state.live_state = {}
    if "market_odds" not in st.session_state:
        st.session_state.market_odds = None
    if "market_manual" not in st.session_state:
        st.session_state.market_manual = {}
    if "today_signature" not in st.session_state:
        st.session_state.today_signature = ""
    if "today_df" not in st.session_state:
        st.session_state.today_df = pd.DataFrame()
    if "final_real_total" not in st.session_state:
        st.session_state.final_real_total = 0.0


_init_state()


# -----------------------------------------------------------------------------
# Yardimcilar — Lig Ayarlari & Bugunku Maclar
# -----------------------------------------------------------------------------
def _euro_season_code(league: str, season: str) -> str:
    """EuroLeague/EuroCup kaynağının beklediği sezon kodu (E2024/U2024)."""
    prefix = "E" if league == "EuroLeague" else "U"
    s = (season or "").strip()
    if s.upper().startswith(prefix):
        return s
    digits = re.sub(r"[^0-9]", "", s) or "2024"
    if len(digits) == 4:
        digits = digits[2:]  # 2024 -> 24
    year = int(digits or 24)
    return f"{prefix}{year}"


def _status_label_nba(status_val: Any) -> str:
    try:
        code = int(status_val)
    except (TypeError, ValueError):
        code = 0
    return {1: "planlanmadi", 2: "canli", 3: "final"}.get(code, str(status_val))


def _load_today_games(league: str, season: str) -> pd.DataFrame:
    """Bugünkü maçlar (NBA canlı feed / Euro v2 API)."""
    if league == "NBA":
        return df_lib.fetch_nba_today_games()
    if league in ("EuroLeague", "EuroCup"):
        code = _euro_season_code(league, season)
        comp = "E" if league == "EuroLeague" else "U"
        return df_lib.fetch_euroleague_today_games(code, comp)
    return pd.DataFrame()


def _format_today_options(df: pd.DataFrame, league: str) -> list[str]:
    if df is None or df.empty:
        return []
    if league == "NBA":
        opts = []
        for row in df.itertuples():
            st_lbl = _status_label_nba(row.STATUS)
            score = (
                f"{row.HOME_SCORE:.0f}-{row.AWAY_SCORE:.0f}"
                if row.HOME_SCORE or row.AWAY_SCORE
                else ""
            )
            opts.append(
                f"{row.HOME_FULL} vs {row.AWAY_FULL} — {st_lbl}" + (f" [{score}]" if score else "")
            )
        return opts
    opts = []
    for row in df.itertuples():
        score = (
            f" [{row.EV_SKOR:.0f}-{row.DEPLASMAN_SKOR:.0f}]"
            if row.STATUS in ("live", "final")
            else ""
        )
        opts.append(f"{row.EV_SAHIBI} vs {row.DEPLASMAN} — {row.STATUS}" + score)
    return opts


def _extract_today_match(df: pd.DataFrame, idx: int, league: str) -> dict[str, Any] | None:
    if df is None or df.empty or idx is None or idx < 0 or idx >= len(df):
        return None
    row = df.iloc[idx]
    if league == "NBA":
        return {
            "source": "today",
            "game_id": str(row.get("GAME_ID", "")),
            "home": str(row.get("HOME_FULL", "") or row.get("HOME", "")),
            "away": str(row.get("AWAY_FULL", "") or row.get("AWAY", "")),
            "date": pd.Timestamp.now(),
            "label": f"{row.get('HOME_FULL', '')} vs {row.get('AWAY_FULL', '')}",
        }
    return {
        "source": "today",
        "game_id": str(row.get("GAME_CODE", "")),
        "home": str(row.get("EV_SAHIBI", "")),
        "away": str(row.get("DEPLASMAN", "")),
        "round": int(row.get("HAFTA", 0) or 0),
        "label": f"{row.get('EV_SAHIBI', '')} vs {row.get('DEPLASMAN', '')}",
    }


# -----------------------------------------------------------------------------
# Yardimcilar — Fikstur Yukleme (uzun donem / tunnel)
# -----------------------------------------------------------------------------
def _load_schedule(league: str, season: str, season_type: str) -> pd.DataFrame:
    if league == "NBA":
        return df_lib.fetch_nba_season_schedule(season=season, season_type=season_type)
    if league == "EuroLeague":
        return df_lib.fetch_euroleague_season_cached(
            _euro_season_code(league, season), competition="E"
        )
    if league == "EuroCup":
        return df_lib.fetch_euroleague_season_cached(
            _euro_season_code(league, season), competition="U"
        )
    return pd.DataFrame()


def _format_match_options(df: pd.DataFrame, league: str) -> list[str]:
    if df is None or df.empty:
        return []
    if league == "NBA":
        return [
            f"{row.HOME} vs {row.AWAY} - {pd.to_datetime(row.GAME_DATE).strftime('%Y-%m-%d')}"
            for row in df.itertuples()
        ]
    return [
        f"{row.EV_SAHIBI} vs {row.DEPLASMAN} - Round {int(row.HAFTA)}" for row in df.itertuples()
    ]


def _extract_match(df: pd.DataFrame, idx: int, league: str) -> dict[str, Any] | None:
    if df is None or df.empty or idx is None or idx < 0 or idx >= len(df):
        return None
    row = df.iloc[idx]
    if league == "NBA":
        return {
            "source": "fixture",
            "game_id": str(row.get("GAME_ID", "")),
            "home": str(row.get("HOME", "")),
            "away": str(row.get("AWAY", "")),
            "date": pd.to_datetime(row.get("GAME_DATE"), errors="coerce"),
            "label": f"{row.get('HOME', '')} vs {row.get('AWAY', '')}",
        }
    return {
        "source": "fixture",
        "game_id": str(row.get("GAME_CODE", "")),
        "home": str(row.get("EV_SAHIBI", "")),
        "away": str(row.get("DEPLASMAN", "")),
        "round": int(row.get("HAFTA", 0) or 0),
        "label": f"{row.get('EV_SAHIBI', '')} vs {row.get('DEPLASMAN', '')}",
    }


def _ensure_schedule() -> None:
    sig = f"{st.session_state.league}|{st.session_state.season}|{st.session_state.season_type}"
    if st.session_state.schedule_signature == sig and not st.session_state.schedule_df.empty:
        return
    with st.spinner("Fikstur yukleniyor..."):
        st.session_state.schedule_df = _load_schedule(
            st.session_state.league, st.session_state.season, st.session_state.season_type
        )
        st.session_state.schedule_signature = sig
        st.session_state.selected_match = None
        st.session_state.baseline_avg = 0.0
        st.session_state.home_baseline = 0.0
        st.session_state.away_baseline = 0.0


def _ensure_today_games() -> None:
    sig = f"{st.session_state.league}|{st.session_state.season}"
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    full_sig = f"{sig}|{today}"
    if st.session_state.today_signature == full_sig and not st.session_state.today_df.empty:
        return
    with st.spinner("Bugunun maclari yukleniyor..."):
        st.session_state.today_df = _load_today_games(
            st.session_state.league, st.session_state.season
        )
        st.session_state.today_signature = full_sig


def _refresh_today_games() -> None:
    st.session_state.today_signature = ""
    _ensure_today_games()


# -----------------------------------------------------------------------------
# Yardimcilar — Takim Formu (Gerçek Baseline) & Market (Odds)
# -----------------------------------------------------------------------------
def _compute_baselines() -> None:
    """
    Seçili maça özel gerçek form üretir:
      NBA  : son 10 maç ev/deplasman ayrımlı gerçek ortalama (olanak varsa)
      Euro : sezon fikstüründen takım bazlı ortalama
      falls: lig genelinde sezon ortalama (eski davranış)
    """
    match = st.session_state.selected_match
    league = st.session_state.league
    season = st.session_state.season
    hb = ab = 0.0
    source = "lig_ort"
    if match and match.get("home") and match.get("away"):
        hb, ab = df_lib.compute_team_form(
            match["home"], match["away"], league, season=season, lookback=10
        )
        if hb > 0 and ab > 0:
            source = "takim_formu"

    if hb <= 0 or ab <= 0:
        df = st.session_state.schedule_df
        hb2, ab2 = df_lib.compute_team_baselines(df, league)
        if hb2 > 0 and ab2 > 0:
            hb, ab = hb2, ab2

    st.session_state.home_baseline = float(hb)
    st.session_state.away_baseline = float(ab)
    st.session_state.baseline_avg = float(hb) + float(ab)
    st.session_state.baseline_source = source


def _force_schedule_reload() -> None:
    st.session_state.schedule_signature = ""


def _resolve_market_odds(match: dict[str, Any] | None) -> None:
    """Seçili maç için The Odds API'den gerçek baraj/fiyat çeker (opsiyonel)."""
    if not match or match.get("source") != "today":
        st.session_state.market_odds = None
        return
    home = match.get("home", "")
    away = match.get("away", "")
    if not home or not away:
        st.session_state.market_odds = None
        return
    league = st.session_state.league
    market = of_lib.best_totals_for_match(home, away, league)
    st.session_state.market_odds = market


def _market_line_for_prediction() -> float | None:
    """Tahmine geçirelecek gerçek/manuel baraj; yoksa None."""
    market = st.session_state.market_odds
    if market and market.get("consensus_line", 0) > 0:
        return float(market["consensus_line"])
    manual = st.session_state.market_manual or {}
    line = manual.get("line")
    if line and float(line) > 0:
        return float(line)
    return None


# -----------------------------------------------------------------------------
# Yardimcilar — Zaman Tuneli
# -----------------------------------------------------------------------------
def _fetch_team_quarters_for_row(row: pd.Series, league: str) -> dict[str, dict[int, float]]:
    """Schedule satırından takım-bazlı gerçek çeyrek structı alır."""
    try:
        if league == "NBA":
            gid = str(row.get("GAME_ID", ""))
            if gid:
                return df_lib.fetch_nba_quarters_by_team(gid)
        if league in ("EuroLeague", "EuroCup"):
            comp = "E" if league == "EuroLeague" else "U"
            season_code = str(row.get("SEASON_CODE", "") or "")
            game_code = int(row.get("GAME_CODE", 0) or 0)
            if season_code and game_code > 0:
                return df_lib.fetch_euroleague_quarters_by_team(
                    season_code=season_code, game_code=game_code, competition=comp
                )
    except Exception:
        pass
    return {"home": {}, "away": {}, "total": {}}


def _start_timeline(label: str, team_struct: dict[str, dict[int, float]]) -> None:
    cumulative = team_struct.get("total") or {}
    st.session_state.historical_label = label
    st.session_state.historical_team_quarters = team_struct
    st.session_state.historical_quarters = cumulative
    st.session_state.historical_scored_quarter = 0
    st.session_state.current_quarter = 1 if cumulative else 0
    st.session_state.historical_running = bool(cumulative)
    st.session_state.historical_mode = True
    st.session_state.dual_engine.reset_learning()


def _reset_engine() -> None:
    st.session_state.dual_engine.reset_learning()
    st.session_state.current_quarter = 0
    st.session_state.historical_scored_quarter = 0
    st.session_state.historical_running = False
    st.session_state.historical_quarters = {}
    st.session_state.historical_team_quarters = {}
    st.session_state.last_scoreboard = None


# -----------------------------------------------------------------------------
# Yardimcilar — Canli Skor Durumu
# -----------------------------------------------------------------------------
def _clock_to_minutes_remaining(clock: str, period_minutes: int) -> float | None:
    """gameClock 'PT11M58.00S' formatını kalan dakikaya çevirir."""
    s = (clock or "").strip()
    if not s or "final" in s.lower():
        return 0.0
    m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", s, flags=re.IGNORECASE)
    if m:
        mins = int(m.group(1) or 0)
        frac = float(m.group(2) or 0.0) / 60.0
        remaining = mins + frac
        return max(0.0, min(float(period_minutes), remaining))
    try:
        return float(s.rstrip("Ss"))
    except ValueError:
        return None


def _pull_nba_live_state() -> None:
    """NBA canlı maç seçiliyse gerçek skor/dakika çekip state'e yaz."""
    match = st.session_state.selected_match
    league = st.session_state.league
    if st.session_state.mod != "canli":
        return
    if match and match.get("source") == "today" and league == "NBA":
        gid = match.get("game_id", "")
        if not gid:
            return
        state = df_lib.fetch_nba_live_state(gid)
        st.session_state.live_state = state
        if state.get("home_score", 0) or state.get("away_score", 0):
            st.session_state.home_score = float(state.get("home_score", 0))
            st.session_state.away_score = float(state.get("away_score", 0))
        period = int(state.get("period") or 0)
        per_min = cfg.LEAGUE_PERIOD_MINUTES.get(league, 12)
        total_min = cfg.get_total_minutes(league)
        if state.get("finished"):
            st.session_state.current_minute = total_min
            st.session_state.final_real_total = (
                st.session_state.home_score + st.session_state.away_score
            )
        elif period >= 1:
            clock_rem = _clock_to_minutes_remaining(state.get("clock", ""), per_min)
            minutes_played = (period - 1) * per_min
            if clock_rem is not None:
                minutes_played += max(0.0, per_min - clock_rem)
            st.session_state.current_minute = min(total_min, max(0.0, minutes_played))
    elif match and match.get("source") == "today":
        # Euro: v2 API satırından skorlar zaten seçimle gelir
        pass


def _pull_euro_today_scores() -> None:
    """Euro bugünkü maç seçiliyse skoru state'e uygular."""
    if st.session_state.mod != "canli" or st.session_state.league == "NBA":
        return
    match = st.session_state.selected_match
    if not match or match.get("source") != "today":
        return
    df = st.session_state.today_df
    gid = match.get("game_id", "")
    row = None
    for r in df.itertuples():
        if str(r.GAME_CODE) == str(gid):
            row = r
            break
    if row is None:
        return
    st.session_state.home_score = float(row.EV_SKOR or 0)
    st.session_state.away_score = float(row.DEPLASMAN_SKOR or 0)
    st.session_state.total_minutes = cfg.get_total_minutes(st.session_state.league)
    if row.STATUS == "final":
        st.session_state.current_minute = st.session_state.total_minutes
        st.session_state.final_real_total = (
            st.session_state.home_score + st.session_state.away_score
        )
    # Canlı Euro'da saat yok: kullanici slider'da kalan dakikayi ayarlar


# -----------------------------------------------------------------------------
# Sidebar — Mod / Mac Secimi / Ayarlar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("GoldenBet Kontrol")

    _MODES = ["Canli Mac Takibi", "Zaman Tuneli (Backtest)"]
    _mod_label = st.radio(
        "Mod Secimi", _MODES, key="_sb_mod", index=0 if st.session_state.mod == "canli" else 1
    )
    st.session_state.mod = "canli" if "Canli" in _mod_label else "zaman_tuneli"

    st.divider()

    # --- Ortak Lig/Sezon Secimi ---
    _LEAGUES = ["NBA", "EuroLeague", "EuroCup"]
    league = st.selectbox(
        "Lig",
        _LEAGUES,
        index=_LEAGUES.index(st.session_state.league) if st.session_state.league in _LEAGUES else 0,
        key="_sb_league",
    )
    st.session_state.league = league

    if league == "NBA":
        _placeholder = "2024-25"
    elif league == "EuroLeague":
        _placeholder = "E2024"
    else:
        _placeholder = "U2024"
    season = st.text_input(
        "Sezon",
        value=st.session_state.season or _placeholder,
        placeholder=_placeholder,
        key="_sb_season",
    )
    st.session_state.season = season or _placeholder

    if league == "NBA":
        _TYPES = ["Regular Season", "Playoffs"]
        _type_idx = (
            _TYPES.index(st.session_state.season_type)
            if st.session_state.season_type in _TYPES
            else 0
        )
        st.selectbox(
            "Sezon Tipi",
            _TYPES,
            index=_type_idx,
            format_func=lambda x: "Regular Season" if x == "Regular Season" else "Playoffs",
            key="_sb_season_type",
        )
        st.session_state.season_type = st.session_state._sb_season_type
        if st.session_state.season_type == "Playoffs":
            st.session_state.context_tag = "Playoff_Elimination_G7"

    _ensure_schedule()

    if st.session_state.mod == "canli":
        # --- CANLI MOD: Bugunku maclar ---
        _ensure_today_games()
        st.button(
            "Maclari Yenile",
            key="_sb_refresh_today",
            on_click=_refresh_today_games,
            use_container_width=True,
        )
        today_options = _format_today_options(st.session_state.today_df, st.session_state.league)
        if today_options:
            today_idx = st.selectbox(
                "Bugunun Maclari",
                range(len(today_options)),
                format_func=lambda i: today_options[i],
                key="_sb_today_match",
            )
            st.session_state.selected_match = _extract_today_match(
                st.session_state.today_df, today_idx, st.session_state.league
            )
            if st.session_state.selected_match:
                _compute_baselines()
                _resolve_market_odds(st.session_state.selected_match)

                league_ = st.session_state.league
                if league_ == "NBA":
                    _pull_nba_live_state()
                else:
                    _pull_euro_today_scores()
                st.session_state.total_minutes = cfg.get_total_minutes(league_)

                m = st.session_state.selected_match
                if league_ == "NBA":
                    live = st.session_state.live_state
                    status_txt = live.get("status") or "planlanmadi"
                    if live.get("clock") and not live.get("finished"):
                        status_txt = f"canli {status_txt}"
                    st.caption(
                        f"Cikis: {status_txt}"
                        f"  |  Canli skor {st.session_state.home_score:.0f}"
                        f"-{st.session_state.away_score:.0f}"
                    )
                else:
                    df = st.session_state.today_df
                    row = None
                    for r in df.itertuples():
                        if str(r.GAME_CODE) == str(m.get("game_id", "")):
                            row = r
                            break
                    if row is not None:
                        st.caption(
                            f"Cikis: {row.STATUS}"
                            f"  |  Canli skor {row.EV_SKOR:.0f}-{row.DEPLASMAN_SKOR:.0f}"
                        )
        else:
            st.caption(
                "Bugun maclara rastlanmadi. 'Maclari Yenile' dene ya da "
                "sezonu kontrol et. (NBA verisi cdn.nba.com, Euro v2 API)"
            )
            st.session_state.selected_match = None

        st.divider()

        # --- Canli skor/kalan dakika ayarlari ---
        with st.expander("Canli Durum Ayar", expanded=False):
            league_ = st.session_state.league
            _tm = cfg.get_total_minutes(league_)
            st.session_state.total_minutes = _tm
            live_game = (st.session_state.selected_match or {}).get("source") == "today"
            nba_clock_known = (
                league_ == "NBA"
                and bool(st.session_state.live_state)
                and st.session_state.live_state.get("period", 0) >= 1
                and not st.session_state.live_state.get("finished")
            )
            if st.session_state.home_score or st.session_state.away_score:
                st.metric(
                    "Canli Skor",
                    f"{st.session_state.home_score:.0f} - {st.session_state.away_score:.0f}",
                )
            if nba_clock_known:
                _played = st.session_state.current_minute
                st.metric("Oynanan Dakika", f"{_played:.1f}")
            else:
                remaining_min = st.slider(
                    f"Kalan Dakika (0-{_tm})",
                    min_value=0,
                    max_value=_tm,
                    value=_tm - st.session_state.get("current_minute", _tm / 2),
                    key="_sb_minute",
                )
                st.session_state.current_minute = _tm - remaining_min

            st.button("Motoru Sifirla", key="_sb_reset", on_click=_reset_engine)
    else:
        # --- Zaman Tuneli: sezon discipline match ---
        match_options = _format_match_options(st.session_state.schedule_df, st.session_state.league)
        if match_options:
            match_label = st.selectbox("Eslesme", match_options, index=0, key="_sb_match")
            match_idx = match_options.index(match_label)
            st.session_state.selected_match = _extract_match(
                st.session_state.schedule_df, match_idx, st.session_state.league
            )
            _compute_baselines()

            row_tt = st.session_state.schedule_df.iloc[match_idx]
            team_struct = _fetch_team_quarters_for_row(row_tt, st.session_state.league)
            if team_struct.get("total"):
                st.caption(
                    f"Q1={team_struct['total'].get(1, 0):.0f}  "
                    f"Q2={team_struct['total'].get(2, 0):.0f}  "
                    f"Q3={team_struct['total'].get(3, 0):.0f}  "
                    f"Q4={team_struct['total'].get(4, 0):.0f}"
                )
                st.button(
                    "Zaman TUNELINI BASLAT",
                    type="primary",
                    use_container_width=True,
                    key="_sb_tt_start",
                    on_click=lambda: _start_timeline(match_label, team_struct),
                )
            else:
                st.caption("Bu macin ceyrek verisi yuklenemedi.")
        else:
            st.caption("Fikstur bos. Veri kaynagina ulasilamiyor olabilir.")
            st.session_state.selected_match = None

    st.divider()

    # --- Ayarlar (expander) ---
    with st.expander("Ayarlar", expanded=False):
        ctx_keys = list(cfg.CONTEXTUAL_MODIFIERS.keys())
        _default_ctx = st.session_state.context_tag
        if _default_ctx not in ctx_keys:
            _default_ctx = "Normal_Season_Match"
        _ctx_idx = ctx_keys.index(_default_ctx)
        context_tag = st.selectbox(
            "Mac Baglami",
            ctx_keys,
            index=_ctx_idx,
            format_func=lambda k: (
                f"{cfg.CONTEXTUAL_MODIFIERS[k]['emoji']} {cfg.CONTEXTUAL_MODIFIERS[k]['label']}"
            ),
            key="_sb_ctx",
        )
        st.session_state.context_tag = context_tag

        # Manuel market fallback (Bugunku maclar odaklı!)
        st.caption("Gerçek piyasa verilisi (The Odds API) kullanılır; elede yoksa bu alanlar.")
        _manual_line = st.number_input(
            "Piyasa Baraji (manuel)",
            min_value=0.0,
            max_value=500.0,
            value=float(st.session_state.market_manual.get("line", 0)),
            step=0.5,
            key="_sb_manual_line",
        )
        _manual_over = st.number_input(
            "Over Orani (ondalik)",
            min_value=1.01,
            max_value=3.0,
            value=float(st.session_state.market_manual.get("odds_over", 1.91)),
            step=0.01,
            key="_sb_manual_over",
        )
        _manual_under = st.number_input(
            "Under Orani (ondalik)",
            min_value=1.01,
            max_value=3.0,
            value=float(st.session_state.market_manual.get("odds_under", 1.91)),
            step=0.01,
            key="_sb_manual_under",
        )
        st.session_state.market_manual = {
            "line": float(_manual_line) if _manual_line > 0 else None,
            "odds_over": float(_manual_over),
            "odds_under": float(_manual_under),
        }

        # --- Fikstür Topolojisi (TopologyAware katman) ---
        st.markdown("**Fikstür Topolojisi**")
        _tp = st.session_state.setdefault(
            "topology_inputs",
            {
                "is_b2b_home": False,
                "is_b2b_away": False,
                "prev_match_was_ot": False,
                "next_match_importance": "normal",
                "loss_tolerability": "low",
                "rotation_active": False,
                "home_in_bonus": False,
                "away_in_bonus": False,
            },
        )
        tcol1, tcol2 = st.columns(2)
        with tcol1:
            _tp["is_b2b_home"] = st.checkbox("Ev: B2B (ertesi gün maç)", key="_tp_b2b_h")
            _tp["prev_match_was_ot"] = st.checkbox("Önceki maç uzatmaya gitti", key="_tp_ot")
            _tp["home_in_bonus"] = st.checkbox("Ev: Faul bonusunda", key="_tp_bonus_h")
            _tp["away_in_bonus"] = st.checkbox("Dep: Faul bonusunda", key="_tp_bonus_a")
        with tcol2:
            _tp["is_b2b_away"] = st.checkbox("Dep: B2B (ertesi gün maç)", key="_tp_b2b_a")
            _tp["next_match_importance"] = st.selectbox(
                "Sonraki maç önemi", ["low", "normal", "critical"], key="_tp_next_impo"
            )
            _tp["loss_tolerability"] = st.selectbox(
                "Kaybetme toleransı", ["low", "high"], key="_tp_toler"
            )
            _tp["rotation_active"] = st.checkbox("Geniş rotasyon aktif", key="_tp_rot")
        st.session_state.topology_inputs = _tp

    st.divider()

    # --- Bahis Stratejisi ---
    _bet_strategy = bui.render_strategy_selector()
    bui.render_strategy_info(_bet_strategy)
    _bet_config = bui.render_betting_config(_bet_strategy)


# -----------------------------------------------------------------------------
# KATMAN 1: Mac Kimligi & Kural Matrisi (collapsed expander)
# -----------------------------------------------------------------------------
_match_label = (
    st.session_state.selected_match["label"]
    if st.session_state.selected_match
    else (st.session_state.historical_label or "-")
)

st.title("GoldenBet AI  Skor Tahmin Merkezi")

with st.expander("MAC KIMLIGI & KURAL MATRISI", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        op_mode = "Canli Mac" if st.session_state.mod == "canli" else "Zaman Tuneli"
        st.metric("Operasyon Modu", op_mode)
    with c2:
        st.metric("Lig & Sezon", f"{st.session_state.league}  {st.session_state.season}")
    with c3:
        st.metric(
            "Mac Turu",
            st.session_state.season_type if st.session_state.league == "NBA" else "Sezon",
        )
    with c4:
        _per = cfg.LEAGUE_PERIODS.get(st.session_state.league, 4)
        _pmin = cfg.LEAGUE_PERIOD_MINUTES.get(st.session_state.league, 10)
        st.metric("Periyot", f"{_per}x{_pmin} dk")
    _src_label = {"takim_formu": "Son 10 mac formu", "lig_ort": "Lig geneli"}.get(
        st.session_state.baseline_source, "Lig geneli"
    )
    st.caption(
        f"Eslesme: {_match_label}  |  "
        f"Baseline: Ev {st.session_state.home_baseline:.1f} - "
        f"Dep {st.session_state.away_baseline:.1f} (Toplam {st.session_state.baseline_avg:.1f}) "
        f"[{_src_label}]  |  "
        f"Lig Varyans x{cfg.get_league_variance(st.session_state.league):.2f}  |  "
        f"Lig Tempo x{cfg.get_league_pace(st.session_state.league):.2f}"
    )

st.divider()


# -----------------------------------------------------------------------------
# Tahmin Uretimi (Canli / Zaman Tuneli)
# -----------------------------------------------------------------------------
scoreboard: dict[str, Any] | None = None
context_tag = st.session_state.context_tag
ctx_meta = cfg.CONTEXTUAL_MODIFIERS[context_tag]

# Canli mod: bugunku mac aktifse reaktif tahmin
if (
    st.session_state.mod == "canli"
    and not st.session_state.historical_running
    and st.session_state.baseline_avg > 0
):
    market_line = _market_line_for_prediction()
    _topo = st.session_state.topology_inputs
    scoreboard = st.session_state.dual_engine.predict_match_scoreboard(
        current_home=float(st.session_state.home_score),
        current_away=float(st.session_state.away_score),
        current_minute=float(st.session_state.current_minute),
        baseline_home_avg=float(st.session_state.home_baseline),
        baseline_away_avg=float(st.session_state.away_baseline),
        total_minutes=int(st.session_state.total_minutes),
        context_tag=context_tag,
        league=st.session_state.league,
        market_line=market_line,
        is_b2b_home=_topo["is_b2b_home"],
        is_b2b_away=_topo["is_b2b_away"],
        prev_match_was_ot=_topo["prev_match_was_ot"],
        next_match_importance=_topo["next_match_importance"],
        loss_tolerability=_topo["loss_tolerability"],
        rotation_active=_topo["rotation_active"],
        home_in_bonus=_topo["home_in_bonus"],
        away_in_bonus=_topo["away_in_bonus"],
    )
    st.session_state.last_scoreboard = scoreboard

# Zaman Tuneli: quarter-by-quarter (gerçek takım kırılımları)
elif (
    st.session_state.mod == "zaman_tuneli"
    and st.session_state.historical_running
    and st.session_state.historical_quarters
):
    tqs: dict[str, dict[int, float]] = st.session_state.historical_team_quarters or {}
    cumulative = st.session_state.historical_quarters
    q_now = st.session_state.current_quarter
    _tm = int(st.session_state.total_minutes)
    per_q_minutes = _tm // 4
    hs, as_ = tqs.get("home") or {}, tqs.get("away") or {}

    if 0 < q_now <= 4 and q_now in cumulative:
        engine_obj: eng.DualTeamScoreEngine = st.session_state.dual_engine

        # Gerçek kümülatif değerler
        prev_cum_total = cumulative.get(q_now - 1, 0.0)
        cur_cum_total = cumulative[q_now]
        act_total_q = cur_cum_total - prev_cum_total

        cum_home_prev = float(hs.get(q_now - 1, 0.0) or 0.0)
        cum_away_prev = float(as_.get(q_now - 1, 0.0) or 0.0)
        cum_home_now = float(hs.get(q_now, 0.0) or 0.0)
        cum_away_now = float(as_.get(q_now, 0.0) or 0.0)
        if hs and as_:
            act_home_q = cum_home_now - cum_home_prev
            act_away_q = cum_away_now - cum_away_prev
        else:
            act_home_q = act_total_q * 0.5
            act_away_q = act_total_q * 0.5

        # Maç başından q_now başına kadar: gerçek parçalı skor + kalan dakika
        minute_at_q_start = per_q_minutes * (q_now - 1)
        _topo = st.session_state.topology_inputs
        result = engine_obj.predict_match_scoreboard(
            current_home=cum_home_prev,
            current_away=cum_away_prev,
            current_minute=minute_at_q_start,
            baseline_home_avg=float(st.session_state.home_baseline) or 110.0,
            baseline_away_avg=float(st.session_state.away_baseline) or 105.0,
            total_minutes=per_q_minutes * 4,
            context_tag=context_tag,
            league=st.session_state.league,
            is_b2b_home=_topo["is_b2b_home"],
            is_b2b_away=_topo["is_b2b_away"],
            prev_match_was_ot=_topo["prev_match_was_ot"],
            next_match_importance=_topo["next_match_importance"],
            loss_tolerability=_topo["loss_tolerability"],
            rotation_active=_topo["rotation_active"],
            home_in_bonus=_topo["home_in_bonus"],
            away_in_bonus=_topo["away_in_bonus"],
        )
        pred_home = result["home_predicted"]
        pred_away = result["away_predicted"]

        # Bu ceyrek tahmininin artisi:
        pred_home_q = pred_home - cum_home_prev
        pred_away_q = pred_away - cum_away_prev

        # Ceyrek gerceklesince bilgileri once kez isle
        if st.session_state.historical_scored_quarter < q_now:
            engine_obj.update_team_weights(
                quarter=q_now,
                pred_home=pred_home_q,
                actual_home=act_home_q,
                pred_away=pred_away_q,
                actual_away=act_away_q,
            )
            st.session_state.historical_scored_quarter = q_now
        scoreboard = result
        st.session_state.last_scoreboard = result

# --- Zaman Tuneli Kontrolleri (her zaman erisilebilir) ---
if (
    st.session_state.mod == "zaman_tuneli"
    and st.session_state.historical_running
    and st.session_state.historical_quarters
):
    q_now = st.session_state.current_quarter
    quarters = st.session_state.historical_quarters
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("ADIM AT", key="_tt_step", use_container_width=True) and q_now < 4:
            st.session_state.current_quarter = q_now + 1
    with c2:
        auto = st.checkbox("OTO (1.2s)", key="_tt_auto", value=False)
    with c3:
        st.progress(min(q_now / 4.0, 1.0), text=f"Ceyrek {q_now}/4 tamamlandi")

    if 0 < q_now <= 4 and q_now in quarters:
        cur_cum = quarters[q_now]
        hs = (st.session_state.historical_team_quarters or {}).get("home") or {}
        as_ = (st.session_state.historical_team_quarters or {}).get("away") or {}
        extra = ""
        if hs and as_:
            extra = f"  |  Gercek Ev {hs.get(q_now, 0):.0f}-Dep {as_.get(q_now, 0):.0f}"
        st.caption(
            f"Q{q_now} kumulatif: {cur_cum:.1f}  |  "
            f"Bias Ev: {st.session_state.dual_engine.bias_home:+.3f}  |  "
            f"Bias Dep: {st.session_state.dual_engine.bias_away:+.3f}  |  "
            f"MAE: {st.session_state.dual_engine.current_mae():.2f}"
            f"{extra}"
        )

    if auto and q_now < 4:
        time.sleep(1.2)
        st.session_state.current_quarter = q_now + 1
        st.rerun()
    if q_now >= 4:
        st.success("Mac tamamlandi. Model kalibre edildi.")

# --- Canli mod otomatik yenileme (20 sn) ---
_auto_refresh_active = (
    st.session_state.mod == "canli"
    and bool(st.session_state.today_df is not None and not st.session_state.today_df.empty)
    and (st.session_state.selected_match or {}).get("source") == "today"
)
if _auto_refresh_active:
    with st.sidebar:
        _poll_on = st.toggle("Canli Polling Ac (20 sn)", key="_sb_poll_on", value=False)
else:
    _poll_on = False
if _poll_on:
    time.sleep(20)
    st.rerun()


# -----------------------------------------------------------------------------
# KATMAN 2: Dev Dijital Skor Tabelasi
# -----------------------------------------------------------------------------
if scoreboard is not None:
    hp = scoreboard["home_predicted"]
    ap = scoreboard["away_predicted"]
    tp = scoreboard["total_predicted"]
    total_p10 = scoreboard.get("total_p10", 0)
    total_p90 = scoreboard.get("total_p90", 0)
    ctx_label = scoreboard.get("context_tag", "")
    ctx_emoji = scoreboard.get("context_emoji", "")

    live_state = st.session_state.live_state or {}
    _status_bits = ""
    if live_state.get("clock"):
        _status_bits = f"  |  {live_state['period']}. Periyot {live_state['clock']}"
    _topo = scoreboard.get("topology") or {}
    _topo_bits = ""
    if _topo and (_topo.get("fatigue_home", 1.0) != 1.0 or _topo.get("bonus_home", 1.0) != 1.0):
        _topo_bits = (
            f"&nbsp;|&nbsp; B2B×{_topo.get('fatigue_home', 1):.2f}/{_topo.get('fatigue_away', 1):.2f}"
            f" | Efor {_topo.get('effort_home', 1):.2f}"
            f" | Bonus {_topo.get('bonus_home', 1):.2f}/{_topo.get('bonus_away', 1):.2f}"
        )
    st.markdown(
        f"""
    <div class="scoreboard">
        <div class="score-side">
            <div class="team-name">{(st.session_state.selected_match or {}).get("home", "EV") if st.session_state.selected_match else "EV"}</div>
            <div class="score-number">{hp:.0f}</div>
        </div>
        <div class="score-dash">-</div>
        <div class="score-side">
            <div class="team-name">{(st.session_state.selected_match or {}).get("away", "DEP") if st.session_state.selected_match else "DEP"}</div>
            <div class="score-number">{ap:.0f}</div>
        </div>
    </div>
    <div class="scoreboard-sub">
        Toplam Projeksiyon: <b>{tp:.1f}</b>
        &nbsp;|&nbsp; Guven Araligi: p10={total_p10:.0f} - p90={total_p90:.0f}
        &nbsp;|&nbsp; {ctx_emoji} {ctx_label}
        <br>
        Bias Ev {scoreboard.get("bias_home", 0):+.2f}
        &nbsp;|&nbsp; Bias Dep {scoreboard.get("bias_away", 0):+.2f}
        {_topo_bits}
        {_status_bits}
    </div>
    """,
        unsafe_allow_html=True,
    )
else:
    # Bos durum: hicbir statik uyari kutusu gosterme
    pass

st.divider()


# -----------------------------------------------------------------------------
# KATMAN 3: 5 Ceyrek Karti (Q1, Q2, 1H, Q3, Q4)
# -----------------------------------------------------------------------------
if scoreboard is not None:
    q1, q2, h1, q3, q4 = st.columns(5)

    def _quarter_card(col, label, h_score, a_score, is_half=False):
        extra = " class='q-card half'" if is_half else " class='q-card'"
        with col:
            st.markdown(
                f"""
            <div{extra}>
                <div class="q-label">{label}</div>
                <div class="q-score">{h_score:.0f} - {a_score:.0f}</div>
                <div class="q-total">S {h_score + a_score:.0f}</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

    _quarter_card(q1, "1. Ceyrek", scoreboard["q1_home"], scoreboard["q1_away"])
    _quarter_card(q2, "2. Ceyrek", scoreboard["q2_home"], scoreboard["q2_away"])
    _quarter_card(h1, "ILK YARI", scoreboard["home_h1"], scoreboard["away_h1"], is_half=True)
    _quarter_card(q3, "3. Ceyrek", scoreboard["q3_home"], scoreboard["q3_away"])
    _quarter_card(q4, "4. Ceyrek", scoreboard["q4_home"], scoreboard["q4_away"])
else:
    st.caption("Fikstur yuklendiginde skor tahminleri burada goruntulenecek.")

st.divider()


# -----------------------------------------------------------------------------
# KATMAN 3.5: Gerçek Piyasa Paneli (The Odds API)
# -----------------------------------------------------------------------------
market = st.session_state.market_odds
if st.session_state.mod == "canli" and scoreboard is not None:
    st.subheader("Gerçek Piyasa Paneli (The Odds API)")
    if market and market.get("consensus_line", 0) > 0:
        mc = st.columns(4)
        with mc[0]:
            st.metric("Konsensus Baraj", f"{market['consensus_line']:.1f}")
        with mc[1]:
            st.metric("Best Over", f"{market['best_over_price']:.2f}")
        with mc[2]:
            st.metric("Best Under", f"{market['best_under_price']:.2f}")
        with mc[3]:
            st.metric("Kitapler", str(market.get("books_count", 0)))
        prob_over = scoreboard.get("prob_over_market")
        if prob_over is not None:
            ev_over = prob_over * float(market["best_over_price"]) - 1.0
            ev_under = (1.0 - prob_over) * float(market["best_under_price"]) - 1.0
            cls_over = "odds-ev-pos" if ev_over >= 0 else "odds-ev-neg"
            cls_under = "odds-ev-pos" if ev_under >= 0 else "odds-ev-neg"
            quota = (market.get("quota") or {}).get("requests_remaining")
            st.markdown(
                f"""
                <span class="odds-chip">Model-ÜST: <b>{prob_over * 100:.1f}%</b></span>
                <span class="odds-chip">EV(ÜST): <span class="{cls_over}">{ev_over * 100:+.1f}%</span></span>
                <span class="odds-chip">EV(ALT): <span class="{cls_under}">{ev_under * 100:+.1f}%</span></span>
                <span class="odds-chip">En iyi kitaplar: U {market["best_over_book"]} / A {market["best_under_book"]}</span>
                <span class="odds-chip">Kalan API kredi: {quota if quota else "?"}</span>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.caption("Baraj manuelken Model-vs-Line olasılığı için baraj girmelisiniz.")
    else:
        st.caption(
            "Gerçek odds gelmedi (anahtar yok ya da maç listede değil). "
            "Ayarlar → manuel baraj/oran girilebilir."
        )
    st.divider()


# -----------------------------------------------------------------------------
# Ogrenme Monitoru (MAE grafigi + Bias/Variance)
# -----------------------------------------------------------------------------
hist_df = st.session_state.dual_engine.history_dataframe()

st.subheader("Yapay Zeka Canli Evrim Grafigi (Self-Learning)")

if hist_df is not None and not hist_df.empty:
    col_g1, col_g2 = st.columns([3, 1])
    with col_g1:
        st.markdown('<div class="mae-card">', unsafe_allow_html=True)
        st.markdown("##### MAE Yakinamasi")
        st.line_chart(hist_df.set_index("Ceyrek")[["Hata_Home", "Hata_Away", "MAE"]], height=200)
        st.markdown("</div>", unsafe_allow_html=True)
    with col_g2:
        st.markdown('<div class="mae-card">', unsafe_allow_html=True)
        st.metric(
            "Bias Ev",
            f"{st.session_state.dual_engine.bias_home:+.3f}",
            help="Ev sahibi icin ogrenilmis sapma",
        )
        st.metric(
            "Bias Dep",
            f"{st.session_state.dual_engine.bias_away:+.3f}",
            help="Deplasman icin ogrenilmis sapma",
        )
        st.metric(
            "Var Ev",
            f"{st.session_state.dual_engine.variance_modifier_home:.3f}",
            help="Ev sahibi oynaklik katsayisi",
        )
        st.metric(
            "Var Dep",
            f"{st.session_state.dual_engine.variance_modifier_away:.3f}",
            help="Deplasman oynaklik katsayisi",
        )
        st.metric("Mevcut MAE", f"{st.session_state.dual_engine.current_mae():.2f}")
        st.markdown("</div>", unsafe_allow_html=True)
else:
    st.caption("Henuz ogrenme verisi yok. Canli modda tahmin uretin veya Zaman Tunelini baslatin.")

st.divider()

# -----------------------------------------------------------------------------
# KATMAN 4: Bahis Simulatoru Dashboard
# -----------------------------------------------------------------------------
if scoreboard is not None and st.session_state.baseline_avg > 0:
    pred = dict(scoreboard)
    match = st.session_state.selected_match
    if match:
        pred["home_name"] = match.get("home", "")
        pred["away_name"] = match.get("away", "")
        pred["game_id"] = match.get("game_id", "")
    market = st.session_state.market_odds
    if market and market.get("consensus_line", 0) > 0:
        pred["market_total"] = float(market["consensus_line"])
        pred["odds_over"] = float(market.get("best_over_price", 0) or 0)
        pred["odds_under"] = float(market.get("best_under_price", 0) or 0)
    manual = st.session_state.market_manual or {}
    if manual.get("line") and "market_total" not in pred:
        pred["market_total"] = float(manual["line"])
        pred.setdefault("odds_over", manual.get("odds_over", 1.91))
        pred.setdefault("odds_under", manual.get("odds_under", 1.91))

    _pred_list = [pred]
    _actual_list: list = []

    if st.session_state.mod == "zaman_tuneli" and st.session_state.historical_quarters:
        final_total = max(st.session_state.historical_quarters.values())
        _actual_list = [{"total": final_total}]
    elif st.session_state.mod == "canli" and st.session_state.get("final_real_total", 0) > 0:
        _actual_list = [{"total": st.session_state.final_real_total}]

    bui.render_betting_tab(_pred_list, _actual_list)
else:
    st.caption("Bahis simulasyonu icin once mac secimi yapin ve tahmin olusturun.")
