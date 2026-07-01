"""Discovery Sweep Runner for Candidate C003 — Session Open Range Breakout (SORB).

QRP Framework v2.0 — Phase 1 Discovery Sweep

Executes 3,216 SORB parameter configurations in parallel across the complete
25-asset research universe. Applies all structural pruning rules from the
approved C003 Discovery Matrix (C003-DM-v1).

Usage:
    python research_engine/run_sweep_c003.py [--workers N] [--dry-run]

Features:
    - Full checkpoint / resume support (safe to interrupt and restart)
    - Live dashboard state updates (streamed to dashboard_state.json)
    - Parallel execution via ProcessPoolExecutor
    - Experiment registry logging
    - Ranked output CSV with PASS/BORDERLINE/REJECT verdicts
    - Markdown discovery analysis report
"""

from __future__ import annotations

import argparse
import datetime
import itertools
import json
import os
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
workspace_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_dir))

from research_engine.core.discovery_engine import DiscoveryEngine
from research_engine.core.metrics_engine import MetricsEngine
from research_engine.core.candidate_dashboard import CandidateDashboard
from research_engine.core.experiment_registry import ExperimentRegistry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANDIDATE_ID = "C003"
CANDIDATE_FOLDER = "candidate_03"
CANDIDATE_LABEL = "Candidate 03"

FRAMEWORK_CONFIG_PATH = workspace_dir / "research_engine" / "configs" / "framework_config.yaml"
CANDIDATE_DIR = workspace_dir / "research" / CANDIDATE_FOLDER
CANDIDATE_YAML_PATH = CANDIDATE_DIR / "configs" / "candidate.yaml"
OUTPUTS_DIR = CANDIDATE_DIR / "outputs"
REPORTS_DIR = CANDIDATE_DIR / "reports"
CHECKPOINT_PATH = workspace_dir / "research_engine" / "outputs" / f"checkpoint_sweep_c003.pkl"
DASHBOARD_PATH = workspace_dir / "research_engine" / "outputs" / "dashboard_state.json"
REGISTRY_DB_PATH = workspace_dir / "research_engine" / "outputs" / "experiment_registry.db"

# Verdict thresholds (from objective_definition.md)
PASS_SHARPE = 0.80
PASS_PF = 1.40
PASS_DD = 35.0
PASS_TRADES = 50
BORDERLINE_SHARPE = 0.50
BORDERLINE_DD = 45.0
BORDERLINE_TRADES = 35


# ---------------------------------------------------------------------------
# Dashboard helper (patched for extended fields — same as C002 sweep)
# ---------------------------------------------------------------------------

