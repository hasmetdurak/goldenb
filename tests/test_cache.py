from __future__ import annotations

import cache


class TestCache:
    def test_is_available_returns_false_in_test(self):
        assert cache.is_available() is False

    def test_cache_get_returns_none_unavailable(self):
        assert cache.cache_get("test") is None

    def test_cache_set_returns_false_unavailable(self):
        assert cache.cache_set("test", "value") is False

    def test_cache_invalidate_returns_zero_unavailable(self):
        assert cache.cache_invalidate("test:*") == 0

    def test_rate_limit_check_returns_true_unavailable(self):
        assert cache.rate_limit_check("nba_api", 10, 60) is True

    def test_publish_anomaly_returns_zero_unavailable(self):
        assert cache.publish_anomaly("NBA", {"msg": "test"}) == 0

    def test_cache_stats_returns_unavailable(self):
        stats = cache.cache_stats()
        assert stats["available"] is False
        assert stats["keys"] == 0

    def test_key_formatters(self):
        assert cache.k_nba_team(1, "2024-25") == "goldenb:cache:nba:team:1:2024-25"
        assert cache.k_euro_season("E2024", "E") == "goldenb:cache:euro:E:E2024"
        assert cache.k_live_score("0022400001") == "goldenb:live:score:0022400001"
        assert cache.k_live_odds("0022400001") == "goldenb:live:odds:0022400001"
        assert cache.k_rate_limit("nba") == "goldenb:rl:nba"
        assert cache.k_anomaly_channel("NBA") == "goldenb:anomalies:NBA"
