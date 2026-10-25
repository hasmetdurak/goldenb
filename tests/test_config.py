from __future__ import annotations

import config as cfg


class TestConfig:
    def test_get_total_minutes_nba(self):
        assert cfg.get_total_minutes("NBA") == 48

    def test_get_total_minutes_euroleague(self):
        assert cfg.get_total_minutes("EUROLEAGUE") == 40

    def test_get_total_minutes_eurocup(self):
        assert cfg.get_total_minutes("EUROCUP") == 40

    def test_get_total_minutes_unknown(self):
        assert cfg.get_total_minutes("Bogus") == 40

    def test_get_league_variance_nba(self):
        assert cfg.get_league_variance("NBA") == 1.20

    def test_get_league_variance_euroleague(self):
        assert cfg.get_league_variance("EUROLEAGUE") == 0.85

    def test_get_league_variance_default(self):
        assert cfg.get_league_variance("UNKNOWN") == 1.0

    def test_get_league_pace_all(self):
        for lig in ["NBA", "EUROLEAGUE", "EUROCUP"]:
            assert cfg.get_league_pace(lig) == 1.0

    def test_get_context_modifier_normal(self):
        mod = cfg.get_context_modifier("Normal_Season_Match")
        assert mod["pace_multiplier"] == 1.0
        assert mod["variance_multiplier"] == 1.0

    def test_get_context_modifier_derby(self):
        mod = cfg.get_context_modifier("Derby_Intense")
        assert mod["pace_multiplier"] < 1.0
        assert mod["variance_multiplier"] < 1.0

    def test_get_context_modifier_unknown_returns_normal(self):
        mod = cfg.get_context_modifier("Bogus")
        assert mod["label"] == "Normal Sezon Maçı"

    def test_contextual_modifiers_all_keys_present(self):
        required = [
            "Normal_Season_Match",
            "Derby_Intense",
            "Playoff_Elimination_G7",
            "Revenge_Matchup",
            "Garbage_Time_Heavy",
            "Defensive_Grind",
        ]
        for key in required:
            assert key in cfg.CONTEXTUAL_MODIFIERS
            meta = cfg.CONTEXTUAL_MODIFIERS[key]
            assert "pace_multiplier" in meta
            assert "variance_multiplier" in meta
            assert "label" in meta
            assert "emoji" in meta

    def test_league_constants_complete(self):
        for lig in ["NBA", "EUROLEAGUE", "EUROCUP"]:
            assert lig in cfg.LEAGUE_TOTAL_MINUTES
            assert lig in cfg.LEAGUE_PERIOD_MINUTES
            assert lig in cfg.LEAGUE_PERIODS
            assert cfg.LEAGUE_PERIODS[lig] == 4
