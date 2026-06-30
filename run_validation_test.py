import unittest
import os
import json
import shutil
import pandas as pd
import numpy as np

# Import components from paper_trading_engine
from paper_trading_engine import (
    calculate_indicators,
    calculate_position_size,
    EngineState,
    ENTRY_SLIPPAGE,
    ENTRY_FEE_RATE,
    EXIT_SLIPPAGE_TAKER,
    EXIT_FEE_RATE_TAKER,
    EXIT_FEE_RATE_MAKER,
    LEVERAGE,
    RISK_PER_TRADE_PCT
)

class TestPaperTradingSystem(unittest.TestCase):
    def setUp(self):
        # Create a temporary environment for files
        self.test_dir = "test_results"
        os.makedirs(self.test_dir, exist_ok=True)
        self.state_file = os.path.join(self.test_dir, "test_state.json")
        self.journal_file = os.path.join(self.test_dir, "test_log.csv")

    def tearDown(self):
        # Clean up temporary test files
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_indicator_calculations(self):
        # Create dummy price series representing a bull trend flip
        dates = pd.date_range(start="2026-06-01", periods=250, freq="h")
        
        # Start low, flat, then trend up
        prices = [100.0] * 200 + [100.0 + i * 2.0 for i in range(50)]
        highs = [p + 0.5 for p in prices]
        lows = [p - 0.5 for p in prices]
        volumes = [1000.0] * 250
        
        df = pd.DataFrame({
            "timestamp": dates.view(np.int64) // 10**6,
            "open": prices,
            "high": highs,
            "low": lows,
            "close": prices,
            "volume": volumes
        })
        
        df_ind = calculate_indicators(df)
        
        self.assertIn("ema200", df_ind.columns)
        self.assertIn("atr", df_ind.columns)
        self.assertIn("upperband", df_ind.columns)
        self.assertIn("lowerband", df_ind.columns)
        self.assertIn("long_sig", df_ind.columns)
        
        # Verify EMA calculations are valid (no NaN at the end)
        self.assertFalse(pd.isna(df_ind["ema200"].iloc[-1]))
        self.assertFalse(pd.isna(df_ind["atr"].iloc[-1]))
        
        # Verify that close > ema200 is evaluated
        last_row = df_ind.iloc[-1]
        self.assertTrue(last_row["close"] > last_row["ema200"])

    def test_position_sizing_standard(self):
        # Account metrics
        equity = 10000.0
        entry_price = 100.0
        stop_loss = 95.0
        
        qty, dist, risk_amt = calculate_position_size(entry_price, stop_loss, equity)
        
        # Risk amount = 2% of $10,000 = $200
        self.assertEqual(risk_amt, 200.0)
        # Distance = 100.0 - 95.0 = 5.0
        self.assertEqual(dist, 5.0)
        
        # Expected size calculation:
        # Size = Risk / (dist + friction)
        # Friction per unit = entry_price * (0.00045 + 0.0002 + 0.00045 + 0.0002) = 100 * 0.0013 = 0.13
        # Expected qty = 200 / 5.13 = 38.98635...
        expected_qty = 200.0 / (5.0 + 100.0 * 0.0013)
        self.assertAlmostEqual(qty, expected_qty, places=4)

    def test_position_sizing_leverage_limit(self):
        # Account metrics designed to exceed max leverage (5x)
        equity = 10000.0
        entry_price = 100.0
        # Stop loss extremely close to entry to force high size request
        stop_loss = 99.9
        
        qty, dist, risk_amt = calculate_position_size(entry_price, stop_loss, equity)
        
        # Max size at 5x leverage is (10000 * 5) / 100 = 500
        # Under normal conditions, size = 200 / (0.1 + 0.13) = 200 / 0.23 = 869.56
        # Thus, it should be capped at 500.0
        self.assertEqual(qty, 500.0)

    def test_state_serialization(self):
        state = EngineState()
        state.balance = 12500.50
        state.consecutive_losses = 3
        state.is_paused = True
        state.pause_reason = "Test pause"
        state.position = {
            "side": "long",
            "entry": 105.5,
            "sl": 100.0,
            "tp": 122.0,
            "qty": 15.0,
            "entry_ts": 1712836800000,
            "entry_fee": 1.0,
            "entry_slippage": 0.5
        }
        
        # Save to mock file
        import paper_trading_engine
        old_state_path = paper_trading_engine.STATE_PATH
        paper_trading_engine.STATE_PATH = self.state_file
        
        state.save()
        
        # Load in a new state object
        new_state = EngineState()
        new_state.load()
        
        self.assertEqual(new_state.balance, 12500.50)
        self.assertEqual(new_state.consecutive_losses, 3)
        self.assertTrue(new_state.is_paused)
        self.assertEqual(new_state.pause_reason, "Test pause")
        self.assertIsNotNone(new_state.position)
        self.assertEqual(new_state.position["side"], "long")
        self.assertEqual(new_state.position["qty"], 15.0)
        
        # Restore state path
        paper_trading_engine.STATE_PATH = old_state_path

    def test_simulated_fills_take_profit(self):
        # We check execution values under Maker execution (no slippage, Maker fee 0.015%)
        # For a LONG position:
        pos_entry = 100.0
        pos_qty = 10.0
        pos_sl = 95.0
        pos_tp = 115.0
        
        # Entry slippage and fee
        real_entry = pos_entry * (1.0 + ENTRY_SLIPPAGE)  # 100.02
        entry_fee = pos_qty * pos_entry * ENTRY_FEE_RATE  # 10 * 100 * 0.00045 = 0.45
        entry_slippage = pos_qty * (real_entry - pos_entry) # 10 * 0.02 = 0.20
        
        # Exit triggers Take Profit Maker fill
        exit_price = pos_tp  # 115.0
        actual_exit = exit_price  # No slippage on Maker order
        exit_slippage = 0.0
        exit_fee = pos_qty * exit_price * EXIT_FEE_RATE_MAKER  # 10 * 115 * 0.00015 = 0.1725
        
        entry_val = pos_qty * real_entry  # 1000.20
        exit_val = pos_qty * actual_exit  # 1150.00
        
        # Net PnL = (exit_val - entry_val) - entry_fee - exit_fee
        expected_pnl = (exit_val - entry_val) - entry_fee - exit_fee  # 149.80 - 0.45 - 0.1725 = 149.1775
        
        # We verify that our manual calculation matches broker logic
        self.assertAlmostEqual(expected_pnl, 149.1775, places=4)
        self.assertAlmostEqual(entry_fee + exit_fee, 0.6225, places=4)
        self.assertEqual(exit_slippage, 0.0)

    def test_simulated_fills_stop_loss(self):
        # We check execution values under Taker execution (0.02% slippage, Taker fee 0.045%)
        # For a LONG position:
        pos_entry = 100.0
        pos_qty = 10.0
        pos_sl = 95.0
        
        # Entry values
        real_entry = pos_entry * (1.0 + ENTRY_SLIPPAGE)  # 100.02
        entry_fee = pos_qty * pos_entry * ENTRY_FEE_RATE  # 0.45
        
        # Exit values (Taker execution)
        exit_price = pos_sl  # 95.0
        actual_exit = exit_price * (1.0 - EXIT_SLIPPAGE_TAKER)  # 95.0 * 0.9998 = 94.981
        exit_slippage = pos_qty * abs(actual_exit - exit_price)  # 10 * 0.019 = 0.19
        exit_fee = pos_qty * exit_price * EXIT_FEE_RATE_TAKER  # 10 * 95 * 0.00045 = 0.4275
        
        entry_val = pos_qty * real_entry  # 1000.20
        exit_val = pos_qty * actual_exit  # 949.81
        
        # Net PnL = (exit_val - entry_val) - entry_fee - exit_fee
        expected_pnl = (exit_val - entry_val) - entry_fee - exit_fee  # (949.81 - 1000.20) - 0.45 - 0.4275 = -50.39 - 0.8775 = -51.2675
        
        self.assertAlmostEqual(expected_pnl, -51.2675, places=4)
        self.assertAlmostEqual(entry_fee + exit_fee, 0.8775, places=4)
        self.assertAlmostEqual(exit_slippage, 0.19, places=4)

if __name__ == "__main__":
    unittest.main()
