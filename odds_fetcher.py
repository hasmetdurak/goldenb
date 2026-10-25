"""
GoldenBet AI - Gerçek Bahis Oranları (The Odds API)
===================================================

the-odds-api.com v4'ünden gerçek bahisçi toplam (totals) baraj ve
fiyatlarını çeker. Ücretsiz anahtar: 500 istek/ay — bu yüzden her
çekim Redis/None-cache TTL ile sarılır ve aramalar tek çekime daraltılır.

Kurulum:
    1) https://the-odds-api.com → API key (ücretsiz Start seviyesi)
    2) ODDS_API_KEY ortam değişkenini set et
    3) odds_fetcher.best_totals_for_match(home, away, league) kullan

Yetenekler:
    * sport_key_for_league(...)      : lig → sport key eşleşmesi
    * fetch_totals_events(...)       : ham event listesi (TTL cache'li)
    * best_totals_for_match(...)     : takım eşleştirmeli en iyi fiyatlar
    * consensus_totals(...)          : hesap baraj + best over/under + EV
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import Any

import requests

cache_lib: Any | None = None
try:
    import cache as _cache_mod

    cache_lib = _cache_mod
except Exception:  # pragma: no cover
    cache_lib = None

logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_API_KEY_ENV = os.getenv("ODDS_API_KEY", "")

REQUEST_TIMEOUT_SEC = 15
CACHE_TTL_SECONDS = 600

SPORT_KEYS: dict[str, str] = {"NBA": "basketball_nba", "EUROLEAGUE": "basketball_euroleague"}

# NBA kısaltma → tam ad (takım eşleştirmesi için)
NBA_ABBR_TO_FULL: dict[str, str] = {
    "ATL": "atlanta hawks",
    "BOS": "boston celtics",
    "BKN": "brooklyn nets",
    "CHA": "charlotte hornets",
    "CHI": "chicago bulls",
    "CLE": "cleveland cavaliers",
    "DAL": "dallas mavericks",
    "DEN": "denver nuggets",
    "DET": "detroit pistons",
    "GSW": "golden state warriors",
    "HOU": "houston rockets",
    "IND": "indiana pacers",
    "LAC": "los angeles clippers",
    "LAL": "los angeles lakers",
    "MEM": "memphis grizzlies",
    "MIA": "miami heat",
    "MIL": "milwaukee bucks",
    "MIN": "minnesota timberwolves",
    "NOP": "new orleans pelicans",
    "NYK": "new york knicks",
    "OKC": "oklahoma city thunder",
    "ORL": "orlando magic",
    "PHI": "philadelphia 76ers",
    "PHX": "phoenix suns",
    "POR": "portland trail blazers",
    "SAC": "sacramento kings",
    "SAS": "san antonio spurs",
    "TOR": "toronto raptors",
    "UTA": "utah jazz",
    "WAS": "washington wizards",
}


def _norm(name: str) -> str:
    """Team adı eşleştirme normalize: lowercase + harf/rakam yalnız."""
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def sport_key_for_league(league: str) -> str | None:
    """Lig adı → The Odds API sport_key. Bilinmeyen lig -> None."""
    return SPORT_KEYS.get((league or "").upper())


def _quota_from_headers(headers: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(headers, dict) or headers is not None:
        try:
            out["requests_remaining"] = int((headers or {}).get("x-requests-remaining", 0) or 0)
            out["requests_used"] = int((headers or {}).get("x-requests-used", 0) or 0)
        except (TypeError, ValueError):
            pass
    return out


def fetch_totals_events(league: str, regions: str = "us,eu,uk") -> dict[str, Any]:
    """
    Lig için gerçek bahisçi toplam event'lerini çeker (TTL cache'li).

    Dönüş: {"events": [...], "quota": {...}} — hata durumunda boş event.
    """
    empty: dict[str, Any] = {"events": [], "quota": {}}
    sport_key = sport_key_for_league(league)
    api_key = os.getenv("ODDS_API_KEY", "").strip() or ODDS_API_KEY_ENV
    if not sport_key or not api_key:
        return empty
    if cache_lib and not cache_lib.rate_limit_check("odds_api", 12, 60):
        return empty
    try:
        r = requests.get(
            f"{ODDS_API_BASE}/sports/{sport_key}/odds",
            params={
                "apiKey": api_key,
                "regions": regions,
                "markets": "totals",
                "oddsFormat": "decimal",
            },
            timeout=REQUEST_TIMEOUT_SEC,
        )
        if r.status_code != 200:
            logger.warning("Odds API %s döndü (%s)", r.status_code, sport_key)
            return empty
        events = r.json()
        if not isinstance(events, list):
            return empty
        return {"events": events, "quota": _quota_from_headers(r.headers)}
    except Exception as e:
        logger.warning("Odds API çağrısı başarısız: %s", e)
        return empty


def fetch_totals_events_cached(league: str) -> dict[str, Any]:
    """Sonuçları 10 dakika TTL cache'e sarır — kota dostu tek çekim."""
    sport_key = sport_key_for_league(league) or league.lower()
    key = f"goldenb:cache:odds:{sport_key}:totals"
    if cache_lib:
        cached = cache_lib.cache_get(key)
        if isinstance(cached, dict) and cached.get("events") is not None:
            return cached
    payload = fetch_totals_events(league)
    if cache_lib and payload.get("events"):
        cache_lib.cache_set(key, payload, ttl_seconds=CACHE_TTL_SECONDS)
    return payload


