"""
GoldenBet AI - Patron Komut Paneli
==================================

3-katmanli minimalist UI:
  1) Akordeon: Mac Kimligi & Kural Matrisi
  2) Dev Dijital Skor Tabelasi (Ev - Dep)
  3) 5 kart: Q1, Q2, 1H (vurgulu), Q3, Q4
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

import config as cfg
import data_fetcher as df_lib
import engine as eng


# -----------------------------------------------------------------------------
# Sayfa Konfigurasyonu
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="GoldenBet AI · Skor Tahmin Merkezi",
    layout="wide",
    initial_sidebar_state="expanded",
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
    if "context_tag" not in st.session_state:
        st.session_state.context_tag = "Normal_Season_Match"
    if "last_scoreboard" not in st.session_state:
        st.session_state.last_scoreboard = None
    if "historical_mode" not in st.session_state:
        st.session_state.historical_mode = False
    if "historical_quarters" not in st.session_state:
        st.session_state.historical_quarters = {}
    if "historical_label" not in st.session_state:
        st.session_state.historical_label = ""
    if "current_quarter" not in st.session_state:
        st.session_state.current_quarter = 0
    if "historical_running" not in st.session_state:
        st.session_state.historical_running = False


_init_state()


# -----------------------------------------------------------------------------
# Yardimcilar — Fikstur Yukleme & Eslesme Listesi
# -----------------------------------------------------------------------------
def _load_schedule(league: str, season: str, season_type: str) -> pd.DataFrame:
    if league == "NBA":
        return df_lib.fetch_nba_season_schedule(
            season=season, season_type=season_type
        )
    if league == "EuroLeague":
        return df_lib.fetch_euroleague_data(season_code=season, competition="E")
    if league == "EuroCup":
        return df_lib.fetch_euroleague_data(season_code=season, competition="U")
    return pd.DataFrame()


def _format_match_options(df: pd.DataFrame, league: str) -> list[str]:
    if df is None or df.empty:
        return []
    if league == "NBA":
        return [
            f"{row.HOME} vs {row.AWAY} - "
            f"{pd.to_datetime(row.GAME_DATE).strftime('%Y-%m-%d')}"
            for row in df.itertuples()
        ]
    return [
        f"{row.EV_SAHIBI} vs {row.DEPLASMAN} - Round {int(row.HAFTA)}"
        for row in df.itertuples()
    ]


def _extract_match(df: pd.DataFrame, idx: int, league: str) -> Optional[Dict[str, Any]]:
    if df is None or df.empty or idx is None or idx < 0 or idx >= len(df):
        return None
    row = df.iloc[idx]
    if league == "NBA":
        return {
            "home": str(row.get("HOME", "")),
            "away": str(row.get("AWAY", "")),
            "date": pd.to_datetime(row.get("GAME_DATE"), errors="coerce"),
            "label": f"{row.get('HOME','')} vs {row.get('AWAY','')}",
        }
    return {
        "home": str(row.get("EV_SAHIBI", "")),
        "away": str(row.get("DEPLASMAN", "")),
        "round": int(row.get("HAFTA", 0) or 0),
        "label": f"{row.get('EV_SAHIBI','')} vs {row.get('DEPLASMAN','')}",
    }


def _ensure_schedule() -> None:
    sig = (
        f"{st.session_state.league}|"
        f"{st.session_state.season}|"
        f"{st.session_state.season_type}"
    )
    if st.session_state.schedule_signature == sig and not st.session_state.schedule_df.empty:
        return
    with st.spinner("Fikstur yukleniyor..."):
        st.session_state.schedule_df = _load_schedule(
            st.session_state.league,
            st.session_state.season,
            st.session_state.season_type,
        )
        st.session_state.schedule_signature = sig
        st.session_state.selected_match = None
        st.session_state.baseline_avg = 0.0
        st.session_state.home_baseline = 0.0
        st.session_state.away_baseline = 0.0


def _compute_baselines() -> None:
    """Schedule'dan Ev/Dep baselinelarini hesaplar."""
    df = st.session_state.schedule_df
    if df is not None and not df.empty:
        hb, ab = df_lib.compute_team_baselines(df, st.session_state.league)
        st.session_state.home_baseline = hb
        st.session_state.away_baseline = ab
        st.session_state.baseline_avg = hb + ab


def _force_schedule_reload() -> None:
    st.session_state.schedule_signature = ""


def _start_timeline(label: str, quarters: Dict[int, float]) -> None:
    st.session_state.historical_label = label
    st.session_state.historical_quarters = quarters
    st.session_state.current_quarter = 0
    st.session_state.historical_running = True
    st.session_state.historical_mode = True
    st.session_state.dual_engine.reset_learning()


