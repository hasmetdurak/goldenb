from __future__ import annotations

import pytest

from betting_simulator import (
    Bankroll,
    Bet,
    BetResult,
    StrategyConfig,
    StrategyType,
    edge_calculation,
    find_best_line,
    flat_stake,
    implied_probability,
    kelly_optimal_bet,
    kelly_stake,
    martingale_stake,
    monte_carlo_simulation,
    optimize_strategy,
    remove_vig,
    run_betting_simulation,
    simulate_book_odds,
    value_stake,
    walk_forward_backtest,
)


class TestBet:
    def test_bet_creation(self):
        bet = Bet(
            game_id="G1",
            league="NBA",
            home_team="LAL",
            away_team="BOS",
            predicted_total=220,
            market_total=215,
            odds=1.91,
            stake=100,
            side="over",
        )
        assert bet.is_over is True
        assert bet.is_winner is None
        assert bet.result is None

    def test_bet_win_calculation(self):
        bet = Bet(
            game_id="G1",
            league="NBA",
            home_team="LAL",
            away_team="BOS",
            predicted_total=220,
            market_total=215,
            odds=2.0,
            stake=100,
            side="over",
            result=BetResult.WIN,
            actual_total=225,
        )
        assert bet.payout == 200.0
        assert bet.pnl == 100.0

    def test_bet_loss_calculation(self):
        bet = Bet(
            game_id="G1",
            league="NBA",
            home_team="LAL",
            away_team="BOS",
            predicted_total=220,
            market_total=215,
            odds=2.0,
            stake=100,
            side="over",
            result=BetResult.LOSS,
            actual_total=200,
        )
        assert bet.payout == 0.0
        assert bet.pnl == -100.0

    def test_bet_push(self):
        bet = Bet(
            game_id="G1",
            league="NBA",
            home_team="LAL",
            away_team="BOS",
            predicted_total=220,
            market_total=220,
            odds=1.91,
            stake=100,
            side="over",
            result=BetResult.PUSH,
            actual_total=220,
        )
        assert bet.payout == 100.0
        assert bet.pnl == 0.0


