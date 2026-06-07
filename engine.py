"""
GoldenBet AI - Monte Carlo Simülasyon ve Risk Çekirdeği
========================================================

AdaptiveMonteCarloEngine: 10.000 iterasyonlu Monte Carlo simülasyonu.
Her çeyrek sonunda gerçek skorla karşılaştırma yaparak `bias_weight`
ve `variance_modifier` parametrelerini logaritmik öğrenme katsayısı
(`learning_rate`) ile kalibre eder. Bir sonraki tahmin, eğitilmiş
dağılımla üretilir.

Sinyal Algoritması:
    * ÜST  → diff >= +2.0 VE confidence >= %65
    * ALT  → diff <= -2.0
    * PAS  → arada
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

import config as cfg


# -----------------------------------------------------------------------------
# Sabitler (Bilgi Yoğunluğuna Göre Logaritmik Kasa Dağılımı)
# -----------------------------------------------------------------------------
PREMATCH_BUDGET_SHARE = 0.50      # Toplam bütçenin maç öncesi pusuya giden kısmı
LIVE_BUDGET_SHARE = 0.50          # Canlı nakit kurşunlara ayrılan kısım
LADDER_LEVELS = 5                 # Maç öncesi merdiven kademe sayısı
LADDER_HALF_SPREAD = 4.0          # Merdiven toplam yarı açıklığı (±4 → 5 kademe)

OVER_THRESHOLD = 2.0              # AI_pred - piyasa >= +2.0 → ÜST
UNDER_THRESHOLD = -2.0            # AI_pred - piyasa <= -2.0 → ALT (HEDGE)
MIN_CONFIDENCE_PCT = 65.0         # Minimum güven endeksi (ÜST için)

# Logaritmik kasa dağılımı — bilgi saflık katsayısı arttıkça pay büyür
LIVE_PHASE_DISTRIBUTION: Dict[str, float] = {
    "Q1_END": 0.10,
    "Q2_END": 0.15,
    "Q3_END": 0.25,
    "LAST_2_MIN": 0.50,
}

DEFAULT_ODDS = 1.91               # Bahis oranı varsayılanı (10/11 Avrupa baremi)


# -----------------------------------------------------------------------------
# Adaptive Monte Carlo Engine
# -----------------------------------------------------------------------------
class AdaptiveMonteCarloEngine:
    """
    Öğrenen Monte Carlo motoru. `bias_weight` ve `variance_modifier`
    parametreleri, her `update_learning_weights` çağrısında gerçek
    ölçümlerle kalibre edilir.
    """

    def __init__(self, learning_rate: float = 0.15, n_iter: int = 10_000) -> None:
        self.learning_rate = learning_rate
        self.n_iter = n_iter
        self.bias_weight: float = 0.0          # Nötr başlangıç
        self.variance_modifier: float = 1.0   # Standart oynaklık
        self.learning_history: List[Dict[str, Any]] = []

    # ----- Öğrenme -----
    def update_learning_weights(self, quarter: int,
                                predicted_at_quarter: float,
                                actual_at_quarter: float) -> float:
        """
        Çeyrek sonu gerçek skoru tahminle karşılaştırıp bias/variance'ı kalibre eder.
        Dönüş: ham hata (actual - predicted).
        """
        error = float(actual_at_quarter) - float(predicted_at_quarter)
        # Logaritmik/çarpımsal öğrenme
        self.bias_weight += error * self.learning_rate
        # Varyans: hata büyükse dağılımı genişlet, küçükse daralt
        if abs(error) > 5:
            self.variance_modifier *= 1.1
        else:
            self.variance_modifier = max(0.4, self.variance_modifier * 0.9)

        # MAE güncelle
        mae = float(np.mean([abs(h["Hata"]) for h in self.learning_history] or [0.0]))
        self.learning_history.append({
            "Çeyrek": quarter,
            "Tahmin": round(float(predicted_at_quarter), 2),
            "Gerçek": round(float(actual_at_quarter), 2),
            "Hata": round(error, 2),
            "Bias_Weight": round(self.bias_weight, 3),
            "Variance_Mod": round(self.variance_modifier, 3),
            "MAE": round((mae * len(self.learning_history) + abs(error))
                          / (len(self.learning_history) + 1), 3),
        })
        return error

    # ----- Tahmin -----
    def predict_remaining_game(self,
                              current_score: float,
                              current_minute: float,
                              baseline_avg: float,
                              bookmaker_line: Optional[float] = None,
                              total_minutes: int = 40,
                              context_tag: str = "Normal_Season_Match",
                              league: Optional[str] = None) -> Dict[str, Any]:
        """
        Eğitilmiş ağırlıklarla 10.000 iterasyonlu Monte Carlo koşturur.

        Yapısal kural matrisi uygulaması:
            * Lig bazlı varyans (NBA=1.20, EuroLeague=0.85, EuroCup=0.90)
            * Bağlam etiketi (context_tag) → pace_multiplier baseline'a,
              variance_multiplier standart sapmaya uygulanır.
            * Adaptif bias_weight / variance_modifier de eklenir.

        Parametreler
        ----------
        current_score      : Şu anki kümülatif toplam skor
        current_minute     : Şu anki maç dakikası (0..total_minutes)
        baseline_avg       : Maç başına beklenen toplam skor (veri ortalaması)
        bookmaker_line     : Piyasa ÜST/ALT baremi (opsiyonel)
        total_minutes      : Maçın toplam dakikası (NBA=48, EuroLeague=40)
        context_tag        : CONTEXTUAL_MODIFIERS anahtarı
        league             : "NBA" | "EUROLEAGUE" | "EUROCUP" (opsiyonel)
        """
        remaining = max(0.0, float(total_minutes) - float(current_minute))
        if remaining <= 0:
            return {
                "final_predicted_score": float(current_score),
                "confidence_pct": 100.0,
                "p10": float(current_score),
                "p50": float(current_score),
                "p90": float(current_score),
                "distribution": np.array([float(current_score)]),
                "bias_weight": self.bias_weight,
                "variance_modifier": self.variance_modifier,
                "context_tag": context_tag,
                "league_variance": cfg.get_league_variance(league or ""),
            }

        # ---- Yapısal Kural Matrisi Katmanları ----
        ctx = cfg.get_context_modifier(context_tag)
        pace_mult = float(ctx.get("pace_multiplier", 1.0))
        var_mult = float(ctx.get("variance_multiplier", 1.0))
        league_var = cfg.get_league_variance(league or "")
        league_pace = cfg.get_league_pace(league or "")

        # Tempo: lig × bağlam
        effective_baseline = float(baseline_avg) * league_pace * pace_mult
        base_per_minute = effective_baseline / float(total_minutes)

        # Eğitilmiş tempo — bias eklendi
        adapted_mu = base_per_minute + (self.bias_weight / float(total_minutes))

        # Eğitilmiş oynaklık — adaptif × lig × bağlam × kalan-süre ölçeklemesi
        adapted_sigma = (
            0.6
            * self.variance_modifier
            * league_var
            * var_mult
            * np.sqrt(remaining / 40.0)
        )

        sim = np.random.normal(adapted_mu, adapted_sigma, self.n_iter) * remaining
        finals = float(current_score) + sim

        confidence_pct: Optional[float] = None
        if bookmaker_line is not None:
            confidence_pct = float((finals > float(bookmaker_line)).mean() * 100.0)

        return {
            "final_predicted_score": float(np.mean(finals)),
            "confidence_pct": confidence_pct,
            "p10": float(np.percentile(finals, 10)),
            "p50": float(np.percentile(finals, 50)),
            "p90": float(np.percentile(finals, 90)),
            "distribution": finals,
            "bias_weight": self.bias_weight,
            "variance_modifier": self.variance_modifier,
            "context_tag": context_tag,
            "league_variance": league_var,
            "context_pace_multiplier": pace_mult,
            "context_variance_multiplier": var_mult,
            "effective_baseline": round(effective_baseline, 2),
        }

    # ----- Geçmiş erişimi -----
    def history_dataframe(self) -> pd.DataFrame:
        """Öğrenme geçmişini Pandas DataFrame olarak döndürür."""
        if not self.learning_history:
            return pd.DataFrame(
                columns=["Çeyrek", "Tahmin", "Gerçek", "Hata",
                         "Bias_Weight", "Variance_Mod", "MAE"]
            )
        return pd.DataFrame(self.learning_history)

    def current_mae(self) -> float:
        """En son MAE değerini döndürür."""
        if not self.learning_history:
            return 0.0
        return float(self.learning_history[-1].get("MAE", 0.0))

    def reset_learning(self) -> None:
        """Tüm öğrenilmiş ağırlıkları sıfırlar."""
        self.bias_weight = 0.0
        self.variance_modifier = 1.0
        self.learning_history = []


# -----------------------------------------------------------------------------
# Geriye Uyumluluk Helper'ı
# -----------------------------------------------------------------------------
def run_monte_carlo(current_score: float,
                    current_minute: float,
                    baseline_avg: float,
                    bookmaker_line: float,
                    n_iter: int = 10_000,
                    total_minutes: int = 40,
                    context_tag: str = "Normal_Season_Match",
                    league: Optional[str] = None) -> Dict[str, Any]:
    """
    Eski `run_monte_carlo` API'si. AdaptiveMonteCarloEngine'in nötr halini
    kullanır (bias_weight=0, variance_modifier=1.0). Aynı sonuç verir.

    Yeni parametreler: context_tag, league → Yapısal Kural Matrisi.
    """
    engine = AdaptiveMonteCarloEngine(learning_rate=0.15, n_iter=n_iter)
    return engine.predict_remaining_game(
        current_score=current_score,
        current_minute=current_minute,
        baseline_avg=baseline_avg,
        bookmaker_line=bookmaker_line,
        total_minutes=total_minutes,
        context_tag=context_tag,
        league=league,
    )


# -----------------------------------------------------------------------------
# Sinyal Üretimi
# -----------------------------------------------------------------------------
def generate_signal(ai_pred: float,
                    market_line: float,
                    confidence_pct: Optional[float]) -> Dict[str, str]:
    """
    AI tahmini ile piyasa baremi arasındaki farka göre ÜST/ALT/PAS üretir.

    Dönüş:
        {"order": "ÜST"|"ALT (HEDGE)"|"PAS",
         "strength": "GÜÇLÜ"|"KORUMA"|"ZAYIF",
         "diff": str, "confidence": str}
    """
    try:
        diff = float(ai_pred) - float(market_line)
    except (TypeError, ValueError):
        diff = 0.0
    conf = float(confidence_pct) if confidence_pct is not None else 0.0

    if diff >= OVER_THRESHOLD and conf >= MIN_CONFIDENCE_PCT:
        return {
            "order": "ÜST",
            "strength": "GÜÇLÜ",
            "diff": f"{diff:+.2f}",
            "confidence": f"{conf:.1f}%",
        }
    if diff <= UNDER_THRESHOLD:
        return {
            "order": "ALT (HEDGE)",
            "strength": "KORUMA",
            "diff": f"{diff:+.2f}",
            "confidence": f"{conf:.1f}%",
        }
    return {
        "order": "PAS",
        "strength": "ZAYIF",
        "diff": f"{diff:+.2f}",
        "confidence": f"{conf:.1f}%",
    }


# -----------------------------------------------------------------------------
# Maç Öncesi Merdiven (5 Kademe) ve Canlı Emir Planı
# -----------------------------------------------------------------------------
def build_ladder_lines(baseline_total: float) -> List[float]:
    """
    Simetrik 5 kademeli merdiven baremlerini üretir.
    Örnek: baseline=210 → [206.5, 208.5, 210.5, 212.5, 214.5]
    """
    base = float(baseline_total)
    step = LADDER_HALF_SPREAD / ((LADDER_LEVELS - 1) / 2)  # 4/2 = 2.0
    levels = [base + (i - 2) * step for i in range(LADDER_LEVELS)]
    # 0.5 barem aralığına yuvarla
    return [round(x * 2) / 2 for x in levels]


def build_prematch_orders(budget: float,
                          ladder_lines: List[float],
                          odds: float = DEFAULT_ODDS) -> pd.DataFrame:
    """
    Maç öncesi %50 bütçeyi 5 eşit kademeye böler, her birini merdiven bareminde
    ÜST yönünde planlar.
    """
    prematch_pool = float(budget) * PREMATCH_BUDGET_SHARE
    per_ladder = prematch_pool / LADDER_LEVELS
    rows = []
    for i, line in enumerate(ladder_lines, start=1):
        rows.append({
            "Faz": "PRE-MATCH",
            "Kademe": i,
            "Barem": line,
            "Tutar (₺)": round(per_ladder, 2),
            "Oran": odds,
            "Yön": "ÜST",
            "Güç": "PUSU",
        })
    return pd.DataFrame(rows)


def determine_live_phase(current_minute: float, total_minutes: int = 40) -> str:
    """
    Kalan dakikaya göre hangi fazda olduğumuzu belirler.
    """
    if total_minutes >= 48:  # NBA
        per_q = 12
    else:                   # EuroLeague/EuroCup
        per_q = 10
    last2_threshold = total_minutes - 2.0

    if current_minute < per_q:
        return "Q1_END"
    if current_minute < 2 * per_q:
        return "Q2_END"
    if current_minute < 3 * per_q:
        return "Q3_END"
    if current_minute >= last2_threshold:
        return "LAST_2_MIN"
    # Çeyrekler arası
    return "Q3_END"  # güvenli default


def build_live_order_plan(budget: float,
                          signal: Dict[str, str],
                          current_minute: float,
                          total_minutes: int = 40,
                          odds: float = DEFAULT_ODDS) -> pd.DataFrame:
    """
    Canlı %50 bütçeyi mevcut faza göre dağıtır ve tek satırlık emir önerir.
    """
    live_pool = float(budget) * LIVE_BUDGET_SHARE
    phase = determine_live_phase(current_minute, total_minutes)
    share = LIVE_PHASE_DISTRIBUTION.get(phase, 0.10)
    amount = live_pool * share

    return pd.DataFrame([{
        "Faz": phase,
        "Kademe": "—",
        "Barem": "—",
        "Tutar (₺)": round(amount, 2),
        "Oran": odds,
        "Yön": signal.get("order", "PAS"),
        "Güç": signal.get("strength", "ZAYIF"),
    }])


# -----------------------------------------------------------------------------
# Backtest
# -----------------------------------------------------------------------------
def backtest(df: pd.DataFrame,
             baseline_avg: float,
             total_minutes: int = 48,
             line_offset: float = 0.0,
             n_iter: int = 5_000,
             context_tag: str = "Normal_Season_Match",
             league: Optional[str] = None) -> Dict[str, Any]:
    """
    Geçmiş maçlar üzerinde motor koşturur, ÜST/ALT isabet oranı ve ROI hesaplar.

    Her maç için varsayım: maç ortası (toplam_minutes/2) senaryosu ile
    tahmin üretilir, barem `baseline_avg + line_offset` olur.

    Yapısal kural matrisi: `context_tag` ve `league` ile her maça aynı
    bağlamı uygular (varsayılan normal sezon). NBA vs EuroLeague
    varyans farkı bu sayede backtest'e de yansır.

    NBA için 'SAYI' (tek takım) → 2x ile maç toplamı tahmin edilir.
    EuroLeague için 'TOPLAM' doğrudan kullanılır.
    """
    if df is None or df.empty or baseline_avg <= 0:
        return {
            "hit_rate_pct": 0.0,
            "roi_pct": 0.0,
            "total_simulations": 0,
            "avg_diff": 0.0,
            "details": pd.DataFrame(),
        }

    n = min(len(df), 60)  # performans için sınır
    sample = df.tail(n).copy()

    if "TOPLAM" in sample.columns:
        actual_totals = pd.to_numeric(sample["TOPLAM"], errors="coerce").dropna()
    elif "SAYI" in sample.columns:
        actual_totals = (
            pd.to_numeric(sample["SAYI"], errors="coerce").dropna() * 2.0
        )
    else:
        return {
            "hit_rate_pct": 0.0, "roi_pct": 0.0,
            "total_simulations": 0, "avg_diff": 0.0,
            "details": pd.DataFrame(),
        }

    engine = AdaptiveMonteCarloEngine(learning_rate=0.0, n_iter=n_iter)
    market_line = float(baseline_avg) + float(line_offset)
    half = float(total_minutes) / 2.0

    hits = 0
    diffs: List[float] = []
    rows = []
    for actual in actual_totals.tolist():
        # "Şu an" senaryosu: maç ortası, skor=baseline/2
        cur_score = float(baseline_avg) * (half / float(total_minutes))
        pred = engine.predict_remaining_game(
            current_score=cur_score,
            current_minute=half,
            baseline_avg=float(baseline_avg),
            bookmaker_line=market_line,
            total_minutes=int(total_minutes),
            context_tag=context_tag,
            league=league,
        )
        predicted = pred["final_predicted_score"]
        # Bahis: tahmin piyasanın üstündeyse ÜST, altındaysa ALT
        if predicted > market_line:
            pick = "ÜST"
        else:
            pick = "ALT"
        if pick == "ÜST" and actual > market_line:
            hits += 1
        elif pick == "ALT" and actual < market_line:
            hits += 1
        diffs.append(actual - predicted)
        rows.append({
            "Tahmin": round(predicted, 2),
            "Gerçek": round(actual, 2),
            "Piyasa": market_line,
            "Seçim": pick,
            "Sapma": round(actual - predicted, 2),
        })

    total = len(actual_totals)
    hit_rate = (hits / total * 100.0) if total else 0.0
    # ROI: 1.91 oranında isabet başına net +0.91 birim
    roi = (hits * 0.91 - (total - hits)) / total * 100.0 if total else 0.0
    return {
        "hit_rate_pct": round(hit_rate, 2),
        "roi_pct": round(roi, 2),
        "total_simulations": total,
        "avg_diff": round(float(np.mean(diffs)) if diffs else 0.0, 2),
        "details": pd.DataFrame(rows),
    }
