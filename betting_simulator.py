"""
GoldenBet AI - Bahis Simülatörü
================================

Tam kapsamlı bahis simülasyon motoru:
- Kelly Criterion, Flat Betting, Martingale
- Bankroll yönetimi, drawdown limitleri
- Multi-book odds simülasyonu
- Strateji optimizer (parametre sweep)
- ROI, Sharpe ratio, max drawdown metrikleri
- Betting dashboard için Streamlit entegrasyonu
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

# -----------------------------------------------------------------------------
# Sabitler
# -----------------------------------------------------------------------------
DEFAULT_MAX_BANKROLL = 10_000.0
DEFAULT_UNIT_STAKE = 100.0
DEFAULT_ODDS = 1.91  # -110 / -110 vig
DEFAULT_VIG = 0.0476  # ~4.76%
KELLY_FRACTION = 0.25  # fractional Kelly (conservative)

STRATEGY_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "strategy_config.json")


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------
class BetResult(Enum):
    WIN = "win"
    LOSS = "loss"
    PUSH = "push"


class StrategyType(Enum):
    KELLY = "kelly"
    FLAT = "flat"
    VALUE = "value"
    MARTINGALE = "martingale"
    ARBITRAGE = "arbitrage"


# -----------------------------------------------------------------------------
# Data Classes
# -----------------------------------------------------------------------------
@dataclass
class Bet:
    game_id: str
    league: str
    home_team: str
    away_team: str
    predicted_total: float
    market_total: float
    odds: float
    stake: float
    side: str  # "over" or "under"
    timestamp: str = ""
    result: BetResult | None = None
    actual_total: float | None = None
    pnl: float = 0.0
    strategy: str = ""

    @property
    def is_over(self) -> bool:
        return self.side == "over"

    @property
    def is_winner(self) -> bool | None:
        if self.result is None or self.actual_total is None:
            return None
        if self.result == BetResult.PUSH:
            return None
        if self.is_over:
            return self.actual_total > self.market_total
        return self.actual_total < self.market_total

    @property
    def payout(self) -> float:
        if self.result == BetResult.PUSH:
            return self.stake
        if self.result == BetResult.WIN:
            return self.stake * self.odds
        return 0.0

    @property
    def total_bets(self) -> int:
        return 1

    def __post_init__(self) -> None:
        if self.pnl == 0.0 and self.result is not None and self.stake > 0:
            if self.result == BetResult.WIN:
                self.pnl = self.stake * (self.odds - 1.0)
            elif self.result == BetResult.LOSS:
                self.pnl = -self.stake

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "result": self.result.value if self.result else None,
            "is_over": self.is_over,
        }


@dataclass
class Bankroll:
    initial: float
    current: float
    peak: float
    total_staked: float = 0.0
    total_pnl: float = 0.0
    total_wins: int = 0
    total_losses: int = 0
    total_pushes: int = 0
    bet_history: list[Bet] = field(default_factory=list)
    drawdown_limit: float = 0.25  # %25 max drawdown

    @property
    def roi(self) -> float:
        if self.total_staked == 0:
            return 0.0
        return (self.total_pnl / self.total_staked) * 100.0

    @property
    def win_rate(self) -> float:
        total = self.total_wins + self.total_losses
        if total == 0:
            return 0.0
        return self.total_wins / total * 100.0

    @property
    def drawdown(self) -> float:
        if self.peak == 0:
            return 0.0
        return (self.peak - self.current) / self.peak

    @property
    def is_bankrupted(self) -> bool:
        return self.current <= 0

    @property
    def is_drawdown_hit(self) -> bool:
        return self.drawdown >= self.drawdown_limit

    @property
    def total_bets(self) -> int:
        return len(self.bet_history)

    @property
    def sharpe_ratio(self) -> float:
        if len(self.bet_history) < 2:
            return 0.0
        returns = [b.pnl / max(b.stake, 1) for b in self.bet_history]
        if len(returns) < 2 or np.std(returns) == 0:
            return 0.0
        return float(np.mean(returns) / np.std(returns) * math.sqrt(len(returns)))

    def record_bet(self, bet: Bet) -> None:
        self.bet_history.append(bet)
        self.total_staked += bet.stake
        self.total_pnl += bet.pnl
        self.current += bet.pnl
        if self.current > self.peak:
            self.peak = self.current
        if bet.result == BetResult.WIN:
            self.total_wins += 1
        elif bet.result == BetResult.LOSS:
            self.total_losses += 1
        elif bet.result == BetResult.PUSH:
            self.total_pushes += 1

    def can_bet(self, stake: float) -> bool:
        if self.is_bankrupted or self.is_drawdown_hit:
            return False
        return stake <= self.current

    def summary(self) -> dict[str, Any]:
        return {
            "initial": round(self.initial, 2),
            "current": round(self.current, 2),
            "peak": round(self.peak, 2),
            "total_staked": round(self.total_staked, 2),
            "total_pnl": round(self.total_pnl, 2),
            "roi_pct": round(self.roi, 2),
            "win_rate": round(self.win_rate, 2),
            "wins": self.total_wins,
            "losses": self.total_losses,
            "pushes": self.total_pushes,
            "total_bets": len(self.bet_history),
            "drawdown_pct": round(self.drawdown * 100, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "is_bankrupted": self.is_bankrupted,
            "is_drawdown_hit": self.is_drawdown_hit,
        }


# -----------------------------------------------------------------------------
# Strateji Fonksiyonları
# -----------------------------------------------------------------------------
def kelly_stake(
    bankroll: Bankroll, predicted_prob: float, odds: float, fraction: float = KELLY_FRACTION
) -> float:
    """
    Kelly Criterion: f* = (bp - q) / b
    b = odds - 1, p = predicted_prob, q = 1 - p
    fractional Kelly ile daha conservative bahis.
    """
    if odds <= 1.0 or predicted_prob <= 0 or predicted_prob >= 1:
        return 0.0
    b = odds - 1.0
    q = 1.0 - predicted_prob
    kelly_pct = (b * predicted_prob - q) / b
    if kelly_pct <= 0:
        return 0.0
    return bankroll.current * kelly_pct * fraction


def flat_stake(bankroll: Bankroll, unit_stake: float = DEFAULT_UNIT_STAKE) -> float:
    """Flat betting - her bahiste sabit birim."""
    return min(unit_stake, bankroll.current)


def value_stake(
    bankroll: Bankroll,
    predicted_prob: float,
    odds: float,
    unit_stake: float = DEFAULT_UNIT_STAKE,
    threshold: float = 0.05,
) -> float:
    """
    Value betting sadece positive edge varken bahis.
    Edge = (predicted_prob * odds) - 1
    Stake = edge * unit_stake (scaled).
    """
    edge = (predicted_prob * odds) - 1.0
    if edge <= threshold:
        return 0.0
    stake = unit_stake * (1.0 + edge * 2.0)
    return min(stake, bankroll.current * 0.1)


def martingale_stake(
    bankroll: Bankroll, base_stake: float = DEFAULT_UNIT_STAKE, max_multiplier: int = 5
) -> float:
    """
    Martingale: son bahis kaybettiyse 2x, limitli.
    """
    if not bankroll.bet_history or bankroll.bet_history[-1].result != BetResult.LOSS:
        return min(base_stake, bankroll.current)
    streak = 0
    for b in reversed(bankroll.bet_history):
        if b.result == BetResult.LOSS:
            streak += 1
        else:
            break
    multiplier = min(2**streak, max_multiplier)
    return min(base_stake * multiplier, bankroll.current)


# -----------------------------------------------------------------------------
# Odds Simülasyonu
# -----------------------------------------------------------------------------
def fair_odds(implied_prob: float, vig: float = DEFAULT_VIG) -> tuple[float, float]:
    """
    V'li over/under çifti üret.
    implied_prob = P(over). Her iki tarafa da toplam vig/2 marj eklenir.
    Örn p=0.50 & vig=0.0476 -> (1.91, 1.91) [-110/-110].
    """
    p_over = min(max(implied_prob, 0.0), 1.0)
    margin = min(max(vig, 0.0), 0.5)
    imp_over = p_over * (1.0 + margin)
    imp_under = (1.0 - p_over) * (1.0 + margin)
    over_odds = 1.0 / imp_over if imp_over > 0 else 2.0
    under_odds = 1.0 / imp_under if imp_under > 0 else 2.0
    return round(over_odds, 2), round(under_odds, 2)


def simulate_book_odds(
    predicted_total: float,
    baseline_total: float,
    num_books: int = 3,
    vig: float = DEFAULT_VIG,
    rng: np.random.Generator | None = None,
) -> list[dict[str, Any]]:
    """
    Farkli bahis site odds'larini simule eder.
    Her book'un kendi vig + margin varyasyonu olur.
    """
    if rng is None:
        rng = np.random.default_rng()
    implied_prob = predicted_total / (predicted_total + baseline_total)
    books = []
    book_names = ["Bet365", "Pinnacle", "DraftKings", "FanDuel", "BetMGM", "Caesars"]
    for i in range(num_books):
        book_vig = vig * (1.0 + rng.normal(0, 0.15))
        book_vig = max(0.01, min(0.15, book_vig))
        margin_offset = rng.normal(0, predicted_total * 0.01)
        book_implied = implied_prob + rng.normal(0, 0.02)
        book_implied = max(0.1, min(0.9, book_implied))
        over_odds, under_odds = fair_odds(book_implied, book_vig)
        books.append(
            {
                "book": book_names[i % len(book_names)],
                "over_odds": over_odds * (1.0 + rng.normal(0, 0.005)),
                "under_odds": under_odds * (1.0 + rng.normal(0, 0.005)),
                "over_line": predicted_total + margin_offset,
                "under_line": predicted_total + margin_offset,
                "vig": round(book_vig * 100, 2),
            }
        )
    return books


def find_best_line(books: list[dict[str, Any]], side: str) -> dict[str, Any]:
    """En iyi odds'u bul."""
    key = f"{side}_odds"
    best = max(books, key=lambda b: b.get(key, 0))
    return best