class TestBankroll:
    def test_initial_state(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        assert br.roi == 0.0
        assert br.win_rate == 0.0
        assert br.drawdown == 0.0
        assert br.is_bankrupted is False
        assert br.is_drawdown_hit is False

    def test_win_increases_bankroll(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        bet = Bet(
            "G1",
            "NBA",
            "LAL",
            "BOS",
            220,
            215,
            2.0,
            100,
            "over",
            result=BetResult.WIN,
            actual_total=225,
            pnl=100.0,
        )
        br.record_bet(bet)
        assert br.current == 10100
        assert br.total_wins == 1
        assert br.total_pnl == 100.0
        assert br.total_staked == 100.0

    def test_loss_decreases_bankroll(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        bet = Bet(
            "G1",
            "NBA",
            "LAL",
            "BOS",
            220,
            215,
            2.0,
            100,
            "over",
            result=BetResult.LOSS,
            actual_total=200,
            pnl=-100.0,
        )
        br.record_bet(bet)
        assert br.current == 9900
        assert br.total_losses == 1

    def test_bankruptcy_detection(self):
        br = Bankroll(initial=100, current=0, peak=100)
        assert br.is_bankrupted is True

    def test_drawdown_calculation(self):
        br = Bankroll(initial=10000, current=8000, peak=10000, drawdown_limit=0.25)
        assert br.drawdown == 0.20
        assert br.is_drawdown_hit is False

    def test_drawdown_limit_hit(self):
        br = Bankroll(initial=10000, current=7000, peak=10000, drawdown_limit=0.25)
        assert br.drawdown == 0.30
        assert br.is_drawdown_hit is True

    def test_roi_calculation(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        bet = Bet(
            "G1",
            "NBA",
            "LAL",
            "BOS",
            220,
            215,
            2.0,
            100,
            "over",
            result=BetResult.WIN,
            actual_total=225,
            pnl=100.0,
        )
        br.record_bet(bet)
        assert br.roi == 100.0

    def test_can_bet_checks_bankrupt(self):
        br = Bankroll(initial=0, current=0, peak=0)
        assert br.can_bet(10) is False

    def test_summary_contains_keys(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        summary = br.summary()
        for key in ["initial", "current", "roi_pct", "win_rate", "sharpe_ratio"]:
            assert key in summary


class TestStakeCalculators:
    def test_kelly_stake_zero_when_no_edge(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        stake = kelly_stake(br, predicted_prob=0.4, odds=1.5)
        assert stake == 0.0

    def test_kelly_stake_positive(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        stake = kelly_stake(br, predicted_prob=0.6, odds=2.0, fraction=0.25)
        assert stake > 0
        assert stake <= br.current

    def test_flat_stake_limits_to_bankroll(self):
        br = Bankroll(initial=100, current=50, peak=100)
        stake = flat_stake(br, unit_stake=100)
        assert stake == 50.0

    def test_value_stake_no_edge(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        stake = value_stake(br, predicted_prob=0.4, odds=2.0, threshold=0.05)
        assert stake == 0.0

    def test_value_stake_with_edge(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        stake = value_stake(br, predicted_prob=0.6, odds=2.0, threshold=0.05)
        assert stake > 0

    def test_martingale_stake_doubles_after_loss(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        bet = Bet(
            "G1", "NBA", "LAL", "BOS", 220, 215, 2.0, 100, "over", result=BetResult.LOSS, pnl=-100.0
        )
        br.record_bet(bet)
        stake = martingale_stake(br, base_stake=100)
        assert stake == 200.0

    def test_kelly_optimal_bet(self):
        stake = kelly_optimal_bet(10000, 0.6, 2.0, fraction=0.25)
        expected = 10000 * ((1.0 * 0.6 - 0.4) / 1.0) * 0.25
        assert stake == expected


class TestEdgeAndOdds:
    def test_edge_calculation_positive(self):
        edge = edge_calculation(0.6, 2.0)
        assert edge == pytest.approx(0.2)

    def test_edge_calculation_negative(self):
        edge = edge_calculation(0.4, 2.0)
        assert edge == pytest.approx(-0.2)

    def test_implied_probability(self):
        prob = implied_probability(2.0)
        assert prob == 0.5

    def test_remove_vig(self):
        over, under = remove_vig(1.91, 1.91)
        assert over > 1.91
        assert under > 1.91

    def test_simulate_book_odds(self):
        books = simulate_book_odds(predicted_total=220, baseline_total=215, num_books=3)
        assert len(books) == 3
        for book in books:
            assert "book" in book
            assert book["over_odds"] > 0
            assert book["under_odds"] > 0

    def test_find_best_line(self):
        books = [
            {"book": "A", "over_odds": 1.85, "under_odds": 1.95},
            {"book": "B", "over_odds": 1.91, "under_odds": 1.91},
        ]
        best = find_best_line(books, "over")
        assert best["book"] == "B"


class TestSimulation:
    def test_run_betting_simulation_empty(self):
        br = run_betting_simulation([], [])
        assert br.total_bets == 0

    def test_run_betting_simulation_kelly(self):
        predictions = [
            {
                "total_predicted": 220,
                "league": "NBA",
                "effective_baseline_home": 112,
                "effective_baseline_away": 108,
            },
            {
                "total_predicted": 210,
                "league": "NBA",
                "effective_baseline_home": 108,
                "effective_baseline_away": 102,
            },
        ]
        actual_results = [{"total": 225}, {"total": 200}]
        br = run_betting_simulation(predictions, actual_results, strategy=StrategyType.FLAT)
        assert br.total_bets == 2

    def test_strategy_config_serialization(self):
        config = StrategyConfig()
        data = config.to_dict()
        assert data["strategy"] == "kelly"
        restored = StrategyConfig.from_dict(data)
        assert restored.strategy == StrategyType.KELLY

    def test_real_market_skip_unfinished(self):
        """Gerçek market olsa da maç bitmediyse bahis atılmaz."""
        preds = [
            {
                "total_predicted": 222.0,
                "league": "NBA",
                "effective_baseline_home": 112.0,
                "effective_baseline_away": 108.0,
                "market_total": 220.5,
                "odds_over": 1.91,
                "odds_under": 1.91,
                "prob_over_market": 0.60,
            }
        ]
        br = run_betting_simulation(preds, [], strategy=StrategyType.FLAT)
        assert br.total_bets == 0

    def test_real_market_over_bet_when_value(self):
        """Piyasaya göre yüksek olasılık + iyi oran → ÜST bahis ve kazanma."""
        preds = [
            {
                "total_predicted": 222.0,
                "league": "NBA",
                "effective_baseline_home": 112.0,
                "effective_baseline_away": 108.0,
                "market_total": 220.5,
                "odds_over": 2.20,
                "odds_under": 1.72,
                "prob_over_market": 0.60,
                "home_name": "Lakers",
                "away_name": "Celtics",
                "game_id": "0022400001",
            }
        ]
        actual = [{"total": 226}]
        br = run_betting_simulation(preds, actual, strategy=StrategyType.FLAT)
        assert br.total_bets == 1
        bet = br.bet_history[0]
        assert bet.side == "over"
        assert bet.actual_total == 226.0
        assert br.total_wins == 1

    def test_strategy_descriptions(self):
        from betting_simulator import STRATEGY_DESCRIPTIONS

        assert StrategyType.KELLY in STRATEGY_DESCRIPTIONS
        assert StrategyType.FLAT in STRATEGY_DESCRIPTIONS

    def test_monte_carlo_returns_dataframe(self):
        predictions = [
            {
                "total_predicted": 220,
                "league": "NBA",
                "effective_baseline_home": 112,
                "effective_baseline_away": 108,
            }
        ]
        actual_results = [{"total": 225}]
        df = monte_carlo_simulation(
            predictions, actual_results, strategy=StrategyType.FLAT, num_simulations=10
        )
        assert len(df) == 10
        assert "roi_pct" in df.columns

    def test_optimize_strategy(self):
        predictions = [
            {
                "total_predicted": 220,
                "league": "NBA",
                "effective_baseline_home": 112,
                "effective_baseline_away": 108,
            }
        ]
        actual_results = [{"total": 225}]
        config, summary = optimize_strategy(predictions, actual_results, strategy=StrategyType.FLAT)
        assert summary["total_bets"] > 0

    def test_bankroll_sharpe_with_multiple_bets(self):
        br = Bankroll(initial=10000, current=10000, peak=10000)
        for i in range(5):
            bet = Bet(
                f"G{i}",
                "NBA",
                "LAL",
                "BOS",
                220,
                215,
                2.0,
                100,
                "over",
                result=BetResult.WIN if i % 2 == 0 else BetResult.LOSS,
                actual_total=225 if i % 2 == 0 else 200,
                pnl=100.0 if i % 2 == 0 else -100.0,
            )
            br.record_bet(bet)
        assert br.sharpe_ratio != 0.0


class TestWalkForward:
    def test_walk_forward_short_dataset(self):
        predictions = [
            {
                "total_predicted": 220,
                "league": "NBA",
                "effective_baseline_home": 112,
                "effective_baseline_away": 108,
            }
        ]
        actual_results = [{"total": 225}]
        df = walk_forward_backtest(predictions, actual_results, window_size=50, step_size=10)
        assert len(df) > 0
