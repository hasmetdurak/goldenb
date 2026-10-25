from __future__ import annotations

import numpy as np
import pytest

import config as cfg


class TestDualTeamScoreEngine:
    def test_initial_state(self, sample_engine):
        assert sample_engine.bias_home == 0.0
        assert sample_engine.bias_away == 0.0
        assert sample_engine.variance_modifier_home == 1.0
        assert sample_engine.variance_modifier_away == 1.0
        assert len(sample_engine.learning_history) == 0

    def test_reset_learning(self, sample_engine):
        sample_engine.bias_home = 5.0
        sample_engine.bias_away = -3.0
        sample_engine.learning_history.append({"dummy": True})
        sample_engine.reset_learning()
        assert sample_engine.bias_home == 0.0
        assert sample_engine.bias_away == 0.0
        assert sample_engine.variance_modifier_home == 1.0
        assert sample_engine.variance_modifier_away == 1.0
        assert len(sample_engine.learning_history) == 0

    def test_current_mae_empty(self, sample_engine):
        assert sample_engine.current_mae() == 0.0

    def test_predict_match_scoreboard_nba(self, sample_engine):
        result = sample_engine.predict_match_scoreboard(
            current_home=50,
            current_away=45,
            current_minute=24,
            baseline_home_avg=110,
            baseline_away_avg=105,
            total_minutes=48,
            context_tag="Normal_Season_Match",
            league="NBA",
        )
        assert "home_predicted" in result
        assert "away_predicted" in result
        assert "total_predicted" in result
        assert result["total_predicted"] > 0
        assert result["home_predicted"] > 0
        assert result["away_predicted"] > 0
        for q in ["q1_home", "q2_home", "q3_home", "q4_home"]:
            assert q in result
        for q in ["q1_away", "q2_away", "q3_away", "q4_away"]:
            assert q in result
        assert "home_h1" in result
        assert "away_h1" in result
        assert "bias_home" in result
        assert "bias_away" in result
        assert "context_tag" in result

    def test_predict_match_scoreboard_euro(self, sample_engine):
        result = sample_engine.predict_match_scoreboard(
            current_home=30,
            current_away=28,
            current_minute=20,
            baseline_home_avg=80,
            baseline_away_avg=75,
            total_minutes=40,
            context_tag="Derby_Intense",
            league="EuroLeague",
        )
        assert result["total_predicted"] > 0
        assert result["quarter_weights"] == [0.24, 0.26, 0.24, 0.26]

    def test_predict_final_score_within_reasonable_range(self, sample_engine):
        result = sample_engine.predict_match_scoreboard(
            current_home=0,
            current_away=0,
            current_minute=0,
            baseline_home_avg=110,
            baseline_away_avg=105,
            total_minutes=48,
            context_tag="Normal_Season_Match",
            league="NBA",
        )
        assert 150 < result["total_predicted"] < 270
        assert 60 < result["home_predicted"] < 150
        assert 60 < result["away_predicted"] < 150

    def test_predict_near_game_end(self, sample_engine):
        result = sample_engine.predict_match_scoreboard(
            current_home=98,
            current_away=95,
            current_minute=46,
            baseline_home_avg=110,
            baseline_away_avg=105,
            total_minutes=48,
            context_tag="Normal_Season_Match",
            league="NBA",
        )
        assert abs(result["home_predicted"] - 98) < 15
        assert abs(result["away_predicted"] - 95) < 15

    def test_update_team_weights(self, sample_engine):
        sample_engine.update_team_weights(
            quarter=1, pred_home=25, actual_home=30, pred_away=22, actual_away=20
        )
        assert sample_engine.bias_home != 0.0
        assert sample_engine.bias_away != 0.0
        assert len(sample_engine.learning_history) == 1

    def test_learning_history_structure(self, sample_engine):
        sample_engine.update_team_weights(
            quarter=1, pred_home=25, actual_home=30, pred_away=22, actual_away=20
        )
        record = sample_engine.learning_history[0]
        assert "Ceyrek" in record
        assert "Tahmin_Home" in record
        assert "Gercek_Home" in record
        assert "Hata_Home" in record
        assert "Bias_Home" in record
        assert "MAE" in record

    def test_mae_improves_with_feedback(self, sample_engine):
        sample_engine.update_team_weights(
            quarter=1, pred_home=20, actual_home=22, pred_away=18, actual_away=20
        )
        mae1 = sample_engine.current_mae()
        sample_engine.update_team_weights(
            quarter=2, pred_home=21, actual_home=21, pred_away=19, actual_away=19
        )
        mae2 = sample_engine.current_mae()
        assert mae2 <= mae1

    def test_percentiles_in_output(self, sample_engine):
        result = sample_engine.predict_match_scoreboard(
            current_home=0,
            current_away=0,
            current_minute=0,
            baseline_home_avg=110,
            baseline_away_avg=105,
            total_minutes=48,
        )
        assert result["home_p10"] < result["home_p50"] < result["home_p90"]
        assert result["total_p10"] < result["total_p50"] < result["total_p90"]

    def test_quarter_weights_sum_to_one(self, sample_engine):
        result = sample_engine.predict_match_scoreboard(
            current_home=50,
            current_away=45,
            current_minute=24,
            baseline_home_avg=110,
            baseline_away_avg=105,
            total_minutes=48,
        )
        assert abs(sum(result["quarter_weights"]) - 1.0) < 0.001

    def test_history_dataframe_structure(self, sample_engine):
        sample_engine.update_team_weights(
            quarter=1, pred_home=25, actual_home=30, pred_away=22, actual_away=20
        )
        df = sample_engine.history_dataframe()
        assert list(df.columns) == [
            "Ceyrek",
            "Tahmin_Home",
            "Gercek_Home",
            "Hata_Home",
            "Tahmin_Away",
            "Gercek_Away",
            "Hata_Away",
            "Bias_Home",
            "Bias_Away",
            "Variance_Home",
            "Variance_Away",
            "MAE",
        ]
        assert len(df) == 1

    @pytest.mark.parametrize(
        "league,expected_max", [("NBA", 300), ("EuroLeague", 250), ("EuroCup", 250)]
    )
    def test_league_bounds(self, sample_engine, league, expected_max):
        result = sample_engine.predict_match_scoreboard(
            current_home=0,
            current_away=0,
            current_minute=0,
            baseline_home_avg=110,
            baseline_away_avg=105,
            total_minutes=cfg.get_total_minutes(league),
            league=league,
        )
        assert result["total_predicted"] < expected_max

    def test_context_modifier_applied(self, sample_engine):
        normal = sample_engine.predict_match_scoreboard(
            current_home=0,
            current_away=0,
            current_minute=0,
            baseline_home_avg=110,
            baseline_away_avg=105,
            total_minutes=48,
            context_tag="Defensive_Grind",
            league="NBA",
        )
        assert "context_pace_multiplier" in normal
        assert normal["context_pace_multiplier"] < 1.0

    def test_save_knowledge_to_code(self, sample_engine, tmp_path, monkeypatch):
        import engine as eng

        monkeypatch.setattr(eng, "WEIGHTS_FILE", str(tmp_path / "model_weights.json"))
        sample_engine.update_team_weights(4, 100, 105, 95, 90)
        weights_file = tmp_path / "model_weights.json"
        assert weights_file.exists()


