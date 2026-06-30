# QRP Framework Regression Validation Report

This report presents the execution results and code coverage of the regression test suite implemented under **QRP Framework v2.0.1**.

---

## 1. Test Suite Specifications
The tests reside inside **[test_regression.py](file:///c:/Users/HP/Desktop/crypto-backtester/research_engine/tests/test_regression.py)** and verify the edge cases and boundary limits of the Discovery Engine.

### Test A: Zero Equity Liquidation Handoff
- **Objective**: Verify that the engine exits and stops when portfolio equity drops to zero.
- **Methodology**: Set `initial_capital = 0.0` at start.
- **Expected Outcome**: Status = `TERMINATED`, reason contains "zero or negative", and the equity curve has length 1 (stops at start).
- **Result**: **PASS**

### Test B: Negative / Zero Sizing Safeguards
- **Objective**: Ensure that negative or zero order quantities are bypassed and do not cause division-by-zero crashes.
- **Methodology**: Pass close price series of `0.0`.
- **Expected Outcome**: Status = `COMPLETED` or `TERMINATED` safely, no NaN/inf errors, and trade ledger is empty.
- **Result**: **PASS**

### Test C: NaN Portfolio Accounting Abort
- **Objective**: Verify that NaN close values in historical CSVs halt execution.
- **Methodology**: Inject `np.nan` close price at bar 20.
- **Expected Outcome**: Status = `FAILED`, reason contains "NaN or Infinite", and the last processed candle is index 20.
- **Result**: **PASS**

### Test D: Invalid Configuration Pre-Flight Gates
- **Objective**: Check that validation checks raise exceptions before execution.
- **Methodology**: Passes `15M` timeframe, which is unsupported.
- **Expected Outcome**: Validation check raises `AssertionError`.
- **Result**: **PASS**

---

## 2. Test Execution Log

```text
venv\Scripts\python.exe -m unittest research_engine/tests/test_regression.py
C:\Users\HP\Desktop\crypto-backtester\research_engine\tests\test_regression.py:20: FutureWarning: 'H' is deprecated and will be removed in a future version, please use 'h' instead.
  self.dates = pd.date_range("2026-01-01", periods=60, freq="1H", tz="UTC")
....
----------------------------------------------------------------------
Ran 4 tests in 0.053s

OK
```

All 4 boundary guards passed validation successfully.
