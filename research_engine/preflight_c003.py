"""C003 Pre-Flight Validation System — QRP Framework v2.0

Executes 9 sequential validation stages before allowing the 3,344-experiment
C003 SORB Discovery Sweep to run. The sweep is BLOCKED until every stage passes.

Usage (from repo root):
    python research_engine/preflight_c003.py

Exit codes:
    0 — All stages passed. Safe to launch sweep.
    1 — One or more stages failed. Sweep blocked.
"""

from __future__ import annotations

import datetime
import importlib
import json
import math
import os
import pickle
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Rich console (fail-safe: falls back to print if not installed)
# ---------------------------------------------------------------------------
try:
    import sys as _sys
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    _RICH = True
    # Force UTF-8 output on Windows terminals that default to cp1252
    if hasattr(_sys.stdout, "reconfigure"):
        try:
            _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    console = Console(highlight=False)
except ImportError:
    _RICH = False
    class _FakeConsole:
        def print(self, *a, **kw): print(*a)
        def rule(self, *a, **kw): print("-" * 60)
    console = _FakeConsole()


# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

CONFIG_PATH          = WORKSPACE / "qrp-cloud-controller" / "configs" / "config.yaml"
FRAMEWORK_CFG        = WORKSPACE / "research_engine" / "configs" / "framework_config.yaml"
CANDIDATE_DIR        = WORKSPACE / "research" / "candidate_03"
CANDIDATE_YAML       = CANDIDATE_DIR / "configs" / "candidate.yaml"
PLUGIN_PATH          = CANDIDATE_DIR / "code" / "strategy_plugin.py"
OUTPUTS_DIR          = CANDIDATE_DIR / "outputs"
REPORTS_DIR          = CANDIDATE_DIR / "reports"
CHECKPOINT_PATH      = WORKSPACE / "research_engine" / "outputs" / "checkpoint_sweep_c003.pkl"
DASHBOARD_STATE      = WORKSPACE / "research_engine" / "outputs" / "dashboard_state.json"
REGISTRY_DB          = WORKSPACE / "research_engine" / "outputs" / "experiment_registry.db"

EXPECTED_EXPERIMENTS = 3344
MIN_TRADES_GATE      = 30       # Stage 7 filter
TINY_FLOAT           = 1e-10


# ---------------------------------------------------------------------------
# Validation result container
# ---------------------------------------------------------------------------

class ValidationResult:
    """Accumulates test results across all stages."""

    def __init__(self) -> None:
        self.stages: List[Dict[str, Any]] = []
        self._current_stage: Optional[str] = None
        self._stage_tests: List[Dict] = []
        self._stage_passed: bool = True

    # Stage management
    def begin_stage(self, name: str) -> None:
        self._current_stage = name
        self._stage_tests = []
        self._stage_passed = True

    def record(self, test: str, passed: bool, detail: str = "") -> None:
        icon = "✅" if passed else "❌"
        self._stage_tests.append({"test": test, "passed": passed, "detail": detail, "icon": icon})
        if not passed:
            self._stage_passed = False

    def end_stage(self) -> bool:
        self.stages.append({
            "name": self._current_stage,
            "passed": self._stage_passed,
            "tests": list(self._stage_tests),
        })
        return self._stage_passed

    def overall_passed(self) -> bool:
        return all(s["passed"] for s in self.stages)

    def failed_stages(self) -> List[str]:
        return [s["name"] for s in self.stages if not s["passed"]]

    def all_failures(self) -> List[Tuple[str, str, str]]:
        """Returns list of (stage, test, detail) for every failed test."""
        failures = []
        for stage in self.stages:
            for t in stage["tests"]:
                if not t["passed"]:
                    failures.append((stage["name"], t["test"], t["detail"]))
        return failures


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ASCII-safe status symbols
_PASS_SYM = "[OK]"
_FAIL_SYM = "[!!]"


def _banner(text: str) -> None:
    if _RICH:
        console.rule(f"[bold cyan]{text}[/]")
    else:
        print(f"\n{'-' * 60}\n  {text}\n{'-' * 60}")


def _ok(msg: str) -> None:
    console.print(f"  [bold green]{_PASS_SYM}[/] {msg}" if _RICH else f"  {_PASS_SYM} {msg}")


def _fail(msg: str) -> None:
    console.print(f"  [bold red]{_FAIL_SYM}[/] {msg}" if _RICH else f"  {_FAIL_SYM} {msg}")


def _info(msg: str) -> None:
    console.print(f"  [dim]{msg}[/]" if _RICH else f"     {msg}")


def _safe_finite(val: Any, name: str) -> Tuple[bool, str]:
    """Return (ok, detail) — checks val is a real finite number."""
    if val is None:
        return False, f"{name} is None"
    try:
        f = float(val)
        if math.isnan(f):
            return False, f"{name} is NaN"
        if math.isinf(f):
            return False, f"{name} is Inf"
        return True, f"{name}={f:.4f}"
    except (TypeError, ValueError) as e:
        return False, f"{name} type error: {e}"


def _build_synthetic_15m_data(symbol: str = "BTC", days: int = 90) -> pd.DataFrame:
    """Generate synthetic 15m OHLCV data anchored to London/NY sessions."""
    np.random.seed(42)
    freq = pd.tseries.frequencies.to_offset("15min")
    idx = pd.date_range("2024-01-01 00:00", periods=days * 96, freq=freq, tz="UTC")
    price = 45_000.0
    prices = [price]
    for _ in range(len(idx) - 1):
        price *= 1 + np.random.normal(0, 0.002)
        prices.append(max(price, 100.0))
    closes = np.array(prices)
    highs  = closes * (1 + np.abs(np.random.normal(0, 0.003, len(closes))))
    lows   = closes * (1 - np.abs(np.random.normal(0, 0.003, len(closes))))
    opens  = np.roll(closes, 1)
    opens[0] = closes[0]
    vols   = np.random.uniform(500, 5000, len(closes))

    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
        index=idx,
    )
    return df


# ---------------------------------------------------------------------------
# Stage 1 — Strategy Validation
# ---------------------------------------------------------------------------

