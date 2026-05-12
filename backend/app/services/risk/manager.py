"""
리스크 관리 모듈.

RiskManager       : 개별 포지션 손절/익절/트레일링 스탑
PortfolioRiskManager : 포트폴리오 레벨 리스크 (일일 손실 한도, 최대 노출)
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

KST = timezone(timedelta(hours=9))


class RiskManager:
    def __init__(self, config: dict):
        config = config or {}
        self.stop_loss_pct = config.get("stop_loss_pct", 1.5)  # 2.0% → 1.5% (더 엄격)
        self.take_profit_pct = config.get(
            "take_profit_pct", 6.0
        )  # 4.0% → 6.0% (더 공격적)
        self.trailing_stop = config.get("trailing_stop", True)  # 기본 활성화
        self.trailing_pct = config.get("trailing_pct", 1.0)  # 1.5% → 1.0% (더 타이트)
        self.max_daily_loss_pct = config.get(
            "max_daily_loss_pct", 3.0
        )  # 일일 손실 한도
        self._peak_price: Optional[float] = None
        self._daily_pnl = 0.0

    def calc_levels(
        self, entry_price: float, direction: str = "long"
    ) -> Tuple[float, float]:
        """손절가, 익절가 계산"""
        if direction == "long":
            sl = entry_price * (1 - self.stop_loss_pct / 100)
            tp = entry_price * (1 + self.take_profit_pct / 100)
        else:
            sl = entry_price * (1 + self.stop_loss_pct / 100)
            tp = entry_price * (1 - self.take_profit_pct / 100)
        self._peak_price = entry_price
        return sl, tp

    def check_exit(
        self, entry_price: float, current_price: float, direction: str = "long"
    ) -> Optional[str]:
        """
        현재가 기준 청산 사유 반환.
        None이면 청산 불필요.
        """
        if direction == "long":
            sl = entry_price * (1 - self.stop_loss_pct / 100)
            tp = entry_price * (1 + self.take_profit_pct / 100)
        else:
            sl = entry_price * (1 + self.stop_loss_pct / 100)
            tp = entry_price * (1 - self.take_profit_pct / 100)

        if self._peak_price is None:
            self._peak_price = entry_price

        if direction == "long":
            if self.trailing_stop and self._peak_price:
                if current_price > self._peak_price:
                    self._peak_price = current_price
                trailing_sl = self._peak_price * (1 - self.trailing_pct / 100)
                if current_price <= trailing_sl:
                    return "trailing_stop"

            if current_price <= sl:
                return "stop_loss"
            if current_price >= tp:
                return "take_profit"

        else:  # short
            if current_price >= sl:
                return "stop_loss"
            if current_price <= tp:
                return "take_profit"

        return None

    def validate_config(self) -> list[str]:
        """설정 유효성 검사 - 오류 메시지 리스트 반환"""
        errors = []
        if self.stop_loss_pct <= 0:
            errors.append("stop_loss_pct must be > 0")
        if self.take_profit_pct <= 0:
            errors.append("take_profit_pct must be > 0")
        if self.stop_loss_pct > 50:
            errors.append("stop_loss_pct seems too large (> 50%)")
        if self.take_profit_pct > 100:
            errors.append("take_profit_pct seems too large (> 100%)")
        return errors


class PortfolioRiskManager:
    """
    포트폴리오 레벨 리스크 관리.

    기능:
      - 일일 최대 손실 한도 (Daily Loss Limit)
        : 당일 실현 손익이 총 자산의 N% 이상 손실 시 신규 진입 차단
      - 포트폴리오 최대 노출 한도 (Max Exposure)
        : 투자 중인 금액이 총 자산의 N% 이상이면 신규 진입 차단
    """

    def __init__(self):
        self._daily_pnl_krw: float = 0.0
        self._daily_date: str = ""

    def _refresh_day(self):
        """날짜 바뀌면 일일 PnL 리셋"""
        today = datetime.now(KST).strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_pnl_krw = 0.0
            self._daily_date = today

    def record_trade(self, pnl_krw: float):
        """청산 후 일일 PnL 누적 기록"""
        self._refresh_day()
        self._daily_pnl_krw += pnl_krw

    def can_enter(
        self,
        total_value_krw: float,
        total_invested_krw: float,
        max_daily_loss_pct: float,
        max_exposure_pct: float,
    ) -> tuple[bool, str]:
        """
        신규 진입 가능 여부 체크.
        Returns: (ok, reason)  ok=False 면 진입 차단
        """
        self._refresh_day()

        if total_value_krw <= 0:
            return True, ""

        # ── 일일 손실 한도 ────────────────────────────────────────────────
        max_loss_krw = total_value_krw * max_daily_loss_pct / 100
        if self._daily_pnl_krw < -max_loss_krw:
            return False, (
                f"일일 손실 한도 도달 "
                f"({self._daily_pnl_krw:,.0f}₩ / -{max_loss_krw:,.0f}₩)"
            )

        # ── 포트폴리오 최대 노출 한도 ─────────────────────────────────────
        exposure_pct = total_invested_krw / total_value_krw * 100
        if exposure_pct >= max_exposure_pct:
            return False, (
                f"포트폴리오 노출 한도 " f"({exposure_pct:.0f}% ≥ {max_exposure_pct}%)"
            )

        return True, ""

    @property
    def daily_pnl_krw(self) -> float:
        self._refresh_day()
        return self._daily_pnl_krw

    def check_correlation(
        self,
        new_symbol: str,
        open_positions: list[str],
        close_cache: dict,  # symbol → list[float] (1h 종가 리스트, 최신값이 마지막)
        threshold: float = 0.8,
    ) -> tuple[bool, str]:
        """
        새 진입 종목과 현재 보유 종목 간 피어슨 상관계수 체크. (TODO 10)
        threshold 초과 종목이 1개 이상이면 (False, 차단 이유) 반환.
        데이터 부족(< 10봉) 종목은 스킵.
        """
        new_closes = close_cache.get(new_symbol, [])
        if len(new_closes) < 10:
            return True, ""

        for sym in open_positions:
            if sym == new_symbol:
                continue
            other_closes = close_cache.get(sym, [])
            if len(other_closes) < 10:
                continue

            n = min(len(new_closes), len(other_closes))
            new_r = [
                new_closes[-n + i] / new_closes[-n + i - 1] - 1
                for i in range(1, n)
                if new_closes[-n + i - 1] != 0
            ]
            other_r = [
                other_closes[-n + i] / other_closes[-n + i - 1] - 1
                for i in range(1, n)
                if other_closes[-n + i - 1] != 0
            ]

            corr = _pearson(new_r, other_r)
            if corr > threshold:
                return False, f"{sym} 상관계수 {corr:.2f} (임계값 {threshold})"

        return True, ""


def _pearson(x: list[float], y: list[float]) -> float:
    """피어슨 상관계수 계산. 분산이 0이면 0 반환."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x, y = x[:n], y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    den_x = math.sqrt(sum((v - mx) ** 2 for v in x))
    den_y = math.sqrt(sum((v - my) ** 2 for v in y))
    if den_x == 0 or den_y == 0:
        return 0.0
    return round(num / (den_x * den_y), 4)


