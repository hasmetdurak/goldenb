from __future__ import annotations

from typing import Any

import odds_fetcher as of


class TestSportKey:
    def test_nba(self):
        assert of.sport_key_for_league("NBA") == "basketball_nba"

    def test_euroleague(self):
        assert of.sport_key_for_league("EUROLEAGUE") == "basketball_euroleague"

    def test_unknown_league(self):
        assert of.sport_key_for_league("BOGUS") is None


class TestAbbr:
    def test_abbr_expand_via_tokens(self):
        tokens = of._resolve_team_tokens("LAL", "NBA")
        assert "los angeles lakers" in tokens

    def test_abbr_expand_non_nba_league(self):
        tokens = of._resolve_team_tokens("LAL", "EUROLEAGUE")
        assert tokens == ["LAL"]

    def test_tokens_include_original(self):
        tokens = of._resolve_team_tokens("Boston Celtics", "NBA")
        assert tokens == ["Boston Celtics"]


class TestNormMatch:
    def test_norm_unicode(self):
        assert of._norm("Fenerbahçe Beko") == "fenerbah e beko"

    def test_norm_whitespace(self):
        assert of._norm("  Anadolu   Efes  ") == "anadolu efes"

    def test_match_name_contains(self):
        assert of._match_name("Los Angeles Lakers", "Lakers") is True

    def test_match_name_exact(self):
        assert of._match_name("Anadolu Efes", "Anadolu Efes") is True

    def test_match_name_empty(self):
        assert of._match_name("", "X") is False

    def test_match_name_miss(self):
        assert of._match_name("Chicago Bulls", "Boston Celtics") is False


def _mk_event(line: float, over: float, under: float, name: str = "Booker") -> dict[str, Any]:
    return {
        "bookmakers": [
            {
                "title": name,
                "markets": [
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": over, "point": line},
                            {"name": "Under", "price": under, "point": line},
                        ],
                    }
                ],
            }
        ]
    }


class TestEventMatching:
    def test_event_matches_abbreviations(self):
        event = {"home_team": "Los Angeles Lakers", "away_team": "Boston Celtics"}
        assert of.event_matches(event, "LAL", "BOS", "NBA") is True

    def test_event_matches_full_names(self):
        event = {"home_team": "Anadolu Efes", "away_team": "Real Madrid"}
        assert of.event_matches(event, "Anadolu Efes", "Real Madrid", "EUROLEAGUE") is True

    def test_event_matches_reversed_side(self):
        event = {"home_team": "Boston Celtics", "away_team": "Los Angeles Lakers"}
        assert of.event_matches(event, "LAL", "BOS", "NBA") is False

    def test_event_matches_garbage(self):
        event = {"home_team": "Miami Heat", "away_team": "Orlando Magic"}
        assert of.event_matches(event, "CHI", "MIL", "NBA") is False

    def test_event_matches_missing_fields(self):
        assert of.event_matches({}, "LAL", "BOS", "NBA") is False


class TestConsensusTotals:
    def test_consensus_picks_best_price(self):
        event = {
            "bookmakers": [
                _mk_event(220.5, 1.90, 1.95)["bookmakers"][0],
                _mk_event(220.5, 1.95, 1.98, "Book2")["bookmakers"][0],
                _mk_event(221.5, 1.80, 1.75, "Book3")["bookmakers"][0],
            ]
        }
        result = of.consensus_totals_for_event(event)
        assert result is not None
        assert result["consensus_line"] == 220.5
        assert result["best_over_price"] == 1.95
        assert result["best_under_price"] == 1.98
        assert result["books_count"] == 3

    def test_consensus_none_when_no_totals(self):
        event = {"bookmakers": [{"title": "X", "markets": [{"key": "h2h", "outcomes": []}]}]}
        assert of.consensus_totals_for_event(event) is None

    def test_consensus_none_when_no_books(self):
        assert of.consensus_totals_for_event({"bookmakers": []}) is None

    def test_consensus_none_non_dict(self):
        assert of.consensus_totals_for_event(None) is None  # type: ignore[arg-type]

    def test_consensus_single_book(self):
        result = of.consensus_totals_for_event(_mk_event(225.5, 1.85, 1.92))
        assert result is not None
        assert result["consensus_line"] == 225.5
        assert result["best_over_book"] == "Booker"


