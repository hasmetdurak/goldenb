"""
GoldenBet AI - Patron Komut Paneli
==================================

Streamlit tabanlı dark-mode trading arayüzü.

Yan menü 3 modülden oluşur:
    1) Canlı Tahmin       → lig, sezon, eşleşme, kasa, oran, canlı gözlem
    2) Veriyle Tahmin     → sezon yükleme, backtest, tarihsel derin öğrenme
    3) Ayarlar            → bağlam etiketi, motor sıfırlama

Akış
----
1) Sidebar → lig + sezon seçilir, eşleşme otomatik yüklenir.
2) Eşleşme seçilince baseline otomatik hesaplanır.
3) Slider/input değiştikçe AdaptiveMonteCarloEngine tahmin üretir.
4) Sinyal (ÜST/ALT/PAS) + tutar hesaplanır, neon kutuya yazılır.
5) İsteğe bağlı: Tarihsel modda ünlü maçın çeyrekleri üzerinden motor kalibre edilir.
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
    page_title="GoldenBet AI · Patron Komut Paneli",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# CSS — Minimal / Responsive Neon Trading Ekranı
# -----------------------------------------------------------------------------
NEON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap');

.stApp {
    background: radial-gradient(ellipse at top, #0F172A 0%, #05080F 75%);
    font-family: 'JetBrains Mono', monospace;
}

h1, h2, h3, h4 {
    color: #00FF7F !important;
    font-weight: 800 !important;
    letter-spacing: 0.04em;
}

[data-testid="stSidebar"] {
    background: #0A0E1A;
    border-right: 1px solid #1F2937;
    padding: 0.6rem 0.7rem !important;
}
[data-testid="stSidebar"] h2 {
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #6B7280 !important;
    margin: 0.4rem 0 0.5rem 0 !important;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid #1F2937;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p {
    font-size: 0.75rem !important;
    color: #9CA3AF !important;
}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] select {
    font-size: 0.8rem !important;
    min-height: 30px !important;
}
[data-testid="stSidebar"] button {
    font-size: 0.75rem !important;
    padding: 0.3rem 0.5rem !important;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    font-size: 0.7rem !important;
}
[data-testid="stSidebar"]::-webkit-scrollbar { display: none; }

[data-testid="stMetricValue"] {
    color: #00FF7F !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 800 !important;
}
[data-testid="stMetricLabel"] {
    color: #9CA3AF !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.72rem !important;
}

.neon-box {
    border: 2px solid #FF1744;
    border-radius: clamp(8px, 1.5vw, 14px);
    padding: clamp(12px, 2.5vw, 28px) clamp(14px, 3vw, 32px);
    background: linear-gradient(135deg, rgba(0,255,127,0.06), rgba(0,0,0,0.5));
    box-shadow: 0 0 18px rgba(255,23,68,0.4), inset 0 0 18px rgba(0,255,127,0.05);
    animation: pulse 1.6s ease-in-out infinite;
    text-align: center;
    margin: clamp(8px, 1.5vw, 14px) 0;
}
@keyframes pulse {
    0%, 100% { box-shadow: 0 0 18px rgba(255,23,68,0.4), inset 0 0 18px rgba(0,255,127,0.05); }
    50%      { box-shadow: 0 0 32px rgba(255,23,68,0.7), inset 0 0 24px rgba(0,255,127,0.10); }
}
.neon-title {
    color: #00FF7F;
    font-size: clamp(0.8rem, 1.7vw, 1.4rem);
    font-weight: 800;
    letter-spacing: clamp(0.08em, 0.3vw, 0.2em);
    margin-bottom: clamp(6px, 1vw, 12px);
    text-transform: uppercase;
}
.neon-action {
    color: #FFFFFF;
    font-size: clamp(1.3rem, 4.5vw, 2.4rem);
    font-weight: 800;
    margin: clamp(6px, 1.2vw, 12px) 0;
    text-shadow: 0 0 12px #00FF7F;
    line-height: 1.15;
}
.neon-sub {
    color: #9CA3AF;
    font-size: clamp(0.72rem, 1.3vw, 1.0rem);
    letter-spacing: 0.05em;
    line-height: 1.4;
}
.tag-strong  { color: #00FF7F; font-weight: 800; }
.tag-hedge   { color: #FFB300; font-weight: 800; }
.tag-pass    { color: #6B7280; font-weight: 800; }

.dashboard-card {
    border: 1px solid #1F2937;
    border-radius: 10px;
    padding: 16px;
    background: #0F172A;
    margin-bottom: 12px;
}

[data-testid="stDataFrame"] {
    border: 1px solid #1F2937;
    border-radius: 8px;
}

@media (max-width: 768px) {
    .neon-action { font-size: 1.2rem; }
    .neon-title  { font-size: 0.85rem; }
    .neon-box    { padding: 12px 14px; }
}
@media (max-width: 480px) {
    .neon-action { font-size: 1.05rem; }
    .neon-title  { font-size: 0.78rem; }
    .neon-sub    { font-size: 0.7rem; }
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
    if "df_history" not in st.session_state:
        st.session_state.df_history = pd.DataFrame()
    if "baseline_avg" not in st.session_state:
        st.session_state.baseline_avg = 0.0
    if "total_minutes" not in st.session_state:
        st.session_state.total_minutes = 40
    if "league" not in st.session_state:
        st.session_state.league = "NBA"
    if "season" not in st.session_state:
        st.session_state.season = "2024-25"
    if "team_label" not in st.session_state:
        st.session_state.team_label = ""
    if "prematch_orders" not in st.session_state:
        st.session_state.prematch_orders = pd.DataFrame()
    if "live_order" not in st.session_state:
        st.session_state.live_order = pd.DataFrame()
    if "order_log" not in st.session_state:
        st.session_state.order_log = pd.DataFrame(
            columns=["Zaman", "Faz", "Kademe", "Barem",
                     "Tutar (₺)", "Oran", "Yön", "Güç", "Not"]
        )
    if "last_signal" not in st.session_state:
        st.session_state.last_signal = {"order": "PAS", "strength": "ZAYIF",
                                        "diff": "+0.00", "confidence": "0.0%"}
    if "last_prediction" not in st.session_state:
        st.session_state.last_prediction = None
    if "backtest_result" not in st.session_state:
        st.session_state.backtest_result = None
    if "historical_mode" not in st.session_state:
        st.session_state.historical_mode = False
    if "historical_quarters" not in st.session_state:
        st.session_state.historical_quarters: Dict[int, float] = {}
    if "historical_label" not in st.session_state:
        st.session_state.historical_label = ""
    if "current_quarter" not in st.session_state:
        st.session_state.current_quarter = 0
    if "historical_running" not in st.session_state:
        st.session_state.historical_running = False
    if "context_tag" not in st.session_state:
        st.session_state.context_tag = "Normal_Season_Match"
    if "schedule_df" not in st.session_state:
        st.session_state.schedule_df = pd.DataFrame()
    if "schedule_signature" not in st.session_state:
        st.session_state.schedule_signature = ""
    if "selected_match" not in st.session_state:
        st.session_state.selected_match: Optional[Dict[str, Any]] = None


_init_state()


# -----------------------------------------------------------------------------
# Yardımcılar — Fikstür Yükleme & Eşleşme Listesi
# -----------------------------------------------------------------------------
def _load_schedule(league: str, season: str) -> pd.DataFrame:
    """Lig/sezon fikstürünü yükler; boş DataFrame dönebilir."""
    if league == "NBA":
        return df_lib.fetch_nba_season_schedule(season=season)
    if league in ("EuroLeague", "EuroCup"):
        comp = "E" if league == "EuroLeague" else "U"
        # fetch_euroleague_data zaten oynanmış maçları TOPLAM kolonu ile döner
        return df_lib.fetch_euroleague_data(season_code=season, competition=comp)
    return pd.DataFrame()


def _format_match_options(df: pd.DataFrame, league: str) -> list[str]:
    """Selectbox için etiket listesi üretir."""
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
    """Satırdan sözlük formatında eşleşme çıkarır (baseline için)."""
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
    """Mevcut lig/sezon için fikstür yoksa yükler."""
    sig = f"{st.session_state.league}|{st.session_state.season}"
    if st.session_state.schedule_signature == sig and not st.session_state.schedule_df.empty:
        return
    with st.spinner("📡 Sezon fikstürü yükleniyor…"):
        st.session_state.schedule_df = _load_schedule(
            st.session_state.league, st.session_state.season
        )
        st.session_state.schedule_signature = sig
        # Eşleşme seçimi sıfırlanır
        st.session_state.selected_match = None
        st.session_state.baseline_avg = 0.0
        st.session_state.prematch_orders = pd.DataFrame()
        st.session_state.df_history = pd.DataFrame()


# -----------------------------------------------------------------------------
# Sidebar — 3 Menü Yapısı
# -----------------------------------------------------------------------------
with st.sidebar:
    # ------------------------------------------------------------------ MENU 1
    st.markdown("## 📡 CANLI TAHMİN")
    _ensure_schedule()

    _LEAGUES = ["NBA", "EuroLeague", "EuroCup"]
    league = st.selectbox(
        "Lig",
        _LEAGUES,
        index=_LEAGUES.index(st.session_state.league)
        if st.session_state.league in _LEAGUES else 0,
        key="_sb_league",
    )
    st.session_state.league = league

    if league == "NBA":
        _default_season = "2024-25"
    elif league == "EuroLeague":
        _default_season = "E2024"
    else:
        _default_season = "U2024"
    if not st.session_state.season or (
        league == "NBA" and not st.session_state.season.endswith("-")
        and "-" not in st.session_state.season
    ):
        st.session_state.season = _default_season

    season = st.text_input(
        "Sezon", value=st.session_state.season, key="_sb_season"
    )
    st.session_state.season = season

    # Eşleşme selectbox (otomatik dolu)
    match_options = _format_match_options(
        st.session_state.schedule_df, st.session_state.league
    )
    if match_options:
        match_label = st.selectbox("Eşleşme", match_options, index=0, key="_sb_match")
        match_idx = match_options.index(match_label)
        st.session_state.selected_match = _extract_match(
            st.session_state.schedule_df, match_idx, st.session_state.league
        )
        # Baseline otomatik hesapla
        if st.session_state.baseline_avg <= 0 and not st.session_state.schedule_df.empty:
            st.session_state.baseline_avg = df_lib.compute_schedule_baseline(
                st.session_state.schedule_df, st.session_state.league
            )
            st.session_state.df_history = st.session_state.schedule_df
            ladder = eng.build_ladder_lines(st.session_state.baseline_avg) \
                if st.session_state.baseline_avg > 0 else []
            st.session_state.prematch_orders = eng.build_prematch_orders(
                st.session_state.budget if hasattr(st.session_state, "budget") else 10_000,
                ladder, odds=eng.DEFAULT_ODDS,
            ) if ladder else pd.DataFrame()
    else:
        st.caption("⚠️ Sezon fikstürü boş. Veri kaynağına ulaşılamıyor olabilir.")
        st.session_state.selected_match = None

    st.session_state.team_label = (
        st.session_state.selected_match["label"]
        if st.session_state.selected_match else ""
    )

    # Kompakt canlı gözlem — 2 sütunlu grid
    total_minutes = cfg.get_total_minutes(league)
    st.session_state.total_minutes = total_minutes

    _cg1, _cg2 = st.columns(2)
    with _cg1:
        budget = st.number_input(
            "Kasa (₺)", min_value=100, max_value=1_000_000,
            value=10_000, step=500, key="_sb_budget",
        )
    with _cg2:
        odds = st.number_input(
            "Oran", min_value=1.01, max_value=5.00,
            value=eng.DEFAULT_ODDS, step=0.01, key="_sb_odds",
        )
    _cg3, _cg4 = st.columns(2)
    with _cg3:
        current_score = st.number_input(
            "Skor", min_value=0, max_value=400, value=110, step=1, key="_sb_score",
        )
    with _cg4:
        market_line = st.number_input(
            "Barem", min_value=80.0, max_value=400.0, value=215.0, step=0.5, key="_sb_line",
        )
    current_minute = st.slider(
        f"Kalan Dakika (0–{total_minutes})",
        min_value=0, max_value=total_minutes,
        value=total_minutes // 2, key="_sb_minute",
    )

    # ------------------------------------------------------------------ MENU 2
    st.markdown("## 🧠 VERİYLE TAHMİN")

    if st.button("🔄 FİKSTÜRÜ YENİLE", use_container_width=True):
        st.session_state.schedule_signature = ""
        _ensure_schedule()
        st.success(f"Yüklendi → {len(st.session_state.schedule_df)} maç")

    if st.button("🧪 BACKTEST SİMÜLASYONU", use_container_width=True):
        if st.session_state.baseline_avg <= 0 or st.session_state.schedule_df.empty:
            st.warning("Önce fikstür yüklenmeli.")
        else:
            with st.spinner("Backtest çalışıyor…"):
                st.session_state.backtest_result = eng.backtest(
                    df=st.session_state.schedule_df,
                    baseline_avg=st.session_state.baseline_avg,
                    total_minutes=total_minutes,
                )
            st.success("Backtest tamam.")

    with st.expander("⏳ Tarihsel Derin Öğrenme", expanded=False):
        historical_mode = st.checkbox(
            "Aktifleştir", value=st.session_state.historical_mode, key="_sb_hist_mode"
        )
        st.session_state.historical_mode = historical_mode

        famous = df_lib.get_famous_games_for_league(league)
        if famous:
            labels = list(famous.keys())
            sel = st.selectbox("Ünlü Maç", labels, key="_sb_famous")
            if st.button("⏩ ZAMAN TÜNELİNİ BAŞLAT", use_container_width=True, key="_sb_tt_start"):
                st.session_state.historical_label = sel
                st.session_state.historical_quarters = df_lib.fetch_famous_game_quarters(sel)
                st.session_state.current_quarter = 0
                st.session_state.historical_running = True
                st.session_state.engine.reset_learning()
        else:
            st.caption("Bu lig için ünlü maç yok.")

    if st.button("🔁 MOTORU SIFIRLA", use_container_width=True, key="_sb_reset"):
        st.session_state.engine.reset_learning()
        st.session_state.current_quarter = 0
        st.session_state.historical_running = False
        st.session_state.historical_quarters = {}
        st.session_state.order_log = st.session_state.order_log.iloc[0:0]
        st.success("Motor ve emirler sıfırlandı.")

    # ------------------------------------------------------------------ MENU 3
    st.markdown("## ⚙️ AYARLAR")

    ctx_keys = list(cfg.CONTEXTUAL_MODIFIERS.keys())
    default_ctx = st.session_state.get("context_tag", "Normal_Season_Match")
    if default_ctx not in ctx_keys:
        default_ctx = "Normal_Season_Match"
    context_tag = st.selectbox(
        "Maç Bağlamı",
        ctx_keys,
        index=ctx_keys.index(default_ctx),
        format_func=lambda k: f"{cfg.CONTEXTUAL_MODIFIERS[k]['emoji']} "
                              f"{cfg.CONTEXTUAL_MODIFIERS[k]['label']}",
        key="_sb_ctx",
    )
    st.session_state.context_tag = context_tag
    ctx_meta = cfg.CONTEXTUAL_MODIFIERS[context_tag]
    st.caption(
        f"⏱️ Tempo ×{ctx_meta['pace_multiplier']:.2f} · "
        f"📊 Varyans ×{ctx_meta['variance_multiplier']:.2f}  \n"
        f"🏟️ {league}: tempo ×{cfg.get_league_pace(league):.2f}, "
        f"varyans ×{cfg.get_league_variance(league):.2f}"
    )


# -----------------------------------------------------------------------------
# Başlık
# -----------------------------------------------------------------------------
st.markdown("# 🏀 GoldenBet AI · Patron Komut Paneli")
st.caption(
    "NBA · EuroLeague · EuroCup — Adaptif Monte Carlo Motoru · "
    "Logaritmik Kasa Yönetimi · Bilgi Yoğunluğuna Göre Emir"
)


# -----------------------------------------------------------------------------
# Üst Metric Bar
# -----------------------------------------------------------------------------
_match_label = (
    st.session_state.selected_match["label"]
    if st.session_state.selected_match else "—"
)
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(
        "Aktif Eşleşme",
        _match_label,
        delta=st.session_state.league,
    )
with col2:
    spent = float(
        st.session_state.prematch_orders["Tutar (₺)"].sum()
        if not st.session_state.prematch_orders.empty
        else 0.0
    )
    if not st.session_state.order_log.empty and "Tutar (₺)" in st.session_state.order_log.columns:
        spent = float(pd.to_numeric(
            st.session_state.order_log["Tutar (₺)"], errors="coerce"
        ).sum())
    st.metric("Harcanan Kasa (₺)", f"{spent:,.2f}")
with col3:
    if st.session_state.last_prediction is not None:
        pred_score = st.session_state.last_prediction.get("final_predicted_score", 0.0)
        conf = st.session_state.last_prediction.get("confidence_pct")
        conf_str = f"· Güven {conf:.1f}%" if conf is not None else ""
        st.metric(
            "AI Projeksiyon Skoru",
            f"{pred_score:.1f}",
            delta=f"Şu an {current_score} · Kalan {int(current_minute)} dk{conf_str}",
        )
    else:
        st.metric("AI Projeksiyon Skoru", "—", delta=f"Kalan {int(current_minute)} dk")
with col4:
    expected_pnl = 0.0
    if st.session_state.last_prediction is not None and st.session_state.last_signal is not None:
        conf = st.session_state.last_prediction.get("confidence_pct") or 0.0
        sig = st.session_state.last_signal
        if sig["order"] == "ÜST":
            expected_pnl = (conf / 100.0) * (odds - 1.0) - (1.0 - conf / 100.0)
        elif sig["order"] == "ALT (HEDGE)":
            expected_pnl = 0.05
        else:
            expected_pnl = -0.01
        expected_pnl = expected_pnl * budget
    st.metric("Beklenen P&L (₺)", f"{expected_pnl:+,.2f}")


# -----------------------------------------------------------------------------
# Yapısal Kural Matrisi — Lig ve Bağlam Özeti
# -----------------------------------------------------------------------------
st.markdown("## 🧬 YAPISAL KURAL MATRİSİ (STRUCTURAL RULES)")
_active_league = st.session_state.league
_lg_var = cfg.get_league_variance(_active_league)
_lg_pace = cfg.get_league_pace(_active_league)
_lg_minutes = cfg.get_total_minutes(_active_league)
_ctx_meta = cfg.CONTEXTUAL_MODIFIERS[context_tag]
_lc1, _lc2, _lc3 = st.columns(3)
with _lc1:
    st.metric(
        f"{_active_league} · Temel Varyans",
        f"×{_lg_var:.2f}",
        delta=("Geniş dağılım" if _lg_var > 1.0
               else "Dar dağılım" if _lg_var < 1.0 else "Standart"),
    )
with _lc2:
    st.metric(
        "Lig Tempo Çarpanı",
        f"×{_lg_pace:.2f}",
        delta=f"{_lg_minutes} dk · "
              f"{cfg.LEAGUE_PERIODS[_active_league]}× "
              f"{cfg.LEAGUE_PERIOD_MINUTES[_active_league]} dk/çeyrek",
    )
with _lc3:
    st.metric(
        f"Bağlam · {ctx_meta['emoji']} {_ctx_meta['label']}",
        f"Pace ×{_ctx_meta['pace_multiplier']:.2f}",
        delta=f"Varyans ×{_ctx_meta['variance_multiplier']:.2f}",
    )
st.caption(f"🏟️ {_active_league} oyun akışı: {cfg.LEAGUE_TIMING_NOTES.get(_active_league, '')}")


# -----------------------------------------------------------------------------
# Yapay Zeka Öğrenme Paneli
# -----------------------------------------------------------------------------
st.markdown("## 🧠 YAPAY ZEKA ÖĞRENME PANELİ (SELF-LEARNING MONITOR)")
colA, colB, colC = st.columns(3)
hist_df = st.session_state.engine.history_dataframe()
with colA:
    st.metric("Anlık Model Sapma (MAE)", f"{st.session_state.engine.current_mae():.2f}")
with colB:
    st.metric("Güncellenmiş Bias Weight", f"{st.session_state.engine.bias_weight:+.3f}")
with colC:
    st.metric("Variance Modifier", f"{st.session_state.engine.variance_modifier:.3f}")

if not hist_df.empty:
    st.markdown("##### Kalibrasyon Yakınsama Grafiği")
    st.line_chart(hist_df.set_index("Çeyrek")[["Hata", "MAE"]], height=220)
    with st.expander("📜 Öğrenme Günlüğü (tüm çeyrekler)"):
        st.dataframe(hist_df, use_container_width=True, hide_index=True)
else:
    st.info("Henüz öğrenme verisi yok. Canlı modda tahmin üretin veya "
            "tarihsel zaman tünelini başlatın.")


# -----------------------------------------------------------------------------
# Orta Neon Direktif Kutusu
# -----------------------------------------------------------------------------
prediction: Optional[Dict[str, Any]] = None
signal: Optional[Dict[str, str]] = None
context_tag = st.session_state.get("context_tag", "Normal_Season_Match")
if (not st.session_state.historical_running
        and st.session_state.baseline_avg > 0):
    prediction = st.session_state.engine.predict_remaining_game(
        current_score=current_score,
        current_minute=current_minute,
        baseline_avg=st.session_state.baseline_avg,
        bookmaker_line=market_line,
        total_minutes=total_minutes,
        context_tag=context_tag,
        league=st.session_state.league,
    )
    st.session_state.last_prediction = prediction
    signal = eng.generate_signal(
        ai_pred=prediction["final_predicted_score"],
        market_line=market_line,
        confidence_pct=prediction.get("confidence_pct"),
    )
    st.session_state.last_signal = signal
    st.session_state.live_order = eng.build_live_order_plan(
        budget=budget, signal=signal,
        current_minute=current_minute,
        total_minutes=total_minutes, odds=odds,
    )
    if not st.session_state.live_order.empty:
        live_row = st.session_state.live_order.iloc[0].to_dict()
        live_row["Zaman"] = time.strftime("%H:%M:%S")
        live_row["Not"] = (
            f"AI={prediction['final_predicted_score']:.1f} | "
            f"Şirket={market_line:.1f} | Sapma={signal['diff']}"
        )
        if not st.session_state.order_log.empty:
            mask = st.session_state.order_log["Faz"] == live_row["Faz"]
            st.session_state.order_log = st.session_state.order_log.loc[~mask]
        st.session_state.order_log = pd.concat(
            [st.session_state.order_log, pd.DataFrame([live_row])],
            ignore_index=True,
        )
    if (not st.session_state.prematch_orders.empty
            and st.session_state.order_log.empty):
        for _, row in st.session_state.prematch_orders.iterrows():
            r = row.to_dict()
            r["Zaman"] = time.strftime("%H:%M:%S")
            r["Not"] = "Maç öncesi pusu merdiveni"
            st.session_state.order_log = pd.concat(
                [st.session_state.order_log, pd.DataFrame([r])],
                ignore_index=True,
            )

if signal is not None and prediction is not None:
    order_class = "tag-strong" if signal["order"] == "ÜST" else \
                  "tag-hedge" if signal["order"].startswith("ALT") else "tag-pass"
    if not st.session_state.live_order.empty:
        amount = float(st.session_state.live_order.iloc[0]["Tutar (₺)"])
    else:
        amount = 0.0
    eff_base = prediction.get("effective_baseline", st.session_state.baseline_avg)
    pace_str = f"Pace ×{prediction.get('context_pace_multiplier', 1.0):.2f}"
    var_str = f"Var ×{prediction.get('context_variance_multiplier', 1.0):.2f}"
    league_var = prediction.get("league_variance", 1.0)
    ctx_emoji = ctx_meta.get("emoji", "")
    ctx_label = ctx_meta.get("label", context_tag)
    neon_html = f"""
    <div class="neon-box">
        <div class="neon-title">⚡ PATRON AKSİYON TALİMATI ⚡</div>
        <div class="neon-action">
            {amount:,.0f} ₺ &nbsp;·&nbsp; <span class="{order_class}">{signal['order']}</span>
        </div>
        <div class="neon-sub">
            AI Tahmin: <b>{prediction['final_predicted_score']:.1f}</b> &nbsp;|&nbsp;
            Piyasa: <b>{market_line:.1f}</b> &nbsp;|&nbsp;
            Sapma: <b>{signal['diff']}</b> &nbsp;|&nbsp;
            Güven: <b>{signal['confidence']}</b>
        </div>
        <div class="neon-sub" style="margin-top:8px;">
            p10={prediction['p10']:.1f} · p50={prediction['p50']:.1f} · p90={prediction['p90']:.1f}
        </div>
        <div class="neon-sub" style="margin-top:10px; font-size:0.85rem; color:#6B7280;">
            {ctx_emoji} {ctx_label} &nbsp;|&nbsp;
            Effective Baseline: <b>{eff_base:.1f}</b> &nbsp;|&nbsp;
            Lig Varyans ×{league_var:.2f} &nbsp;|&nbsp;
            {pace_str} &nbsp;|&nbsp; {var_str}
        </div>
    </div>
    """
else:
    neon_html = """
    <div class="neon-box" style="border-color:#374151;">
        <div class="neon-title" style="color:#9CA3AF;">⏳ SİSTEM HAZIR DEĞİL</div>
        <div class="neon-sub">
            Soldan lig + sezon seçildiğinde fikstür otomatik yüklenir.
        </div>
    </div>
    """
st.markdown(neon_html, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Tarihsel Zaman Tüneli
# -----------------------------------------------------------------------------
if st.session_state.historical_mode and st.session_state.historical_running:
    st.markdown("## ⏳ ZAMAN TÜNELİ · " + st.session_state.historical_label)
    q_now = st.session_state.current_quarter
    quarters = st.session_state.historical_quarters

    if quarters:
        baseline_for_q = float(st.session_state.baseline_avg) or 220.0
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button("▶ ADIM AT (Sonraki Çeyrek)", use_container_width=True):
                if q_now < 4:
                    st.session_state.current_quarter = q_now + 1
        with c2:
            auto = st.checkbox("🤖 OTOMATİK OYNAT (1.2s/adım)", value=False)
        with c3:
            st.progress(
                min(q_now / 4.0, 1.0),
                text=f"Çeyrek {q_now}/4 tamamlandı",
            )

        if 0 < q_now <= 4 and q_now in quarters:
            cur_q_start_cum = quarters.get(q_now - 1, 0.0)
            cur_q_end_cum = quarters[q_now]
            per_q_minutes = total_minutes // 4
            minute_at_q_end = per_q_minutes * q_now

            engine_obj: eng.AdaptiveMonteCarloEngine = st.session_state.engine
            result = engine_obj.predict_remaining_game(
                current_score=cur_q_start_cum,
                current_minute=minute_at_q_end - per_q_minutes,
                baseline_avg=baseline_for_q,
                bookmaker_line=None,
                total_minutes=per_q_minutes,
                context_tag=st.session_state.get("context_tag", "Normal_Season_Match"),
                league=st.session_state.league,
            )
            predicted_q_end = result["final_predicted_score"]
            actual_q_end = cur_q_end_cum
            error = engine_obj.update_learning_weights(
                quarter=q_now,
                predicted_at_quarter=predicted_q_end,
                actual_at_quarter=actual_q_end,
            )
            st.session_state.last_prediction = result
            st.session_state.last_signal = eng.generate_signal(
                ai_pred=predicted_q_end,
                market_line=actual_q_end,
                confidence_pct=None,
            )
            st.toast(
                f"Q{q_now} → Model Eğitildi (Bias: {engine_obj.bias_weight:+.2f}, "
                f"MAE: {engine_obj.current_mae():.2f})",
                icon="🧠",
            )

            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric(f"Q{q_now} Tahmin", f"{predicted_q_end:.1f}")
            cc2.metric(f"Q{q_now} Gerçek", f"{actual_q_end:.1f}")
            cc3.metric("Hata (Sapma)", f"{error:+.2f}")
            cc4.metric("MAE", f"{engine_obj.current_mae():.2f}")

        if auto and q_now < 4:
            time.sleep(1.2)
            st.session_state.current_quarter = q_now + 1
            st.rerun()

        if q_now >= 4:
            st.success("🏁 Maç tamamlandı. Model tamamen kalibre edildi.")
    else:
        st.warning("Bu maçın çeyrek verisi yüklenemedi.")


# -----------------------------------------------------------------------------
# Alt: Canlı Portföy Emir Defteri
# -----------------------------------------------------------------------------
st.markdown("## 📋 CANLI PORTFÖY EMİR DEFTERİ")
log = st.session_state.order_log
if log.empty:
    st.info("Henüz emir yok. Yukarıdaki slider'la oyna veya tarihsel modu başlat.")
else:
    st.dataframe(log, use_container_width=True, hide_index=True, height=300)


# -----------------------------------------------------------------------------
# Backtest Sonuçları
# -----------------------------------------------------------------------------
st.markdown("## 🧪 BACKTEST SONUÇLARI")
bt = st.session_state.backtest_result
if bt and bt.get("total_simulations", 0) > 0:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("İsabet Oranı", f"{bt['hit_rate_pct']:.1f}%")
    c2.metric("ROI", f"{bt['roi_pct']:+.2f}%")
    c3.metric("Simülasyon Sayısı", f"{bt['total_simulations']}")
    c4.metric("Ortalama Sapma", f"{bt['avg_diff']:+.2f}")
    with st.expander("Maç Detayları"):
        st.dataframe(bt["details"], use_container_width=True, hide_index=True)
else:
    st.caption("Soldaki 🧪 BACKTEST SİMÜLASYONU butonu ile çalıştır.")


# -----------------------------------------------------------------------------
# Geçmiş Veri Önizleme
# -----------------------------------------------------------------------------
st.markdown("## 📚 GEÇMİŞ VERİ ÖNİZLEME")
if st.session_state.df_history.empty:
    st.caption("Soldan lig + sezon seçildiğinde fikstür burada görüntülenir.")
else:
    st.dataframe(
        st.session_state.df_history.tail(15),
        use_container_width=True, hide_index=True,
    )
