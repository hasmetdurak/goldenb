"""
GoldenBet AI - Patron Komut Paneli
==================================

Streamlit tabanlı dark-mode trading arayüzü (3-zone dashboard).

Yan menü (sidebar)
------------------
* Mod seçimi       : Canlı Maç Takibi | Zaman Tüneli (Backtest)
* Maç seçimi       : mod'a göre lig/sezon/tip/eşleşme VEYA ünlü maç
* Ayarlar expander : kasa, oran, barem, skor, dakika, bağlam, reset

Ana ekran
---------
* Üst bar   : 4 metric (maç, skor, süre, barem)
* Karar     : 2-col (Neon Sinyal Kutusu | Kasa Yönetimi)
* Öğrenme   : 2-col (MAE grafiği | Bias / Variance)

Akış
----
1) Sidebar → lig + sezon + (NBA'de) sezon tipi seçilir.
2) Fikstür otomatik yüklenir, eşleşme selectbox dolar.
3) Slider/input değiştikçe AdaptiveMonteCarloEngine tahmin üretir.
4) Sinyal (ÜST/ALT/PAS) + tutar hesaplanır, neon kutuya yazılır.
5) Zaman Tüneli modunda ünlü maçın çeyrekleri üzerinden motor kalibre edilir.
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
# Sayfa Konfigürasyonu
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="GoldenBet AI · Canlı Tahmin Merkezi",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# CSS — 3-Zone Dashboard (GitHub Dark + Neon Accent)
# -----------------------------------------------------------------------------
NEON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap');

.stApp {
    background: radial-gradient(ellipse at top, #0F172A 0%, #05080F 75%);
    font-family: 'JetBrains Mono', monospace;
}

.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 0rem !important;
    max-width: 100% !important;
}

h1, h2, h3, h4 {
    color: #00FF7F !important;
    font-weight: 800 !important;
    letter-spacing: 0.04em;
}

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
[data-testid="stSidebar"] select,
[data-testid="stSidebar"] textarea {
    font-size: 0.78rem !important;
    min-height: 30px !important;
}
[data-testid="stSidebar"] button {
    font-size: 0.75rem !important;
    padding: 0.3rem 0.5rem !important;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    font-size: 0.68rem !important;
}

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
    width: 100%;
    font-weight: bold;
    border-radius: 6px;
}

.neon-box {
    background-color: #0f1c13;
    padding: clamp(16px, 2.5vw, 28px) clamp(18px, 3vw, 32px);
    border-radius: 12px;
    border: 2px solid #238636;
    text-align: center;
    box-shadow: 0 0 18px rgba(35, 134, 54, 0.25);
    margin: 8px 0;
}
.neon-box.signal-strong { border-color: #238636; box-shadow: 0 0 22px rgba(35, 134, 54, 0.45); }
.neon-box.signal-hedge  { border-color: #FFB300; box-shadow: 0 0 22px rgba(255, 179, 0, 0.35); }
.neon-box.signal-pass   { border-color: #374151; opacity: 0.7; box-shadow: none; }

.neon-badge {
    display: inline-block;
    color: #2ea043;
    font-weight: 800;
    font-size: clamp(0.85rem, 1.4vw, 1.15rem);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 8px;
}
.neon-action {
    color: #ffffff;
    margin: 8px 0 10px 0;
    font-size: clamp(1.6rem, 4.5vw, 2.8rem);
    font-family: 'JetBrains Mono', monospace;
    font-weight: 800;
    line-height: 1.1;
}
.neon-sub {
    color: #8b949e;
    font-size: clamp(0.7rem, 1.2vw, 0.92rem);
    margin: 4px 0;
    letter-spacing: 0.04em;
}
.neon-sub b { color: #c9d1d9; }

.kasa-card {
    background-color: #0d1117;
    padding: clamp(16px, 2.5vw, 24px);
    border-radius: 12px;
    border: 1px solid #30363d;
    height: 100%;
    display: flex;
    flex-direction: column;
}
.kasa-card h3 {
    color: #f0f6fc !important;
    margin: 8px 0 12px 0 !important;
    font-size: clamp(1.1rem, 2vw, 1.5rem) !important;
}
.kasa-card p { color: #8b949e; font-size: 0.85rem; margin: 4px 0; }
.kasa-card .kasa-title {
    color: #58a6ff;
    font-weight: 700;
    font-size: 0.78rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

.mae-card {
    background-color: #0d1117;
    padding: clamp(14px, 2vw, 20px);
    border-radius: 12px;
    border: 1px solid #30363d;
    height: 100%;
}
.mae-card h3 {
    color: #f0f6fc !important;
    font-size: 0.95rem !important;
    margin: 0 0 10px 0 !important;
}

@media (max-width: 768px) {
    .neon-action { font-size: 1.5rem; }
    .neon-box, .kasa-card, .mae-card { padding: 14px; }
}
</style>
"""
st.markdown(NEON_CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Session State Bootstrap
# -----------------------------------------------------------------------------
def _init_state() -> None:
    if "engine" not in st.session_state:
        st.session_state.engine = eng.AdaptiveMonteCarloEngine()
    if "mod" not in st.session_state:
        st.session_state.mod = "canli"
    if "league" not in st.session_state:
        st.session_state.league = "NBA"
    if "season" not in st.session_state:
        st.session_state.season = "2024-25"
    if "season_type" not in st.session_state:
        st.session_state.season_type = "Regular Season"
    if "budget" not in st.session_state:
        st.session_state.budget = 10_000
    if "odds" not in st.session_state:
        st.session_state.odds = eng.DEFAULT_ODDS
    if "market_line" not in st.session_state:
        st.session_state.market_line = 215.0
    if "current_score" not in st.session_state:
        st.session_state.current_score = 110
    if "total_minutes" not in st.session_state:
        st.session_state.total_minutes = 40
    if "schedule_df" not in st.session_state:
        st.session_state.schedule_df = pd.DataFrame()
    if "schedule_signature" not in st.session_state:
        st.session_state.schedule_signature = ""
    if "selected_match" not in st.session_state:
        st.session_state.selected_match = None
    if "baseline_avg" not in st.session_state:
        st.session_state.baseline_avg = 0.0
    if "context_tag" not in st.session_state:
        st.session_state.context_tag = "Normal_Season_Match"
    if "last_prediction" not in st.session_state:
        st.session_state.last_prediction = None
    if "last_signal" not in st.session_state:
        st.session_state.last_signal = {
            "order": "PAS", "strength": "ZAYIF",
            "diff": "+0.00", "confidence": "0.0%",
        }
    if "live_order" not in st.session_state:
        st.session_state.live_order = pd.DataFrame()
    if "order_log" not in st.session_state:
        st.session_state.order_log = pd.DataFrame(
            columns=["Zaman", "Faz", "Kademe", "Barem",
                     "Tutar (₺)", "Oran", "Yön", "Güç", "Not"]
        )
    if "backtest_result" not in st.session_state:
        st.session_state.backtest_result = None
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
# Yardımcılar — Fikstür Yükleme & Eşleşme Listesi
# -----------------------------------------------------------------------------
def _load_schedule(league: str, season: str, season_type: str) -> pd.DataFrame:
    """Lig/sezon(/tip) fikstürünü yükler; hata/boş durumda boş DataFrame."""
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
            f"{row.HOME} vs {row.AWAY} · "
            f"{pd.to_datetime(row.GAME_DATE).strftime('%Y-%m-%d')}"
            for row in df.itertuples()
        ]
    return [
        f"{row.EV_SAHIBI} vs {row.DEPLASMAN} · Round {int(row.HAFTA)}"
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
            "total": float(row.get("TOTAL", 0) or 0),
            "label": f"{row.get('HOME','')} vs {row.get('AWAY','')}",
        }
    return {
        "home": str(row.get("EV_SAHIBI", "")),
        "away": str(row.get("DEPLASMAN", "")),
        "round": int(row.get("HAFTA", 0) or 0),
        "total": float(row.get("TOPLAM", 0) or 0),
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
    with st.spinner("📡 Fikstür yükleniyor…"):
        st.session_state.schedule_df = _load_schedule(
            st.session_state.league,
            st.session_state.season,
            st.session_state.season_type,
        )
        st.session_state.schedule_signature = sig
        st.session_state.selected_match = None
        st.session_state.baseline_avg = 0.0
        st.session_state.prematch_orders = pd.DataFrame() \
            if "prematch_orders" in st.session_state else pd.DataFrame()


# -----------------------------------------------------------------------------
# Sidebar — Mod · Maç Seçimi · Ayarlar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("🎯 GoldenBet Kontrol")

    _MODES = ["🔴 Canlı Maç Takibi", "⏳ Zaman Tüneli (Backtest)"]
    _mod_label = st.radio("Mod Seçimi", _MODES, key="_sb_mod",
                          index=0 if st.session_state.mod == "canli" else 1)
    st.session_state.mod = "canli" if "Canlı" in _mod_label else "zaman_tuneli"

    st.divider()

    # --- Maç Seçimi (mod'a göre) ---
    if st.session_state.mod == "canli":
        _LEAGUES = ["NBA", "EuroLeague", "EuroCup"]
        league = st.selectbox(
            "Lig", _LEAGUES,
            index=_LEAGUES.index(st.session_state.league)
            if st.session_state.league in _LEAGUES else 0,
            key="_sb_league",
        )
        st.session_state.league = league

        # Sezon placeholder / default
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

        # Sezon Tipi (sadece NBA)
        if league == "NBA":
            _TYPES = ["Regular Season", "Playoffs"]
            _type_idx = _TYPES.index(st.session_state.season_type) \
                if st.session_state.season_type in _TYPES else 0
            season_type = st.selectbox(
                "Sezon Tipi", _TYPES, index=_type_idx,
                format_func=lambda x: "🟢 Regular Season" if x == "Regular Season" else "🔴 Playoffs",
                key="_sb_season_type",
            )
            st.session_state.season_type = season_type
            # Akıllı context_tag öneri
            if season_type == "Playoffs":
                st.session_state.context_tag = "Playoff_Elimination_G7"

        # Fikstür yükle
        _ensure_schedule()

        match_options = _format_match_options(
            st.session_state.schedule_df, st.session_state.league
        )
        if match_options:
            match_label = st.selectbox(
                "Eşleşme", match_options, index=0, key="_sb_match"
            )
            match_idx = match_options.index(match_label)
            st.session_state.selected_match = _extract_match(
                st.session_state.schedule_df, match_idx, st.session_state.league
            )
            if st.session_state.baseline_avg <= 0 and not st.session_state.schedule_df.empty:
                st.session_state.baseline_avg = df_lib.compute_schedule_baseline(
                    st.session_state.schedule_df, st.session_state.league
                )
        else:
            st.caption("⚠️ Fikstür boş. Veri kaynağına ulaşılamıyor olabilir.")
            st.session_state.selected_match = None

        st.button("🔄 Oranları Eş Zamanlı Doğrula", key="_sb_refresh",
                  help="Fikstürü yeniden yükle")

    else:
        # Zaman Tüneli modu
        st.markdown("##### Tarihsel Maç")
        famous = df_lib.get_famous_games_for_league(st.session_state.league)
        if famous:
            labels = list(famous.keys())
            sel = st.selectbox("Ünlü Maç", labels, key="_sb_famous")
            if st.button("▶️ Zaman Tünelini Başlat", type="primary",
                         use_container_width=True, key="_sb_tt_start"):
                st.session_state.historical_label = sel
                st.session_state.historical_quarters = df_lib.fetch_famous_game_quarters(sel)
                st.session_state.current_quarter = 0
                st.session_state.historical_running = True
                st.session_state.historical_mode = True
                st.session_state.engine.reset_learning()
        else:
            st.caption("Bu lig için ünlü maç tanımlı değil.")

    st.divider()

    # --- Ayarlar (expander) ---
    with st.expander("⚙️ Ayarlar", expanded=False):
        st.session_state.budget = st.number_input(
            "💰 Kasa (₺)", min_value=100, max_value=1_000_000,
            value=int(st.session_state.budget), step=500, key="_sb_budget"
        )
        st.session_state.odds = st.number_input(
            "📈 Oran", min_value=1.01, max_value=5.00,
            value=float(st.session_state.odds), step=0.01, key="_sb_odds"
        )

        # Live input'lar sadece canlı modda
        if st.session_state.mod == "canli":
            st.session_state.market_line = st.number_input(
                "🎯 Barem", min_value=80.0, max_value=400.0,
                value=float(st.session_state.market_line), step=0.5, key="_sb_line"
            )
            st.session_state.current_score = st.number_input(
                "🏀 Skor", min_value=0, max_value=400,
                value=int(st.session_state.current_score), step=1, key="_sb_score"
            )
            _tm = cfg.get_total_minutes(st.session_state.league)
            st.session_state.total_minutes = _tm
            current_minute = st.slider(
                f"⏱️ Kalan Dakika (0–{_tm})",
                min_value=0, max_value=_tm,
                value=st.session_state.get("current_minute", _tm // 2),
                key="_sb_minute",
            )
            st.session_state.current_minute = current_minute
        else:
            _tm = cfg.get_total_minutes(st.session_state.league)
            st.session_state.total_minutes = _tm
            current_minute = st.session_state.get("current_minute", _tm // 2)

        # Maç Bağlamı
        ctx_keys = list(cfg.CONTEXTUAL_MODIFIERS.keys())
        _default_ctx = st.session_state.context_tag
        if _default_ctx not in ctx_keys:
            _default_ctx = "Normal_Season_Match"
        _ctx_idx = ctx_keys.index(_default_ctx)
        context_tag = st.selectbox(
            "🧬 Maç Bağlamı", ctx_keys, index=_ctx_idx,
            format_func=lambda k: f"{cfg.CONTEXTUAL_MODIFIERS[k]['emoji']} "
                                  f"{cfg.CONTEXTUAL_MODIFIERS[k]['label']}",
            key="_sb_ctx",
        )
        st.session_state.context_tag = context_tag
        ctx_meta = cfg.CONTEXTUAL_MODIFIERS[context_tag]
        st.caption(
            f"Tempo ×{ctx_meta['pace_multiplier']:.2f} · "
            f"Varyans ×{ctx_meta['variance_multiplier']:.2f}"
        )

        st.button("🔁 Motoru Sıfırla", key="_sb_reset",
                  on_click=lambda: _reset_engine())


def _reset_engine() -> None:
    st.session_state.engine.reset_learning()
    st.session_state.current_quarter = 0
    st.session_state.historical_running = False
    st.session_state.historical_quarters = {}
    st.session_state.order_log = st.session_state.order_log.iloc[0:0]


# Backtest handler (sidebar butonu)
def _run_backtest() -> None:
    if st.session_state.baseline_avg <= 0 or st.session_state.schedule_df.empty:
        st.warning("Önce fikstür yüklenmeli.")
        return
    with st.spinner("Backtest çalışıyor…"):
        st.session_state.backtest_result = eng.backtest(
            df=st.session_state.schedule_df,
            baseline_avg=st.session_state.baseline_avg,
            total_minutes=st.session_state.total_minutes,
        )
    st.success("Backtest tamam.")


# Backtest butonu canlı modda görünür
if st.session_state.mod == "canli":
    with st.sidebar:
        st.button("🧪 Backtest", key="_sb_backtest", on_click=_run_backtest)


# -----------------------------------------------------------------------------
# Ana Ekran — Üst Bar (4 metric)
# -----------------------------------------------------------------------------
_match_label = (
    st.session_state.selected_match["label"]
    if st.session_state.selected_match
    else (st.session_state.historical_label or "—")
)
_match_delta = st.session_state.league

# Kalan dakika (canlı modda slider, tünelde sabit)
_tm = st.session_state.total_minutes
_cur_min = st.session_state.get("current_minute", _tm // 2)
_period_idx = min(4, max(0, int((_tm - _cur_min) / (_tm / 4)) + 1)) \
    if _tm > 0 else 1
_period_label = f"Q{_period_idx}" if _cur_min > 0 else "Final"

# Delta için AI sapması
_signal_delta = ""
if st.session_state.last_prediction is not None and st.session_state.last_signal is not None:
    _signal_delta = st.session_state.last_signal.get("diff", "")

st.title("🏀 GoldenBet AI • Canlı Tahmin Merkezi")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Akan Maç", _match_label, delta=_match_delta)
with col2:
    st.metric(
        "Skor / Periyot",
        f"{int(st.session_state.current_score)}",
        delta=_period_label,
    )
with col3:
    st.metric("Kalan Süre", f"{int(_cur_min)} dk", delta="")
with col4:
    st.metric(
        "Şirket Baremi",
        f"{float(st.session_state.market_line):.1f}",
        delta=_signal_delta or "—",
    )

st.divider()


# -----------------------------------------------------------------------------
# Orta Neon Karar Kutusu + Kasa Yönetimi
# -----------------------------------------------------------------------------
prediction: Optional[Dict[str, Any]] = None
signal: Optional[Dict[str, str]] = None
context_tag = st.session_state.context_tag
ctx_meta = cfg.CONTEXTUAL_MODIFIERS[context_tag]

# Canlı modda reactive tahmin
if (st.session_state.mod == "canli"
        and not st.session_state.historical_running
        and st.session_state.baseline_avg > 0):
    prediction = st.session_state.engine.predict_remaining_game(
        current_score=int(st.session_state.current_score),
        current_minute=int(_cur_min),
        baseline_avg=float(st.session_state.baseline_avg),
        bookmaker_line=float(st.session_state.market_line),
        total_minutes=int(_tm),
        context_tag=context_tag,
        league=st.session_state.league,
    )
    st.session_state.last_prediction = prediction
    signal = eng.generate_signal(
        ai_pred=prediction["final_predicted_score"],
        market_line=float(st.session_state.market_line),
        confidence_pct=prediction.get("confidence_pct"),
    )
    st.session_state.last_signal = signal
    st.session_state.live_order = eng.build_live_order_plan(
        budget=float(st.session_state.budget),
        signal=signal,
        current_minute=int(_cur_min),
        total_minutes=int(_tm),
        odds=float(st.session_state.odds),
    )
    # Emir defteri güncelle
    if not st.session_state.live_order.empty:
        live_row = st.session_state.live_order.iloc[0].to_dict()
        live_row["Zaman"] = time.strftime("%H:%M:%S")
        live_row["Not"] = (
            f"AI={prediction['final_predicted_score']:.1f} | "
            f"Barem={float(st.session_state.market_line):.1f} | "
            f"Sapma={signal['diff']}"
        )
        if not st.session_state.order_log.empty:
            mask = st.session_state.order_log["Faz"] == live_row["Faz"]
            st.session_state.order_log = st.session_state.order_log.loc[~mask]
        st.session_state.order_log = pd.concat(
            [st.session_state.order_log, pd.DataFrame([live_row])],
            ignore_index=True,
        )

# Zaman Tüneli modunda: mevcut çeyrek verisiyle tahmin üret
elif st.session_state.mod == "zaman_tuneli" and st.session_state.historical_running:
    quarters = st.session_state.historical_quarters
    q_now = st.session_state.current_quarter
    if 0 < q_now <= 4 and q_now in quarters:
        cur_q_start_cum = quarters.get(q_now - 1, 0.0)
        cur_q_end_cum = quarters[q_now]
        per_q_minutes = _tm // 4
        minute_at_q_end = per_q_minutes * q_now
        baseline_for_q = float(st.session_state.baseline_avg) or 220.0
        engine_obj: eng.AdaptiveMonteCarloEngine = st.session_state.engine
        result = engine_obj.predict_remaining_game(
            current_score=cur_q_start_cum,
            current_minute=minute_at_q_end - per_q_minutes,
            baseline_avg=baseline_for_q,
            bookmaker_line=None,
            total_minutes=per_q_minutes,
            context_tag=context_tag,
            league=st.session_state.league,
        )
        predicted_q_end = result["final_predicted_score"]
        actual_q_end = cur_q_end_cum
        engine_obj.update_learning_weights(
            quarter=q_now,
            predicted_at_quarter=predicted_q_end,
            actual_at_quarter=actual_q_end,
        )
        st.session_state.last_prediction = result
        signal = eng.generate_signal(
            ai_pred=predicted_q_end,
            market_line=actual_q_end,
            confidence_pct=None,
        )
        st.session_state.last_signal = signal
        prediction = result

st.subheader("🔮 Yapay Zeka Karar Mekanizması")

col_left, col_right = st.columns([2, 1])

with col_left:
    if signal is not None and prediction is not None:
        order = signal["order"]
        strength = signal.get("strength", "ZAYIF")
        if order == "ÜST":
            signal_class = "signal-strong"
            badge = "🟢 GÜÇLÜ SİNYAL: ÜST (OVER)" if strength == "GÜÇLÜ" else "🟡 ÜST (OVER)"
        elif order.startswith("ALT"):
            signal_class = "signal-hedge"
            badge = "🟠 ALT (UNDER) — HEDGE" if strength == "GÜÇLÜ" else "🟡 ALT (UNDER)"
        else:
            signal_class = "signal-pass"
            badge = "⚪ PAS — FIRSAT YOK"

        eff_base = prediction.get("effective_baseline", st.session_state.baseline_avg)
        conf_pct = prediction.get("confidence_pct")
        conf_str = f"%{conf_pct:.1f}" if conf_pct is not None else "—"
        neon_html = f"""
        <div class="neon-box {signal_class}">
            <div class="neon-badge">{badge}</div>
            <div class="neon-action">PROJEKSİYON: {prediction['final_predicted_score']:.1f}</div>
            <div class="neon-sub">
                Şirket Barem: <b>{float(st.session_state.market_line):.1f}</b> &nbsp;|&nbsp;
                Güven: <b>{conf_str}</b> &nbsp;|&nbsp;
                Oran: <b>{float(st.session_state.odds):.2f}</b>
            </div>
            <div class="neon-sub">
                p10=<b>{prediction['p10']:.1f}</b> &nbsp;·&nbsp;
                p50=<b>{prediction['p50']:.1f}</b> &nbsp;·&nbsp;
                p90=<b>{prediction['p90']:.1f}</b>
            </div>
            <div class="neon-sub" style="margin-top:8px; font-size:0.78rem; color:#6B7280;">
                {ctx_meta['emoji']} {ctx_meta['label']} &nbsp;|&nbsp;
                Effective Baseline: <b>{eff_base:.1f}</b> &nbsp;|&nbsp;
                Tempo ×{prediction.get('context_pace_multiplier', 1.0):.2f} &nbsp;|&nbsp;
                Var ×{prediction.get('context_variance_multiplier', 1.0):.2f}
            </div>
        </div>
        """
    else:
        neon_html = """
        <div class="neon-box signal-pass">
            <div class="neon-badge" style="color:#9CA3AF;">⏳ SİSTEM HAZIR DEĞİL</div>
            <div class="neon-action" style="font-size:1.3rem; color:#9CA3AF;">
                Soldan lig + sezon seçildiğinde fikstür otomatik yüklenir.
            </div>
        </div>
        """
    st.markdown(neon_html, unsafe_allow_html=True)

with col_right:
    # Kasa Yönetimi kartı
    if not st.session_state.live_order.empty:
        _kurşun = float(st.session_state.live_order.iloc[0]["Tutar (₺)"])
    elif signal is not None and prediction is not None:
        # Tahmin varsa ama emir yoksa (PAS durumu) hesapla
        try:
            _kurşun = float(st.session_state.budget) * 0.0
        except Exception:
            _kurşun = 0.0
    else:
        _kurşun = 0.0

    _kasa_orani = (_kurşun / float(st.session_state.budget) * 100.0) \
        if float(st.session_state.budget) > 0 else 0.0
    _pusu = max(0.0, float(st.session_state.budget) - _kurşun)

    st.markdown(f"""
    <div class="kasa-card">
        <div class="kasa-title">💰 KASA YÖNETİMİ</div>
        <h3>Önerilen Kurşun: {_kurşun:,.0f} ₺</h3>
        <p>Mevcut Kasa Oranı: %{_kasa_orani:.1f}</p>
        <p>Kalan Pusu Bütçesi: {_pusu:,.0f} ₺</p>
    </div>
    """, unsafe_allow_html=True)

    # Emirler (collapsed)
    with st.expander("📋 Emirler", expanded=False):
        log = st.session_state.order_log
        if log.empty:
            st.caption("Henüz emir yok.")
        else:
            st.dataframe(log, use_container_width=True, hide_index=True, height=220)

    # Backtest sonucu (varsa)
    bt = st.session_state.backtest_result
    if bt and bt.get("total_simulations", 0) > 0:
        with st.expander("🧪 Backtest Sonucu", expanded=False):
            bm1, bm2 = st.columns(2)
            bm1.metric("İsabet", f"{bt['hit_rate_pct']:.1f}%")
            bm2.metric("ROI", f"{bt['roi_pct']:+.2f}%")

st.divider()


# -----------------------------------------------------------------------------
# Alt: Öğrenme Monitörü (MAE grafiği + Bias/Variance)
# -----------------------------------------------------------------------------
st.subheader("🧠 Yapay Zeka Canlı Evrim Grafiği (Self-Learning)")

col_g1, col_g2 = st.columns([3, 1])

with col_g1:
    hist_df = st.session_state.engine.history_dataframe()
    if hist_df is None or hist_df.empty:
        # Mock data: MAE yakınsama simülasyonu
        chart_data = pd.DataFrame({
            "Çeyrek": ["Maç Başı", "1. Çeyrek", "2. Çeyrek", "3. Çeyrek", "4. Çeyrek"],
            "Model Hata Payı (MAE)": [22.4, 14.2, 8.5, 3.1, 0.8],
        }).set_index("Çeyrek")
        st.markdown('<div class="mae-card">', unsafe_allow_html=True)
        st.caption("Örnek yakınsama — canlı veri gelince güncellenir.")
        st.line_chart(chart_data, height=200)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown('<div class="mae-card">', unsafe_allow_html=True)
        st.markdown("<h3>Model Hata Payı (MAE) — Yakınsama</h3>",
                    unsafe_allow_html=True)
        st.line_chart(
            hist_df.set_index("Çeyrek")[["Hata", "MAE"]],
            height=200,
        )
        st.markdown("</div>", unsafe_allow_html=True)

with col_g2:
    st.markdown('<div class="mae-card">', unsafe_allow_html=True)
    st.metric(
        "Öğrenilmiş Sapma (Bias)",
        f"{st.session_state.engine.bias_weight:+.3f}",
        help="Modelin maçı ne kadar yukarı/aşağı kalibre ettiği",
    )
    st.metric(
        "Oynaklık Katsayısı (Variance)",
        f"{st.session_state.engine.variance_modifier:.3f}",
        help="Monte Carlo dağılım genişliği",
    )
    if hist_df is not None and not hist_df.empty:
        st.metric("Mevcut MAE", f"{st.session_state.engine.current_mae():.2f}")
    st.markdown("</div>", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Zaman Tüneli Kontrolleri (sadece mod aktifken)
# -----------------------------------------------------------------------------
if (st.session_state.mod == "zaman_tuneli"
        and st.session_state.historical_running
        and st.session_state.historical_quarters):
    st.divider()
    st.subheader("⏳ Zaman Tüneli · " + st.session_state.historical_label)
    q_now = st.session_state.current_quarter
    quarters = st.session_state.historical_quarters

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("▶ ADIM AT", key="_tt_step", use_container_width=True):
            if q_now < 4:
                st.session_state.current_quarter = q_now + 1
    with c2:
        auto = st.checkbox("🤖 OTO (1.2s)", key="_tt_auto", value=False)
    with c3:
        st.progress(
            min(q_now / 4.0, 1.0),
            text=f"Çeyrek {q_now}/4 tamamlandı",
        )

    if 0 < q_now <= 4 and q_now in quarters:
        cur_q_end_cum = quarters[q_now]
        st.caption(
            f"Q{q_now} sonu kümülatif skor: **{cur_q_end_cum:.1f}** | "
            f"Bias: **{st.session_state.engine.bias_weight:+.3f}** | "
            f"MAE: **{st.session_state.engine.current_mae():.2f}**"
        )

    if auto and q_now < 4:
        time.sleep(1.2)
        st.session_state.current_quarter = q_now + 1
        st.rerun()
    if q_now >= 4:
        st.success("🏁 Maç tamamlandı. Model tamamen kalibre edildi.")