# -----------------------------------------------------------------------------
# Simülasyon Motoru
# -----------------------------------------------------------------------------
def run_betting_simulation(
    predictions: list[dict[str, Any]],
    actual_results: list[dict[str, Any]],
    strategy: StrategyType = StrategyType.KELLY,
    initial_bankroll: float = DEFAULT_MAX_BANKROLL,
    unit_stake: float = DEFAULT_UNIT_STAKE,
    kelly_fraction: float = KELLY_FRACTION,
    value_threshold: float = 0.05,
    drawdown_limit: float = 0.25,
) -> Bankroll:
    """
    Tam bahis simülasyonu.

    predictions: AI tahminleri listesi. Her tahmin dict'i bu anahtarları
        TANIYABİLİR (opsiyonel):
          market_total      : gerçek konsensus bahisçinin toplam barajı
          odds_over         : en iyi Over fiyatı (ondalık, 1.95 gibi)
          odds_under        : en iyi Under fiyatı
          prob_over_market  : Monte Carlo P(toplam > market_total)
          home_name/away_name: takım adları (rapor için)
    Verilmeyen alanlar için dağılım-kestirimli fallback devreye girer.
    actual_results: Gerçek sonuçlar listesi [{"total": ...}]
    """
    bankroll = Bankroll(
        initial=initial_bankroll,
        current=initial_bankroll,
        peak=initial_bankroll,
        drawdown_limit=drawdown_limit,
    )

    for i, pred in enumerate(predictions):
        if bankroll.is_bankrupted or bankroll.is_drawdown_hit:
            break

        actual = actual_results[i] if i < len(actual_results) else None
        if actual is None:
            continue

        predicted_total = float(pred.get("total_predicted", 0) or 0)
        actual_total = float(actual.get("total", 0) or 0)
        if predicted_total <= 0:
            continue

        # --- Gerçek market verisi yoksa fallback ---
        market_raw = pred.get("market_total")
        if market_raw is None or float(market_raw) <= 0:
            baseline = float(pred.get("effective_baseline_home", 0) or 0) + float(
                pred.get("effective_baseline_away", 0) or 0
            )
            market_total = baseline if baseline > 0 else predicted_total
        else:
            market_total = float(market_raw)

        # --- Olasılık: doğrudan Monte Carlo ya da dağılım kestirimi ---
        prob_over = prob_over_from_distribution(pred, market_total)
        prob_over = min(max(prob_over, 0.0), 1.0)
        prob_under = 1.0 - prob_over

        # --- Oranlar: gerçek var mı? yoksa fair odds (vig'li) ---
        odds_over_raw = pred.get("odds_over")
        odds_under_raw = pred.get("odds_under")
        try:
            odds_over = float(odds_over_raw or 0)
            odds_under = float(odds_under_raw or 0)
        except (TypeError, ValueError):
            odds_over = odds_under = 0.0
        if odds_over <= 1.0 or odds_under <= 1.0 or odds_over + odds_under >= 4.2:
            fair_over, fair_under = fair_odds(prob_over)
            if odds_over <= 1.0:
                odds_over = fair_over
            if odds_under <= 1.0:
                odds_under = fair_under

        # --- Taraf seçimi: model olasılığı ile en yüksek EV ---
        ev_over = prob_over * odds_over - 1.0
        ev_under = prob_under * odds_under - 1.0
        if ev_over >= ev_under:
            side, odds, implied_prob = "over", odds_over, prob_over
        else:
            side, odds, implied_prob = "under", odds_under, prob_under

        # Stake calculation
        if strategy == StrategyType.KELLY:
            stake = kelly_stake(bankroll, implied_prob, odds, kelly_fraction)
        elif strategy == StrategyType.FLAT:
            stake = flat_stake(bankroll, unit_stake)
        elif strategy == StrategyType.VALUE:
            stake = value_stake(bankroll, implied_prob, odds, unit_stake, value_threshold)
        elif strategy == StrategyType.MARTINGALE:
            stake = martingale_stake(bankroll, unit_stake)
        else:
            stake = flat_stake(bankroll, unit_stake)

        if stake <= 0 or not bankroll.can_bet(stake):
            continue

        # Determine result  (yarı baraj push dahil: values p10/p90 dışında da tutarlı)
        if side == "over":
            bet_result = BetResult.WIN if actual_total > market_total else BetResult.LOSS
        else:
            bet_result = BetResult.WIN if actual_total < market_total else BetResult.LOSS
        if actual_total == market_total:
            bet_result = BetResult.PUSH

        pnl = stake * (odds - 1.0) if bet_result == BetResult.WIN else -stake
        if bet_result == BetResult.PUSH:
            pnl = 0.0

        bet = Bet(
            game_id=str(pred.get("game_id", "") or (str(pred.get("league", "")) + "_" + str(i))),
            league=str(pred.get("league", "")),
            home_team=str(pred.get("home_name", "") or pred.get("home_predicted", "")),
            away_team=str(pred.get("away_name", "") or pred.get("away_predicted", "")),
            predicted_total=predicted_total,
            market_total=market_total,
            odds=odds,
            stake=round(stake, 2),
            side=side,
            result=bet_result,
            actual_total=actual_total,
            pnl=round(pnl, 2),
            strategy=strategy.value,
        )
        bankroll.record_bet(bet)

    return bankroll