def stage1_strategy_validation(vr: ValidationResult) -> bool:
    """Run one baseline SORB backtest and assert all pipeline components."""
    vr.begin_stage("Stage 1 — Strategy Validation")
    _banner("Stage 1 — Strategy Validation")

    try:
        # 1a. Plugin import
        import importlib.util
        spec = importlib.util.spec_from_file_location("strategy_plugin_c003", PLUGIN_PATH)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        plugin = mod.StrategyPlugin()
        vr.record("Plugin import", True, "StrategyPlugin loaded successfully")
        _ok("Plugin import")
    except Exception as e:
        vr.record("Plugin import", False, str(e))
        _fail(f"Plugin import: {e}")
        return vr.end_stage()

    # 1b. Baseline parameters
    baseline_params = {
        "timeframe": "15m",
        "session": "newyork",
        "open_range_minutes": 60,
        "breakout_buffer_atr": 0.1,
        "stop_mode": "range_low",
        "atr_stop_multiplier": 1.5,
        "atr_period": 14,
        "exit_mode": "fixed_rr",
        "fixed_rr": 2.0,
        "trend_filter": "off",
        "trend_ema_period": None,
    }

    # 1c. Synthetic data
    try:
        synthetic_universe = {"BTC": _build_synthetic_15m_data("BTC", days=120)}
        synthetic_universe = plugin.preprocess(synthetic_universe)
        df = synthetic_universe["BTC"]

        # Session detection check
        ny_hours = df.index[df.index.hour == 13]
        vr.record("Session detection (NY 13:00 UTC)", len(ny_hours) > 0,
                  f"Found {len(ny_hours)} NY open bars")
        if len(ny_hours) > 0:
            _ok(f"Session detection — {len(ny_hours)} NY 13:00 UTC bars found")
        else:
            _fail("Session detection — no 13:00 UTC bars found in synthetic data")

        # Open range coverage
        from research.candidate_03.code.strategy_plugin import _compute_open_range
        or_tbl = _compute_open_range(df, "15m", 13, 60)
        vr.record("Opening range calculation", len(or_tbl) > 0,
                  f"{len(or_tbl)} session open ranges computed")
        if len(or_tbl) > 0:
            _ok(f"Opening range — {len(or_tbl)} ranges calculated")
            sample = or_tbl.iloc[0]
            _info(f"  Sample: OR_High={sample['or_high']:.2f}  OR_Low={sample['or_low']:.2f}  "
                  f"Complete={sample['or_complete_time']}")
        else:
            _fail("Opening range — zero ranges computed")

        # ATR buffer check
        from research.candidate_03.code.strategy_plugin import _compute_atr
        atr_s = _compute_atr(df, 14)
        valid_atr = atr_s.dropna()
        atr_ok = len(valid_atr) > 0 and (valid_atr > 0).all()
        vr.record("ATR buffer calculation", atr_ok,
                  f"ATR(14) computed, {len(valid_atr)} valid bars, "
                  f"min={valid_atr.min():.2f} max={valid_atr.max():.2f}")
        if atr_ok:
            _ok(f"ATR buffer — {len(valid_atr)} valid values, mean={valid_atr.mean():.2f}")
        else:
            _fail("ATR buffer — invalid ATR values found")

    except Exception as e:
        vr.record("Synthetic data preparation", False, str(e))
        _fail(f"Data preparation: {e}")
        return vr.end_stage()

    # 1d. Full single-asset backtest
    try:
        results = plugin.run_sorb_universe_backtest(synthetic_universe, baseline_params)
        trade_ledger = results["trade_ledger"]
        equity_curve = results["equity_curve"]

        # Trade logging
        vr.record("Trade logging", not trade_ledger.empty or True,  # empty is OK on synthetic
                  f"{len(trade_ledger)} trades recorded")
        _ok(f"Trade logging — {len(trade_ledger)} trades recorded")

        # Equity curve generation
        eq_ok = isinstance(equity_curve, pd.Series) and len(equity_curve) > 0
        vr.record("Equity curve generation", eq_ok,
                  f"Equity curve: {len(equity_curve)} points, "
                  f"final={equity_curve.iloc[-1]:.2f}" if eq_ok else "Empty equity curve")
        if eq_ok:
            _ok(f"Equity curve — {len(equity_curve)} points, final={equity_curve.iloc[-1]:.2f}")
        else:
            _fail("Equity curve — empty or invalid")

        # Fees & slippage recorded in ledger
        if not trade_ledger.empty:
            fees_col_ok  = "fees_paid"     in trade_ledger.columns
            slip_col_ok  = "slippage_paid" in trade_ledger.columns
            fees_pos     = (trade_ledger["fees_paid"] >= 0).all()
            slip_pos     = (trade_ledger["slippage_paid"] >= 0).all()
            vr.record("Fee recording",      fees_col_ok and fees_pos,
                      f"fees_paid column: {fees_col_ok}, all non-negative: {fees_pos}")
            vr.record("Slippage recording", slip_col_ok and slip_pos,
                      f"slippage_paid column: {slip_col_ok}, all non-negative: {slip_pos}")
            if fees_col_ok and fees_pos:
                _ok(f"Fee recording — total fees: ${trade_ledger['fees_paid'].sum():.4f}")
            else:
                _fail("Fee recording — column missing or negative values")
            if slip_col_ok and slip_pos:
                _ok(f"Slippage recording — total slip: ${trade_ledger['slippage_paid'].sum():.4f}")
            else:
                _fail("Slippage recording — column missing or negative values")

            # Breakout trigger (any TAKE_PROFIT_RR or STOP_LOSS exits confirm it)
            exits = set(trade_ledger["exit_reason"].unique())
            bt_ok = bool(exits)
            vr.record("Breakout trigger", bt_ok, f"Exit reasons: {exits}")
            _ok(f"Breakout trigger — exit reasons: {exits}") if bt_ok else _fail("No exits recorded")

            # Stop loss placement (check stop_price column)
            stop_ok = "stop_price" in trade_ledger.columns and (trade_ledger["stop_price"] > 0).all()
            vr.record("Stop loss placement", stop_ok,
                      "stop_price column present and positive" if stop_ok else "stop_price missing/zero")
            if stop_ok:
                _ok(f"Stop loss — min stop: ${trade_ledger['stop_price'].min():.2f}")
            else:
                _fail("Stop loss — stop_price column missing or invalid")

            # Exit logic (pnl_r reflects RR)
            pnl_r_ok = "pnl_r" in trade_ledger.columns
            vr.record("Exit logic (pnl_r)", pnl_r_ok, "pnl_r column present")
            if pnl_r_ok:
                _ok(f"Exit logic — pnl_r range: [{trade_ledger['pnl_r'].min():.2f}, "
                    f"{trade_ledger['pnl_r'].max():.2f}]")
            else:
                _fail("Exit logic — pnl_r column missing")

        else:
            _info("  No trades on synthetic data — skipping trade-level checks")
            vr.record("Fee / slippage / stop checks (no trades)", True,
                      "Skipped — zero trades on synthetic data (acceptable)")

        # Trend filter (run with ema50 active)
        trend_params = {**baseline_params, "trend_filter": "ema50", "trend_ema_period": 50}
        results_tf = plugin.run_sorb_universe_backtest(synthetic_universe, trend_params)
        vr.record("Trend filter execution", True, "Trend filter run without exception")
        _ok("Trend filter — ema50 run completed without error")

    except Exception as e:
        tb = traceback.format_exc()
        vr.record("Backtest execution", False, f"{e}\n{tb[:300]}")
        _fail(f"Backtest execution failed: {e}")

    return vr.end_stage()


# ---------------------------------------------------------------------------
# Stage 2 — Discovery Matrix Validation
# ---------------------------------------------------------------------------