class TestBestTotalsForMatch:
    def test_found_via_abbr(self, monkeypatch):
        payload = {
            "events": [
                {
                    "id": "e1",
                    "home_team": "Los Angeles Lakers",
                    "away_team": "Boston Celtics",
                    "bookmakers": [_mk_event(220.5, 1.90, 1.95)["bookmakers"][0]],
                }
            ],
            "quota": {"requests_remaining": 400},
        }
        monkeypatch.setattr(of, "fetch_totals_events_cached", lambda lg: payload)
        result = of.best_totals_for_match("LAL", "BOS", "NBA")
        assert result is not None
        assert result["consensus_line"] == 220.5
        assert result["quota"]["requests_remaining"] == 400
        assert result["event_id"] == "e1"

    def test_not_found_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            of, "fetch_totals_events_cached", lambda lg: {"events": [], "quota": {}}
        )
        assert of.best_totals_for_match("LAL", "BOS", "NBA") is None

    def test_empty_names(self, monkeypatch):
        monkeypatch.setattr(
            of, "fetch_totals_events_cached", lambda lg: {"events": [], "quota": {}}
        )
        assert of.best_totals_for_match("", "BOS", "NBA") is None


class TestFetchTotalsEvents:
    def test_empty_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ODDS_API_KEY", raising=False)
        monkeypatch.setattr(of, "ODDS_API_KEY_ENV", "")
        result = of.fetch_totals_events("NBA")
        assert result["events"] == []
        assert result["quota"] == {}

    def test_invalid_league(self, monkeypatch):
        monkeypatch.setenv("ODDS_API_KEY", "test-key")
        result = of.fetch_totals_events("BOGUS")
        assert result["events"] == []

    def test_http_401_returns_empty(self, monkeypatch):
        class FakeResp:
            status_code = 401
            text = "unauthorized"
            headers: dict[str, str] = {}

            def json(self):  # noqa: D105
                return []

        monkeypatch.setattr(of.requests, "get", lambda *a, **kw: FakeResp())
        monkeypatch.setenv("ODDS_API_KEY", "bad-key")
        monkeypatch.setattr(of, "cache_lib", None)
        result = of.fetch_totals_events("NBA")
        assert result["events"] == []

    def test_success_payload(self, monkeypatch):
        class FakeResp:
            status_code = 200
            headers = {"x-requests-remaining": "498", "x-requests-used": "2"}

            def json(self):  # noqa: D105
                return [{"id": "e1", "home_team": "BOS", "away_team": "LAL"}]

        monkeypatch.setattr(of.requests, "get", lambda *a, **kw: FakeResp())
        monkeypatch.setenv("ODDS_API_KEY", "good-key")
        monkeypatch.setattr(of, "cache_lib", None)
        result = of.fetch_totals_events("NBA")
        assert len(result["events"]) == 1
        assert result["quota"]["requests_remaining"] == 498

    def test_non_list_json_returns_empty(self, monkeypatch):
        class FakeResp:
            status_code = 200
            headers: dict[str, str] = {}

            def json(self):  # noqa: D105
                return {"error": "boom"}

        monkeypatch.setattr(of.requests, "get", lambda *a, **kw: FakeResp())
        monkeypatch.setenv("ODDS_API_KEY", "good-key")
        monkeypatch.setattr(of, "cache_lib", None)
        result = of.fetch_totals_events("NBA")
        assert result["events"] == []


class TestCached:
    def test_passthrough_without_cache(self, monkeypatch):
        calls: list[str] = []

        def fake_fetch(league: str) -> dict[str, Any]:
            calls.append(league)
            return {"events": [{"id": "e1"}], "quota": {}}

        monkeypatch.setattr(of, "fetch_totals_events", fake_fetch)
        monkeypatch.setattr(of, "cache_lib", None)
        result = of.fetch_totals_events_cached("NBA")
        assert result["events"]
        assert calls == ["NBA"]

    def test_cache_hit_short_circuits(self, monkeypatch):
        calls: list[str] = []

        def fake_fetch(league: str) -> dict[str, Any]:
            calls.append(league)
            return {}

        monkeypatch.setattr(of, "fetch_totals_events", fake_fetch)

        class FakeCache:
            @staticmethod
            def cache_get(key: str) -> dict[str, Any]:
                return {"events": [{"id": "cached"}], "quota": {}}

        monkeypatch.setattr(of, "cache_lib", FakeCache)
        result = of.fetch_totals_events_cached("NBA")
        assert result["events"] == [{"id": "cached"}]
        assert calls == []