# -----------------------------------------------------------------------------
# Çoklu Simülasyon (Monte Carlo)
# -----------------------------------------------------------------------------
def monte_carlo_simulation(
    predictions: list[dict[str, Any]],
    actual_results: list[dict[str, Any]],
    strategy: StrategyType = StrategyType.KELLY,
    num_simulations: int = 1000,
    initial_bankroll: float = DEFAULT_MAX_BANKROLL,
    unit_stake: float = DEFAULT_UNIT_STAKE,
    kelly_fraction: float = KELLY_FRACTION,
) -> pd.DataFrame:
    """
    Monte Carlo ile çoklu simülasyon koşar.
    Gerçek sonuçlara noise ekleyerek varyasyon yaratır.
    """
    results = []
    rng = np.random.default_rng()
    for sim in range(num_simulations):
        noisy_results = []
        for ar in actual_results:
            noisy = dict(ar)
            noise = rng.normal(0, 3.0)
            noisy["total"] = float(ar.get("total", 0)) + noise
            noisy_results.append(noisy)

        bankroll = run_betting_simulation(
            predictions,
            noisy_results,
            strategy=strategy,
            initial_bankroll=initial_bankroll,
            unit_stake=unit_stake,
            kelly_fraction=kelly_fraction,
        )
        summary = bankroll.summary()
        summary["simulation"] = sim + 1
        results.append(summary)

    return pd.DataFrame(results)


