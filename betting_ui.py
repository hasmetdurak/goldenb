"""
GoldenBet AI - Bahis Paneli UI Bilesenleri
===========================================

Streamlit icin bahis simulatörü UI bilesenleri:
- Strateji secimi ve yapilandirma
- Bankroll takip paneli
- Bahis gecmisi tablosu
- Simulasyon sonuc karti
- Strateji karsilastirma grafikleri
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from betting_simulator import (
    STRATEGY_DESCRIPTIONS,
    Bankroll,
    BetResult,
    StrategyType,
    monte_carlo_simulation,
    optimize_strategy,
    run_betting_simulation,
)


def render_strategy_selector() -> StrategyType:
    """Sidebar'da strateji secimi."""
    strategies = {
        "Kelly Criterion (Optimal)": StrategyType.KELLY,
        "Flat Betting (Sabit)": StrategyType.FLAT,
        "Value Betting (Edge)": StrategyType.VALUE,
        "Martingale (Riskli)": StrategyType.MARTINGALE,
    }
    labels = list(strategies.keys())
    default_idx = 0
    choice = st.sidebar.selectbox(
        "Bahis Stratejisi", labels, index=default_idx, key="_bet_strategy"
    )
    return strategies[choice]


def render_betting_config(strategy: StrategyType) -> dict[str, Any]:
    """Sidebar'da bahis konfigurasyonu."""
    config = {}
    with st.sidebar.expander("Bahis Ayarlari", expanded=False):
        config["initial_bankroll"] = st.number_input(
            "Baslangic Bakiye (TL)",
            min_value=100,
            max_value=1_000_000,
            value=10_000,
            step=500,
            key="_bet_bankroll",
        )
        config["unit_stake"] = st.number_input(
            "Birim Bahis (TL)", min_value=10, max_value=10_000, value=100, step=10, key="_bet_unit"
        )
        if strategy == StrategyType.KELLY:
            config["kelly_fraction"] = st.slider(
                "Kelly Kesri",
                0.05,
                1.0,
                0.25,
                0.05,
                help="0.25 = conservative, 0.50 = aggressive, 1.0 = full Kelly",
                key="_bet_kelly_frac",
            )
        if strategy == StrategyType.VALUE:
            config["value_threshold"] = st.slider(
                "Edge Esik Degeri",
                0.0,
                0.20,
                0.05,
                0.01,
                help="Minimum edge yuzdesi (0.05 = %5)",
                key="_bet_value_thresh",
            )
        config["drawdown_limit"] = st.slider(
            "Max Drawdown",
            0.10,
            0.50,
            0.25,
            0.05,
            help="Ornegin 0.25 = %25 dususte dur",
            key="_bet_drawdown",
        )
    return config


def render_strategy_info(strategy: StrategyType) -> None:
    """Strateji hakkinda bilgi gosterir."""
    info = STRATEGY_DESCRIPTIONS.get(strategy, {})
    if info:
        st.sidebar.caption(
            f"**{info.get('name', strategy.value)}**  |  "
            f"Risk: {info.get('risk', 'N/A')}  |  "
            f"{info.get('description', '')}"
        )


def render_bankroll_card(bankroll: Bankroll) -> None:
    """Bankroll durum karti."""
    s = bankroll.summary()
    cols = st.columns(5)
    with cols[0]:
        st.metric(
            "Bakiye",
            f"${s['current']:,.0f}",
            delta=f"${s['total_pnl']:+,.0f}",
            delta_color="normal",
        )
    with cols[1]:
        st.metric("ROI", f"%{s['roi_pct']:+.2f}", delta_color="off")
    with cols[2]:
        st.metric(
            "Kazanma Orani",
            f"%{s['win_rate']:.1f}",
            delta=f"{s['wins']}/{s['losses']} W/L",
            delta_color="normal",
        )
    with cols[3]:
        st.metric("Drawdown", f"%{s['drawdown_pct']:.1f}", delta_color="inverse")
    with cols[4]:
        st.metric("Sharpe", f"{s['sharpe_ratio']:.2f}", delta_color="off")