def _update_dashboard(
    dashboard: CandidateDashboard,
    stage: str,
    status: str,
    progress_pct: float,
    notes: str = "",
    eta: str = "N/A",
    best_label: str = "N/A",
    highest_sharpe: float = 0.0,
    highest_pf: float = 0.0,
    highest_cagr: float = 0.0,
) -> None:
    """Write extended dashboard state (same schema as C002 sweeps)."""
    state: dict = {"last_updated": "", "candidates": {}}
    try:
        with open(dashboard.state_file_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        pass

    candidates = state.get("candidates", {})
    cand = candidates.get(CANDIDATE_LABEL, {})

    cand["name"] = CANDIDATE_LABEL
    cand["stage"] = stage
    cand["status"] = status
    cand["progress_pct"] = progress_pct
    cand["notes"] = notes
    cand["eta"] = eta
    cand["current_best_candidate"] = best_label
    cand["highest_sharpe"] = highest_sharpe
    cand["highest_profit_factor"] = highest_pf
    cand["highest_cagr"] = highest_cagr

    now_str = datetime.datetime.utcnow().isoformat() + "Z"
    if status == "RUNNING" and not cand.get("start_time"):
        cand["start_time"] = now_str
        cand["end_time"] = None
    elif status in ("COMPLETED", "FAILED", "TERMINATED"):
        cand["end_time"] = now_str

    candidates[CANDIDATE_LABEL] = cand
    state["candidates"] = candidates
    state["last_updated"] = now_str

    with open(dashboard.state_file_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Experiment Grid Builder
# ---------------------------------------------------------------------------

def build_experiment_grid() -> List[Dict[str, Any]]:
    """Build the full C003 experiment parameter list with structural pruning applied.

    Pruning rules (from C003-DM-v1):
        PR-01: timeframe=1H + open_range_minutes=30 — INVALID (no sub-hour 1H bars)
        PR-02: session=both + timeframe=1H + open_range_minutes=90 — INVALID (overlap ambiguity)
        PR-03: buffer=0.2 + stop=range_low + exit=session_close + session=both — INVALID
        PR-04: exit=fixed_rr + stop=range_low + rr in {1.0, 1.25} — fee-dominated, uninterpretable

    Returns:
        List of parameter dicts, one per experiment.
    """
    # Dimension values
    TIMEFRAMES = ["15m", "1H"]
    SESSIONS = ["london", "newyork", "both"]
    OPEN_RANGE_MINUTES = [30, 60, 90]
    BREAKOUT_BUFFERS = [0.0, 0.1, 0.2]
    STOP_MODES = ["range_low", "atr_stop"]
    # Non-RR exit modes
    NON_RR_EXITS = ["session_close", "atr_trail", "swing_trail"]
    # Fixed RR exit mode
    FIXED_RR_VALS_RANGE_LOW = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]   # PR-04: 1.0/1.25 excluded
    FIXED_RR_VALS_ATR_STOP = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    TREND_FILTERS = ["off", "ema50", "ema100", "ema200"]

    TREND_EMA_MAP = {"off": None, "ema50": 50, "ema100": 100, "ema200": 200}

    # Fixed baseline values (locked in v1 discovery pass)
    ATR_STOP_MULTIPLIER = 1.5
    ATR_PERIOD = 14

    experiments: List[Dict[str, Any]] = []
    exp_idx = 0

    for tf, sess, orm, buf, trend in itertools.product(
        TIMEFRAMES, SESSIONS, OPEN_RANGE_MINUTES, BREAKOUT_BUFFERS, TREND_FILTERS
    ):
        # --- PR-01: 1H + 30-min range is structurally invalid ---
        if tf == "1H" and orm == 30:
            continue

        # --- PR-02: session=both + 1H + 90-min has session overlap ambiguity ---
        if sess == "both" and tf == "1H" and orm == 90:
            continue

        base = {
            "timeframe": tf,
            "session": sess,
            "open_range_minutes": orm,
            "breakout_buffer_atr": buf,
            "atr_stop_multiplier": ATR_STOP_MULTIPLIER,
            "atr_period": ATR_PERIOD,
            "trend_filter": trend,
            "trend_ema_period": TREND_EMA_MAP[trend],
        }

        # --- Group A: Non-RR exits ---
        for stop in STOP_MODES:
            for exit_mode in NON_RR_EXITS:
                # --- PR-03: buf=0.2 + stop=range_low + session_close + session=both ---
                if buf == 0.2 and stop == "range_low" and exit_mode == "session_close" and sess == "both":
                    continue

                exp_idx += 1
                experiments.append(
                    {
                        **base,
                        "stop_mode": stop,
                        "exit_mode": exit_mode,
                        "fixed_rr": None,
                        "experiment_id": f"C003_E{exp_idx:04d}",
                    }
                )

        # --- Group B: Fixed RR exits ---
        for stop in STOP_MODES:
            rr_vals = (
                FIXED_RR_VALS_RANGE_LOW if stop == "range_low" else FIXED_RR_VALS_ATR_STOP
            )
            for rr in rr_vals:
                exp_idx += 1
                experiments.append(
                    {
                        **base,
                        "stop_mode": stop,
                        "exit_mode": "fixed_rr",
                        "fixed_rr": rr,
                        "experiment_id": f"C003_E{exp_idx:04d}",
                    }
                )

    return experiments


# ---------------------------------------------------------------------------
# Worker initialization and function (runs in subprocess — must be top-level for pickling)
# ---------------------------------------------------------------------------

# Subprocess globals to avoid copying dataframes over IPC on every experiment
_worker_universe_15m = None
_worker_universe_1h = None


def _init_worker(u15m: dict, u1h: dict) -> None:
    """Initialize subprocess worker pool with global dataframes to avoid IPC overhead."""
    global _worker_universe_15m, _worker_universe_1h
    _worker_universe_15m = u15m
    _worker_universe_1h = u1h


def _worker_run_experiment(
    args: Tuple[Dict[str, Any], Optional[Dict[str, pd.DataFrame]]],
) -> Dict[str, Any]:
    """Execute a single SORB experiment (runs inside a worker process).

    Args:
        args: Tuple of (params dict, universe_data dict).

    Returns:
        Result record dict.
    """
    params, universe_data = args

    # IPC optimization: use global dataframes if available
    global _worker_universe_15m, _worker_universe_1h
    if universe_data is None:
        universe_data = _worker_universe_1h if params["timeframe"] == "1H" else _worker_universe_15m

    try:
        # Import here (subprocess context)
        _ws = Path(__file__).resolve().parent.parent
        if str(_ws) not in sys.path:
            sys.path.insert(0, str(_ws))

        from research_engine.core.metrics_engine import MetricsEngine
        from research.candidate_03.code.strategy_plugin import StrategyPlugin

        plugin = StrategyPlugin()
        metrics_engine = MetricsEngine()

        results = plugin.run_sorb_universe_backtest(universe_data, params)

        trade_ledger = results["trade_ledger"]
        equity_curve = results["equity_curve"]
        num_rebalances = results["number_of_rebalances"]
        total_volume = results["total_volume_traded"]
        avg_port_val = results["average_portfolio_value"]

        metrics = metrics_engine.calculate_metrics(
            trade_ledger=trade_ledger,
            daily_equity=equity_curve,
            number_of_rebalances=num_rebalances,
            total_volume_traded=total_volume,
            average_portfolio_value=avg_port_val,
        )

        tc = metrics["trade_count"]
        sh = round(metrics["sharpe_ratio"], 4)
        pf = round(metrics["profit_factor"], 4)
        dd = round(metrics["max_drawdown"]["drawdown_pct"], 2)
        cagr = round(metrics["cagr"], 2)
        wr = round(metrics["win_rate"], 2)
        exp_r = round(metrics["expectancy_r"], 4)
        avg_hold = round(metrics["avg_holding_period_hours"], 2)

        # Fee cost
        gross_fees = trade_ledger["fees_paid"].sum() if not trade_ledger.empty else 0.0
        gross_slip = trade_ledger["slippage_paid"].sum() if not trade_ledger.empty else 0.0
        net_pnl = trade_ledger["pnl_nominal"].sum() if not trade_ledger.empty else 0.0
        gross_pnl = net_pnl + gross_fees + gross_slip
        fee_pct = (gross_fees / abs(gross_pnl)) * 100.0 if abs(gross_pnl) > 0 else 0.0

        # Quality Score (same formula as C002)
        quality_score = (
            sh * 1.5
            + pf * 1.0
            - (dd / 100.0) * 1.0
            - (fee_pct / 100.0) * 0.5
        )

        # Research validation gates checks
        rejection_reason = None
        if tc < 30:
            rejection_reason = f"Trade Count {tc} < 30"
        elif not np.isfinite(pf) or pf >= 999.0:
            rejection_reason = f"Profit Factor {pf} >= 999 or non-finite"
        elif not np.isfinite(sh):
            rejection_reason = f"Sharpe Ratio {sh} is non-finite"
        elif not np.isfinite(dd):
            rejection_reason = f"Max Drawdown {dd} is non-finite"
        elif not np.isfinite(cagr):
            rejection_reason = f"CAGR {cagr} is non-finite"

        if rejection_reason is not None:
            verdict = "REJECT"
            print(f"REJECTED [{params['experiment_id']}]: {rejection_reason}")
        else:
            # Verdict
            if sh >= PASS_SHARPE and pf >= PASS_PF and dd <= PASS_DD and tc >= PASS_TRADES:
                verdict = "PASS"
            elif sh >= BORDERLINE_SHARPE and dd <= BORDERLINE_DD and tc >= BORDERLINE_TRADES:
                verdict = "BORDERLINE"
            else:
                verdict = "REJECT"

        return {
            "experiment_id": params["experiment_id"],
            "timeframe": params["timeframe"],
            "session": params["session"],
            "open_range_minutes": params["open_range_minutes"],
            "breakout_buffer_atr": params["breakout_buffer_atr"],
            "stop_mode": params["stop_mode"],
            "exit_mode": params["exit_mode"],
            "fixed_rr": params.get("fixed_rr"),
            "trend_filter": params["trend_filter"],
            "trade_count": tc,
            "win_rate": wr,
            "profit_factor": pf,
            "expectancy_r": exp_r,
            "cagr": cagr,
            "sharpe_ratio": sh,
            "max_drawdown": dd,
            "avg_hold_hours": avg_hold,
            "fee_pct": round(fee_pct, 2),
            "quality_score": round(quality_score, 4),
            "verdict": verdict,
            "status": results["status"],
            "rejection_reason": rejection_reason,
            "error": None,
        }

    except Exception as exc:
        return {
            "experiment_id": params.get("experiment_id", "UNKNOWN"),
            "timeframe": params.get("timeframe"),
            "session": params.get("session"),
            "open_range_minutes": params.get("open_range_minutes"),
            "breakout_buffer_atr": params.get("breakout_buffer_atr"),
            "stop_mode": params.get("stop_mode"),
            "exit_mode": params.get("exit_mode"),
            "fixed_rr": params.get("fixed_rr"),
            "trend_filter": params.get("trend_filter"),
            "trade_count": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy_r": 0.0,
            "cagr": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "avg_hold_hours": 0.0,
            "fee_pct": 0.0,
            "quality_score": -999.0,
            "verdict": "ERROR",
            "status": "FAILED",
            "rejection_reason": f"Execution error: {exc}",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_checkpoint() -> Tuple[List[Dict], set]:
    """Load completed experiment records and completed IDs from checkpoint."""
    if not CHECKPOINT_PATH.exists():
        return [], set()
    try:
        with open(CHECKPOINT_PATH, "rb") as f:
            data = pickle.load(f)
        completed_records = data.get("records", [])
        completed_ids = {r["experiment_id"] for r in completed_records}
        print(f"[Checkpoint] Resuming from checkpoint: {len(completed_ids)} experiments already done.")
        return completed_records, completed_ids
    except Exception as e:
        print(f"[Checkpoint] Warning: could not load checkpoint ({e}). Starting fresh.")
        return [], set()


def _save_checkpoint(records: List[Dict]) -> None:
    """Persist completed records to checkpoint file."""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_PATH, "wb") as f:
        pickle.dump({"records": records, "timestamp": datetime.datetime.utcnow().isoformat()}, f)
    # Write checkpoint.json as requested by Execution Requirements
    json_ckpt_path = CHECKPOINT_PATH.parent / "checkpoint.json"
    with open(json_ckpt_path, "w", encoding="utf-8") as f:
        json.dump({"records": records, "timestamp": datetime.datetime.utcnow().isoformat()}, f, indent=2)


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def _generate_report(df_ranked: pd.DataFrame, winner: pd.Series) -> None:
    """Write the Markdown discovery analysis report."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "discovery_analysis.md"

    pass_count = (df_ranked["verdict"] == "PASS").sum()
    borderline_count = (df_ranked["verdict"] == "BORDERLINE").sum()
    reject_count = (df_ranked["verdict"] == "REJECT").sum()

    top20 = df_ranked.head(20)[
        [
            "experiment_id", "timeframe", "session", "open_range_minutes",
            "breakout_buffer_atr", "stop_mode", "exit_mode", "fixed_rr",
            "trend_filter", "trade_count", "sharpe_ratio", "profit_factor",
            "max_drawdown", "cagr", "win_rate", "quality_score", "verdict",
        ]
    ]

    md_table = top20.to_markdown(index=False)

    content = f"""# Candidate C003 — SORB Discovery Analysis

**Sweep Date**: {datetime.datetime.utcnow().strftime('%Y-%m-%d')}  
**Framework**: QRP Framework v2.0  
**Total Experiments**: {len(df_ranked)}  
**Asset Universe**: 25 crypto perpetuals  

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| PASS configurations | {pass_count} |
| BORDERLINE configurations | {borderline_count} |
| REJECT configurations | {reject_count} |
| Best Sharpe Ratio | {df_ranked['sharpe_ratio'].max():.4f} |
| Best Profit Factor | {df_ranked['profit_factor'].max():.4f} |
| Best CAGR | {df_ranked['cagr'].max():.2f}% |

---

## Top 20 Configurations by Quality Score

{md_table}

---

## Winning Configuration

| Parameter | Value |
|-----------|-------|
| Experiment ID | {winner['experiment_id']} |
| Timeframe | {winner['timeframe']} |
| Session | {winner['session']} |
| Open Range Minutes | {winner['open_range_minutes']} |
| Breakout Buffer ATR | {winner['breakout_buffer_atr']} |
| Stop Mode | {winner['stop_mode']} |
| Exit Mode | {winner['exit_mode']} |
| Fixed RR | {winner.get('fixed_rr', 'N/A')} |
| Trend Filter | {winner['trend_filter']} |
| Trade Count | {winner['trade_count']} |
| Sharpe Ratio | {winner['sharpe_ratio']:.4f} |
| Profit Factor | {winner['profit_factor']:.4f} |
| Max Drawdown | {winner['max_drawdown']:.2f}% |
| CAGR | {winner['cagr']:.2f}% |
| Win Rate | {winner['win_rate']:.2f}% |
| Quality Score | {winner['quality_score']:.4f} |
| Verdict | **{winner['verdict']}** |

---

## Gate Assessment

| Gate | Requirement | Winner | Pass? |
|------|-------------|--------|-------|
| Sharpe ≥ 0.80 | ≥ 0.80 | {winner['sharpe_ratio']:.4f} | {'✅' if winner['sharpe_ratio'] >= 0.80 else '❌'} |
| Profit Factor ≥ 1.40 | ≥ 1.40 | {winner['profit_factor']:.4f} | {'✅' if winner['profit_factor'] >= 1.40 else '❌'} |
| Max Drawdown ≤ 35% | ≤ 35% | {winner['max_drawdown']:.2f}% | {'✅' if winner['max_drawdown'] <= 35.0 else '❌'} |
| Trade Count ≥ 50 | ≥ 50 | {winner['trade_count']} | {'✅' if winner['trade_count'] >= 50 else '❌'} |
| **Overall** | All gates pass | — | **{'✅ ADVANCE TO WALK-FORWARD' if winner['verdict'] == 'PASS' else '❌ REQUIRES INVESTIGATION'}** |

---

*Generated by run_sweep_c003.py - QRP Framework v2.0*
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[Report] Discovery analysis saved -> {report_path}")


def _generate_additional_outputs(df: pd.DataFrame, df_ranked: pd.DataFrame, winner: pd.Series) -> None:
    """Generate summary report and top 10 ranked slices as CSV."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    summary_path = REPORTS_DIR / "candidate_summary.md"
    pass_count = (df_ranked["verdict"] == "PASS").sum()
    borderline_count = (df_ranked["verdict"] == "BORDERLINE").sum()
    reject_count = (df_ranked["verdict"] == "REJECT").sum()

    # Render performance table for top 10 ranked configs
    top10 = df_ranked.head(10)[
        [
            "experiment_id", "timeframe", "session", "open_range_minutes",
            "breakout_buffer_atr", "stop_mode", "exit_mode", "fixed_rr",
            "trend_filter", "trade_count", "sharpe_ratio", "profit_factor",
            "max_drawdown", "cagr", "win_rate", "quality_score", "verdict",
        ]
    ]
    perf_table = top10.to_markdown(index=False)

    summary_content = f"""# Candidate C003 — Discovery Summary

This document summarizes the results of the Candidate C003 Session Open Range Breakout (SORB) parameter sweep.

## Discovery Matrix Performance Summary (Top 10)

{perf_table}

---

## Verdict Summary
* **PASS**: {pass_count}
* **BORDERLINE**: {borderline_count}
* **REJECT**: {reject_count}
* **Total**: {len(df_ranked)}

## Winning Variant Details
* **Experiment ID**: {winner['experiment_id']}
* **Timeframe**: {winner['timeframe']}
* **Session**: {winner['session']}
* **Open Range Minutes**: {winner['open_range_minutes']}
* **Breakout Buffer ATR**: {winner['breakout_buffer_atr']}
* **Stop Mode**: {winner['stop_mode']}
* **Exit Mode**: {winner['exit_mode']}
* **Fixed RR**: {winner.get('fixed_rr', 'N/A')}
* **Trend Filter**: {winner['trend_filter']}
* **Trade Count**: {winner['trade_count']}
* **Sharpe Ratio**: {winner['sharpe_ratio']:.4f}
* **Profit Factor**: {winner['profit_factor']:.4f}
* **Max Drawdown**: {winner['max_drawdown']:.2f}%
* **CAGR**: {winner['cagr']:.2f}%
* **Quality Score**: {winner['quality_score']:.4f}
* **Verdict**: **{winner['verdict']}**
"""
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_content)
    print(f"[Output] Candidate summary saved -> {summary_path}")

    # Top-10 slices
    df_ranked.head(10).to_csv(OUTPUTS_DIR / "top10_overall.csv", index=False)
    df.sort_values("sharpe_ratio", ascending=False).head(10).to_csv(OUTPUTS_DIR / "top10_sharpe.csv", index=False)
    df.sort_values("profit_factor", ascending=False).head(10).to_csv(OUTPUTS_DIR / "top10_pf.csv", index=False)
    df.sort_values("cagr", ascending=False).head(10).to_csv(OUTPUTS_DIR / "top10_cagr.csv", index=False)
    # Lowest drawdown is best
    df.sort_values("max_drawdown", ascending=True).head(10).to_csv(OUTPUTS_DIR / "top10_drawdown.csv", index=False)
    print("[Output] Top-10 slice CSV files generated.")


# ---------------------------------------------------------------------------
# Main sweep orchestrator
# ---------------------------------------------------------------------------

def run_sweep(workers: int = 7, dry_run: bool = False) -> None:
    """Execute the full C003 SORB discovery sweep.

    Args:
        workers: Number of parallel worker processes.
        dry_run: If True, builds the grid and prints the count only — no backtests.
    """
    print("=" * 72)
    print("  QRP Framework v2.0 — Candidate C003 SORB Discovery Sweep")
    print("  Session Open Range Breakout | 25-Asset Research Universe")
    print("=" * 72)
    print(f"  Workers: {workers}")
    print(f"  Checkpoint path: {CHECKPOINT_PATH}")
    print()

    # Setup output directories
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load candidate config
    with open(CANDIDATE_YAML_PATH, "r", encoding="utf-8") as f:
        candidate_cfg = yaml.safe_load(f)
    symbols: List[str] = candidate_cfg["candidate"]["universe"]["symbols"]
    print(f"[Grid] Asset universe: {len(symbols)} symbols")

    # Build experiment grid
    experiments = build_experiment_grid()
    total_experiments = len(experiments)
    print(f"[Grid] Total experiments (after pruning): {total_experiments}")

    if dry_run:
        print("[DRY-RUN] Grid built successfully. Exiting without executing backtests.")
        return

    # Dashboard and registry
    dashboard = CandidateDashboard(state_file_path=DASHBOARD_PATH)
    registry = ExperimentRegistry(database_path=REGISTRY_DB_PATH)

    _update_dashboard(
        dashboard,
        stage="C003 Discovery Sweep",
        status="RUNNING",
        progress_pct=1.0,
        notes=f"Loading universe data for {len(symbols)} assets…",
    )

    # Load universe data (15m — the primary resolution; 1H loaded separately)
    engine = DiscoveryEngine(config_path=FRAMEWORK_CONFIG_PATH)

    print("[Data] Loading 15m universe data…")
    universe_15m = engine.load_dataset(symbols, "15m")
    print(f"[Data] Loaded {len(universe_15m)} assets at 15m resolution.")

    print("[Data] Loading 1H universe data…")
    universe_1h = engine.load_dataset(symbols, "1H")
    print(f"[Data] Loaded {len(universe_1h)} assets at 1H resolution.")

    if not universe_15m and not universe_1h:
        print("[ERROR] No data loaded. Check data directory. Aborting.")
        _update_dashboard(dashboard, "C003 Discovery Sweep", "FAILED", 0.0, "No data loaded.")
        return

    # Pre-process
    from research.candidate_03.code.strategy_plugin import StrategyPlugin
    plugin = StrategyPlugin()
    universe_15m = plugin.preprocess(universe_15m)
    universe_1h = plugin.preprocess(universe_1h)

    # Checkpoint — resume from prior run if available
    completed_records, completed_ids = _load_checkpoint()
    pending = [e for e in experiments if e["experiment_id"] not in completed_ids]
    print(f"[Sweep] {len(completed_records)} already done, {len(pending)} remaining.")

    _update_dashboard(
        dashboard,
        stage="C003 Discovery Sweep",
        status="RUNNING",
        progress_pct=2.0,
        notes=f"Starting {len(pending)} experiments on {workers} workers…",
    )

    # Track best metrics for dashboard live updates
    best_sharpe = max((r["sharpe_ratio"] for r in completed_records), default=0.0)
    best_pf = max((r["profit_factor"] for r in completed_records), default=0.0)
    best_cagr = max((r["cagr"] for r in completed_records), default=0.0)
    best_label = "N/A"

    sweep_start = time.perf_counter()
    done_count = len(completed_records)
    checkpoint_interval = 50  # save every N completed experiments

    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_worker,
        initargs=(universe_15m, universe_1h),
    ) as executor:
        # Build future map
        future_to_params: dict = {}
        for params in pending:
            future = executor.submit(_worker_run_experiment, (params, None))
            future_to_params[future] = params

        for future in as_completed(future_to_params):
            result = future.result()
            completed_records.append(result)
            done_count += 1

            # Update best trackers
            if result["sharpe_ratio"] > best_sharpe:
                best_sharpe = result["sharpe_ratio"]
                best_label = result["experiment_id"]
            if result["profit_factor"] > best_pf:
                best_pf = result["profit_factor"]
            if result["cagr"] > best_cagr:
                best_cagr = result["cagr"]

            # Progress
            pct = (done_count / total_experiments) * 100.0
            elapsed = time.perf_counter() - sweep_start
            rate = done_count / max(elapsed, 1.0)
            remaining = (total_experiments - done_count) / max(rate, 0.001)
            eta_str = str(datetime.timedelta(seconds=int(remaining)))

            if done_count % 25 == 0 or done_count == total_experiments:
                print(
                    f"  Progress: {done_count}/{total_experiments} ({pct:.1f}%) | "
                    f"ETA {eta_str} | Best Sharpe={best_sharpe:.3f} | "
                    f"Best PF={best_pf:.3f} | {result['experiment_id']} → {result['verdict']}"
                )
                _update_dashboard(
                    dashboard,
                    stage="C003 Discovery Sweep",
                    status="RUNNING",
                    progress_pct=2.0 + pct * 0.95,
                    notes=f"{done_count}/{total_experiments} done. ETA {eta_str}",
                    eta=eta_str,
                    best_label=best_label,
                    highest_sharpe=round(best_sharpe, 4),
                    highest_pf=round(best_pf, 4),
                    highest_cagr=round(best_cagr, 4),
                )

            # Register in experiment registry
            registry.register_experiment(
                candidate_id=CANDIDATE_ID,
                experiment_id=result["experiment_id"],
                manifest={"parameters": future_to_params[future]},
                metrics={
                    "sharpe_ratio": result["sharpe_ratio"],
                    "profit_factor": result["profit_factor"],
                    "max_drawdown": result["max_drawdown"],
                    "trade_count": result["trade_count"],
                    "cagr": result["cagr"],
                },
            )

            # Periodic checkpoint save
            if done_count % checkpoint_interval == 0:
                _save_checkpoint(completed_records)

    # Final checkpoint save
    _save_checkpoint(completed_records)

    elapsed_total = time.perf_counter() - sweep_start
    print(f"\n[Sweep] All {total_experiments} experiments completed in {elapsed_total:.1f}s.")

    # ---------------------------------------------------------------------------
    # Results Processing
    # ---------------------------------------------------------------------------
    df = pd.DataFrame(completed_records)

    # Save raw results
    raw_path = OUTPUTS_DIR / "discovery_matrix_results.csv"
    df.to_csv(raw_path, index=False)
    print(f"[Output] Raw results saved → {raw_path}")

    # Rank by quality score
    df_ranked = df.sort_values("quality_score", ascending=False).reset_index(drop=True)
    ranked_path = OUTPUTS_DIR / "ranked_candidates.csv"
    df_ranked.to_csv(ranked_path, index=False)
    print(f"[Output] Ranked results saved → {ranked_path}")

    # Winner
    winner = df_ranked.iloc[0]

    # Verdict summary
    pass_count = (df_ranked["verdict"] == "PASS").sum()
    borderline_count = (df_ranked["verdict"] == "BORDERLINE").sum()
    reject_count = (df_ranked["verdict"] == "REJECT").sum()

    print("\n" + "=" * 72)
    print("  C003 SORB Discovery Sweep — RESULTS")
    print("=" * 72)
    print(f"  Total experiments:   {len(df_ranked)}")
    print(f"  PASS:                {pass_count}")
    print(f"  BORDERLINE:          {borderline_count}")
    print(f"  REJECT:              {reject_count}")
    print()
    print("  ── WINNING CONFIGURATION ──")
    print(f"  Experiment ID:       {winner['experiment_id']}")
    print(f"  Timeframe:           {winner['timeframe']}")
    print(f"  Session:             {winner['session']}")
    print(f"  Open Range Minutes:  {winner['open_range_minutes']}")
    print(f"  Breakout Buffer ATR: {winner['breakout_buffer_atr']}")
    print(f"  Stop Mode:           {winner['stop_mode']}")
    print(f"  Exit Mode:           {winner['exit_mode']}")
    print(f"  Fixed RR:            {winner.get('fixed_rr', 'N/A')}")
    print(f"  Trend Filter:        {winner['trend_filter']}")
    print(f"  Trade Count:         {winner['trade_count']}")
    print(f"  Sharpe Ratio:        {winner['sharpe_ratio']:.4f}")
    print(f"  Profit Factor:       {winner['profit_factor']:.4f}")
    print(f"  Max Drawdown:        {winner['max_drawdown']:.2f}%")
    print(f"  CAGR:                {winner['cagr']:.2f}%")
    print(f"  Win Rate:            {winner['win_rate']:.2f}%")
    print(f"  Verdict:             {winner['verdict']}")
    print("=" * 72)

    # Generate markdown report
    _generate_report(df_ranked, winner)

    # Generate additional required output files (candidate_summary.md, top10 slices)
    _generate_additional_outputs(df, df_ranked, winner)

    # Final dashboard update
    _update_dashboard(
        dashboard,
        stage="C003 Discovery Sweep",
        status="COMPLETED",
        progress_pct=100.0,
        notes=(
            f"Sweep complete. {pass_count} PASS / {borderline_count} BORDERLINE / "
            f"{reject_count} REJECT. Winner: {winner['experiment_id']} "
            f"(Sharpe={winner['sharpe_ratio']:.4f})"
        ),
        best_label=winner["experiment_id"],
        highest_sharpe=round(best_sharpe, 4),
        highest_pf=round(best_pf, 4),
        highest_cagr=round(best_cagr, 4),
    )

    print("\n[Done] C003 Discovery Sweep complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="C003 SORB Discovery Sweep — QRP Framework v2.0"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=7,
        help="Number of parallel worker processes (default: 7)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the experiment grid and print count only — do not execute backtests",
    )
    args = parser.parse_args()

    run_sweep(workers=args.workers, dry_run=args.dry_run)
