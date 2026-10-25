from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_nba_schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "GAME_ID": ["0022400001", "0022400002"],
            "GAME_DATE": pd.to_datetime(["2025-01-15", "2025-01-16"]),
            "HOME": ["LAL", "BOS"],
            "AWAY": ["GSW", "NYK"],
            "HOME_PTS": [115, 110],
            "AWAY_PTS": [108, 105],
            "TOTAL": [223, 215],
            "WINNER": ["LAL", "BOS"],
        }
    )


@pytest.fixture
def sample_euro_schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "HAFTA": [1, 2],
            "GAME_CODE": [1001, 1002],
            "SEASON_CODE": ["E2024", "E2024"],
            "EV_SAHIBI": ["Real Madrid", "Fenerbahce"],
            "DEPLASMAN": ["Panathinaikos", "Olympiacos"],
            "EV_SKOR": [85, 80],
            "DEPLASMAN_SKOR": [78, 75],
            "TOPLAM": [163, 155],
        }
    )


@pytest.fixture
def sample_engine() -> Any:
    from engine import DualTeamScoreEngine

    eng = DualTeamScoreEngine()
    eng.reset_learning()
    return eng


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(42)