def render_bet_history(bankroll: Bankroll) -> None:
    """Bahis gecmisi tablosu."""
    if not bankroll.bet_history:
        st.caption("Henuz bahis kaydi yok.")
        return

    rows = []
    for b in bankroll.bet_history:
        _labels = {BetResult.WIN: "K", BetResult.LOSS: "M", BetResult.PUSH: "I"}
        result_label = _labels.get(b.result, "?") if b.result is not None else "?"
        rows.append(
            {
                "Mac": f"{b.home_team}-{b.away_team}"[:20],
                "Lig": b.league,
                "Tahmin": f"{b.predicted_total:.0f}",
                "Piyasa": f"{b.market_total:.0f}",
                "Oran": f"{b.odds:.2f}",
                "Yon": "Over" if b.is_over else "Under",
                "Stake": f"${b.stake:.0f}",
                "Sonuc": result_label,
                "Kar/Zarar": f"${b.pnl:+.0f}",
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={"Kar/Zarar": st.column_config.NumberColumn("Kar/Zarar", format="$%+d")},
    )


def render_betting_dashboard(
    predictions: list[dict[str, Any]],
    actual_results: list[dict[str, Any]],
    strategy: StrategyType,
    config: dict[str, Any],
) -> None:
    """Ana bahis dashboardu."""
    st.subheader(" Bahis Simulatörü Dashboard")

    # Simulasyonu calistir
    with st.spinner("Bahis simulasyonu calisiyor..."):
        bankroll = run_betting_simulation(
            predictions,
            actual_results,
            strategy=strategy,
            initial_bankroll=config.get("initial_bankroll", 10_000),
            unit_stake=config.get("unit_stake", 100),
            kelly_fraction=config.get("kelly_fraction", 0.25),
            value_threshold=config.get("value_threshold", 0.05),
            drawdown_limit=config.get("drawdown_limit", 0.25),
        )

    # Bankroll karti
    render_bankroll_card(bankroll)

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("##### Bahis Gecmisi")
        render_bet_history(bankroll)

    with col2:
        st.markdown("##### Strateji Dagitimi")
        summary = bankroll.summary()
        metrics_df = pd.DataFrame(
            [
                {"Metrik": "Toplam Bahis", "Deger": summary["total_bets"]},
                {"Metrik": "Kazanan", "Deger": summary["wins"]},
                {"Metrik": "Kaybeden", "Deger": summary["losses"]},
                {"Metrik": "Toplam Stake", "Deger": f"${summary['total_staked']:,.0f}"},
                {"Metrik": "Net Kar/Zarar", "Deger": f"${summary['total_pnl']:+,.0f}"},
                {"Metrik": "ROI", "Deger": f"%{summary['roi_pct']:+.2f}"},
                {"Metrik": "Max Drawdown", "Deger": f"%{summary['drawdown_pct']:.1f}"},
                {"Metrik": "Sharpe Ratio", "Deger": f"{summary['sharpe_ratio']:.3f}"},
                {
                    "Metrik": "Iflas Durumu",
                    "Deger": "Evet" if summary["is_bankrupted"] else "Hayir",
                },
            ]
        )
        st.dataframe(metrics_df, use_container_width=True, hide_index=True)

    # Monte Carlo simulasyonu
    with st.expander("Monte Carlo Simulasyonu (1000 iterasyon)", expanded=False):
        if st.button("MC Simulasyonu Calistir", key="_mc_run"):
            with st.spinner(f"{config.get('mc_iterations', 500)} iterasyon calisiyor..."):
                mc_df = monte_carlo_simulation(
                    predictions,
                    actual_results,
                    strategy=strategy,
                    num_simulations=config.get("mc_iterations", 500),
                    initial_bankroll=config.get("initial_bankroll", 10_000),
                    unit_stake=config.get("unit_stake", 100),
                    kelly_fraction=config.get("kelly_fraction", 0.25),
                )
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Ortalama ROI", f"%{mc_df['roi_pct'].mean():+.2f}")
                st.metric("Medyan ROI", f"%{mc_df['roi_pct'].median():+.2f}")
                st.metric("ROI Std", f"%{mc_df['roi_pct'].std():.2f}")
            with col_b:
                st.metric("Ortalama Bakiye", f"${mc_df['current'].mean():,.0f}")
                st.metric("Min Bakiye", f"${mc_df['current'].min():,.0f}")
                st.metric("Max Bakiye", f"${mc_df['current'].max():,.0f}")
            st.markdown("##### ROI Dagitimi")
            st.line_chart(mc_df[["roi_pct"]].reset_index(), x="index", y="roi_pct", height=200)

    return None


def render_strategy_comparison(
    predictions: list[dict[str, Any]], actual_results: list[dict[str, Any]], config: dict[str, Any]
) -> None:
    """Tum stratejileri karsilastir."""
    st.subheader(" Strateji Karsilastirmasi")

    results = []
    with st.spinner("Tum stratejiler test ediliyor..."):
        for strategy in StrategyType:
            if strategy == StrategyType.ARBITRAGE:
                continue
            br = run_betting_simulation(
                predictions,
                actual_results,
                strategy=strategy,
                initial_bankroll=config.get("initial_bankroll", 10_000),
                unit_stake=config.get("unit_stake", 100),
                kelly_fraction=config.get("kelly_fraction", 0.25),
            )
            s = br.summary()
            info = STRATEGY_DESCRIPTIONS.get(strategy, {})
            results.append(
                {
                    "Strateji": info.get("name", strategy.value),
                    "Risk": info.get("risk", ""),
                    "Net Kar": f"${s['total_pnl']:+,.0f}",
                    "ROI": f"%{s['roi_pct']:+.2f}",
                    "Win Rate": f"%{s['win_rate']:.1f}",
                    "Sharpe": f"{s['sharpe_ratio']:.3f}",
                    "Drawdown": f"%{s['drawdown_pct']:.1f}",
                    "Toplam Bahis": s["total_bets"],
                }
            )

    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Gorsel karsilastirma
    chart_df = pd.DataFrame(results)
    if not chart_df.empty:
        chart_data = pd.DataFrame(
            {s["Strateji"]: float(s["ROI"].replace("%", "").replace("+", "")) for s in results},
            index=[0],
        ).T.reset_index()
        chart_data.columns = ["Strateji", "ROI"]
        st.bar_chart(chart_data.set_index("Strateji"), height=250)


def render_betting_tab(
    predictions: list[dict[str, Any]], actual_results: list[dict[str, Any]]
) -> None:
    """Ana bahis tabini komple render et."""
    if not predictions:
        st.info("Bahis simulasyonu icin once mac verisi yuklenmeli.")
        return
    if not actual_results:
        st.caption(
            "Maç henüz sonuçlanmadı — bahis değerlendirmesi final skoru çekildiğinde yapılır."
        )
        return

    strategy = render_strategy_selector()
    render_strategy_info(strategy)
    config = render_betting_config(strategy)

    tab1, tab2, tab3 = st.tabs(["Simulasyon", "Strateji Karsilastirma", "Optimizasyon"])

    with tab1:
        render_betting_dashboard(predictions, actual_results, strategy, config)

    with tab2:
        render_strategy_comparison(predictions, actual_results, config)

    with tab3:
        st.subheader(" Strateji Optimizasyonu")
        st.caption("Grid search ile en iyi parametreler bulunur.")
        if st.button("Optimize Et", key="_opt_run", type="primary"):
            with st.spinner("Optimizasyon calisiyor..."):
                best_config, best_summary = optimize_strategy(
                    predictions, actual_results, strategy=strategy
                )
            st.success("Optimizasyon tamamlandi!")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("##### En Iyi Parametreler")
                params_df = pd.DataFrame(
                    [
                        {"Parametre": k.replace("_", " ").title(), "Deger": v}
                        for k, v in best_config.to_dict().items()
                    ]
                )
                st.dataframe(params_df, use_container_width=True, hide_index=True)
            with col_b:
                st.markdown("##### Performans")
                perf_df = pd.DataFrame(
                    [
                        {"Metrik": k.replace("_", " ").title(), "Deger": str(v)}
                        for k, v in best_summary.items()
                        if k != "is_bankrupted" and k != "is_drawdown_hit"
                    ]
                )
                st.dataframe(perf_df, use_container_width=True, hide_index=True)
