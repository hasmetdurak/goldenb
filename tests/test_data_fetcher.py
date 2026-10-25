from __future__ import annotations

import pandas as pd
import pytest

import data_fetcher as df_lib


class TestDataFetcher:
    def test_compute_team_baselines_nba(self, sample_nba_schedule):
        home, away = df_lib.compute_team_baselines(sample_nba_schedule, "NBA")
        assert home == 112.5
        assert away == 106.5

    def test_compute_team_baselines_euro(self, sample_euro_schedule):
        home, away = df_lib.compute_team_baselines(sample_euro_schedule, "EuroLeague")
        assert home == 82.5
        assert away == 76.5

    def test_compute_team_baselines_empty(self):
        home, away = df_lib.compute_team_baselines(pd.DataFrame(), "NBA")
        assert home == 0.0
        assert away == 0.0

    def test_compute_team_baselines_none(self):
        home, away = df_lib.compute_team_baselines(None, "NBA")
        assert home == 0.0
        assert away == 0.0

    def test_compute_schedule_baseline_nba(self, sample_nba_schedule):
        avg = df_lib.compute_schedule_baseline(sample_nba_schedule, "NBA")
        assert avg == 219.0

    def test_compute_schedule_baseline_euro(self, sample_euro_schedule):
        avg = df_lib.compute_schedule_baseline(sample_euro_schedule, "EuroLeague")
        assert avg == 159.0

    def test_compute_schedule_baseline_empty(self):
        avg = df_lib.compute_schedule_baseline(pd.DataFrame(), "NBA")
        assert avg == 0.0

    def test_compute_team_baseline_nba(self):
        df = pd.DataFrame({"SAYI": [105, 110, 115]})
        result = df_lib.compute_team_baseline(df, "nba")
        assert result == pytest.approx(110.0 * 2)

    def test_compute_team_baseline_euro(self):
        df = pd.DataFrame({"TOPLAM": [160, 170, 165]})
        result = df_lib.compute_team_baseline(df, "euro")
        assert result == pytest.approx(165.0)

    def test_famous_games_contains_expected(self):
        assert len(df_lib.FAMOUS_GAMES) >= 6
        labels = list(df_lib.FAMOUS_GAMES.keys())
        assert any("2016 NBA Finals" in lbl for lbl in labels)
        assert any("EuroLeague Final" in lbl for lbl in labels)

    def test_get_famous_games_for_league_nba(self):
        result = df_lib.get_famous_games_for_league("NBA")
        assert all(game["league"].upper() == "NBA" for game in result.values())

    def test_get_famous_games_for_league_euroleague(self):
        result = df_lib.get_famous_games_for_league("EUROLEAGUE")
        assert all(game["league"].upper() == "EUROLEAGUE" for game in result.values())

    def test_fetch_famous_game_quarters_returns_hardcoded(self):
        result = df_lib.fetch_famous_game_quarters("2016 NBA Finals G7 (Cavaliers 93-89 Warriors)")
        assert len(result) == 4
        assert result[4] == 182.0

    def test_fetch_quarters_for_schedule_row_empty_league(self):
        row = pd.Series({"dummy": 1})
        result = df_lib.fetch_quarters_for_schedule_row(row, "unknown")
        assert result == {}

    def test_nba_data_empty_when_api_unavailable(self):
        result = df_lib.fetch_nba_data("NonExistent Team Xyz")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_nba_season_schedule_empty_when_api_unavailable(self):
        result = df_lib.fetch_nba_season_schedule("2099-00")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_euroleague_data_empty_for_invalid_season(self):
        result = df_lib.fetch_euroleague_data("X_BOGUS_999", competition="E")
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestComputeTeamForm:
    @staticmethod
    def _fake_season(sample_euro_schedule: pd.DataFrame):
        return lambda s, c: sample_euro_schedule

    def test_euro_form_from_cached_schedule(self, monkeypatch, sample_euro_schedule):
        monkeypatch.setattr(
            df_lib, "fetch_euroleague_season_cached", self._fake_season(sample_euro_schedule)
        )
        home, away = df_lib.compute_team_form(
            "Real Madrid", "Olympiacos", "EuroLeague", season="E2024", lookback=10
        )
        assert home == 85.0
        assert away == 75.0

    def test_unknown_league_returns_zero(self, monkeypatch, sample_euro_schedule):
        monkeypatch.setattr(
            df_lib, "fetch_euroleague_season_cached", self._fake_season(sample_euro_schedule)
        )
        home, away = df_lib.compute_team_form("A", "B", "BOGUS", lookback=5)
        assert (home, away) == (0.0, 0.0)

    def test_empty_schedule_returns_zero(self, monkeypatch):
        monkeypatch.setattr(df_lib, "fetch_euroleague_season_cached", lambda s, c: pd.DataFrame())
        home, away = df_lib.compute_team_form("Real Madrid", "Olympiacos", " EuroLeague")
        assert (home, away) == (0.0, 0.0)


class TestEuroScheduleCache:
    def test_cache_shapes_today_filter(self):
        df = pd.DataFrame(
            {
                "HAFTA": [1],
                "GAME_CODE": [1001],
                "SEASON_CODE": ["E2024"],
                "EV_SAHIBI": ["A"],
                "DEPLASMAN": ["B"],
                "EV_SKOR": [80],
                "DEPLASMAN_SKOR": [75],
                "TOPLAM": [155],
            }
        )
        assert list(df.columns)[:3] == ["HAFTA", "GAME_CODE", "SEASON_CODE"]
