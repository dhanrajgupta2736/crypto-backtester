"""Risk-based position sizing — fixes the fixed-margin / variable-stop bug.

THE BUG THIS FIXES
-------------------
The strategies in strategies.py place stops at structural levels
(swing highs/lows, ATR multiples) that vary in distance from trade to trade.
If position size is fixed (same margin/contracts every trade) while stop
distance varies, then DOLLAR RISK PER TRADE IS NOT CONSTANT — it scales
directly with how wide the stop happened to be. A handful of trades with
unusually wide structural stops will lose far more than the typical trade
wins, even if win rate and RR look fine in aggregate. This is almost
certainly what produced the "many small wins, then a few big losses wipe
them out" pattern.

THE FIX
-------
1. size_for_signal(): position size is derived FROM the stop distance, not
   independent of it. Every trade risks the same % of equity, period.
2. validate_stop_distance(): rejects signals whose stop is abnormally far
   from entry relative to recent volatility (ATR). A stop that's 4x ATR away
   isn't "structural", it's a sign the setup quality is poor — skip it
   rather than size around it.
3. RiskManager: account-level guardrails (max risk per trade, max total open
   risk across concurrent positions, max daily loss) so a string of normal
   trades can't compound into ruin even if individual sizing is correct.
4. round_size_for_hyperliquid() / round_price_for_hyperliquid(): exchange-
   specific rounding so orders aren't rejected and so size isn't silently
   rounded UP past your intended risk.

Integrates with strategies.py's `Signal` dataclass without modifying it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# strategies.Signal has: symbol, strategy, side, entry, stop_loss, take_profit,
# reason, confidence, tf, candle_ts, and a derived .rr property.
# We only depend on entry/stop_loss/take_profit/symbol/side, duck-typed,
# so this module has no hard import dependency on strategies.py.


# ---------------------------------------------------------------------------
# Stop-distance sanity check — run this BEFORE sizing.
# ---------------------------------------------------------------------------
def validate_stop_distance(
    entry: float,
    stop_loss: float,
    atr_value: float,
    min_atr_mult: float = 0.5,
    max_atr_mult: float = 2.5,
) -> tuple[bool, str]:
    """Reject signals whose stop is too tight (noise/slippage will stop you
    out instantly) or too wide (the 'structural' stop is really just
    whatever a big wick happened to do — not a controlled risk).

    Returns (is_valid, reason). Always check this before sizing; if it
    fails, skip the trade entirely rather than sizing around a bad stop.
    """
    if atr_value <= 0:
        return False, "ATR is zero or unavailable — cannot validate stop"

    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        return False, "Stop distance is zero — invalid signal"

    atr_multiple = stop_distance / atr_value

    if atr_multiple < min_atr_mult:
        return False, (
            f"Stop too tight: {atr_multiple:.2f}x ATR "
            f"(min {min_atr_mult}x) — likely to be noise-stopped"
        )
    if atr_multiple > max_atr_mult:
        return False, (
            f"Stop too wide: {atr_multiple:.2f}x ATR "
            f"(max {max_atr_mult}x) — structural level is an outlier, "
            f"not a controlled risk distance"
        )
    return True, f"OK: stop is {atr_multiple:.2f}x ATR"


# ---------------------------------------------------------------------------
# Core sizing fix: position size is DERIVED from stop distance.
# ---------------------------------------------------------------------------
@dataclass
class SizingResult:
    is_valid: bool
    reason: str
    position_size: float = 0.0          # in units of the asset (e.g. BTC, ETH)
    notional_value: float = 0.0         # position_size * entry price
    margin_required: float = 0.0        # notional_value / leverage
    dollar_risk: float = 0.0            # what you actually lose if stopped out
    risk_pct_of_equity: float = 0.0
    leverage_used: float = 0.0


def size_for_signal(
    entry: float,
    stop_loss: float,
    account_equity: float,
    risk_pct: float = 1.0,
    max_leverage: float = 10.0,
    min_notional: float = 10.0,
) -> SizingResult:
    """Compute position size so that EVERY trade risks the same % of equity,
    regardless of how far away the stop is.

    This is the direct fix for fixed-margin sizing: instead of choosing a
    margin amount and letting dollar-risk float with stop distance, we fix
    the dollar risk and let position size (and therefore margin/leverage)
    float instead.

    Args:
        entry: entry price
        stop_loss: stop-loss price
        account_equity: current account equity in USD
        risk_pct: % of equity to risk on this ONE trade (e.g. 1.0 = 1%)
        max_leverage: hard ceiling on leverage Hyperliquid will let you use
                       for this asset / your account settings
        min_notional: exchange minimum order size in USD (Hyperliquid order
                       minimum is currently $10 notional; check current
                       value, this can change)
    """
    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0 or entry <= 0 or account_equity <= 0:
        return SizingResult(False, "Invalid entry/stop/equity values")

    dollar_risk = account_equity * (risk_pct / 100.0)

    # Core formula: size such that (size * stop_distance) == dollar_risk
    position_size = dollar_risk / stop_distance
    notional_value = position_size * entry

    if notional_value < min_notional:
        return SizingResult(
            False,
            f"Resulting notional (${notional_value:.2f}) is below exchange "
            f"minimum (${min_notional}) — stop is too close relative to "
            f"risk_pct, or account is too small for this risk_pct/stop combo",
        )

    leverage_used = notional_value / account_equity
    if leverage_used > max_leverage:
        # Cap leverage instead of dollar risk — this means the trade will
        # risk LESS than risk_pct, never more. Safer to under-risk than to
        # silently exceed your leverage ceiling.
        notional_value = account_equity * max_leverage
        position_size = notional_value / entry
        actual_dollar_risk = position_size * stop_distance
        return SizingResult(
            True,
            f"Leverage-capped at {max_leverage}x — actual risk reduced to "
            f"{(actual_dollar_risk/account_equity)*100:.2f}% "
            f"(target was {risk_pct}%)",
            position_size=position_size,
            notional_value=notional_value,
            margin_required=notional_value / max_leverage,
            dollar_risk=actual_dollar_risk,
            risk_pct_of_equity=(actual_dollar_risk / account_equity) * 100.0,
            leverage_used=max_leverage,
        )

    margin_required = notional_value / max(leverage_used, 1.0) if leverage_used > 1 else notional_value

    return SizingResult(
        True,
        f"Sized to risk exactly {risk_pct}% of equity (${dollar_risk:.2f})",
        position_size=position_size,
        notional_value=notional_value,
        margin_required=margin_required,
        dollar_risk=dollar_risk,
        risk_pct_of_equity=risk_pct,
        leverage_used=max(leverage_used, 1.0),
    )


# ---------------------------------------------------------------------------
# Account-level guardrails — backstop for when sizing is correct but a
# sequence of normal trades still goes against you.
# ---------------------------------------------------------------------------
@dataclass
class RiskManager:
    """Tracks open risk and daily loss so the bot can refuse new trades
    once limits are hit — independent of any single trade's sizing.
    """
    account_equity: float
    max_risk_per_trade_pct: float = 1.0      # risk_pct passed to size_for_signal
    max_total_open_risk_pct: float = 4.0     # sum of dollar_risk across open positions
    max_daily_loss_pct: float = 5.0          # stop trading for the day past this
    max_concurrent_positions: int = 4

    _open_risk_by_symbol: dict = field(default_factory=dict)   # symbol -> dollar_risk
    _realized_pnl_today: float = 0.0
    _current_day: Optional[date] = None

    def _roll_day_if_needed(self) -> None:
        today = date.today()
        if self._current_day != today:
            self._current_day = today
            self._realized_pnl_today = 0.0

    def can_open_new_trade(self) -> tuple[bool, str]:
        self._roll_day_if_needed()

        if len(self._open_risk_by_symbol) >= self.max_concurrent_positions:
            return False, (
                f"Max concurrent positions reached "
                f"({self.max_concurrent_positions})"
            )

        daily_loss_limit = self.account_equity * (self.max_daily_loss_pct / 100.0)
        if self._realized_pnl_today <= -daily_loss_limit:
            return False, (
                f"Daily loss limit hit (-{self.max_daily_loss_pct}% / "
                f"-${daily_loss_limit:.2f}) — no new trades until tomorrow"
            )

        current_open_risk = sum(self._open_risk_by_symbol.values())
        open_risk_limit = self.account_equity * (self.max_total_open_risk_pct / 100.0)
        if current_open_risk >= open_risk_limit:
            return False, (
                f"Max total open risk reached "
                f"(${current_open_risk:.2f} of ${open_risk_limit:.2f} limit)"
            )

        return True, "OK"

    def register_open_position(self, symbol: str, dollar_risk: float) -> None:
        self._open_risk_by_symbol[symbol] = dollar_risk

    def register_closed_position(self, symbol: str, realized_pnl: float) -> None:
        self._open_risk_by_symbol.pop(symbol, None)
        self._roll_day_if_needed()
        self._realized_pnl_today += realized_pnl

    def remaining_daily_loss_budget(self) -> float:
        self._roll_day_if_needed()
        daily_loss_limit = self.account_equity * (self.max_daily_loss_pct / 100.0)
        return daily_loss_limit + self._realized_pnl_today  # pnl_today is negative when losing


# ---------------------------------------------------------------------------
# Hyperliquid-specific rounding.
# Reference: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size
# szDecimals is PER-ASSET and must be fetched live from the /info "meta"
# endpoint — do not hardcode it, it can change. Pass it in.
# ---------------------------------------------------------------------------
def round_size_for_hyperliquid(size: float, sz_decimals: int) -> float:
    """Round size DOWN (truncate) to the asset's szDecimals.
    Rounding down, not to-nearest, ensures we never silently exceed our
    computed risk by rounding size up.
    """
    factor = 10 ** sz_decimals
    return math.floor(size * factor) / factor


def round_price_for_hyperliquid(price: float, sz_decimals: int, is_perp: bool = True) -> float:
    """Round price to Hyperliquid's rules: max 5 significant figures AND
    max (MAX_DECIMALS - szDecimals) decimal places, where MAX_DECIMALS is
    6 for perps and 8 for spot. Integer prices are always valid.
    """
    if price == int(price):
        return float(int(price))

    max_decimals = 6 if is_perp else 8
    decimal_cap = max(max_decimals - sz_decimals, 0)

    # Cap by significant figures (5) first
    if price != 0:
        magnitude = math.floor(math.log10(abs(price))) + 1
        sig_fig_decimals = max(5 - magnitude, 0)
    else:
        sig_fig_decimals = decimal_cap

    decimals = min(decimal_cap, sig_fig_decimals)
    factor = 10 ** decimals
    return math.floor(price * factor) / factor


# ---------------------------------------------------------------------------
# Convenience: full pipeline from a strategies.Signal-like object to a
# ready-to-send order size, in one call.
# ---------------------------------------------------------------------------
def prepare_trade(
    signal,                      # strategies.Signal (duck-typed)
    account_equity: float,
    atr_value: float,
    risk_manager: RiskManager,
    sz_decimals: int,
    risk_pct: float = 1.0,
    max_leverage: float = 10.0,
    min_stop_atr_mult: float = 0.5,
    max_stop_atr_mult: float = 2.5,
) -> tuple[bool, str, Optional[SizingResult]]:
    """Run the full validate -> size -> guardrail-check pipeline.
    Returns (should_trade, reason, sizing_result_or_None).
    """
    can_open, gate_reason = risk_manager.can_open_new_trade()
    if not can_open:
        return False, gate_reason, None

    stop_ok, stop_reason = validate_stop_distance(
        signal.entry, signal.stop_loss, atr_value,
        min_atr_mult=min_stop_atr_mult, max_atr_mult=max_stop_atr_mult,
    )
    if not stop_ok:
        return False, stop_reason, None

    sizing = size_for_signal(
        signal.entry, signal.stop_loss, account_equity,
        risk_pct=risk_pct, max_leverage=max_leverage,
    )
    if not sizing.is_valid:
        return False, sizing.reason, None

    sizing.position_size = round_size_for_hyperliquid(sizing.position_size, sz_decimals)
    if sizing.position_size <= 0:
        return False, "Position size rounded down to zero for this asset's lot size", None

    return True, sizing.reason, sizing
