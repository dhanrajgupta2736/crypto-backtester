"""Metrics calculation engine.

Accepts transaction and portfolio tables, and returns standardized metrics
independent of the active trading strategy.
"""

import pandas as pd
import numpy as np


class MetricsEngine:
    """Computes quantitative metrics from strategy trading logs."""

    def calculate_metrics(self, 
                          trade_ledger: pd.DataFrame, 
                          daily_equity: pd.Series, 
                          number_of_rebalances: int,
                          total_volume_traded: float,
                          average_portfolio_value: float) -> dict:
        """Evaluate performance statistics from execution trade logs.
        
        Args:
            trade_ledger (pd.DataFrame): Trade log containing entries, exits, prices, PnL.
            daily_equity (pd.Series): Time-series of daily ending capital value.
            number_of_rebalances (int): Count of times rebalancing occurred.
            total_volume_traded (float): Total dollar volume of all buys and sells.
            average_portfolio_value (float): Mean portfolio equity over the period.
            
        Returns:
            dict: Evaluated performance metrics.
        """
        # resample daily_equity to daily to compute Sharpe safely
        daily_equity_resampled = daily_equity.resample('1D').last().ffill()
        daily_returns = daily_equity_resampled.pct_change().dropna()

        # CAGR
        cagr_val = 0.0
        if not daily_equity.empty:
            start_val = daily_equity.iloc[0]
            end_val = daily_equity.iloc[-1]
            days = (daily_equity.index[-1] - daily_equity.index[0]).days
            if days > 0 and start_val > 0:
                cagr_val = ((end_val / start_val) ** (365.0 / days) - 1.0) * 100.0

        # Sharpe
        sharpe_val = 0.0
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            # Annualized Sharpe (365 trading days for Crypto)
            sharpe_val = np.sqrt(365.0) * (daily_returns.mean() / daily_returns.std())

        # Max Drawdown
        dd_dict = self.calculate_max_drawdown(daily_equity)
        
        # Portfolio Turnover
        turnover = 0.0
        if average_portfolio_value > 0:
            turnover = total_volume_traded / (2.0 * average_portfolio_value)

        # Average Holding Period
        avg_hold = 0.0
        if not trade_ledger.empty:
            durations = pd.to_datetime(trade_ledger['exit_timestamp']) - pd.to_datetime(trade_ledger['entry_timestamp'])
            avg_hold = durations.mean().total_seconds() / 3600.0  # in hours

        return {
            "trade_count": len(trade_ledger),
            "win_rate": self.calculate_win_rate(trade_ledger),
            "profit_factor": self.calculate_profit_factor(trade_ledger),
            "expectancy_r": self.calculate_expectancy_r(trade_ledger),
            "cagr": cagr_val,
            "sharpe_ratio": sharpe_val,
            "max_drawdown": dd_dict,
            "avg_holding_period_hours": avg_hold,
            "number_of_rebalances": number_of_rebalances,
            "portfolio_turnover": turnover
        }

    def calculate_win_rate(self, trade_ledger: pd.DataFrame) -> float:
        """Percentage of positive PnL trades."""
        if trade_ledger.empty:
            return 0.0
        wins = (trade_ledger['pnl_nominal'] > 0).sum()
        return (wins / len(trade_ledger)) * 100.0

    def calculate_profit_factor(self, trade_ledger: pd.DataFrame) -> float:
        """Gross profits divided by gross losses."""
        if trade_ledger.empty:
            return 1.0
        gross_profit = trade_ledger.loc[trade_ledger['pnl_nominal'] > 0, 'pnl_nominal'].sum()
        gross_loss = abs(trade_ledger.loc[trade_ledger['pnl_nominal'] < 0, 'pnl_nominal'].sum())
        if gross_loss == 0:
            return float(999.0) if gross_profit > 0 else 1.0
        return gross_profit / gross_loss

    def calculate_expectancy_r(self, trade_ledger: pd.DataFrame) -> float:
        """Average performance return in units of initial position size allocation."""
        if trade_ledger.empty:
            return 0.0
        # If pnl_r is explicitly computed, return its mean, otherwise average percent return
        if 'pnl_r' in trade_ledger.columns:
            return trade_ledger['pnl_r'].mean()
        return trade_ledger['pnl_nominal'].mean()

    def calculate_max_drawdown(self, daily_equity: pd.Series) -> dict:
        """Maximum peak-to-trough decline percentage."""
        if daily_equity.empty:
            return {"drawdown_pct": 0.0, "duration_days": 0}
        
        cummax = daily_equity.cummax()
        drawdown = (cummax - daily_equity) / cummax
        max_dd = drawdown.max() * 100.0
        
        return {
            "drawdown_pct": max_dd,
            "duration_days": 0  # Simplified for sprint verification
        }
