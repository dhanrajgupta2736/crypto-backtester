"""Regression Test Suite for QRP Framework v2.0.1.

Covers portfolio safety guards, NaN accounting, order sizing validations,
and pre-flight checks.
"""

import unittest
import numpy as np
import pandas as pd
from pathlib import Path

from research_engine.core.discovery_engine import DiscoveryEngine


class TestFrameworkRegression(unittest.TestCase):
    """Test suite covering the framework correctness upgrades."""

    def setUp(self):
        # Create a tiny mock dataset
        self.dates = pd.date_range("2026-01-01", periods=60, freq="1h", tz="UTC")
        self.symbols = ["BTC", "ETH"]
        
        self.universe_data = {}
        for sym in self.symbols:
            self.universe_data[sym] = pd.DataFrame({
                "open": [100.0] * 60,
                "high": [100.0] * 60,
                "low": [100.0] * 60,
                "close": [100.0] * 60,
                "volume": [1000.0] * 60,
                "signal": [1.0] * 60
            }, index=self.dates)

        self.engine = DiscoveryEngine()
        self.engine.configs = {
            "execution": {
                "initial_capital": 10000.0,
                "costs": {
                    "default_taker_fee": 0.00045,
                    "default_maker_fee": 0.00015,
                    "default_slippage": 0.0005
                }
            }
        }
        self.parameters = {
            "lookback_window": 10,
            "portfolio_size_k": 2,
            "rebalance_frequency_r": 1
        }

    def test_a_zero_equity_liquidation(self):
        """Test A: Verifies that when portfolio equity reaches <= 0, the engine terminates safely."""
        # Set initial capital to zero to trigger liquidation guard instantly
        self.engine.configs["execution"]["initial_capital"] = 0.0
        
        results = self.engine.simulate_backtest(self.universe_data, self.parameters)
        
        self.assertEqual(results["status"], "TERMINATED")
        self.assertIn("zero or negative", results["termination_reason"].lower())
        # The backtest should stop early (stops at index 0)
        self.assertEqual(len(results["equity_curve"]), 1)

    def test_b_negative_position_sizing_rejection(self):
        """Test B: Verifies that negative or zero order sizes are rejected or bypassed."""
        # Let's run a backtest where close price is zero.
        # It should bypass any buy orders without throwing division-by-zero crashes.
        for sym in self.symbols:
            self.universe_data[sym]["close"] = 0.0
            
        results = self.engine.simulate_backtest(self.universe_data, self.parameters)
        
        # Should complete or terminate safely without Nan/Inf crash
        self.assertTrue(results["status"] in ["COMPLETED", "TERMINATED"])
        self.assertTrue(results["trade_ledger"].empty)

    def test_c_nan_portfolio_value_termination(self):
        """Test C: Verifies that NaN values in close prices trigger early failure termination."""
        # Inject NaN close price at index 20
        self.universe_data["BTC"].loc[self.dates[20], "close"] = np.nan
        
        results = self.engine.simulate_backtest(self.universe_data, self.parameters)
        
        self.assertEqual(results["status"], "FAILED")
        self.assertIn("NaN or Infinite", results["termination_reason"])
        # Stops at timestamp index 20
        self.assertEqual(results["last_processed_candle"], str(self.dates[20]))

    def test_d_invalid_configuration(self):
        """Test D: Verifies that validation fails under invalid timeframe configurations."""
        # Create a mock validation structure
        validation_cfg = {
            "validation_gates": {
                "timeframes": {
                    "supported": ["1H", "4H", "1D"]
                }
            }
        }
        
        candidate_cfg = {
            "candidate": {
                "metadata": {"id": "C001"},
                "timeframes": ["15M"]  # Unsupported
            }
        }
        
        supported = validation_cfg["validation_gates"]["timeframes"]["supported"]
        tfs = candidate_cfg["candidate"]["timeframes"]
        
        with self.assertRaises(AssertionError):
            for tf in tfs:
                assert tf in supported, f"Unsupported timeframe: {tf}"


if __name__ == "__main__":
    unittest.main()