# -----------------------------------------------------------------------------
# Strateji Optimizasyonu
# -----------------------------------------------------------------------------
@dataclass
class StrategyConfig:
    strategy: StrategyType = StrategyType.KELLY
    initial_bankroll: float = DEFAULT_MAX_BANKROLL
    unit_stake: float = DEFAULT_UNIT_STAKE
    kelly_fraction: float = KELLY_FRACTION
    value_threshold: float = 0.05
    drawdown_limit: float = 0.25
    param_ranges: dict[str, list[float]] = field(
        default_factory=lambda: {
            "kelly_fraction": [0.1, 0.15, 0.25, 0.33, 0.5],
            "value_threshold": [0.0, 0.03, 0.05, 0.08, 0.10],
            "unit_stake": [50, 100, 200, 500],
            "drawdown_limit": [0.15, 0.25, 0.35, 0.50],
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "initial_bankroll": self.initial_bankroll,
            "unit_stake": self.unit_stake,
            "kelly_fraction": self.kelly_fraction,
            "value_threshold": self.value_threshold,
            "drawdown_limit": self.drawdown_limit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyConfig:
        return cls(
            strategy=StrategyType(data.get("strategy", "kelly")),
            initial_bankroll=data.get("initial_bankroll", DEFAULT_MAX_BANKROLL),
            unit_stake=data.get("unit_stake", DEFAULT_UNIT_STAKE),
            kelly_fraction=data.get("kelly_fraction", KELLY_FRACTION),
            value_threshold=data.get("value_threshold", 0.05),
            drawdown_limit=data.get("drawdown_limit", 0.25),
        )


def optimize_strategy(
    predictions: list[dict[str, Any]],
    actual_results: list[dict[str, Any]],
    strategy: StrategyType = StrategyType.KELLY,
    config: StrategyConfig | None = None,
    metric: str = "sharpe_ratio",
) -> tuple[StrategyConfig, dict[str, Any]]:
    """
    Grid search ile en iyi strateji parametrelerini bulur.

    metric: "sharpe_ratio", "roi_pct", "total_pnl"
    """
    if config is None:
        config = StrategyConfig(strategy=strategy)

    best_score = -float("inf")
    best_params: dict[str, Any] | None = None
    best_summary: dict[str, Any] = {}

    param_ranges = config.param_ranges
    keys = list(param_ranges.keys())
    values = list(param_ranges.values())

    from itertools import product

    for combo in product(*values):
        kwargs = dict(zip(keys, combo))

        kelly_f = kwargs.get("kelly_fraction", KELLY_FRACTION)
        unit_s = kwargs.get("unit_stake", DEFAULT_UNIT_STAKE)
        value_t = kwargs.get("value_threshold", 0.05)
        drawdown_l = kwargs.get("drawdown_limit", 0.25)

        bankroll = run_betting_simulation(
            predictions,
            actual_results,
            strategy=strategy,
            initial_bankroll=config.initial_bankroll,
            unit_stake=unit_s,
            kelly_fraction=kelly_f,
            value_threshold=value_t,
            drawdown_limit=drawdown_l,
        )
        summary = bankroll.summary()
        score = summary.get(metric, 0)

        if score > best_score:
            best_score = score
            best_params = dict(kwargs)
            best_summary = summary

    if best_params is None:
        best_params = {}
    best_config = StrategyConfig(
        strategy=strategy,
        initial_bankroll=config.initial_bankroll,
        unit_stake=best_params.get("unit_stake", DEFAULT_UNIT_STAKE),
        kelly_fraction=best_params.get("kelly_fraction", KELLY_FRACTION),
        value_threshold=best_params.get("value_threshold", 0.05),
        drawdown_limit=best_params.get("drawdown_limit", 0.25),
    )

    return best_config, best_summary


# -----------------------------------------------------------------------------
# Walk-Forward Backtesting
# -----------------------------------------------------------------------------
def walk_forward_backtest(
    predictions: list[dict[str, Any]],
    actual_results: list[dict[str, Any]],
    strategy: StrategyType = StrategyType.KELLY,
    window_size: int = 50,
    step_size: int = 10,
    initial_bankroll: float = DEFAULT_MAX_BANKROLL,
) -> pd.DataFrame:
    """
    Walk-forward backtest - zamansal overfitting'i önler.
    Her pencerede optimize edip bir sonraki dilimde test eder.
    """
    if len(predictions) < window_size + step_size:
        df = run_betting_simulation(
            predictions, actual_results, strategy=strategy, initial_bankroll=initial_bankroll
        )
        return pd.DataFrame([df.summary()])

    results = []
    total_bankroll = initial_bankroll

    for start in range(0, len(predictions) - window_size, step_size):
        train_end = start + window_size
        test_end = min(train_end + step_size, len(predictions))

        train_preds = predictions[start:train_end]
        train_actuals = actual_results[start:train_end]
        test_preds = predictions[train_end:test_end]
        test_actuals = actual_results[train_end:test_end]

        if not test_preds:
            continue

        best_config, _ = optimize_strategy(train_preds, train_actuals, strategy=strategy)

        bankroll = run_betting_simulation(
            test_preds,
            test_actuals,
            strategy=strategy,
            initial_bankroll=total_bankroll,
            unit_stake=best_config.unit_stake,
            kelly_fraction=best_config.kelly_fraction,
        )

        summary = bankroll.summary()
        summary["window"] = f"{start}-{test_end}"
        summary["train_games"] = len(train_preds)
        summary["test_games"] = len(test_preds)
        results.append(summary)
        total_bankroll = bankroll.current

    return pd.DataFrame(results)


# -----------------------------------------------------------------------------
# Yardımcı Fonksiyonlar
# -----------------------------------------------------------------------------
def normal_cdf(x: float) -> float:
    """Standart normal CDF (scipy bağımlılığı olmadan)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def estimate_sigma(pred: dict[str, Any]) -> float:
    """
    Tahmin dağılımının std sapmasını çıkar.
    Öncelik: Monte Carlo p10/p90 (2.563 sigma aralığı); yoksa kaba varsayım.
    """
    try:
        p10 = float(pred.get("total_p10", 0) or 0)
        p90 = float(pred.get("total_p90", 0) or 0)
        if p90 > p10:
            return (p90 - p10) / 2.5631031311
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    total = float(pred.get("total_predicted", 0) or 0)
    return max(6.0, 0.08 * total) if total > 0 else 6.0


def prob_over_from_distribution(pred: dict[str, Any], market_total: float) -> float:
    """
    Dağılımdan P(toplam > market_line) hesapla.
    Monte Carlo olasılığı varsa doğrudan kullanılır.
    """
    direct = pred.get("prob_over_market")
    if direct is not None:
        try:
            p = float(direct)
            if 0.0 <= p <= 1.0:
                return p
        except (TypeError, ValueError):
            pass
    mu = float(pred.get("total_p50", pred.get("total_predicted", 0)) or 0)
    sigma = estimate_sigma(pred)
    if sigma <= 0:
        sigma = 6.0
    return 1.0 - normal_cdf(((market_total) - mu) / sigma)


def edge_calculation(predicted_prob: float, odds: float) -> float:
    """Bahis edge'ini hesapla. Pozitifse value var."""
    return (predicted_prob * odds) - 1.0


def implied_probability(odds: float) -> float:
    """Oddstan implied probability."""
    if odds <= 1:
        return 0.0
    return 1.0 / odds


def remove_vig(over_odds: float, under_odds: float) -> tuple[float, float]:
    """Vig'i temizle, fair odds döndür."""
    implied_over = 1.0 / over_odds
    implied_under = 1.0 / under_odds
    total_implied = implied_over + implied_under
    if total_implied <= 0:
        return (2.0, 2.0)
    fair_over = 1.0 / (implied_over / total_implied)
    fair_under = 1.0 / (implied_under / total_implied)
    return (round(fair_over, 2), round(fair_under, 2))


def kelly_optimal_bet(
    bankroll: float, win_prob: float, odds: float, fraction: float = KELLY_FRACTION
) -> float:
    """Doğrudan Kelly optimal bahis miktarı."""
    if odds <= 1 or win_prob <= 0 or win_prob >= 1:
        return 0.0
    b = odds - 1.0
    f_star = (b * win_prob - (1.0 - win_prob)) / b
    if f_star <= 0:
        return 0.0
    return bankroll * f_star * fraction


# -----------------------------------------------------------------------------
# Strateji Konfigürasyonu
# -----------------------------------------------------------------------------
STRATEGY_DESCRIPTIONS: dict[StrategyType, dict[str, Any]] = {
    StrategyType.KELLY: {
        "name": "Kelly Criterion",
        "description": "Uzun vadede optimal büyüme. Edge oranında bahis.",
        "risk": "Orta",
        "best_for": "Yüksek edge, düşük varyans",
    },
    StrategyType.FLAT: {
        "name": "Flat Betting",
        "description": "Her bahiste sabit miktar. Düşük risk.",
        "risk": "Düşük",
        "best_for": "Başlangıç, riskten kaçınan",
    },
    StrategyType.VALUE: {
        "name": "Value Betting",
        "description": "Sadece pozitif edge'de bahis. Edge büyüdükçe stake artar.",
        "risk": "Orta-Yüksek",
        "best_for": "Analitik, edge odaklı",
    },
    StrategyType.MARTINGALE: {
        "name": "Martingale",
        "description": "Her kayıpta 2x. Streak kovalamaca. Çok riskli!",
        "risk": "Çok Yüksek",
        "best_for": "Hiçbir şey. Tavsiye edilmez.",
    },
    StrategyType.ARBITRAGE: {
        "name": "Arbitraj",
        "description": "Farklı book'lar arası odds farkından garantili kar.",
        "risk": "Çok Düşük",
        "best_for": "Multi-book, düşük marj",
    },
}


def get_strategy_config() -> dict[str, Any]:
    """JSON config dosyasini yukle yoksa default."""
    try:
        if os.path.exists(STRATEGY_CONFIG_FILE):
            with open(STRATEGY_CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return StrategyConfig().to_dict()


def save_strategy_config(config: StrategyConfig) -> bool:
    """Config'i JSON'a kaydet."""
    try:
        with open(STRATEGY_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False