# ── 성과 지표 계산 유틸 ──────────────────────────────────────────────────────


def calc_futures_position_size(
    usdt_balance: float,
    leverage: int,
    risk_pct: float = 0.02,  # 계좌 대비 최대 손실 허용 2%
    sl_pct: float = 0.03,  # 손절선 3%
) -> float:
    """
    레버리지를 고려한 선물 투자금 계산.

    실제 손실 = 투자금 * sl_pct * leverage
    → 투자금 = risk_pct * balance / (sl_pct * leverage)
    레버리지가 높을수록 투자금이 작아져 리스크 일정 유지.
    최대 계좌 20% 상한.
    """
    if sl_pct <= 0 or leverage <= 0:
        return 0.0
    invest = (risk_pct * usdt_balance) / (sl_pct * leverage)
    max_invest = usdt_balance * 0.20  # 계좌 20% 상한
    return round(min(invest, max_invest), 4)


def calc_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    max_fraction: float = 0.25,
) -> float:
    """
    Half-Kelly Criterion 기반 투자 비중 계산.

    Kelly fraction = win_rate - (1 - win_rate) / (avg_win / avg_loss)
    안전을 위해 Half-Kelly (÷2) 적용.
    음수 → 0, max_fraction 초과 → max_fraction 반환.

    Args:
        win_rate: 승률 (0.0~1.0)
        avg_win:  평균 수익률 (소수, e.g. 0.03 = 3%)
        avg_loss: 평균 손실률 절댓값 (소수, e.g. 0.015 = 1.5%)
        max_fraction: 상한선 (기본 25%)
    """
    if avg_win <= 0 or avg_loss <= 0:
        return 0.0
    kelly = win_rate - (1 - win_rate) / (avg_win / avg_loss)
    half_kelly = kelly / 2
    return max(0.0, min(half_kelly, max_fraction))