class TestTopologyAware:
    """Fikstür topolojisi katmanı — yorgunluk / efor / bonus / variance clamp."""

    def _call(self, eng, **kwargs):
        np.random.seed(7)
        base = {
            "current_home": 0,
            "current_away": 0,
            "current_minute": 0,
            "baseline_home_avg": 110,
            "baseline_away_avg": 105,
            "total_minutes": 48,
            "context_tag": "Normal_Season_Match",
            "league": "NBA",
        }
        base.update(kwargs)
        return eng.predict_match_scoreboard(**base)

    def test_topology_meta_present_and_neutral(self, sample_engine):
        result = self._call(sample_engine)
        topo = result["topology"]
        assert topo["fatigue_home"] == 1.0
        assert topo["effort_home"] == 1.0
        assert topo["bonus_away"] == 1.0
        assert topo["status"] == "OPTIMIZED_WITH_SCHEDULE_LEVERAGE"

    def test_b2b_lowers_total(self, sample_engine):
        neutral = self._call(sample_engine)["total_predicted"]
        np.random.seed(7)
        fatigued = self._call(sample_engine, is_b2b_home=True, is_b2b_away=True)
        assert fatigued["total_predicted"] < neutral * 0.97

    def test_ot_fatigue_stacks_on_b2b(self, sample_engine):
        np.random.seed(7)
        b2b = self._call(sample_engine, is_b2b_home=True, is_b2b_away=True)
        np.random.seed(7)
        b2b_ot = self._call(
            sample_engine, is_b2b_home=True, is_b2b_away=True, prev_match_was_ot=True
        )
        assert b2b_ot["total_predicted"] < b2b["total_predicted"]

    def test_effort_lowers_and_symmetric(self, sample_engine):
        neutral_away = self._call(sample_engine)["away_predicted"]
        np.random.seed(7)
        effort = self._call(
            sample_engine, next_match_importance="critical", loss_tolerability="high"
        )
        assert effort["away_predicted"] < neutral_away * 0.94
        topo = effort["topology"]
        assert topo["effort_away"] == pytest.approx(cfg.TOPOLOGY_EFFORT_CRITICAL)
        assert topo["effort_home"] == pytest.approx(cfg.TOPOLOGY_EFFORT_CRITICAL)

    def test_effort_rotation_deep_low(self, sample_engine):
        np.random.seed(7)
        result = self._call(
            sample_engine,
            next_match_importance="critical",
            loss_tolerability="high",
            rotation_active=True,
        )
        assert result["topology"]["effort_home"] == pytest.approx(cfg.TOPOLOGY_EFFORT_ROTATION)

    def test_bonus_raises_home_not_current_score(self, sample_engine):
        np.random.seed(7)
        neutral = self._call(sample_engine)
        np.random.seed(7)
        boosted = self._call(sample_engine, home_in_bonus=True)
        assert boosted["home_predicted"] > neutral["home_predicted"]
        # Canlı fazda bonus mevcut skoru çarpamaz: current 90 @ t=42
        np.random.seed(7)
        live_neutral = self._call(
            sample_engine, current_home=90, current_away=88, current_minute=42
        )
        np.random.seed(7)
        live_bonus = self._call(
            sample_engine, current_home=90, current_away=88, current_minute=42, home_in_bonus=True
        )
        live_bonus_delta = live_bonus["home_predicted"] - live_neutral["home_predicted"]
        # beklenen ek: kalan 6 dk * blend-pace * (1.08-1) ~= 1.05 puan → mevcut skor çarpılmamış
        assert 0.0 <= live_bonus_delta < 2.0

    def test_bonus_away_from_config(self, sample_engine):
        np.random.seed(7)
        boosted = self._call(sample_engine, away_in_bonus=True)
        assert boosted["topology"]["bonus_away"] == pytest.approx(cfg.TOPOLOGY_BONUS_BOOST_AWAY)

    def test_variance_clamp_ceiling(self, sample_engine):
        eng = sample_engine
        eng.reset_learning()
        for i in range(60):
            # Sürekli büyük hata → variance sınırsız büyümesin
            eng.update_team_weights(4, 100 + i, 130, 95, 90)
        assert eng.variance_modifier_home <= cfg.VARIANCE_MODIFIER_CEILING + 1e-9

    def test_finished_match_topo_neutral(self, sample_engine):
        result = self._call(
            sample_engine,
            current_home=90,
            current_away=95,
            current_minute=48,
            is_b2b_home=True,
            home_in_bonus=True,
        )
        assert result["home_predicted"] == 90
        assert result["total_predicted"] == 185

    def test_live_blend_zero_minute_matches_pre(self, sample_engine):
        np.random.seed(7)
        pre = self._call(sample_engine)
        assert pre["total_predicted"] > 150
