"""
GoldenBet AI - PostgreSQL Kalıcı Veri Katmanı
==============================================

Canlı API + çok kullanıcı senaryoları için tahmin ve sonuç geçmişini
saklar. Servis erişilemezse tüm fonksiyonlar sessizce `None`/`False`
döner — uygulama çökmez, MVP akışı bozulmaz.

Kurulum:
    1) Dokploy'da "live" profilini aktive et → postgres ayağa kalkar
    2) DATABASE_URL ortam değişkeni otomatik set edilir
    3) `init_schema()` çağrısıyla tablolar oluşur
    4) `save_prediction(...)` / `save_outcome(...)` kullanıma hazır
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Ortam değişkenleri (Dokploy docker-compose otomatik set eder)
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "goldenb")
DB_USER = os.getenv("POSTGRES_USER", "goldenb")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "goldenb")

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ---------------------------------------------------------------------------
# Bağlantı Yönetimi
# ---------------------------------------------------------------------------
_engine: Optional[Any] = None
_schema_initialized: bool = False


def _get_engine() -> Optional[Any]:
    """SQLAlchemy engine'ini lazy yükler. Servis yoksa None döner."""
    global _engine
    if _engine is not None:
        return _engine
    try:
        from sqlalchemy import create_engine
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=5,
            connect_args={"connect_timeout": 3},
        )
        # Hızlı sağlık testi
        with _engine.connect() as conn:
            conn.execute("SELECT 1")
        return _engine
    except Exception as e:
        logger.warning("PostgreSQL bağlantısı kurulamadı: %s", e)
        _engine = None
        return None


def is_available() -> bool:
    """Postgres erişilebilir mi?"""
    return _get_engine() is not None


# ---------------------------------------------------------------------------
# Şema
# ---------------------------------------------------------------------------
INIT_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    league TEXT,
    team TEXT,
    context_tag TEXT,
    phase TEXT,
    current_minute INT,
    current_score INT,
    baseline_avg DOUBLE PRECISION,
    ai_predicted_score DOUBLE PRECISION,
    market_line DOUBLE PRECISION,
    confidence_pct DOUBLE PRECISION,
    signal TEXT,
    strength TEXT,
    bias_weight DOUBLE PRECISION,
    variance_modifier DOUBLE PRECISION,
    stake_try DOUBLE PRECISION,
    odds DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_predictions_created_at
    ON predictions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_league
    ON predictions (league, created_at DESC);

CREATE TABLE IF NOT EXISTS outcomes (
    id BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT REFERENCES predictions(id) ON DELETE CASCADE,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    final_total_score INT,
    won BOOLEAN,
    pnl_try DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_outcomes_prediction_id
    ON outcomes (prediction_id);

CREATE TABLE IF NOT EXISTS model_snapshots (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    league TEXT,
    context_tag TEXT,
    bias_weight DOUBLE PRECISION,
    variance_modifier DOUBLE PRECISION,
    mae DOUBLE PRECISION
);
"""


def init_schema() -> bool:
    """Tabloları oluşturur (idempotent). Servis yoksa False."""
    global _schema_initialized
    eng = _get_engine()
    if eng is None:
        return False
    try:
        with eng.begin() as conn:
            for stmt in [s.strip() for s in INIT_SQL.split(";") if s.strip()]:
                conn.exec_driver_sql(stmt)
        _schema_initialized = True
        return True
    except Exception as e:
        logger.warning("init_schema başarısız: %s", e)
        return False


def _is_ready() -> bool:
    return _schema_initialized or init_schema()


# ---------------------------------------------------------------------------
# CRUD Operasyonları
# ---------------------------------------------------------------------------
def save_prediction(payload: Dict[str, Any]) -> Optional[int]:
    """
    Bir tahmini predictions tablosuna yazar, dönüş: prediction_id veya None.
    """
    if not _is_ready():
        return None
    eng = _get_engine()
    if eng is None:
        return None
    try:
        with eng.begin() as conn:
            result = conn.exec_driver_sql(
                """
                INSERT INTO predictions
                  (league, team, context_tag, phase, current_minute,
                   current_score, baseline_avg, ai_predicted_score,
                   market_line, confidence_pct, signal, strength,
                   bias_weight, variance_modifier, stake_try, odds)
                VALUES
                  (%(league)s, %(team)s, %(context_tag)s, %(phase)s,
                   %(current_minute)s, %(current_score)s, %(baseline_avg)s,
                   %(ai_predicted_score)s, %(market_line)s,
                   %(confidence_pct)s, %(signal)s, %(strength)s,
                   %(bias_weight)s, %(variance_modifier)s,
                   %(stake_try)s, %(odds)s)
                RETURNING id
                """,
                payload,
            )
            return int(result.scalar())
    except Exception as e:
        logger.warning("save_prediction başarısız: %s", e)
        return None


def save_outcome(prediction_id: int,
                 final_total_score: int,
                 won: bool,
                 pnl_try: float) -> Optional[int]:
    """Tahmin sonucunu outcomes tablosuna yazar."""
    if not _is_ready() or prediction_id is None:
        return None
    eng = _get_engine()
    if eng is None:
        return None
    try:
        with eng.begin() as conn:
            result = conn.exec_driver_sql(
                """
                INSERT INTO outcomes
                  (prediction_id, final_total_score, won, pnl_try)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (prediction_id, final_total_score, won, pnl_try),
            )
            return int(result.scalar())
    except Exception as e:
        logger.warning("save_outcome başarısız: %s", e)
        return None


