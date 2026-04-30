"""
리스크 관리 모듈.
손절가(%), 익절가(%), 트레일링 스탑 지원.
"""
from typing import Optional, Tuple


class RiskManager:
    def __init__(self, config: dict):
        self.stop_loss_pct = config.get("stop_loss_pct", 2.0)      # %
        self.take_profit_pct = config.get("take_profit_pct", 4.0)  # %
        self.trailing_stop = config.get("trailing_stop", False)
        self.trailing_pct = config.get("trailing_pct", 1.5)        # %
        self._peak_price: Optional[float] = None

    def calc_levels(self, entry_price: float, direction: str = "long") -> Tuple[float, float]:
        """손절가, 익절가 계산"""
        if direction == "long":
            sl = entry_price * (1 - self.stop_loss_pct / 100)
            tp = entry_price * (1 + self.take_profit_pct / 100)
        else:
            sl = entry_price * (1 + self.stop_loss_pct / 100)
            tp = entry_price * (1 - self.take_profit_pct / 100)
        self._peak_price = entry_price
        return sl, tp

    def check_exit(self, entry_price: float, current_price: float, direction: str = "long") -> Optional[str]:
        """
        현재가 기준 청산 사유 반환.
        None이면 청산 불필요.
        """
        sl, tp = self.calc_levels(entry_price, direction)

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
