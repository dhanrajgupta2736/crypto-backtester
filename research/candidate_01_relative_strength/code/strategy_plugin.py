"""Candidate C001 Relative Strength Strategy Plugin.

Implements raw percentage return cross-sectional momentum ranking
to select the Top 3 assets for a long-only equal-weighted portfolio.
"""

import pandas as pd
import numpy as np
from research_engine.core.strategy_interface import BaseStrategyPlugin


class StrategyPlugin(BaseStrategyPlugin):
    """Strategy Plugin for Candidate C001 (Relative Strength)."""

    @property
    def metadata(self) -> dict:
        return {
            "candidate_id": "C001",
            "name": "Relative Strength",
            "version": "0.1",
            "author": "Quant Team",
            "description": "Raw percentage return cross-sectional momentum ranking. "
                           "Holds Top 3 ranked assets equally weighted on a 1H timeframe, "
                           "rebalanced every candle."
        }

    @property
    def parameter_space(self) -> dict:
        return {
            "lookback_window": [50],
            "portfolio_size_k": [3],
            "rebalance_frequency_r": [1]
        }

    def preprocess(self, universe_data: dict) -> dict:
        """Align all asset timestamps and fill any data gaps to ensure uniform cross-sections."""
        # Check if universe_data is empty
        if not universe_data:
            return universe_data

        # Align datetime index across all assets
        close_dict = {}
        for symbol, df in universe_data.items():
            close_dict[symbol] = df['close']
        
        close_df = pd.DataFrame(close_dict)
        close_df = close_df.ffill().bfill()

        # Re-index each symbol's DataFrame to the aligned index
        aligned_universe = {}
        for symbol, df in universe_data.items():
            # Align DataFrame to close_df's index
            aligned_df = df.reindex(close_df.index)
            # Re-populate values
            aligned_df['close'] = close_df[symbol]
            aligned_df = aligned_df.ffill().bfill()
            aligned_universe[symbol] = aligned_df

        return aligned_universe

    def generate_signals(self, universe_data: dict, parameters: dict) -> dict:
        """Compute relative strength rank and assign long signal (1.0) to Top K assets."""
        if not universe_data:
            return universe_data

        lookback = parameters.get("lookback_window", 50)
        k = parameters.get("portfolio_size_k", 3)

        # Assemble a combined close price matrix
        close_dict = {}
        for symbol, df in universe_data.items():
            close_dict[symbol] = df['close']
        close_df = pd.DataFrame(close_dict)

        # Compute percentage returns over lookback period L
        returns_df = close_df.pct_change(periods=lookback)

        # Compute cross-sectional rank (ascending=False: largest return gets rank 1)
        # method='first' handles ties deterministically
        ranks_df = returns_df.rank(axis=1, ascending=False, method='first')

        # Generate binary signals (1.0 for rank <= k, 0.0 otherwise)
        signals_df = (ranks_df <= k).astype(float)

        # Map signals back to asset DataFrames
        for symbol, df in universe_data.items():
            df['signal'] = signals_df[symbol].fillna(0.0)

        return universe_data
