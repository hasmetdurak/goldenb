"""
GoldenBet AI - Patron Komut Paneli
==================================

Streamlit tabanlı dark-mode trading arayüzü.

Akış
----
1) Sidebar → kasa, lig, sezon, takım seçilir.
2) "GEÇMİŞ VERİLERİ ÇEK" tıklanır → data_fetcher → session_state.
3) Canlı slider/input'lar değiştikçe AdaptiveMonteCarloEngine tahmin üretir.
4) Sinyal (ÜST/ALT/PAS) + tutar hesaplanır, neon kutuya yazılır.
5) Emir defterine yeni satır eklenir.
6) İsteğe bağlı: "Tarihsel Derin Öğrenme" modunda ünlü maçın çeyrekleri
   üzerinden motor otomatik kalibre edilir.
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
# CSS — Neon Trading Ekranı
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
}

[data-testid="stMetricValue"] {
    color: #00FF7F !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 800 !important;
}

[data-testid="stMetricLabel"] {
    color: #9CA3AF !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.75rem !important;
}

.neon-box {
    border: 2px solid #FF1744;
    border-radius: 14px;
    padding: 28px 32px;
    background: linear-gradient(135deg, rgba(0,255,127,0.06), rgba(0,0,0,0.5));
    box-shadow: 0 0 18px rgba(255,23,68,0.4), inset 0 0 18px rgba(0,255,127,0.05);
    animation: pulse 1.6s ease-in-out infinite;
    text-align: center;
    margin: 14px 0;
}
@keyframes pulse {
    0%, 100% { box-shadow: 0 0 18px rgba(255,23,68,0.4), inset 0 0 18px rgba(0,255,127,0.05); }
    50%      { box-shadow: 0 0 32px rgba(255,23,68,0.7), inset 0 0 24px rgba(0,255,127,0.10); }
}
.neon-title {
    color: #00FF7F;
    font-size: 1.4rem;
    font-weight: 800;
    letter-spacing: 0.2em;
    margin-bottom: 12px;
    text-transform: uppercase;
}
.neon-action {
    color: #FFFFFF;
    font-size: 2.4rem;
    font-weight: 800;
    margin: 12px 0;
    text-shadow: 0 0 12px #00FF7F;
}
.neon-sub {
    color: #9CA3AF;
    font-size: 1.0rem;
    letter-spacing: 0.1em;
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


_init_state()


# -----------------------------------------------------------------------------
# NBA Takım Listesi (lazy cache)
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _nba_team_list() -> list[tuple[str, int]]:
    try:
        from nba_api.stats.static import teams as nba_static_teams
        teams = nba_static_teams.get_teams()
        return [(t["full_name"], int(t["id"])) for t in teams]
    except Exception:
        return []


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 💰 KASA & LİG")
    budget = st.number_input(
        "Toplam Kasa (₺)",
        min_value=100, max_value=1_000_000,
        value=10_000, step=500,
    )
    league = st.selectbox(
        "Lig",
        ["NBA", "EuroLeague", "EuroCup"],
        index=["NBA", "EuroLeague", "EuroCup"].index(st.session_state.league)
        if st.session_state.league in ["NBA", "EuroLeague", "EuroCup"] else 0,
    )
    st.session_state.league = league

    # Takım seçimi
    team_label = ""
    season = ""
    if league == "NBA":
        teams = _nba_team_list()
        team_names = [t[0] for t in teams] or ["Los Angeles Lakers"]
        default_idx = 0
        try:
            default_idx = team_names.index(st.session_state.team_label)
        except ValueError:
            pass
        team_label = st.selectbox("Takım", team_names, index=default_idx)
        season = st.text_input("NBA Sezonu", value="2024-25")
    else:
        team_label = st.text_input("Takım (filtre için)", value="Real Madrid")
        season = st.text_input(
            "Sezon Kodu (Euro*)",
            value="E2024" if league == "EuroLeague" else "U2024",
        )
    st.session_state.team_label = team_label

    st.markdown("---")
    st.markdown("## 📡 CANLI GÖZLEM")
    total_minutes = cfg.get_total_minutes(league)
    st.session_state.total_minutes = total_minutes

    current_minute = st.slider(
        f"Kalan Dakika (0–{total_minutes})",
        min_value=0, max_value=total_minutes,
        value=total_minutes // 2,
    )
    current_score = st.number_input(
        "Mevcut Toplam Skor",
        min_value=0, max_value=400, value=110, step=1,
    )
    market_line = st.number_input(
        "Şirket Canlı Baremi (ÜST/ALT)",
        min_value=80.0, max_value=400.0, value=215.0, step=0.5,
    )
    odds = st.number_input(
        "Bahis Oranı",
        min_value=1.01, max_value=5.00,
        value=eng.DEFAULT_ODDS, step=0.01,
    )

    st.markdown("---")
    st.markdown("## 🧬 MAÇ BAĞLAMI (CONTEXT TAG)")
    ctx_keys = list(cfg.CONTEXTUAL_MODIFIERS.keys())
    default_ctx = st.session_state.get("context_tag", "Normal_Season_Match")
    if default_ctx not in ctx_keys:
        default_ctx = "Normal_Season_Match"
    context_tag = st.selectbox(
        "Bağlam Etiketi",
        ctx_keys,
        index=ctx_keys.index(default_ctx),
        format_func=lambda k: f"{cfg.CONTEXTUAL_MODIFIERS[k]['emoji']} "
                              f"{cfg.CONTEXTUAL_MODIFIERS[k]['label']}",
    )
    st.session_state.context_tag = context_tag
    ctx_meta = cfg.CONTEXTUAL_MODIFIERS[context_tag]
    st.caption(
        f"📝 {ctx_meta['description']}  \n"
        f"⏱️ Tempo ×{ctx_meta['pace_multiplier']:.2f} · "
        f"📊 Varyans ×{ctx_meta['variance_multiplier']:.2f}  \n"
        f"🏟️ Lig temposu ×{cfg.get_league_pace(league):.2f} · "
        f"🎲 Lig varyansı ×{cfg.get_league_variance(league):.2f}"
    )

    st.markdown("---")
    st.markdown("## 📊 VERİ")
    if st.button("📥 GEÇMİŞ VERİLERİ ÇEK", use_container_width=True):
        with st.spinner("Veri çekiliyor…"):
            if league == "NBA":
                df = df_lib.fetch_nba_data(team_label, season=season)
                baseline = df_lib.compute_team_baseline(df, mode="nba")
            else:
                df = df_lib.fetch_euroleague_data(
                    season_code=season,
                    competition="E" if league == "EuroLeague" else "U",
                )
                baseline = df_lib.compute_team_baseline(df, mode="euro")
            st.session_state.df_history = df
            st.session_state.baseline_avg = baseline
            # İlk merdiven emirlerini oluştur
            ladder = eng.build_ladder_lines(baseline) if baseline > 0 else []
            st.session_state.prematch_orders = eng.build_prematch_orders(
                budget, ladder, odds=odds
            ) if ladder else pd.DataFrame()
        st.success(f"Tamamlandı → {len(df)} maç, baseline={baseline:.1f}")

    if st.button("🔁 MOTORU SIFIRLA", use_container_width=True):
        st.session_state.engine.reset_learning()
        st.session_state.current_quarter = 0
        st.session_state.historical_running = False
        st.session_state.historical_quarters = {}
        st.session_state.order_log = st.session_state.order_log.iloc[0:0]
        st.success("Motor ve emirler sıfırlandı.")

    st.markdown("---")
    st.markdown("## 🧬 TARİHSEL DERİN ÖĞRENME")
    historical_mode = st.checkbox(
        "Tarihsel modu aktifleştir",
        value=st.session_state.historical_mode,
    )
    st.session_state.historical_mode = historical_mode

    famous = df_lib.get_famous_games_for_league(league)
    if famous:
        labels = list(famous.keys())
        sel = st.selectbox("Ünlü Maç Seç", labels)
        if st.button("⏩ ZAMAN TÜNELİNİ BAŞLAT", use_container_width=True):
            st.session_state.historical_label = sel
            st.session_state.historical_quarters = df_lib.fetch_famous_game_quarters(sel)
            st.session_state.current_quarter = 0
            st.session_state.historical_running = True
            st.session_state.engine.reset_learning()
    else:
        st.info("Bu lig için tanımlı ünlü maç yok.")

    st.markdown("---")
    st.markdown("## 🧪 BACKTEST")
    if st.button("▶ BACKTEST SİMÜLASYONU", use_container_width=True):
        if st.session_state.df_history.empty or st.session_state.baseline_avg <= 0:
            st.warning("Önce veri çekmelisin.")
        else:
            with st.spinner("Backtest çalışıyor…"):
                st.session_state.backtest_result = eng.backtest(
                    df=st.session_state.df_history,
                    baseline_avg=st.session_state.baseline_avg,
                    total_minutes=total_minutes,
                )
            st.success("Backtest tamam.")


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
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(
        "Aktif Takım / Lig",
        f"{st.session_state.team_label or '—'}",
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
            expected_pnl = 0.05  # koruma primi
        else:
            expected_pnl = -0.01  # pas fırsat maliyeti
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
# 🧠 Yapay Zeka Öğrenme Paneli
# -----------------------------------------------------------------------------
st.markdown("## 🧠 YAPAY ZEKA ÖĞRENME PANELİ (SELF-LEARNING MONITOR)")
colA, colB, colC = st.columns(3)
hist_df = st.session_state.engine.history_dataframe()
with colA:
    st.metric(
        "Anlık Model Sapma (MAE)",
        f"{st.session_state.engine.current_mae():.2f}",
    )
with colB:
    st.metric(
        "Güncellenmiş Bias Weight",
        f"{st.session_state.engine.bias_weight:+.3f}",
    )
with colC:
    st.metric(
        "Variance Modifier",
        f"{st.session_state.engine.variance_modifier:.3f}",
    )

if not hist_df.empty:
    st.markdown("##### Kalibrasyon Yakınsama Grafiği")
    st.line_chart(
        hist_df.set_index("Çeyrek")[["Hata", "MAE"]],
        height=220,
    )
    with st.expander("📜 Öğrenme Günlüğü (tüm çeyrekler)"):
        st.dataframe(hist_df, use_container_width=True, hide_index=True)
else:
    st.info("Henüz öğrenme verisi yok. Canlı modda tahmin üretin veya "
            "tarihsel zaman tünelini başlatın.")


# -----------------------------------------------------------------------------
# Orta Neon Direktif Kutusu
# -----------------------------------------------------------------------------
# Canlı modda motor tahminini hesapla (reactive)
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
    # Canlı emir planı
    st.session_state.live_order = eng.build_live_order_plan(
        budget=budget, signal=signal,
        current_minute=current_minute,
        total_minutes=total_minutes, odds=odds,
    )
    # Emir defterine ekle (sadece yeni emirse)
    if not st.session_state.live_order.empty:
        live_row = st.session_state.live_order.iloc[0].to_dict()
        live_row["Zaman"] = time.strftime("%H:%M:%S")
        live_row["Not"] = (
            f"AI={prediction['final_predicted_score']:.1f} | "
            f"Şirket={market_line:.1f} | Sapma={signal['diff']}"
        )
        # Aynı anda yalnızca 1 canlı emir; mevcut canlı satırı güncelle
        if not st.session_state.order_log.empty:
            mask = st.session_state.order_log["Faz"] == live_row["Faz"]
            st.session_state.order_log = st.session_state.order_log.loc[~mask]
        st.session_state.order_log = pd.concat(
            [st.session_state.order_log, pd.DataFrame([live_row])],
            ignore_index=True,
        )
    # Prematch emirlerini de ilk defa ekle
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


# Neon kutu içeriğini hazırla
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
            Soldan "GEÇMİŞ VERİLERİ ÇEK" tıkla, motor tahmin üretsin.
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

        # Gösterilecek mevcut çeyrek: q_now
        if 0 < q_now <= 4 and q_now in quarters:
            cur_q_start_cum = quarters.get(q_now - 1, 0.0)
            cur_q_end_cum = quarters[q_now]
            per_q_minutes = total_minutes // 4
            minute_at_q_end = per_q_minutes * q_now

            # ADAPTİF MOTOR — başlangıç: bias=0, nötr tahmin
            # Şu anki kümülatif tahmin (q_now sonu)
            engine: eng.AdaptiveMonteCarloEngine = st.session_state.engine
            result = engine.predict_remaining_game(
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
            error = engine.update_learning_weights(
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
                f"Q{q_now} → Model Eğitildi (Bias: {engine.bias_weight:+.2f}, "
                f"MAE: {engine.current_mae():.2f})",
                icon="🧠",
            )

            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric(f"Q{q_now} Tahmin", f"{predicted_q_end:.1f}")
            cc2.metric(f"Q{q_now} Gerçek", f"{actual_q_end:.1f}")
            cc3.metric("Hata (Sapma)", f"{error:+.2f}")
            cc4.metric("MAE", f"{engine.current_mae():.2f}")

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
    st.caption("Soldaki ▶ BACKTEST SİMÜLASYONU butonu ile çalıştır.")


# -----------------------------------------------------------------------------
# Geçmiş Veri Önizleme
# -----------------------------------------------------------------------------
st.markdown("## 📚 GEÇMİŞ VERİ ÖNİZLEME")
if st.session_state.df_history.empty:
    st.caption("Soldan veri çek → burada görüntülenir.")
else:
    st.dataframe(
        st.session_state.df_history.tail(15),
        use_container_width=True, hide_index=True,
    )
