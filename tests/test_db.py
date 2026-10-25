from __future__ import annotations

import db


class TestDB:
    def test_is_available_returns_false_in_test(self):
        assert db.is_available() is False

    def test_save_prediction_returns_none_when_unavailable(self):
        result = db.save_prediction({"mock": True})
        assert result is None

    def test_save_outcome_returns_none_when_unavailable(self):
        result = db.save_outcome(1, 200, True, 10.0)
        assert result is None

    def test_save_model_snapshot_returns_none_when_unavailable(self):
        result = db.save_model_snapshot("NBA", "Normal", 0.5, 1.0, 0.1)
        assert result is None

    def test_init_schema_returns_false_when_unavailable(self):
        result = db.init_schema()
        assert result is False

    def test_recent_predictions_empty_when_unavailable(self):
        result = db.recent_predictions()
        assert result == []

    def test_long_term_roi_returns_default_when_unavailable(self):
        result = db.long_term_roi()
        assert result["total"] == 0
        assert result["won"] == 0
        assert result["lost"] == 0
        assert result["roi_pct"] == 0.0