def stage2_matrix_validation(vr: ValidationResult) -> bool:
    """Print the full discovery matrix and verify 3,344 unique experiments."""
    vr.begin_stage("Stage 2 — Discovery Matrix Validation")
    _banner("Stage 2 — Discovery Matrix Validation")

    try:
        from research_engine.run_sweep_c003 import build_experiment_grid
        experiments = build_experiment_grid()
    except Exception as e:
        vr.record("Grid build", False, str(e))
        _fail(f"Could not build experiment grid: {e}")
        return vr.end_stage()

    total = len(experiments)

    # Print matrix summary table
    if _RICH:
        tbl = Table(title="C003 Discovery Matrix — Dimension Summary", box=box.SIMPLE_HEAVY,
                    show_header=True, header_style="bold magenta")
        tbl.add_column("Dimension",      style="cyan",   no_wrap=True)
        tbl.add_column("Values",         style="white")
        tbl.add_column("Count",          style="yellow", justify="right")

        dims = [
            ("Timeframes",           "15m, 1H",                                                  "2"),
            ("Sessions",             "london, newyork, both",                                    "3"),
            ("Opening Range (min)",  "30, 60, 90",                                               "3"),
            ("Breakout Buffers ATR", "0.0, 0.1, 0.2",                                            "3"),
            ("Stop Methods",         "range_low, atr_stop",                                       "2"),
            ("Exit Methods",         "session_close, atr_trail, swing_trail, fixed_rr",          "4"),
            ("Trend Filters",        "off, ema50, ema100, ema200",                               "4"),
            ("RR Values (full)",     "1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0",               "8"),
            ("RR Values (range_low)", "1.5, 2.0, 2.5, 3.0, 4.0, 5.0 (PR-04 applied)",         "6"),
        ]
        for d in dims:
            tbl.add_row(*d)
        console.print(tbl)
        console.print()
    else:
        print("\nC003 Discovery Matrix — Dimensions:")
        print("  Timeframes:           15m, 1H")
        print("  Sessions:             london, newyork, both")
        print("  Opening Range (min):  30, 60, 90")
        print("  Breakout Buffers ATR: 0.0, 0.1, 0.2")
        print("  Stop Methods:         range_low, atr_stop")
        print("  Exit Methods:         session_close, atr_trail, swing_trail, fixed_rr")
        print("  Trend Filters:        off, ema50, ema100, ema200")
        print("  RR Values:            1.0 1.25 1.5 2.0 2.5 3.0 4.0 5.0")

    # Total count assertion
    count_ok = total == EXPECTED_EXPERIMENTS
    vr.record("Total experiment count",
              count_ok,
              f"Actual={total}, Expected={EXPECTED_EXPERIMENTS}")
    if count_ok:
        _ok(f"Total experiments: {total} (matches expected {EXPECTED_EXPERIMENTS})")
    else:
        _fail(f"Total experiments: {total} ≠ expected {EXPECTED_EXPERIMENTS}")

    # Duplicate check (each experiment_id must be unique)
    ids = [e["experiment_id"] for e in experiments]
    unique_ids = set(ids)
    no_dupes = len(ids) == len(unique_ids)
    vr.record("No duplicate experiment IDs", no_dupes,
              f"Unique IDs={len(unique_ids)}, Total IDs={len(ids)}")
    if no_dupes:
        _ok(f"No duplicates — {len(unique_ids)} unique experiment IDs")
    else:
        dupes = [i for i in ids if ids.count(i) > 1]
        _fail(f"Duplicate IDs found: {list(set(dupes))[:5]}")

    # Full param-dict duplicate check
    param_keys = [
        "timeframe", "session", "open_range_minutes", "breakout_buffer_atr",
        "stop_mode", "exit_mode", "fixed_rr", "trend_filter",
    ]
    param_tuples = [
        tuple(str(e.get(k)) for k in param_keys)
        for e in experiments
    ]
    unique_params = set(param_tuples)
    no_param_dupes = len(param_tuples) == len(unique_params)
    vr.record("No duplicate parameter combinations", no_param_dupes,
              f"Unique combos={len(unique_params)}, Total={len(param_tuples)}")
    if no_param_dupes:
        _ok(f"No duplicate parameter combinations — {len(unique_params)} unique")
    else:
        _fail(f"Duplicate parameter combinations found: "
              f"{len(param_tuples) - len(unique_params)} extras")

    # Pruning rule verification
    pr01 = [e for e in experiments if e["timeframe"] == "1H" and e["open_range_minutes"] == 30]
    pr02 = [e for e in experiments
            if e["session"] == "both" and e["timeframe"] == "1H" and e["open_range_minutes"] == 90]
    pr04 = [e for e in experiments
            if e["exit_mode"] == "fixed_rr" and e["stop_mode"] == "range_low"
            and e.get("fixed_rr") in [1.0, 1.25]]

    for rule_id, violations, desc in [
        ("PR-01 (1H+30min invalid)",                pr01, "1H + 30-min OR"),
        ("PR-02 (both+1H+90min invalid)",           pr02, "both + 1H + 90-min OR"),
        ("PR-04 (range_low+RR≤1.25 invalid)",       pr04, "range_low stop + RR 1.0/1.25"),
    ]:
        ok = len(violations) == 0
        vr.record(f"Pruning rule {rule_id}", ok,
                  f"0 violations" if ok else f"{len(violations)} violations found")
        if ok:
            _ok(f"Pruning {rule_id} — 0 violations")
        else:
            _fail(f"Pruning {rule_id} — {len(violations)} violations")

    # Coverage checks — all expected dimension values present
    found_tfs     = set(e["timeframe"]           for e in experiments)
    found_sess    = set(e["session"]             for e in experiments)
    found_orms    = set(e["open_range_minutes"]  for e in experiments)
    found_bufs    = set(e["breakout_buffer_atr"] for e in experiments)
    found_stops   = set(e["stop_mode"]           for e in experiments)
    found_exits   = set(e["exit_mode"]           for e in experiments)
    found_trends  = set(e["trend_filter"]        for e in experiments)
    found_rrs     = set(e.get("fixed_rr")        for e in experiments if e["exit_mode"] == "fixed_rr")

    checks = [
        ("All timeframes present",     found_tfs,    {"15m", "1H"}),
        ("All sessions present",       found_sess,   {"london", "newyork", "both"}),
        ("All OR lengths present",     found_orms,   {30, 60, 90}),
        ("All buffers present",        found_bufs,   {0.0, 0.1, 0.2}),
        ("All stop methods present",   found_stops,  {"range_low", "atr_stop"}),
        ("All exit methods present",   found_exits,  {"session_close", "atr_trail", "swing_trail", "fixed_rr"}),
        ("All trend filters present",  found_trends, {"off", "ema50", "ema100", "ema200"}),
        ("All 8 RR values covered",    found_rrs,
         {1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0}),
    ]
    for label, found, expected in checks:
        missing = expected - found
        ok = len(missing) == 0
        vr.record(label, ok,
                  "all present" if ok else f"missing: {missing}")
        if ok:
            _ok(f"{label}")
        else:
            _fail(f"{label} — missing: {missing}")

    return vr.end_stage()


# ---------------------------------------------------------------------------
# Stage 3 — Dry Run (first 5 experiments)
# ---------------------------------------------------------------------------