def save_model_snapshot(league: str,
                        context_tag: str,
                        bias_weight: float,
                        variance_modifier: float,
                        mae: float) -> Optional[int]:
    """Model ağırlıklarını zaman damgalı olarak saklar (A/B test için)."""
    if not _is_ready():
        return None
    eng = _get_engine()
    if eng is None:
        return None
    try:
        with eng.begin() as conn:
            result = conn.exec_driver_sql(
                """
                INSERT INTO model_snapshots
                  (league, context_tag, bias_weight, variance_modifier, mae)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (league, context_tag, bias_weight, variance_modifier, mae),
            )
            return int(result.scalar())
    except Exception as e:
        logger.warning("save_model_snapshot başarısız: %s", e)
        return None


def recent_predictions(limit: int = 50) -> list[dict]:
    """Son N tahmini JSON-friendly liste olarak döner."""
    if not _is_ready():
        return []
    eng = _get_engine()
    if eng is None:
        return []
    try:
        with eng.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT * FROM predictions ORDER BY created_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
            cols = conn.exec_driver_sql(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='predictions' ORDER BY ordinal_position"
            ).fetchall()
            col_names = [c[0] for c in cols]
            return [dict(zip(col_names, row)) for row in rows]
    except Exception as e:
        logger.warning("recent_predictions başarısız: %s", e)
        return []


def long_term_roi() -> Dict[str, Any]:
    """Tüm sonuçlanmış tahminler üzerinden toplam ROI özetini döner."""
    if not _is_ready():
        return {"total": 0, "won": 0, "lost": 0, "pnl_try": 0.0, "roi_pct": 0.0}
    eng = _get_engine()
    if eng is None:
        return {"total": 0, "won": 0, "lost": 0, "pnl_try": 0.0, "roi_pct": 0.0}
    try:
        with eng.connect() as conn:
            row = conn.exec_driver_sql(
                """
                SELECT
                  COUNT(*)        AS total,
                  SUM(CASE WHEN won THEN 1 ELSE 0 END) AS won,
                  SUM(CASE WHEN won THEN 0 ELSE 1 END) AS lost,
                  COALESCE(SUM(pnl_try), 0) AS pnl_try
                FROM outcomes
                """
            ).fetchone()
        total = int(row[0] or 0)
        won = int(row[1] or 0)
        lost = int(row[2] or 0)
        pnl = float(row[3] or 0.0)
        roi = (pnl / total * 100.0) if total else 0.0
        return {"total": total, "won": won, "lost": lost,
                "pnl_try": round(pnl, 2), "roi_pct": round(roi, 2)}
    except Exception as e:
        logger.warning("long_term_roi başarısız: %s", e)
        return {"total": 0, "won": 0, "lost": 0, "pnl_try": 0.0, "roi_pct": 0.0}