def _reset_engine() -> None:
    st.session_state.dual_engine.reset_learning()
    st.session_state.current_quarter = 0
    st.session_state.historical_running = False
    st.session_state.historical_quarters = {}
    st.session_state.last_scoreboard = None


def _refresh_prediction() -> None:
    """Force a re-run of the prediction for reactive updates."""
    pass  # streamlit handles reactivity automatically


# -----------------------------------------------------------------------------
# Sidebar — Mod / Mac Secimi / Ayarlar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("GoldenBet Kontrol")

    _MODES = ["Canli Mac Takibi", "Zaman Tuneli (Backtest)"]
    _mod_label = st.radio("Mod Secimi", _MODES, key="_sb_mod",
                          index=0 if st.session_state.mod == "canli" else 1)
    st.session_state.mod = "canli" if "Canli" in _mod_label else "zaman_tuneli"

    st.divider()

    # --- Ortak Mac Secimi ---
    _LEAGUES = ["NBA", "EuroLeague", "EuroCup"]
    league = st.selectbox(
        "Lig", _LEAGUES,
        index=_LEAGUES.index(st.session_state.league)
        if st.session_state.league in _LEAGUES else 0,
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
        "Sezon", value=st.session_state.season or _placeholder,
        placeholder=_placeholder, key="_sb_season",
    )
    st.session_state.season = season or _placeholder

    if league == "NBA":
        _TYPES = ["Regular Season", "Playoffs"]
        _type_idx = _TYPES.index(st.session_state.season_type) \
            if st.session_state.season_type in _TYPES else 0
        st.selectbox("Sezon Tipi", _TYPES, index=_type_idx,
                     format_func=lambda x: "Regular Season" if x == "Regular Season" else "Playoffs",
                     key="_sb_season_type")
        st.session_state.season_type = st.session_state._sb_season_type
        if st.session_state.season_type == "Playoffs":
            st.session_state.context_tag = "Playoff_Elimination_G7"

    _ensure_schedule()

    match_options = _format_match_options(
        st.session_state.schedule_df, st.session_state.league
    )
    if match_options:
        match_label = st.selectbox("Eslesme", match_options, index=0, key="_sb_match")
        match_idx = match_options.index(match_label)
        st.session_state.selected_match = _extract_match(
            st.session_state.schedule_df, match_idx, st.session_state.league
        )
        if st.session_state.baseline_avg <= 0:
            _compute_baselines()
    else:
        st.caption("Fikstur bos. Veri kaynagina ulasilamiyor olabilir.")
        st.session_state.selected_match = None

    st.divider()

    # --- Mod-spesifik aksiyon ---
    if st.session_state.mod == "canli":
        st.button("Fiksturu Yenile", key="_sb_refresh",
                  on_click=_force_schedule_reload)
    else:
        if not st.session_state.schedule_df.empty and match_options:
            row_tt = st.session_state.schedule_df.iloc[match_idx]
            quarters_preview = df_lib.fetch_quarters_for_schedule_row(
                row_tt, st.session_state.league
            )
            if quarters_preview:
                st.caption(
                    f"Q1={quarters_preview.get(1,0):.0f}  "
                    f"Q2={quarters_preview.get(2,0):.0f}  "
                    f"Q3={quarters_preview.get(3,0):.0f}  "
                    f"Q4={quarters_preview.get(4,0):.0f}"
                )
            else:
                st.caption("Bu macin ceyrek verisi yuklenemedi.")

            st.button("Zaman TUNELINI BASLAT", type="primary",
                      use_container_width=True, key="_sb_tt_start",
                      disabled=not bool(quarters_preview),
                      on_click=lambda: _start_timeline(match_label, quarters_preview))
        else:
            st.caption("Fikstur bos.")

    st.divider()

    # --- Ayarlar (expander) ---
    with st.expander("Ayarlar", expanded=False):
        if st.session_state.mod == "canli":
            col_h, col_a = st.columns(2)
            with col_h:
                home_score = st.number_input(
                    "Ev Skoru", min_value=0, max_value=200,
                    value=int(st.session_state.home_score), step=1,
                    key="_sb_home_score",
                )
                st.session_state.home_score = home_score
            with col_a:
                away_score = st.number_input(
                    "Dep Skoru", min_value=0, max_value=200,
                    value=int(st.session_state.away_score), step=1,
                    key="_sb_away_score",
                )
                st.session_state.away_score = away_score

            _tm = cfg.get_total_minutes(st.session_state.league)
            st.session_state.total_minutes = _tm
            remaining_min = st.slider(
                f"Kalan Dakika (0-{_tm})",
                min_value=0, max_value=_tm,
                value=_tm - st.session_state.get("current_minute", _tm // 2),
                key="_sb_minute",
            )
            st.session_state.current_minute = _tm - remaining_min
        else:
            _tm = cfg.get_total_minutes(st.session_state.league)
            st.session_state.total_minutes = _tm
            st.session_state.current_minute = st.session_state.get(
                "current_minute", _tm // 2
            )

        ctx_keys = list(cfg.CONTEXTUAL_MODIFIERS.keys())
        _default_ctx = st.session_state.context_tag
        if _default_ctx not in ctx_keys:
            _default_ctx = "Normal_Season_Match"
        _ctx_idx = ctx_keys.index(_default_ctx)
        context_tag = st.selectbox(
            "Mac Baglami", ctx_keys, index=_ctx_idx,
            format_func=lambda k: f"{cfg.CONTEXTUAL_MODIFIERS[k]['emoji']} "
                                  f"{cfg.CONTEXTUAL_MODIFIERS[k]['label']}",
            key="_sb_ctx",
        )
        st.session_state.context_tag = context_tag

        st.button("Motoru Sifirla", key="_sb_reset", on_click=_reset_engine)


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
        st.metric("Lig & Sezon",
                  f"{st.session_state.league}  {st.session_state.season}")
    with c3:
        st.metric("Mac Turu",
                  st.session_state.season_type if st.session_state.league == "NBA" else "Sezon")
    with c4:
        _per = cfg.LEAGUE_PERIODS.get(st.session_state.league, 4)
        _pmin = cfg.LEAGUE_PERIOD_MINUTES.get(st.session_state.league, 10)
        st.metric("Periyot", f"{_per}x{_pmin} dk")
    st.caption(
        f"Eslesme: {_match_label}  |  "
        f"Baseline: Ev {st.session_state.home_baseline:.1f} - "
        f"Dep {st.session_state.away_baseline:.1f} (Toplam {st.session_state.baseline_avg:.1f})  |  "
        f"Lig Varyans x{cfg.get_league_variance(st.session_state.league):.2f}  |  "
        f"Lig Tempo x{cfg.get_league_pace(st.session_state.league):.2f}"
    )

st.divider()


# -----------------------------------------------------------------------------
# Tahmin Uretimi (Canli / Zaman Tuneli)
# -----------------------------------------------------------------------------
scoreboard: Optional[Dict[str, Any]] = None
context_tag = st.session_state.context_tag
ctx_meta = cfg.CONTEXTUAL_MODIFIERS[context_tag]

# Canli mod: reactive
if (st.session_state.mod == "canli"
        and not st.session_state.historical_running
        and st.session_state.baseline_avg > 0):
    scoreboard = st.session_state.dual_engine.predict_match_scoreboard(
        current_home=float(st.session_state.home_score),
        current_away=float(st.session_state.away_score),
        current_minute=float(st.session_state.current_minute),
        baseline_home_avg=float(st.session_state.home_baseline),
        baseline_away_avg=float(st.session_state.away_baseline),
        total_minutes=int(st.session_state.total_minutes),
        context_tag=context_tag,
        league=st.session_state.league,
    )
    st.session_state.last_scoreboard = scoreboard

# Zaman Tuneli: quarter-by-quarter
elif (st.session_state.mod == "zaman_tuneli"
      and st.session_state.historical_running
      and st.session_state.historical_quarters):
    quarters = st.session_state.historical_quarters
    q_now = st.session_state.current_quarter
    _tm = int(st.session_state.total_minutes)
    per_q_minutes = _tm // 4

    if 0 < q_now <= 4 and q_now in quarters:
        prev_cum = quarters.get(q_now - 1, 0.0)
        cur_cum = quarters[q_now]
        minute_at_q_end = per_q_minutes * q_now

        # Bu ceyregin home/away skorunu tahmin et
        # (kumulatiften ceyrek skoru cikar)
        q_home = cur_cum * 0.5   # yaklasik: kumulatifin yarisi ev
        q_away = cur_cum * 0.5

        engine_obj: eng.DualTeamScoreEngine = st.session_state.dual_engine
        result = engine_obj.predict_match_scoreboard(
            current_home=0, current_away=0,
            current_minute=minute_at_q_end - per_q_minutes,
            baseline_home_avg=float(st.session_state.home_baseline) or 110.0,
            baseline_away_avg=float(st.session_state.away_baseline) or 105.0,
            total_minutes=per_q_minutes,
            context_tag=context_tag,
            league=st.session_state.league,
        )
        pred_home = result["home_predicted"]
        pred_away = result["away_predicted"]

        engine_obj.update_team_weights(
            quarter=q_now,
            pred_home=pred_home,
            actual_home=q_home,
            pred_away=pred_away,
            actual_away=q_away,
        )
        scoreboard = result
        st.session_state.last_scoreboard = result

# --- Zaman Tuneli Kontrolleri (her zaman erisilebilir) ---
if (st.session_state.mod == "zaman_tuneli"
        and st.session_state.historical_running
        and st.session_state.historical_quarters):
    q_now = st.session_state.current_quarter
    quarters = st.session_state.historical_quarters
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("ADIM AT", key="_tt_step", use_container_width=True):
            if q_now < 4:
                st.session_state.current_quarter = q_now + 1
    with c2:
        auto = st.checkbox("OTO (1.2s)", key="_tt_auto", value=False)
    with c3:
        st.progress(min(q_now / 4.0, 1.0),
                    text=f"Ceyrek {q_now}/4 tamamlandi")

    if 0 < q_now <= 4 and q_now in quarters:
        cur_cum = quarters[q_now]
        st.caption(
            f"Q{q_now} kumulatif: {cur_cum:.1f}  |  "
            f"Bias Ev: {st.session_state.dual_engine.bias_home:+.3f}  |  "
            f"Bias Dep: {st.session_state.dual_engine.bias_away:+.3f}  |  "
            f"MAE: {st.session_state.dual_engine.current_mae():.2f}"
        )

    if auto and q_now < 4:
        time.sleep(1.2)
        st.session_state.current_quarter = q_now + 1
        st.rerun()
    if q_now >= 4:
        st.success("Mac tamamlandi. Model kalibre edildi.")

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

    st.markdown(f"""
    <div class="scoreboard">
        <div class="score-side">
            <div class="team-name">{st.session_state.selected_match.get("home", "EV") if st.session_state.selected_match else "EV"}</div>
            <div class="score-number">{hp:.0f}</div>
        </div>
        <div class="score-dash">-</div>
        <div class="score-side">
            <div class="team-name">{st.session_state.selected_match.get("away", "DEP") if st.session_state.selected_match else "DEP"}</div>
            <div class="score-number">{ap:.0f}</div>
        </div>
    </div>
    <div class="scoreboard-sub">
        Toplam Projeksiyon: <b>{tp:.1f}</b>
        &nbsp;|&nbsp; Guven Araligi: p10={total_p10:.0f} - p90={total_p90:.0f}
        &nbsp;|&nbsp; {ctx_emoji} {ctx_label}
        &nbsp;|&nbsp; Bias Ev {scoreboard.get("bias_home", 0):+.2f}
        &nbsp;|&nbsp; Bias Dep {scoreboard.get("bias_away", 0):+.2f}
    </div>
    """, unsafe_allow_html=True)
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
        if is_half:
            extra = " class='q-card half'"
            prefix = ""
        else:
            extra = " class='q-card'"
            prefix = ""
        with col:
            st.markdown(f"""
            <div{extra}>
                <div class="q-label">{prefix}{label}</div>
                <div class="q-score">{h_score:.0f} - {a_score:.0f}</div>
                <div class="q-total">S {h_score + a_score:.0f}</div>
            </div>
            """, unsafe_allow_html=True)

    _quarter_card(q1, "1. Ceyrek", scoreboard["q1_home"], scoreboard["q1_away"])
    _quarter_card(q2, "2. Ceyrek", scoreboard["q2_home"], scoreboard["q2_away"])
    _quarter_card(h1, "ILK YARI", scoreboard["home_h1"], scoreboard["away_h1"], is_half=True)
    _quarter_card(q3, "3. Ceyrek", scoreboard["q3_home"], scoreboard["q3_away"])
    _quarter_card(q4, "4. Ceyrek", scoreboard["q4_home"], scoreboard["q4_away"])
else:
    st.caption("Fikstur yuklendiginde skor tahminleri burada goruntulenecek.")

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
        st.line_chart(
            hist_df.set_index("Ceyrek")[["Hata_Home", "Hata_Away", "MAE"]],
            height=200,
        )
        st.markdown("</div>", unsafe_allow_html=True)
    with col_g2:
        st.markdown('<div class="mae-card">', unsafe_allow_html=True)
        st.metric("Bias Ev", f"{st.session_state.dual_engine.bias_home:+.3f}",
                  help="Ev sahibi icin ogrenilmis sapma")
        st.metric("Bias Dep", f"{st.session_state.dual_engine.bias_away:+.3f}",
                  help="Deplasman icin ogrenilmis sapma")
        st.metric("Var Ev", f"{st.session_state.dual_engine.variance_modifier_home:.3f}",
                  help="Ev sahibi oynaklik katsayisi")
        st.metric("Var Dep", f"{st.session_state.dual_engine.variance_modifier_away:.3f}",
                  help="Deplasman oynaklik katsayisi")
        st.metric("Mevcut MAE", f"{st.session_state.dual_engine.current_mae():.2f}")
        st.markdown("</div>", unsafe_allow_html=True)
else:
    st.caption("Henuz ogrenme verisi yok. Canli modda tahmin uretin veya Zaman Tunelini baslatin.")