def _match_name(name: str, target: str) -> bool:
    """Fuzzy takım adı eşleşmesi: içerlik + tam-word kontrol."""
    n, t = _norm(name), _norm(target)
    if not n or not t:
        return False
    if n == t:
        return True
    return bool(n in t or t in n)


def _resolve_team_tokens(team: str, league: str) -> list[str]:
    """
    Eşleştirme için aday ad üret:
    NBA abbr ise tam adı da ekler; genelde hedef adın kendisi yeter.
    """
    tokens = [team]
    key = (team or "").upper().strip()
    if league.upper() == "NBA" and key in NBA_ABBR_TO_FULL:
        tokens.append(NBA_ABBR_TO_FULL[key])
    return tokens


def extract_teams(event: dict[str, Any]) -> tuple[str, str]:
    """Event dict'inin home/away tam adlarını çıkarır."""
    home = str(event.get("home_team") or "").strip()
    away = str(event.get("away_team") or "").strip()
    return home, away


def event_matches(event: dict[str, Any], home_name: str, away_name: str, league: str) -> bool:
    """
    Event eşleşmesi: her iki taraf için tokenize adlar çift yönlü kontrol.
    """
    ev_home, ev_away = extract_teams(event)
    if not ev_home or not ev_away:
        return False
    cand_h = _resolve_team_tokens(home_name, league)
    cand_a = _resolve_team_tokens(away_name, league)
    for ch in cand_h:
        if _match_name(ev_home, ch):
            for ca in cand_a:
                if _match_name(ev_away, ca):
                    return True
    return False


def consensus_totals_for_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """
    Tek event için konsensus baraj + en iyi Over/Under fiyat.

    Mantık:
      * Her bookmaker'ın totals market'i Over/Under outcome'ları (point, price).
      * Baraj: kitaplar arası en yaygın 'point' (mod; eşitlikte ortalama).
      * best_over / best_under: konsensus barajındaki (veya ±0.5 komşuda)
        en yüksek fiyat veren kitap.
    Dönüş: {
        consensus_line, best_over_price, best_over_book,
        best_under_price, best_under_book, books_count,
        last_update
    }
    Hata/eksik durumda None.
    """
    if not isinstance(event, dict):
        return None
    books = event.get("bookmakers") or []
    if not books:
        return None

    books_rows: list[dict[str, Any]] = []
    for b in books:
        price_over = price_under = None
        point_over = point_under = None
        for m in b.get("markets") or []:
            if str(m.get("key", "")) != "totals":
                continue
            for o in m.get("outcomes") or []:
                name = str(o.get("name", "")).lower()
                try:
                    point = float(o.get("point", 0) or 0)
                    price = float(o.get("price", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if name == "over" and price > 1.0:
                    price_over, point_over = price, point
                elif name == "under" and price > 1.0:
                    price_under, point_under = price, point
        if price_over and price_under:
            books_rows.append(
                {
                    "book": str(b.get("title", "") or b.get("key", "")),
                    "price_over": price_over,
                    "price_under": price_under,
                    "point": point_over if point_over is not None else point_under,
                    "last_update": str(b.get("last_update", "") or ""),
                }
            )

    if not books_rows:
        return None

    lines = [row["point"] for row in books_rows if row["point"] is not None]
    if not lines:
        return None
    counts = Counter(lines)
    top_count = max(counts.values())
    most_common = [ln for ln, c in counts.items() if c == top_count]
    consensus = (
        float(min(most_common))
        if len(most_common) == 1
        else round(sum(most_common) / len(most_common), 1)
    )

    near = [
        row
        for row in books_rows
        if row["point"] is not None and abs(row["point"] - consensus) <= 0.51
    ]
    pool = near if near else books_rows

    best_over = max(pool, key=lambda r: r["price_over"])
    best_under = max(pool, key=lambda r: r["price_under"])

    return {
        "consensus_line": consensus,
        "best_over_price": best_over["price_over"],
        "best_over_book": best_over["book"],
        "best_under_price": best_under["price_under"],
        "best_under_book": best_under["book"],
        "books_count": len(books_rows),
        "last_update": best_over["last_update"],
    }


def best_totals_for_match(home_name: str, away_name: str, league: str) -> dict[str, Any] | None:
    """
    Seçili maç için gerçek piyasa özeti:
    {"consensus_line", "best_over_price", "best_under_price",
     "books_count", "home_name", "away_name", "quota", "event_id"}
    Bulunamadıysa None (UI manuel girişe düşer).
    """
    if not home_name or not away_name:
        return None
    payload = fetch_totals_events_cached(league)
    events = payload.get("events") or []
    for ev in events:
        if isinstance(ev, dict) and event_matches(ev, home_name, away_name, league):
            consensus = consensus_totals_for_event(ev)
            if consensus is not None:
                consensus["home_name"] = home_name
                consensus["away_name"] = away_name
                consensus["quota"] = payload.get("quota", {})
                consensus["event_id"] = str(ev.get("id", "") or "")
                return consensus
    # İkinci tur: serbest ad normuyla gevşek eşleşme
    for ev in events:
        ev_home, ev_away = extract_teams(ev)
        if _match_name(ev_home, home_name) and _match_name(ev_away, away_name):
            consensus = consensus_totals_for_event(ev)
            if consensus is not None:
                consensus["home_name"] = home_name
                consensus["away_name"] = away_name
                consensus["quota"] = payload.get("quota", {})
                consensus["event_id"] = str(ev.get("id", "") or "")
                return consensus
    return None