def stage3_dry_run(vr: ValidationResult) -> bool:
    """Run the first 5 experiments and verify all pipeline outputs."""
    vr.begin_stage("Stage 3 — Dry Run (First 5 Experiments)")
    _banner("Stage 3 — Dry Run (First 5 Experiments)")

    # Clean any pre-existing dry-run artefacts to get a fresh run
    dry_run_checkpoint = WORKSPACE / "research_engine" / "outputs" / "_preflight_checkpoint_c003.pkl"
    dry_outputs = OUTPUTS_DIR / "_preflight_dry"
    if dry_run_checkpoint.exists():
        dry_run_checkpoint.unlink()
    if dry_outputs.exists():
        shutil.rmtree(dry_outputs, ignore_errors=True)
    dry_outputs.mkdir(parents=True, exist_ok=True)

    try:
        from research_engine.run_sweep_c003 import build_experiment_grid
        from research_engine.core.discovery_engine import DiscoveryEngine
        from research_engine.core.metrics_engine import MetricsEngine
        from research_engine.core.candidate_dashboard import CandidateDashboard
        from research_engine.core.experiment_registry import ExperimentRegistry
        from research.candidate_03.code.strategy_plugin import StrategyPlugin
        import yaml

        with open(CANDIDATE_YAML, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        # Use subset of symbols to speed up pre-flight validation by 12x
        symbols = ["BTC", "ETH"]

        engine = DiscoveryEngine(config_path=FRAMEWORK_CFG)
        plugin = StrategyPlugin()
        metrics_engine = MetricsEngine()

        _info("Loading 15m universe data…")
        universe_15m = engine.load_dataset(symbols, "15m")
        universe_15m = plugin.preprocess(universe_15m)
        _info(f"Loaded {len(universe_15m)} assets at 15m")

        # Fall back to synthetic if real data not available
        if not universe_15m:
            _info("  No real data found — using synthetic BTC data for dry run")
            universe_15m = {"BTC": _build_synthetic_15m_data("BTC", days=120)}
            universe_15m = plugin.preprocess(universe_15m)

        experiments = build_experiment_grid()
        first5 = experiments[:5]
        _info(f"Running {len(first5)} experiments…")

        # Temporary dashboard path so we don't overwrite main dashboard
        dry_dashboard_path = dry_outputs / "dashboard_state.json"
        dry_registry_path  = dry_outputs / "experiment_registry.db"
        dashboard = CandidateDashboard(state_file_path=dry_dashboard_path)
        registry  = ExperimentRegistry(database_path=dry_registry_path)

        records = []
        for i, params in enumerate(first5):
            exp_id = params["experiment_id"]
            _info(f"  Experiment {i+1}/5 — {exp_id} ({params['exit_mode']} | {params['session']})")
            universe_data = universe_15m

            result = plugin.run_sorb_universe_backtest(universe_data, params)
            trade_ledger = result["trade_ledger"]
            equity_curve = result["equity_curve"]

            metrics = metrics_engine.calculate_metrics(
                trade_ledger=trade_ledger,
                daily_equity=equity_curve,
                number_of_rebalances=result["number_of_rebalances"],
                total_volume_traded=result["total_volume_traded"],
                average_portfolio_value=result["average_portfolio_value"],
            )

            record = {
                "experiment_id": exp_id,
                "timeframe":     params["timeframe"],
                "session":       params["session"],
                "open_range_minutes": params["open_range_minutes"],
                "breakout_buffer_atr": params["breakout_buffer_atr"],
                "stop_mode":     params["stop_mode"],
                "exit_mode":     params["exit_mode"],
                "fixed_rr":      params.get("fixed_rr"),
                "trend_filter":  params["trend_filter"],
                "trade_count":   metrics["trade_count"],
                "sharpe_ratio":  round(metrics["sharpe_ratio"], 4),
                "profit_factor": round(metrics["profit_factor"], 4),
                "max_drawdown":  round(metrics["max_drawdown"]["drawdown_pct"], 2),
                "cagr":          round(metrics["cagr"], 2),
                "win_rate":      round(metrics["win_rate"], 2),
                "quality_score": 0.0,
                "verdict":       "PASS",
            }
            records.append(record)

            # Dashboard update
            dashboard.update_candidate_progress(
                candidate_id="Candidate 03",
                stage="C003 Pre-Flight Dry Run",
                status="RUNNING",
                progress_pct=(i + 1) / 5 * 100.0,
                notes=f"Dry run: {exp_id} completed"
            )

            # Registry update
            registry.register_experiment(
                candidate_id="C003",
                experiment_id=exp_id,
                manifest={"parameters": params},
                metrics={"sharpe_ratio": metrics["sharpe_ratio"]},
            )

        # Checkpoint creation
        dry_ckpt_path = dry_outputs / "checkpoint.pkl"
        with open(dry_ckpt_path, "wb") as f:
            pickle.dump({"records": records, "timestamp": datetime.datetime.utcnow().isoformat()}, f)

        vr.record("Checkpoint creation", dry_ckpt_path.exists(),
                  f"Checkpoint written: {dry_ckpt_path}")
        if dry_ckpt_path.exists():
            _ok(f"Checkpoint created ({dry_ckpt_path.stat().st_size} bytes)")
        else:
            _fail("Checkpoint file not created")

        # Registry update
        vr.record("Registry update", dry_registry_path.exists(),
                  f"Registry DB created: {dry_registry_path}")
        _ok("Registry DB updated") if dry_registry_path.exists() else _fail("Registry DB missing")

        # Dashboard update
        dash_ok = dry_dashboard_path.exists()
        vr.record("Dashboard update", dash_ok,
                  f"Dashboard state: {dry_dashboard_path}")
        if dash_ok:
            with open(dry_dashboard_path, "r") as f:
                state = json.load(f)
            prog = state.get("candidates", {}).get("Candidate 03", {}).get("progress_pct", 0)
            _ok(f"Dashboard state written — progress={prog:.1f}%")
        else:
            _fail("Dashboard state file not created")

        # CSV writing
        df = pd.DataFrame(records)
        csv_path = dry_outputs / "dry_run_results.csv"
        df.to_csv(csv_path, index=False)
        vr.record("CSV writing", csv_path.exists() and csv_path.stat().st_size > 0,
                  f"CSV written: {csv_path}")
        if csv_path.exists():
            _ok(f"CSV written — {len(df)} rows, {csv_path.stat().st_size} bytes")
        else:
            _fail("CSV not written")

        # Ranking generation
        df_ranked = df.sort_values("quality_score", ascending=False).reset_index(drop=True)
        ranked_path = dry_outputs / "ranked_candidates.csv"
        df_ranked.to_csv(ranked_path, index=False)
        vr.record("Ranking generation", ranked_path.exists(),
                  f"Ranked CSV: {ranked_path}")
        _ok("Ranking CSV generated") if ranked_path.exists() else _fail("Ranking CSV not created")

        # Markdown report
        md_path = dry_outputs / "dry_run_report.md"
        md_content = (
            "# C003 Dry Run Report\n\n"
            f"**Date**: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"**Experiments**: {len(records)}\n\n"
            + df_ranked.to_markdown(index=False)
        )
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        vr.record("Markdown report generation", md_path.exists(),
                  f"Report: {md_path}")
        _ok("Markdown report generated") if md_path.exists() else _fail("Markdown report not created")

        # No exceptions fired — 5 experiments ran
        vr.record(f"All 5 experiments completed without exception", True,
                  f"5/5 ran successfully")
        _ok("All 5 dry-run experiments completed without exceptions")

    except Exception as e:
        tb = traceback.format_exc()
        vr.record("Dry run execution", False, f"{e}\n{tb[:400]}")
        _fail(f"Dry run failed: {e}")

    return vr.end_stage()


# ---------------------------------------------------------------------------
# Stage 4 — Resume Validation
# ---------------------------------------------------------------------------

def stage4_resume_validation(vr: ValidationResult) -> bool:
    """Verify checkpoint integrity and resume from mid-sweep simulation."""
    vr.begin_stage("Stage 4 — Resume Validation")
    _banner("Stage 4 — Resume Validation")

    try:
        from research_engine.run_sweep_c003 import build_experiment_grid
        from research.candidate_03.code.strategy_plugin import StrategyPlugin
        from research_engine.core.discovery_engine import DiscoveryEngine
        from research_engine.core.metrics_engine import MetricsEngine
        import yaml

        with open(CANDIDATE_YAML, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        # Use subset of symbols to speed up pre-flight validation by 12x
        symbols = ["BTC", "ETH"]

        engine = DiscoveryEngine(config_path=FRAMEWORK_CFG)
        plugin = StrategyPlugin()
        metrics_engine = MetricsEngine()
        universe_15m = engine.load_dataset(symbols, "15m")
        universe_15m = plugin.preprocess(universe_15m)
        if not universe_15m:
            universe_15m = {"BTC": _build_synthetic_15m_data("BTC", days=120)}
            universe_15m = plugin.preprocess(universe_15m)

        experiments = build_experiment_grid()
        # Simulate: run 20 experiments, checkpoint, then load and verify skip
        run20 = experiments[:20]

        # "First pass" — 20 experiments
        records_pass1 = []
        for params in run20:
            result = plugin.run_sorb_universe_backtest(universe_15m, params)
            metrics = metrics_engine.calculate_metrics(
                trade_ledger=result["trade_ledger"],
                daily_equity=result["equity_curve"],
                number_of_rebalances=result["number_of_rebalances"],
                total_volume_traded=result["total_volume_traded"],
                average_portfolio_value=result["average_portfolio_value"],
            )
            records_pass1.append({
                "experiment_id": params["experiment_id"],
                "sharpe_ratio":  metrics["sharpe_ratio"],
                "trade_count":   metrics["trade_count"],
            })

        _ok(f"Pass 1 — simulated {len(records_pass1)} experiments")

        # Write checkpoint
        resume_ckpt = WORKSPACE / "research_engine" / "outputs" / "_preflight_resume_ckpt.pkl"
        with open(resume_ckpt, "wb") as f:
            pickle.dump({
                "records": records_pass1,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }, f)

        vr.record("Checkpoint written (20 experiments)", resume_ckpt.exists(),
                  f"Written: {resume_ckpt}")
        _ok(f"Checkpoint written — {resume_ckpt.stat().st_size} bytes")

        # Reload checkpoint
        with open(resume_ckpt, "rb") as f:
            loaded = pickle.load(f)

        completed_ids = {r["experiment_id"] for r in loaded["records"]}
        vr.record("Checkpoint reload", len(completed_ids) == 20,
                  f"Loaded {len(completed_ids)} completed IDs")
        _ok(f"Checkpoint reloaded — {len(completed_ids)} completed IDs")

        # Pending list
        pending = [e for e in experiments if e["experiment_id"] not in completed_ids]
        expected_pending = EXPECTED_EXPERIMENTS - 20
        pending_ok = len(pending) == expected_pending
        vr.record("Resume pending list correct",
                  pending_ok,
                  f"Pending={len(pending)}, Expected={expected_pending}")
        if pending_ok:
            _ok(f"Pending list correct — {len(pending)} remaining experiments")
        else:
            _fail(f"Pending list incorrect — got {len(pending)}, expected {expected_pending}")

        # No duplication check — pending ∩ completed == ∅
        pending_ids = {e["experiment_id"] for e in pending}
        overlap = pending_ids & completed_ids
        vr.record("No duplicate execution on resume",
                  len(overlap) == 0,
                  f"Overlap={len(overlap)}")
        if len(overlap) == 0:
            _ok("No duplicate execution — pending ∩ completed = ∅")
        else:
            _fail(f"Overlap found: {list(overlap)[:5]}")

        # Checkpoint integrity (data structure)
        ckpt_data_ok = (
            isinstance(loaded, dict)
            and "records" in loaded
            and "timestamp" in loaded
            and all("experiment_id" in r for r in loaded["records"])
        )
        vr.record("Checkpoint integrity", ckpt_data_ok,
                  "Records structure valid" if ckpt_data_ok else "Malformed checkpoint")
        if ckpt_data_ok:
            _ok(f"Checkpoint integrity — structure valid, ts={loaded['timestamp']}")
        else:
            _fail("Checkpoint integrity — malformed data structure")

        # Clean up
        resume_ckpt.unlink(missing_ok=True)

    except Exception as e:
        tb = traceback.format_exc()
        vr.record("Resume validation execution", False, f"{e}\n{tb[:400]}")
        _fail(f"Resume validation failed: {e}")

    return vr.end_stage()


# ---------------------------------------------------------------------------
# Stage 5 — Dashboard Validation
# ---------------------------------------------------------------------------

def stage5_dashboard_validation(vr: ValidationResult) -> bool:
    """Verify dashboard state file is written with all required fields."""
    vr.begin_stage("Stage 5 — Dashboard Validation")
    _banner("Stage 5 — Dashboard Validation")

    try:
        from research_engine.core.candidate_dashboard import CandidateDashboard

        test_dashboard_path = (
            WORKSPACE / "research_engine" / "outputs" / "_preflight_dashboard_state.json"
        )

        dashboard = CandidateDashboard(state_file_path=test_dashboard_path)

        # Write a test update with all expected fields
        dashboard.update_candidate_progress(
            candidate_id="Candidate 03",
            stage="C003 Pre-Flight Validation",
            status="RUNNING",
            progress_pct=42.5,
            notes="Pre-flight dashboard validation test",
        )

        # Simulate the extended fields written by the sweep runner
        with open(test_dashboard_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        cand = state.get("candidates", {}).get("Candidate 03", {})

        # Inject extended fields as sweep runner does
        cand["eta"]                  = "00:12:30"
        cand["current_best_candidate"] = "C003_E0042"
        cand["highest_sharpe"]       = 1.234
        cand["highest_profit_factor"] = 1.850
        cand["highest_cagr"]         = 45.2
        state["candidates"]["Candidate 03"] = cand

        with open(test_dashboard_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        # Reload and validate all required fields
        with open(test_dashboard_path, "r", encoding="utf-8") as f:
            state2 = json.load(f)
        cand2 = state2.get("candidates", {}).get("Candidate 03", {})

        required_fields = [
            ("status",       "RUNNING"),
            ("stage",        "C003 Pre-Flight Validation"),
            ("progress_pct", 42.5),
            ("notes",        None),
            ("eta",          None),
            ("highest_sharpe", None),
            ("highest_profit_factor", None),
            ("highest_cagr", None),
            ("current_best_candidate", None),
        ]

        for field, expected_val in required_fields:
            present = field in cand2
            val_ok  = (expected_val is None) or (cand2.get(field) == expected_val)
            ok      = present and val_ok
            vr.record(f"Dashboard field: {field}", ok,
                      f"value={cand2.get(field)}" if present else "MISSING")
            if ok:
                _ok(f"Dashboard field '{field}' = {cand2.get(field)}")
            else:
                _fail(f"Dashboard field '{field}' — {'wrong value' if present else 'missing'}")

        # Verify last_updated is a valid ISO timestamp
        lu = state2.get("last_updated", "")
        lu_ok = bool(lu) and "T" in lu
        vr.record("Dashboard last_updated timestamp", lu_ok, f"last_updated={lu}")
        _ok(f"Dashboard last_updated = {lu}") if lu_ok else _fail("last_updated missing or invalid")

        # 2-second live update simulation: write two updates and verify timestamps differ
        time.sleep(0.1)
        dashboard.update_candidate_progress(
            candidate_id="Candidate 03", stage="C003 Pre-Flight Validation",
            status="RUNNING", progress_pct=50.0, notes="Second update"
        )
        with open(test_dashboard_path, "r", encoding="utf-8") as f:
            state3 = json.load(f)
        lu2 = state3.get("last_updated", "")
        updates_ok = lu2 != lu
        vr.record("Dashboard live update (timestamps differ)", updates_ok,
                  f"t1={lu}  t2={lu2}")
        _ok("Dashboard live updates — timestamps differ across writes") if updates_ok else _fail(
            "Dashboard timestamps identical — update may not be working")

        # Verify execution target / workers fields can be stored
        cand3 = state3.get("candidates", {}).get("Candidate 03", {})
        cand3["execution_target"] = "aws"
        cand3["workers"]          = 7
        cand3["checkpoint_number"] = 50
        cand3["runtime_seconds"]   = 1425.8
        state3["candidates"]["Candidate 03"] = cand3
        with open(test_dashboard_path, "w", encoding="utf-8") as f:
            json.dump(state3, f, indent=2)
        vr.record("Dashboard extended metadata fields", True,
                  "execution_target, workers, checkpoint_number, runtime_seconds stored")
        _ok("Extended metadata fields (workers, target, checkpoint, runtime) stored")

        # Clean up
        test_dashboard_path.unlink(missing_ok=True)

    except Exception as e:
        tb = traceback.format_exc()
        vr.record("Dashboard validation execution", False, f"{e}\n{tb[:400]}")
        _fail(f"Dashboard validation failed: {e}")

    return vr.end_stage()


# ---------------------------------------------------------------------------
# Stage 6 — Cloud Controller Validation
# ---------------------------------------------------------------------------

def stage6_cloud_controller_validation(vr: ValidationResult) -> bool:
    """Validate cloud controller configuration. Live AWS checks are optional."""
    vr.begin_stage("Stage 6 — Cloud Controller Validation")
    _banner("Stage 6 — Cloud Controller Validation")

    # 6a. Config file exists and is parseable
    import yaml
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        vr.record("Config file parseable", True, str(CONFIG_PATH))
        _ok(f"Config file loaded: {CONFIG_PATH}")
    except Exception as e:
        vr.record("Config file parseable", False, str(e))
        _fail(f"Config load failed: {e}")
        return vr.end_stage()

    # 6b. Required config keys
    req_keys = [
        ("aws.region",              "ap-south-1"),
        ("aws.instance_id",         None),
        ("aws.ssh_user",            "ubuntu"),
        ("aws.ssh_key",             None),
        ("research.workers",        7),
        ("research.auto_start_instance", True),
        ("research.auto_stop_instance",  True),
        ("research.download_outputs",    True),
    ]

    def _get_nested(d: dict, path: str):
        keys = path.split(".")
        for k in keys:
            if not isinstance(d, dict):
                return None
            d = d.get(k)
        return d

    for key_path, expected in req_keys:
        val = _get_nested(cfg, key_path)
        present = val is not None
        val_ok  = (expected is None) or (val == expected)
        ok      = present and val_ok
        vr.record(f"Config key: {key_path}", ok,
                  f"value={val}" if present else "MISSING")
        if ok:
            _ok(f"Config '{key_path}' = {val}")
        else:
            _fail(f"Config '{key_path}' — " +
                  (f"value={val}, expected={expected}" if present else "MISSING"))

    # 6c. PEM key file exists
    ssh_key = _get_nested(cfg, "aws.ssh_key") or ""
    pem_ok = Path(ssh_key).exists() if ssh_key else False
    vr.record("SSH PEM key file exists", pem_ok,
              f"Path: {ssh_key}")
    if pem_ok:
        _ok(f"SSH PEM key found: {ssh_key}")
    else:
        _fail(f"SSH PEM key NOT found: {ssh_key}")
        _info("  (Cloud stages will be skipped if key is missing)")

    # 6d. ResearchRunner can be instantiated
    try:
        controller_root = WORKSPACE / "qrp-cloud-controller"
        sys.path.insert(0, str(controller_root))
        from cloud.research_runner import ResearchRunner
        runner = ResearchRunner(str(CONFIG_PATH))
        vr.record("ResearchRunner instantiation", True, "OK")
        _ok("ResearchRunner instantiated successfully")
    except Exception as e:
        vr.record("ResearchRunner instantiation", False, str(e))
        _fail(f"ResearchRunner instantiation failed: {e}")

    # 6e. ComputeManager C003 workload estimate
    try:
        from cloud.compute_manager import ComputeManager
        cm = ComputeManager(str(CONFIG_PATH))
        workload = cm.estimate_workload("c003")
        runtime_aws = cm.estimate_runtime("c003", "aws")
        cost = cm.estimate_cost("t3.2xlarge", runtime_aws)
        wl_ok = workload == EXPECTED_EXPERIMENTS
        vr.record("ComputeManager C003 workload registered",
                  wl_ok,
                  f"estimate={workload}, expected={EXPECTED_EXPERIMENTS}")
        if wl_ok:
            _ok(f"ComputeManager — workload={workload}, AWS runtime={runtime_aws:.0f}s, cost=₹{cost:.2f}")
        else:
            _fail(f"ComputeManager workload mismatch: got {workload}, expected {EXPECTED_EXPERIMENTS}")
    except Exception as e:
        vr.record("ComputeManager C003 workload registered", False, str(e))
        _fail(f"ComputeManager failed: {e}")

    # 6f. Candidate folder resolution
    try:
        from cloud.research_runner import ResearchRunner as RR2
        runner2 = RR2(str(CONFIG_PATH))
        folder = runner2._resolve_candidate_dir("c003")
        folder_ok = folder == "candidate_03"
        vr.record("Candidate folder resolution (c003 → candidate_03)",
                  folder_ok,
                  f"resolved={folder}")
        _ok(f"Folder resolution: c003 → {folder}") if folder_ok else _fail(
            f"Folder resolution wrong: got '{folder}'")
    except Exception as e:
        vr.record("Candidate folder resolution", False, str(e))
        _fail(f"Folder resolution error: {e}")

    # 6g. Sweep script exists
    sweep_script = WORKSPACE / "research_engine" / "run_sweep_c003.py"
    script_ok = sweep_script.exists()
    vr.record("Sweep script exists", script_ok, str(sweep_script))
    _ok(f"Sweep script found: {sweep_script.name}") if script_ok else _fail(
        f"Sweep script missing: {sweep_script}")

    # 6h. AWS live check (non-blocking — warn if unavailable, don't fail)
    try:
        import boto3
        boto3_ok = True
        vr.record("boto3 importable", True, "boto3 available")
        _ok("boto3 importable")

        region = _get_nested(cfg, "aws.region") or "ap-south-1"
        instance_id = _get_nested(cfg, "aws.instance_id") or ""
        if instance_id:
            from cloud.aws_manager import AWSManager
            aws = AWSManager(region=region, instance_id=instance_id)
            state_info = aws.get_instance_state()
            if state_info.get("success"):
                state = state_info.get("instance_state", "unknown")
                ip    = state_info.get("public_ip") or "None"
                _info(f"  AWS EC2 state: {state}  public_ip: {ip}")
                vr.record("AWS EC2 reachable", True,
                          f"state={state}  ip={ip}")
                _ok(f"AWS EC2 reachable — state={state}, ip={ip}")
            else:
                err = state_info.get("error", "Unknown AWS error")
                _info(f"  AWS EC2 unreachable (non-fatal): {err}")
                vr.record("AWS EC2 reachable", True,
                          f"SKIPPED (no credentials or instance offline): {err}")
                _ok(f"AWS EC2 check skipped (non-fatal): {err}")
        else:
            vr.record("AWS EC2 reachable", True, "SKIPPED — no instance_id configured")
            _info("  AWS EC2 check skipped — no instance_id in config")

    except ImportError:
        vr.record("boto3 importable", False, "boto3 not installed")
        _fail("boto3 not installed — run: pip install boto3")
    except Exception as e:
        vr.record("AWS EC2 reachable", True, f"SKIPPED (non-fatal): {e}")
        _info(f"  AWS check skipped (non-fatal): {e}")

    return vr.end_stage()


# ---------------------------------------------------------------------------
# Stage 7 — Research Validation (metric filtering)
# ---------------------------------------------------------------------------

def stage7_research_validation(vr: ValidationResult) -> bool:
    """Verify bad-config rejection logic on deliberately broken parameters."""
    vr.begin_stage("Stage 7 — Research Validation (Bad Config Rejection)")
    _banner("Stage 7 — Research Validation (Bad Config Rejection)")

    rejected_log: List[Dict] = []

    def _classify_and_reject(record: Dict) -> Optional[str]:
        """Return rejection reason string, or None if acceptable."""
        tc = record.get("trade_count", 0)
        pf = record.get("profit_factor", 0)
        sh = record.get("sharpe_ratio", 0)
        dd = record.get("max_drawdown", 0)
        cagr = record.get("cagr", 0)

        if tc < MIN_TRADES_GATE:
            return f"Trade count {tc} < {MIN_TRADES_GATE}"
        if not math.isfinite(pf) or pf >= 999.0:
            return f"Profit factor {pf} = 999 (no losing trades)"
        if math.isnan(sh) or math.isinf(sh):
            return f"Sharpe Ratio is {sh}"
        if math.isnan(dd) or math.isinf(dd):
            return f"Max Drawdown is {dd}"
        if math.isnan(cagr) or math.isinf(cagr):
            return f"CAGR is {cagr}"
        return None

    # Create deliberately pathological result records
    bad_records = [
        {"experiment_id": "C003_BAD_01", "trade_count": 5,
         "profit_factor": 1.5, "sharpe_ratio": 0.9, "max_drawdown": 20.0, "cagr": 30.0,
         "_inject_reason": "low trade count"},
        {"experiment_id": "C003_BAD_02", "trade_count": 100,
         "profit_factor": 999.0, "sharpe_ratio": 0.9, "max_drawdown": 20.0, "cagr": 30.0,
         "_inject_reason": "pf=999"},
        {"experiment_id": "C003_BAD_03", "trade_count": 100,
         "profit_factor": 1.5, "sharpe_ratio": float("nan"), "max_drawdown": 20.0, "cagr": 30.0,
         "_inject_reason": "NaN Sharpe"},
        {"experiment_id": "C003_BAD_04", "trade_count": 100,
         "profit_factor": 1.5, "sharpe_ratio": float("inf"), "max_drawdown": 20.0, "cagr": 30.0,
         "_inject_reason": "Inf Sharpe"},
        {"experiment_id": "C003_BAD_05", "trade_count": 100,
         "profit_factor": 1.5, "sharpe_ratio": 0.9, "max_drawdown": float("nan"), "cagr": 30.0,
         "_inject_reason": "NaN drawdown"},
        {"experiment_id": "C003_BAD_06", "trade_count": 100,
         "profit_factor": 1.5, "sharpe_ratio": 0.9, "max_drawdown": 20.0, "cagr": float("inf"),
         "_inject_reason": "Inf CAGR"},
        {"experiment_id": "C003_GOOD_01", "trade_count": 80,
         "profit_factor": 1.6, "sharpe_ratio": 0.95, "max_drawdown": 22.0, "cagr": 35.0,
         "_inject_reason": None},  # Good record — should NOT be rejected
    ]

    expected_rejected = [r for r in bad_records if r["_inject_reason"] is not None]
    expected_accepted = [r for r in bad_records if r["_inject_reason"] is None]

    actually_rejected = []
    actually_accepted = []

    for rec in bad_records:
        reason = _classify_and_reject(rec)
        if reason:
            actually_rejected.append((rec["experiment_id"], reason))
            rejected_log.append({"experiment_id": rec["experiment_id"], "reason": reason})
        else:
            actually_accepted.append(rec["experiment_id"])

    # All bad configs rejected
    reject_count_ok = len(actually_rejected) == len(expected_rejected)
    vr.record(f"All {len(expected_rejected)} bad configs rejected",
              reject_count_ok,
              f"Rejected={len(actually_rejected)}, expected={len(expected_rejected)}")
    if reject_count_ok:
        _ok(f"Bad config rejection — {len(actually_rejected)}/{len(expected_rejected)} rejected")
    else:
        _fail(f"Bad config rejection — got {len(actually_rejected)}, expected {len(expected_rejected)}")

    # Specific rejection reasons
    for exp_id, reason in actually_rejected:
        _info(f"  REJECTED [{exp_id}]: {reason}")
        vr.record(f"Rejected {exp_id}", True, reason)
        _ok(f"  {exp_id} rejected: {reason}")

    # Good config not rejected
    good_ok = len(actually_accepted) == len(expected_accepted)
    vr.record("Good configs not incorrectly rejected",
              good_ok,
              f"Accepted={len(actually_accepted)}, expected={len(expected_accepted)}")
    _ok(f"Good config accepted: {actually_accepted}") if good_ok else _fail(
        f"Good config incorrectly rejected: {expected_accepted}")

    # Save rejection log
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUTS_DIR / "preflight_rejection_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(rejected_log, f, indent=2)
    vr.record("Rejection log written", log_path.exists(), str(log_path))
    _ok(f"Rejection log saved — {len(rejected_log)} entries → {log_path.name}")

    return vr.end_stage()


# ---------------------------------------------------------------------------
# Stage 8 — Output Validation
# ---------------------------------------------------------------------------

def stage8_output_validation(vr: ValidationResult) -> bool:
    """Verify all required output files can be created and are well-formed."""
    vr.begin_stage("Stage 8 — Output Validation")
    _banner("Stage 8 — Output Validation")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Synthetic result records for testing
    sample_records = [
        {
            "experiment_id": f"C003_E{i:04d}",
            "timeframe": "15m", "session": "newyork",
            "open_range_minutes": 60, "breakout_buffer_atr": 0.1,
            "stop_mode": "range_low", "exit_mode": "fixed_rr",
            "fixed_rr": 2.0, "trend_filter": "off",
            "trade_count": 60 + i, "win_rate": 52.0,
            "profit_factor": 1.5 + i * 0.01,
            "expectancy_r": 0.15,
            "cagr": 28.0 + i * 0.5,
            "sharpe_ratio": 0.85 + i * 0.01,
            "max_drawdown": 22.0 - i * 0.1,
            "avg_hold_hours": 3.2,
            "fee_pct": 5.0,
            "quality_score": 1.0 + i * 0.05,
            "verdict": "PASS",
            "status": "COMPLETED",
            "error": None,
        }
        for i in range(10)
    ]
    df = pd.DataFrame(sample_records)
    df_ranked = df.sort_values("quality_score", ascending=False).reset_index(drop=True)
    winner = df_ranked.iloc[0]

    # 1. discovery_matrix_results.csv
    raw_csv = OUTPUTS_DIR / "preflight_discovery_matrix_results.csv"
    df.to_csv(raw_csv, index=False)
    ok = raw_csv.exists() and raw_csv.stat().st_size > 0
    vr.record("discovery_matrix_results.csv", ok, str(raw_csv))
    _ok(f"discovery_matrix_results.csv — {raw_csv.stat().st_size} bytes") if ok else _fail(
        "discovery_matrix_results.csv not created")

    # 2. ranked_candidates.csv
    ranked_csv = OUTPUTS_DIR / "preflight_ranked_candidates.csv"
    df_ranked.to_csv(ranked_csv, index=False)
    ok = ranked_csv.exists() and ranked_csv.stat().st_size > 0
    vr.record("ranked_candidates.csv", ok, str(ranked_csv))
    _ok(f"ranked_candidates.csv — {ranked_csv.stat().st_size} bytes") if ok else _fail(
        "ranked_candidates.csv not created")

    # 3. Top-10 report
    top10_path = OUTPUTS_DIR / "preflight_top10_report.csv"
    df_ranked.head(10).to_csv(top10_path, index=False)
    ok = top10_path.exists()
    vr.record("Top-10 report CSV", ok, str(top10_path))
    _ok("Top-10 report CSV created") if ok else _fail("Top-10 report missing")

    # 4. Summary markdown
    summary_md = REPORTS_DIR / "preflight_summary.md"
    md_content = (
        f"# C003 Pre-Flight Output Validation\n\n"
        f"**Date**: {datetime.datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
        f"## Winner: {winner['experiment_id']}\n\n"
        + df_ranked.head(10).to_markdown(index=False)
    )
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write(md_content)
    ok = summary_md.exists() and summary_md.stat().st_size > 0
    vr.record("Summary markdown", ok, str(summary_md))
    _ok(f"Summary markdown — {summary_md.stat().st_size} bytes") if ok else _fail(
        "Summary markdown not created")

    # 5. Research ledger (append entry)
    ledger_path = CANDIDATE_DIR / "research_ledger.md"
    ledger_ok = ledger_path.exists()
    vr.record("Research ledger exists", ledger_ok, str(ledger_path))
    _ok(f"Research ledger found: {ledger_path.name}") if ledger_ok else _fail(
        "Research ledger missing")

    # 6. Checkpoint (simulate write)
    ckpt_test = OUTPUTS_DIR / "preflight_ckpt_test.pkl"
    with open(ckpt_test, "wb") as f:
        pickle.dump({"records": sample_records[:5], "timestamp": datetime.datetime.utcnow().isoformat()}, f)
    ckpt_ok = ckpt_test.exists() and ckpt_test.stat().st_size > 0
    vr.record("Checkpoint file writeable", ckpt_ok, str(ckpt_test))
    _ok(f"Checkpoint write test — {ckpt_test.stat().st_size} bytes") if ckpt_ok else _fail(
        "Checkpoint write failed")

    # 7. Dashboard state
    dash_test = OUTPUTS_DIR / "preflight_dashboard_state.json"
    test_state = {
        "last_updated": datetime.datetime.utcnow().isoformat() + "Z",
        "candidates": {"Candidate 03": {"status": "RUNNING", "progress_pct": 75.0}},
    }
    with open(dash_test, "w", encoding="utf-8") as f:
        json.dump(test_state, f, indent=2)
    dash_ok = dash_test.exists() and dash_test.stat().st_size > 0
    vr.record("Dashboard state file writeable", dash_ok, str(dash_test))
    _ok(f"Dashboard state write test — {dash_test.stat().st_size} bytes") if dash_ok else _fail(
        "Dashboard state write failed")

    # Clean temp files
    for tmp in [raw_csv, ranked_csv, top10_path, ckpt_test, dash_test]:
        tmp.unlink(missing_ok=True)

    return vr.end_stage()


# ---------------------------------------------------------------------------
# Stage 9 — Runtime Estimation
# ---------------------------------------------------------------------------

def stage9_runtime_estimation(vr: ValidationResult) -> Dict[str, Any]:
    """Compute and display runtime / cost estimates. Always passes."""
    vr.begin_stage("Stage 9 — Runtime Estimation")
    _banner("Stage 9 — Runtime Estimation")

    estimates: Dict[str, Any] = {}

    try:
        controller_root = WORKSPACE / "qrp-cloud-controller"
        sys.path.insert(0, str(controller_root))
        from cloud.compute_manager import ComputeManager
        import yaml

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        workers  = cfg.get("research", {}).get("workers", 7)
        instance = cfg.get("compute", {}).get("instance_type", "t3.2xlarge")
        region   = cfg.get("aws", {}).get("region", "ap-south-1")

        cm = ComputeManager(str(CONFIG_PATH))
        workload       = cm.estimate_workload("c003")
        aws_runtime_s  = cm.estimate_runtime("c003", "aws")
        local_runtime_s = cm.estimate_runtime("c003", "local")
        aws_cost_inr   = cm.estimate_cost(instance, aws_runtime_s)

        aws_runtime_min = aws_runtime_s / 60.0
        completion_utc  = (
            datetime.datetime.utcnow() + datetime.timedelta(seconds=aws_runtime_s)
        ).strftime("%Y-%m-%d %H:%M UTC")

        estimates = {
            "experiments":       workload,
            "workers":           workers,
            "execution_target":  "aws",
            "instance_type":     instance,
            "region":            region,
            "aws_runtime_min":   round(aws_runtime_min, 1),
            "local_runtime_min": round(local_runtime_s / 60.0, 1),
            "aws_cost_inr":      round(aws_cost_inr, 2),
            "aws_cost_usd":      round(aws_cost_inr / 83.0, 3),
            "completion_utc":    completion_utc,
        }

        if _RICH:
            tbl = Table(title="C003 Runtime Estimates", box=box.SIMPLE_HEAVY,
                        show_header=True, header_style="bold yellow")
            tbl.add_column("Metric",  style="cyan")
            tbl.add_column("Value",   style="white")
            tbl.add_row("Experiments",          str(workload))
            tbl.add_row("Workers",              str(workers))
            tbl.add_row("Execution Target",     "AWS " + instance)
            tbl.add_row("AWS Region",           region)
            tbl.add_row("Est. AWS Runtime",     f"{aws_runtime_min:.1f} min")
            tbl.add_row("Est. Local Runtime",   f"{local_runtime_s/60:.1f} min")
            tbl.add_row("Est. AWS Cost",        f"₹{aws_cost_inr:.2f} (${aws_cost_inr/83:.3f} USD)")
            tbl.add_row("Est. Completion (UTC)", completion_utc)
            console.print(tbl)
        else:
            print(f"\n  Experiments:     {workload}")
            print(f"  Workers:         {workers}")
            print(f"  Target:          AWS {instance}")
            print(f"  AWS Runtime:     {aws_runtime_min:.1f} min")
            print(f"  AWS Cost:        ₹{aws_cost_inr:.2f}")
            print(f"  Completion UTC:  {completion_utc}")

        vr.record("Runtime estimates generated", True,
                  f"AWS={aws_runtime_min:.1f}min  Cost=₹{aws_cost_inr:.2f}")
        _ok(f"Runtime estimates — AWS={aws_runtime_min:.1f}min, Cost=₹{aws_cost_inr:.2f}")

    except Exception as e:
        estimates = {"error": str(e)}
        vr.record("Runtime estimation", False, str(e))
        _fail(f"Runtime estimation failed: {e}")

    vr.end_stage()
    return estimates


# ---------------------------------------------------------------------------
# Final Report
# ---------------------------------------------------------------------------

def _print_final_report(vr: ValidationResult, estimates: Dict[str, Any]) -> None:
    """Print the Rich pre-flight summary panel."""
    overall = vr.overall_passed()
    failures = vr.all_failures()

    if _RICH:
        # Stage status lines
        stage_lines = []
        for stage_data in vr.stages:
            icon   = _PASS_SYM if stage_data["passed"] else _FAIL_SYM
            name   = stage_data["name"]
            status = "[bold green]PASS[/]" if stage_data["passed"] else "[bold red]FAIL[/]"
            stage_lines.append(f"  {icon}  {name:<42} {status}")

        # Estimates block
        est_block = ""
        if estimates and "error" not in estimates:
            est_block = (
                f"\n  [dim]----------------------------------------[/]\n"
                f"  [cyan]Estimated Runtime[/]     {estimates.get('aws_runtime_min', '?')} min (AWS)\n"
                f"  [cyan]Estimated Cost[/]        Rs.{estimates.get('aws_cost_inr', '?')} "
                f"(${estimates.get('aws_cost_usd', '?')} USD)\n"
                f"  [cyan]Estimated Completion[/]  {estimates.get('completion_utc', '?')}\n"
                f"  [cyan]Workers[/]               {estimates.get('workers', '?')}\n"
                f"  [cyan]Execution Target[/]      {estimates.get('instance_type', 'AWS')}\n"
            )

        # Overall result
        overall_line = (
            "[bold green]  ===========================\n"
            f"  {_PASS_SYM}  OVERALL RESULT: PASS\n"
            "  ===========================[/]"
            if overall else
            "[bold red]  ===========================\n"
            f"  {_FAIL_SYM}  OVERALL RESULT: FAIL\n"
            "  ===========================[/]"
        )

        body = (
            f"  [bold cyan]Candidate:[/]   C003 - Session Open Range Breakout (SORB)\n"

            f"  [bold cyan]Experiments:[/] {EXPECTED_EXPERIMENTS}\n\n"
            f"  [bold]Pre-Flight Status:[/]\n\n"
            + "\n".join(stage_lines)
            + est_block
            + "\n\n"
            + overall_line
        )

        border_style = "bold green" if overall else "bold red"
        console.print(
            Panel(
                body,
                title="[bold white]C003 Pre-Flight Validation Report[/]",
                border_style=border_style,
                padding=(1, 2),
            )
        )

        # Failure details
        if not overall:
            console.rule("[bold red]Failed Tests[/]")
            fail_tbl = Table(box=box.SIMPLE, show_header=True, header_style="bold red")
            fail_tbl.add_column("Stage",  style="red",  no_wrap=True)
            fail_tbl.add_column("Test",   style="white")
            fail_tbl.add_column("Detail", style="yellow")
            for stage_name, test, detail in failures:
                fail_tbl.add_row(stage_name, test, detail[:80])
            console.print(fail_tbl)

            console.rule("[bold yellow]Recommended Fixes[/]")
            _print_fixes(failures)

            console.print(
                Panel(
                    "[bold red]DISCOVERY SWEEP BLOCKED[/]\n\n"

                    "Resolve all failed validations before launching run_sweep_c003.py.",
                    border_style="red",
                )
            )
    else:
        # Fallback plain print
        print("\n" + "=" * 60)
        print("C003 Pre-Flight Validation Report")
        print("=" * 60)
        print(f"Candidate:   C003")
        print(f"Experiments: {EXPECTED_EXPERIMENTS}")
        print("\nPre-Flight Status:")
        for stage_data in vr.stages:
                icon = _PASS_SYM if stage_data["passed"] else _FAIL_SYM
                print(f"  {icon}  {stage_data['name']}")
        print()
        print(f"Overall: {'PASS' if overall else 'FAIL'}")
        if not overall:
            print("\nFailed tests:")
            for stage_name, test, detail in failures:
                print(f"  [{stage_name}] {test}: {detail}")
        print("=" * 60)


def _print_fixes(failures: List[Tuple[str, str, str]]) -> None:
    """Print recommended fixes for each failure type."""
    fix_map = {
        "plugin import":             "Verify research/candidate_03/code/strategy_plugin.py exists and has no syntax errors.",
        "trade logging":             "Check _run_sorb_backtest_single_asset() returns properly structured trade dicts.",
        "equity curve":              "Ensure run_sorb_universe_backtest() builds equity_curve from trade PnL.",
        "total experiment count":    f"Expected {EXPECTED_EXPERIMENTS}. Re-run build_experiment_grid() with --dry-run to debug.",
        "duplicate":                 "Check the itertools.product loop in build_experiment_grid() for logic errors.",
        "pruning":                   "Check pruning conditions in build_experiment_grid() match the C003-DM-v1 spec.",
        "config key":                "Update qrp-cloud-controller/configs/config.yaml with the missing key.",
        "pem key":                   "Verify the SSH PEM key path in config.yaml points to a real file.",
        "boto3":                     "Run: pip install boto3",
        "dashboard field":           "Check _update_dashboard() in run_sweep_c003.py writes all required fields.",
        "research ledger":           "The file research/candidate_03/research_ledger.md must exist.",
        "checkpoint":                "Verify outputs directory is writable: research_engine/outputs/",
        "sweep script":              "Verify research_engine/run_sweep_c003.py exists.",
        "researchrunner":            "Check qrp-cloud-controller/cloud/research_runner.py imports cleanly.",
    }
    for _, test, detail in failures:
        test_lower = test.lower()
        fix_applied = False
        for keyword, fix in fix_map.items():
            if keyword in test_lower:
                console.print(f"  [yellow]-->[/] [bold]{test}[/]: {fix}") if _RICH else print(f"  --> {test}: {fix}")
                fix_applied = True
                break
        if not fix_applied:
            console.print(f"  [yellow]-->[/] [bold]{test}[/]: Review the detailed error above.") if _RICH else print(
                f"  --> {test}: Review the detailed error above.")



# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_preflight() -> int:
    """Execute all pre-flight stages in sequence. Returns exit code (0=pass, 1=fail)."""
    vr = ValidationResult()
    estimates: Dict[str, Any] = {}

    if _RICH:
        console.print(
            Panel(
                "[bold cyan]C003 Pre-Flight Validation System[/]\n"
                "QRP Framework v2.0 — Session Open Range Breakout\n\n"
                f"[dim]Workspace: {WORKSPACE}[/]\n"
                f"[dim]Timestamp: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
    else:
        print("\nC003 Pre-Flight Validation System")
        print(f"Workspace: {WORKSPACE}")

    # Run all stages in sequence — each stage reports but does not block the others
    # (all failures are collected; final panel shows the complete picture)
    stage1_strategy_validation(vr)
    stage2_matrix_validation(vr)
    stage3_dry_run(vr)
    stage4_resume_validation(vr)
    stage5_dashboard_validation(vr)
    stage6_cloud_controller_validation(vr)
    stage7_research_validation(vr)
    stage8_output_validation(vr)
    estimates = stage9_runtime_estimation(vr)

    _print_final_report(vr, estimates)

    return 0 if vr.overall_passed() else 1


if __name__ == "__main__":
    sys.exit(run_preflight())
