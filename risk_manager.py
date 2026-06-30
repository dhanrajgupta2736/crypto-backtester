"""Risk engine: dynamic position sizing + daily profit circuit breaker.

Hard rules implemented here:
- Max realized loss per trade: $10 (fees + slippage included in the math)
- Daily net profit target: $10 -> trips a 24-hour lockout, persisted to disk
  so a process restart cannot bypass it.
"""
import json
import math
import threading
from datetime import datetime, timedelta, timezone

from config import STATE_DIR, settings

STATE_FILE = STATE_DIR / "daily_state.json"


def position_size(entry: float, stop_loss: float, *, max_risk_usd: float = None,
                  taker_fee: float = None, slippage: float = None,
                  step: float = None, min_size: float = 0.0,
                  use_margin_cap: bool = True, leverage: float = None):
    """Return (size, worst_case_loss_usd).

    Base formula:  size = $10 / |entry - stop|
    Friction-adjusted so the REALIZED loss never exceeds $10:
        friction_per_unit = entry * (2 * taker_fee + slippage)
        size = max_risk / (|entry - stop| + friction_per_unit)
    Size is rounded DOWN to the exchange amount step.
    """
    max_risk_usd = settings.MAX_RISK_PER_TRADE_USD if max_risk_usd is None else max_risk_usd
    taker_fee = settings.TAKER_FEE_RATE if taker_fee is None else taker_fee
    slippage = settings.SLIPPAGE_RATE if slippage is None else slippage

    dist = abs(entry - stop_loss)
    if dist <= 0:
        raise ValueError("Stop loss must differ from entry price")

    friction = entry * (2 * taker_fee + slippage)   # entry+exit taker fees + slippage
    raw = max_risk_usd / (dist + friction)
    size_by_risk = math.floor(raw / step) * step if step else raw
    size_by_risk = round(size_by_risk, 12)

    if use_margin_cap:
        leverage = settings.LEVERAGE if leverage is None else leverage
        margin_cap = 10.0
        valid_size = 0.0
        while margin_cap <= 1000.0:
            # size allowed by this margin cap
            max_size_by_margin = (margin_cap * leverage) / entry
            size = math.floor(max_size_by_margin / step) * step if step else max_size_by_margin
            size = round(size, 12)
            
            # Position value (size * entry) must be at least $10 (Hyperliquid minimum order value)
            if size > 0 and size >= min_size and (size * entry) >= 10.0:
                valid_size = size
                break
            margin_cap += 10.0
            
        if valid_size == 0.0:
            return 0.0, 0.0
        final_size = min(size_by_risk, valid_size)
    else:
        final_size = size_by_risk

    final_size = math.floor(final_size / step) * step if step else final_size
    final_size = round(final_size, 12)

    if final_size <= 0 or final_size < min_size:
        return 0.0, 0.0
    return final_size, final_size * (dist + friction)


class DailyCircuitBreaker:
    """Tracks daily realized net PnL; locks trading for 24h once >= target."""

    def __init__(self, target_usd: float = None, max_loss_usd: float = None) -> None:
        self.target = settings.DAILY_TARGET_USD if target_usd is None else target_usd
        self.max_loss = settings.DAILY_MAX_LOSS_USD if max_loss_usd is None else max_loss_usd
        self._mutex = threading.Lock()
        self._load()

    # ---- persistence -----------------------------------------------------
    def _load(self) -> None:
        try:
            self.state = json.loads(STATE_FILE.read_text())
        except Exception:
            self.state = {}
        self._roll_day()

    def _save(self) -> None:
        STATE_FILE.write_text(json.dumps(self.state, indent=2))

    def _today(self) -> str:
        return datetime.now().astimezone().date().isoformat()

    def _roll_day(self) -> None:
        """Reset PnL at local midnight, but never clear an active lockout."""
        if self.state.get("date") != self._today():
            self.state = {
                "date": self._today(),
                "realized_pnl": 0.0,
                "locked_until": self.state.get("locked_until") if self.locked else None,
                "reset_timestamp": self.state.get("reset_timestamp"),
            }
            self._save()

    def reset_stats(self) -> None:
        """Set reset_timestamp to now, resetting the start-fresh boundary and unlocking the bot."""
        with self._mutex:
            self._roll_day()
            self.state["reset_timestamp"] = datetime.now(timezone.utc).isoformat()
            self.state["realized_pnl"] = 0.0
            self.state["locked_until"] = None
            self._save()


    # ---- public API --------------------------------------------------------
    @property
    def locked(self) -> bool:
        until = self.state.get("locked_until")
        if not until:
            return False
        return datetime.fromisoformat(until) > datetime.now(timezone.utc)

    @property
    def locked_until(self):
        return self.state.get("locked_until") if self.locked else None

    @property
    def realized_pnl(self) -> float:
        return float(self.state.get("realized_pnl", 0.0))

    def set_realized_pnl(self, pnl: float) -> bool:
        """Update today's realized net PnL.

        Returns True the moment the breaker trips (pnl >= target or pnl <= -max_loss):
        the caller must then cancel all orders and disable trading.
        """
        with self._mutex:
            self._roll_day()
            self.state["realized_pnl"] = float(pnl)
            tripped = False
            if (pnl >= self.target or pnl <= -self.max_loss) and not self.locked:
                until = datetime.now(timezone.utc) + timedelta(hours=24)
                self.state["locked_until"] = until.isoformat()
                tripped = True
            self._save()
            return tripped
