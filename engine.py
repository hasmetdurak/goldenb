"""
GoldenBet AI - Dual Team Score Engine
======================================

İki takımın skorunu ayrı kanallardan simüle eden Monte Carlo motoru.

Her takım (Ev / Dep) kendi bias_weight ve variance_modifier parametresine
sahiptir. Çeyrek sonlarinda güncellenir ve model_weights.json dosyasina
yazilarak kalici hale getirilir.

Kullanim
--------
    engine = DualTeamScoreEngine()
    result = engine.predict_match_scoreboard(
        current_home=0, current_away=0,
        current_minute=0,
        baseline_home_avg=110.0, baseline_away_avg=105.0,
        total_minutes=48, context_tag="Normal_Season_Match",
        league="NBA"
    )
    result["home_predicted"], result["away_predicted"], result["total_predicted"]
    result["q1_home"], ... , result["q4_away"]
    result["home_h1"], result["away_h1"]

    # Ogre
    engine.update_team_weights(quarter, pred_home, actual_home,
                                pred_away, actual_away)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

import config as cfg


# -----------------------------------------------------------------------------
# Sabitler
# -----------------------------------------------------------------------------
DEFAULT_LEARNING_RATE = 0.15
DEFAULT_N_ITER = 10_000
DEFAULT_ODDS = 1.91

WEIGHTS_FILE = os.path.join(os.path.dirname(__file__), "model_weights.json")

# Ceyrek agirliklari (NBA: Q2/Q4 yuksek tempo, Euro: daha dengeli)
#   Bu agirliklar final dagilimindan ceyrek krilimlarina bolmek icindir.
#   Toplam = 1.0 (her takim icin final = sum(q1..q4))
QUARTER_WEIGHTS: Dict[str, List[float]] = {
    "NBA":       [0.22, 0.27, 0.22, 0.29],
    "EUROLEAGUE": [0.24, 0.26, 0.24, 0.26],
    "EUROCUP":    [0.24, 0.26, 0.24, 0.26],
}


# -----------------------------------------------------------------------------
# Dual Team Score Engine
# -----------------------------------------------------------------------------
class DualTeamScoreEngine:
    """
    Iki takimli Monte Carlo motoru.

    Ev sahibi ve deplasman icin AYRI bias_weight ile variance_modifier
    parametreleri ogrenilir ve model_weights.json dosyasinda kalici hale
    getirilir.
    """

    def __init__(self, learning_rate: float = DEFAULT_LEARNING_RATE,
                 n_iter: int = DEFAULT_N_ITER) -> None:
        self.learning_rate = learning_rate
        self.n_iter = n_iter

        # Ev sahibi parametreleri
        self.bias_home: float = 0.0
        self.variance_modifier_home: float = 1.0

        # Deplasman parametreleri
        self.bias_away: float = 0.0
        self.variance_modifier_away: float = 1.0

        self.learning_history: List[Dict[str, Any]] = []

        self.load_knowledge_from_code()

    # ------------------------------------------------------------------
    # Ogre
    # ------------------------------------------------------------------
    def update_team_weights(self, quarter: int,
                            pred_home: float, actual_home: float,
                            pred_away: float, actual_away: float) -> Dict[str, float]:
        """
        Her iki takim icin bias/variance guncellemesi.

        Degerlendirme:
            bias_home   += error_home * learning_rate
            bias_away   += error_away * learning_rate
            |error| > 3 => variance *= 1.10
            |error| <=3 => variance = max(0.4, variance * 0.90)

        Q4 sonrasi save_knowledge_to_code() cagrilir.
        """
        error_home = float(actual_home) - float(pred_home)
        error_away = float(actual_away) - float(pred_away)

        self.bias_home += error_home * self.learning_rate
        self.bias_away += error_away * self.learning_rate

        for vm_attr, err in (
            ("variance_modifier_home", error_home),
            ("variance_modifier_away", error_away),
        ):
            current = float(getattr(self, vm_attr))
            if abs(err) > 3.0:
                setattr(self, vm_attr, current * 1.10)
            else:
                setattr(self, vm_attr, max(0.4, current * 0.90))

        all_errs = [
            abs(h["Hata_Home"]) + abs(h["Hata_Away"])
            for h in self.learning_history
        ]
        new_mae = (
            (sum(all_errs) + abs(error_home) + abs(error_away))
            / (len(all_errs) + 1)
            if all_errs
            else (abs(error_home) + abs(error_away)) / 2.0
        )

        self.learning_history.append({
            "Ceyrek": quarter,
            "Tahmin_Home": round(float(pred_home), 2),
            "Gercek_Home": round(float(actual_home), 2),
            "Hata_Home": round(error_home, 2),
            "Tahmin_Away": round(float(pred_away), 2),
            "Gercek_Away": round(float(actual_away), 2),
            "Hata_Away": round(error_away, 2),
            "Bias_Home": round(self.bias_home, 3),
            "Bias_Away": round(self.bias_away, 3),
            "Variance_Home": round(self.variance_modifier_home, 3),
            "Variance_Away": round(self.variance_modifier_away, 3),
            "MAE": round(new_mae, 3),
        })

        if quarter >= 4:
            self.save_knowledge_to_code()

        return {"error_home": error_home, "error_away": error_away}

    def current_mae(self) -> float:
        if not self.learning_history:
            return 0.0
        return float(self.learning_history[-1].get("MAE", 0.0))

    # ------------------------------------------------------------------
    # Tahmin: Tam Skor Tabelasi (Final + 1H + 4 ceyrek)
    # ------------------------------------------------------------------
    def predict_match_scoreboard(self,
                                 current_home: float,
                                 current_away: float,
                                 current_minute: float,
                                 baseline_home_avg: float,
                                 baseline_away_avg: float,
                                 total_minutes: int = 40,
                                 context_tag: str = "Normal_Season_Match",
                                 league: str = "NBA") -> Dict[str, Any]:
        """
        10.000 iterasyonlu Monte Carlo ile full skor tabelasi uretir.

        Cikti:
            home_predicted, away_predicted, total_predicted
            home_h1, away_h1 (1. Yari)
            q1_home, q1_away, q2_home, q2_away, q3_home, q3_away, q4_home, q4_away
            p10/p50/p90 (final)
            meta: bias/variance, context bilgisi, quarter_weights
        """
        remaining = max(0.0, float(total_minutes) - float(current_minute))

        # --- Yapisal Kural Matrisi ---
        ctx = cfg.get_context_modifier(context_tag)
        pace_mult = float(ctx.get("pace_multiplier", 1.0))
        var_mult = float(ctx.get("variance_multiplier", 1.0))
        league_var = cfg.get_league_variance(league)
        league_pace = cfg.get_league_pace(league)

        # Lig-bazli ceyrek agirliklari
        q_weights = QUARTER_WEIGHTS.get(
            league.upper() if league else "NBA",
            QUARTER_WEIGHTS["NBA"],
        )

        if remaining <= 0:
            home_total = float(current_home)
            away_total = float(current_away)
            total_total = home_total + away_total
            q = {
                "home_predicted": home_total,
                "away_predicted": away_total,
                "total_predicted": total_total,
                "home_h1": home_total,
                "away_h1": away_total,
                "q1_home": home_total * q_weights[0],
                "q1_away": away_total * q_weights[0],
                "q2_home": home_total * q_weights[1],
                "q2_away": away_total * q_weights[1],
                "q3_home": home_total * q_weights[2],
                "q3_away": away_total * q_weights[2],
                "q4_home": home_total * q_weights[3],
                "q4_away": away_total * q_weights[3],
            }
            return self._finalize(q, ctx, league_var, pace_mult, var_mult,
                                  q_weights, league)

        eff_home = float(baseline_home_avg) * league_pace * pace_mult
        eff_away = float(baseline_away_avg) * league_pace * pace_mult

        home_per_min = eff_home / float(total_minutes)
        away_per_min = eff_away / float(total_minutes)

        home_mu = home_per_min + (self.bias_home / float(total_minutes))
        away_mu = away_per_min + (self.bias_away / float(total_minutes))

        home_sigma = (
            0.6
            * self.variance_modifier_home
            * league_var
            * var_mult
            * np.sqrt(remaining / 40.0)
        )
        away_sigma = (
            0.6
            * self.variance_modifier_away
            * league_var
            * var_mult
            * np.sqrt(remaining / 40.0)
        )

        home_sim = np.random.normal(home_mu, max(home_sigma, 0.01), self.n_iter)
        away_sim = np.random.normal(away_mu, max(away_sigma, 0.01), self.n_iter)

        home_remaining = home_sim * remaining
        away_remaining = away_sim * remaining

        home_final = float(current_home) + home_remaining
        away_final = float(current_away) + away_remaining
        total_final = home_final + away_final

        # Ceyrek dagilimi: Q1+Q2+Q3+Q4 = final (tutarlilik)
        # Ornek: home_q = home_final{:, np.newaxis} * np.array(q_weights)
        home_mean = float(np.mean(home_final))
        away_mean = float(np.mean(away_final))
        total_mean = float(np.mean(total_final))

        q = {
            "home_predicted": home_mean,
            "away_predicted": away_mean,
            "total_predicted": total_mean,
            "home_h1": home_mean * (q_weights[0] + q_weights[1]),
            "away_h1": away_mean * (q_weights[0] + q_weights[1]),
            "q1_home": home_mean * q_weights[0],
            "q1_away": away_mean * q_weights[0],
            "q2_home": home_mean * q_weights[1],
            "q2_away": away_mean * q_weights[1],
            "q3_home": home_mean * q_weights[2],
            "q3_away": away_mean * q_weights[2],
            "q4_home": home_mean * q_weights[3],
            "q4_away": away_mean * q_weights[3],
            # Percentiles
            "home_p10": float(np.percentile(home_final, 10)),
            "home_p50": float(np.percentile(home_final, 50)),
            "home_p90": float(np.percentile(home_final, 90)),
            "away_p10": float(np.percentile(away_final, 10)),
            "away_p50": float(np.percentile(away_final, 50)),
            "away_p90": float(np.percentile(away_final, 90)),
            "total_p10": float(np.percentile(total_final, 10)),
            "total_p50": float(np.percentile(total_final, 50)),
            "total_p90": float(np.percentile(total_final, 90)),
        }
        return self._finalize(q, ctx, league_var, pace_mult, var_mult,
                              q_weights, league)

    def _finalize(self, q: Dict[str, Any],
                  ctx: Dict[str, Any],
                  league_var: float,
                  pace_mult: float,
                  var_mult: float,
                  q_weights: List[float],
                  league: str) -> Dict[str, Any]:
        """Meta bilgileri ekleyerek dict'i tamamlar."""
        q["effective_baseline_home"] = round(
            q.get("home_predicted", 0) / 1.0, 2
        )
        q["effective_baseline_away"] = round(
            q.get("away_predicted", 0) / 1.0, 2
        )
        q["bias_home"] = self.bias_home
        q["bias_away"] = self.bias_away
        q["variance_modifier_home"] = self.variance_modifier_home
        q["variance_modifier_away"] = self.variance_modifier_away
        q["context_tag"] = ctx.get("label", "")
        q["context_emoji"] = ctx.get("emoji", "")
        q["context_pace_multiplier"] = pace_mult
        q["context_variance_multiplier"] = var_mult
        q["league_variance"] = league_var
        q["quarter_weights"] = q_weights
        q["league"] = league
        return q

    # ------------------------------------------------------------------
    # Kalici Hafiza
    # ------------------------------------------------------------------
    def save_knowledge_to_code(self) -> None:
        """Bias/variance'i JSON dosyasina yazar. Hata durumunda no-op."""
        try:
            data = {
                "bias_home": round(self.bias_home, 4),
                "bias_away": round(self.bias_away, 4),
                "variance_modifier_home": round(self.variance_modifier_home, 4),
                "variance_modifier_away": round(self.variance_modifier_away, 4),
                "learning_rate": self.learning_rate,
                "n_iter": self.n_iter,
            }
            with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def load_knowledge_from_code(self) -> None:
        """JSON'dan geri yukler. Dosya yoksa no-op."""
        try:
            if not os.path.exists(WEIGHTS_FILE):
                return
            with open(WEIGHTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.bias_home = float(data.get("bias_home", 0.0))
            self.bias_away = float(data.get("bias_away", 0.0))
            self.variance_modifier_home = float(
                data.get("variance_modifier_home", 1.0)
            )
            self.variance_modifier_away = float(
                data.get("variance_modifier_away", 1.0)
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Sifirlama ve Gecmis
    # ------------------------------------------------------------------
    def reset_learning(self) -> None:
        self.bias_home = 0.0
        self.bias_away = 0.0
        self.variance_modifier_home = 1.0
        self.variance_modifier_away = 1.0
        self.learning_history = []

    def history_dataframe(self) -> pd.DataFrame:
        if not self.learning_history:
            return pd.DataFrame(columns=[
                "Ceyrek", "Tahmin_Home", "Gercek_Home", "Hata_Home",
                "Tahmin_Away", "Gercek_Away", "Hata_Away",
                "Bias_Home", "Bias_Away",
                "Variance_Home", "Variance_Away", "MAE",
            ])
        return pd.DataFrame(self.learning_history)