def calc_var(pnl_list: list[float], confidence: float = 0.95) -> float:
    """
    Historical VaR (역사적 시뮬레이션, TODO 13).
    pnl_list(%) 를 정렬해 하위 (1-confidence) 분위수 절댓값 반환.

    예) confidence=0.95 → 하위 5% 분위수
    해석: "95% 확률로 하루 최대 손실은 반환값(%)를 초과하지 않는다"
    데이터 5건 미만이면 0.0 반환 (신뢰도 부족).
    numpy 없이 순수 Python 선형 보간으로 계산.
    """
    if len(pnl_list) < 5:
        return 0.0
    sorted_pnl = sorted(pnl_list)
    # 선형 보간: idx가 정수가 아닐 수 있음
    raw_idx = (1.0 - confidence) * (len(sorted_pnl) - 1)
    lo = int(raw_idx)
    hi = min(lo + 1, len(sorted_pnl) - 1)
    frac = raw_idx - lo
    var_val = sorted_pnl[lo] * (1.0 - frac) + sorted_pnl[hi] * frac
    return round(abs(var_val), 4)


def calc_performance(trade_log: list[dict], initial_capital: float = 1_000_000) -> dict:
    """
    거래 로그로 주요 성과 지표 계산.

    trade_log 는 최신순(newest first) 리스트.
    Returns dict with:
      sharpe_ratio, sortino_ratio, calmar_ratio, profit_factor,
      expectancy_pct, max_drawdown_pct, var_95,
      avg_win_pct, avg_loss_pct, win_rate,
      best_trade_pct, worst_trade_pct, total_trades
    """
    _zero = {
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "calmar_ratio": 0.0,
        "profit_factor": 0.0,
        "expectancy_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "var_95": 0.0,
        "avg_win_pct": 0.0,
        "avg_loss_pct": 0.0,
        "win_rate": 0.0,
        "best_trade_pct": 0.0,
        "worst_trade_pct": 0.0,
        "total_trades": 0,
    }
    if not trade_log:
        return _zero

    pnl_list = [t["pnl_pct"] for t in trade_log]
    wins = [x for x in pnl_list if x > 0]
    losses = [x for x in pnl_list if x <= 0]
    n = len(pnl_list)

    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0  # 음수
    win_rate = len(wins) / n * 100

    # ── Profit Factor ────────────────────────────────────────────────────
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0

    # ── Expectancy ───────────────────────────────────────────────────────
    wr = len(wins) / n
    expectancy = round(wr * avg_win - (1 - wr) * abs(avg_loss), 2)

    # ── Sharpe (거래 단위, 연환산 √252 적용) ─────────────────────────────
    mean_r = sum(pnl_list) / n
    sharpe = sortino = 0.0
    if n >= 2:
        variance = sum((x - mean_r) ** 2 for x in pnl_list) / (n - 1)
        std_r = math.sqrt(variance)
        if std_r > 0:
            sharpe = round(mean_r / std_r * math.sqrt(252), 2)

        # Sortino: 하방 편차만 사용
        if losses:
            downside_sq = sum(x**2 for x in losses) / len(losses)
            down_std = math.sqrt(downside_sq)
            if down_std > 0:
                sortino = round(mean_r / down_std * math.sqrt(252), 2)

    # ── MDD (최대 낙폭) ───────────────────────────────────────────────────
    # trade_log가 최신순이므로 reverse해서 시간순으로 처리
    running = initial_capital
    peak = running
    max_dd = 0.0
    for t in reversed(trade_log):
        running += t.get("pnl_krw", 0)
        if running > peak:
            peak = running
        if peak > 0:
            dd = (peak - running) / peak * 100
            if dd > max_dd:
                max_dd = dd

    # ── Calmar = 연평균 수익 / MDD ────────────────────────────────────────
    calmar = round(mean_r * 252 / max_dd, 2) if max_dd > 0 else 0.0

    return {
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "profit_factor": profit_factor,
        "expectancy_pct": expectancy,
        "max_drawdown_pct": round(max_dd, 2),
        "var_95": calc_var(pnl_list),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "win_rate": round(win_rate, 1),
        "best_trade_pct": round(max(pnl_list), 2),
        "worst_trade_pct": round(min(pnl_list), 2),
        "total_trades": n,
    }
