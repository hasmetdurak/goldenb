"""
GoldenBet AI - Redis Gerçek Zamanlı Hız Katmanı
================================================

Canlı skor/odds feed'leri, dış API cevapları ve rate-limit sayaçları
için TTL tabanlı önbellek + opsiyonel pub/sub. Servis yoksa tüm
operasyonlar sessizce `None`/`False` döner — uygulama çökmez.

Kurulum:
    1) Dokploy'da "live" profilini aktive et → redis ayağa kalkar
    2) REDIS_URL otomatik set edilir
    3) cache_get / cache_set / publish_anomaly kullanıma hazır
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ---------------------------------------------------------------------------
# Bağlantı Yönetimi
# ---------------------------------------------------------------------------
_client: Optional[Any] = None


def _get_client() -> Optional[Any]:
    """Redis client'ını lazy yükler. Servis yoksa None döner."""
    global _client
    if _client is not None:
        return _client
    try:
        import redis as redis_lib
        _client = redis_lib.from_url(
            REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        _client.ping()
        return _client
    except Exception as e:
        logger.warning("Redis bağlantısı kurulamadı: %s", e)
        _client = None
        return None


def is_available() -> bool:
    """Redis erişilebilir mi?"""
    return _get_client() is not None


# ---------------------------------------------------------------------------
# Anahtar Şeması
# ---------------------------------------------------------------------------
def k_nba_team(team_id: int, season: str) -> str:
    return f"goldenb:cache:nba:team:{team_id}:{season}"


def k_euro_season(season_code: str, comp: str) -> str:
    return f"goldenb:cache:euro:{comp}:{season_code}"


def k_live_score(game_id: str) -> str:
    return f"goldenb:live:score:{game_id}"


def k_live_odds(game_id: str) -> str:
    return f"goldenb:live:odds:{game_id}"


def k_rate_limit(api_name: str) -> str:
    return f"goldenb:rl:{api_name}"


def k_anomaly_channel(league: str) -> str:
    return f"goldenb:anomalies:{league}"


# ---------------------------------------------------------------------------
# CRUD Operasyonları
# ---------------------------------------------------------------------------
def cache_get(key: str) -> Optional[Any]:
    """Anahtardaki JSON-decode edilmiş değeri döner; yoksa None."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("cache_get(%s) başarısız: %s", key, e)
        return None


def cache_set(key: str, value: Any, ttl_seconds: int = 3600) -> bool:
    """Değeri JSON-encode edip TTL ile saklar. Başarı: True."""
    client = _get_client()
    if client is None:
        return False
    try:
        client.setex(key, ttl_seconds, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.warning("cache_set(%s) başarısız: %s", key, e)
        return False


def cache_invalidate(pattern: str) -> int:
    """Pattern eşleşen tüm anahtarları siler. Dönüş: silinen sayı."""
    client = _get_client()
    if client is None:
        return 0
    try:
        keys = list(client.scan_iter(match=pattern, count=200))
        if not keys:
            return 0
        return int(client.delete(*keys))
    except Exception as e:
        logger.warning("cache_invalidate(%s) başarısız: %s", pattern, e)
        return 0


def rate_limit_check(api_name: str,
                     max_calls: int,
                     window_seconds: int) -> bool:
    """
    Sliding-window rate limit. Bu saniye içinde max_calls'tan az çağrı
    yapıldıysa True döner ve sayacı 1 artırır. Aksi False.
    """
    client = _get_client()
    if client is None:
        return True  # servis yoksa her zaman izin ver
    try:
        key = k_rate_limit(api_name)
        current = int(client.get(key) or 0)
        if current >= max_calls:
            return False
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        pipe.execute()
        return True
    except Exception as e:
        logger.warning("rate_limit_check başarısız: %s", e)
        return True


def publish_anomaly(league: str, payload: Dict[str, Any]) -> int:
    """
    Anomali tespit edildiğinde pub/sub yayar (multi-worker senaryosu).
    Dönüş: abone sayısı (0 ise kimse dinlemiyor).
    """
    client = _get_client()
    if client is None:
        return 0
    try:
        return int(client.publish(k_anomaly_channel(league),
                                  json.dumps(payload, default=str)))
    except Exception as e:
        logger.warning("publish_anomaly başarısız: %s", e)
        return 0


def cache_stats() -> Dict[str, Any]:
    """Bilgi paneli için Redis istatistikleri."""
    client = _get_client()
    if client is None:
        return {"available": False, "keys": 0, "memory_mb": 0.0}
    try:
        info = client.info("memory")
        dbsize = int(client.dbsize())
        return {
            "available": True,
            "keys": dbsize,
            "memory_mb": round(float(info.get("used_memory", 0)) / 1024 / 1024, 2),
        }
    except Exception as e:
        logger.warning("cache_stats başarısız: %s", e)
        return {"available": False, "keys": 0, "memory_mb": 0.0}
