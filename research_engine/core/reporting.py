"""Reporting and Export Engine.

Compiles backtesting statistics, formats metadata summaries,
and saves result files (CSV, Markdown) to output destinations.
"""

from pathlib import Path
import pandas as pd
import json


class ReportingEngine:
    """Handles report compilation, CSV exporting, and path mapping."""

    def __init__(self, outputs_dir: Path) -> None:
        """Initialize with framework outputs directory."""
        self.outputs_dir: Path = outputs_dir

    def create_experiment_directory(self, candidate_id: str, experiment_id: str) -> Path:
        """Reserve and create output path destination."""
        exp_dir = self.outputs_dir / candidate_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories for outputs
        (exp_dir / "outputs").mkdir(exist_ok=True)
        (exp_dir / "reports").mkdir(exist_ok=True)
        (exp_dir / "manifest").mkdir(exist_ok=True)
        
        return exp_dir

    def export_trade_ledger(self, exp_dir: Path, trade_ledger: pd.DataFrame) -> Path:
        """Save trade logs to a structured CSV file."""
        csv_path = exp_dir / "outputs" / "trade_log.csv"
        trade_ledger.to_csv(csv_path, index=False)
        return csv_path

    def export_portfolio_equity(self, exp_dir: Path, daily_equity: pd.DataFrame) -> Path:
        """Save portfolio equity curve to a CSV file."""
        csv_path = exp_dir / "outputs" / "portfolio_equity.csv"
        daily_equity.to_csv(csv_path, index=True)
        return csv_path

    def export_experiment_summary(self, exp_dir: Path, summary_df: pd.DataFrame) -> Path:
        """Save experiment summary to a CSV file."""
        csv_path = exp_dir / "outputs" / "experiment_summary.csv"
        summary_df.to_csv(csv_path, index=False)
        return csv_path

    def export_metrics_json(self, exp_dir: Path, metrics: dict) -> Path:
        """Save performance metrics to a JSON file."""
        json_path = exp_dir / "outputs" / "metrics.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
        return json_path

    def compile_markdown_report(self, 
                                exp_dir: Path, 
                                manifest: dict, 
                                metrics: dict, 
                                log_path: Path) -> Path:
        """Auto-generate a human-readable markdown summary detailing performance.
        
        Args:
            exp_dir (Path): Output experiment folder.
            manifest (dict): Reproducibility metadata.
            metrics (dict): Performance metrics.
            log_path (Path): Path to associated execution log.
            
        Returns:
            Path: Filepath to compiled markdown file.
        """
        report_path = exp_dir / "reports" / "experiment_report.md"
        
        cand_id = manifest.get('candidate_id', 'C001')
        exp_id = manifest.get('experiment_id', 'N/A')
        universe = manifest.get('universe') or {}
        asset_class = universe.get('asset_class', 'N/A').title()
        timestamp = manifest.get('timestamp', 'N/A')
        fw_ver = manifest.get('framework_version', 'N/A')
        cand_ver = manifest.get('candidate_version', 'N/A')
        git_commit = manifest.get('git_commit', 'N/A')
        tf = manifest.get('timeframe', 'N/A')
        symbols = universe.get('symbols', [])
        univ_size = len(symbols)
        params = manifest.get('parameters') or {}
        
        term_status = manifest.get('termination_status', 'N/A')
        term_reason = manifest.get('termination_reason', 'N/A')
        fw_safety_ver = manifest.get('framework_safety_version', 'QRP Framework v2.0.1')
        regression_test_ver = manifest.get('regression_test_version', 'v1.0.0')
        
        param_list = [f"* **{k}**: {v}" for k, v in params.items()]
        param_str = "\n".join(param_list)
        
        max_dd_val = metrics.get('max_drawdown', {}).get('drawdown_pct', 0.0)
        
        report_content = f"""# Candidate {cand_id} — Experiment Run Report

## Run Metadata
* **Experiment ID**: {exp_id}
* **Strategy Name**: {asset_class} Relative Strength
* **Timestamp**: {timestamp}
* **Framework Version**: {fw_ver}
* **Candidate Version**: {cand_ver}
* **Git Commit**: `{git_commit}`
* **Data Timeframe**: {tf}
* **Universe Size**: {univ_size} assets
* **Termination Status**: {term_status}
* **Termination Reason**: {term_reason}
* **Framework Safety Version**: {fw_safety_ver}
* **Regression Test Version**: {regression_test_ver}

## Sweep Parameter Mapping
{param_str}

---

## Performance Summary

| Metric | Value |
| :--- | :---: |
| **Trade Count** | {metrics.get('trade_count', 0)} |
| **Win Rate** | {metrics.get('win_rate', 0.0):.2f}% |
| **Profit Factor** | {metrics.get('profit_factor', 0.0):.4f} |
| **Sharpe Ratio** | {metrics.get('sharpe_ratio', 0.0):.4f} |
| **CAGR** | {metrics.get('cagr', 0.0):.2f}% |
| **Maximum Drawdown** | {max_dd_val:.2f}% |
| **Expectancy** | {metrics.get('expectancy_r', 0.0):.4f} R |
| **Average Holding Period** | {metrics.get('avg_holding_period_hours', 0.0):.2f} hours |
| **Number of Rebalances** | {metrics.get('number_of_rebalances', 0)} |
| **Portfolio Turnover** | {metrics.get('portfolio_turnover', 0.0):.2f} |

---

## Document Link Mapping
* **Manifest file**: `manifest/experiment_manifest.json`
* **Trade log**: `outputs/trade_log.csv`
* **Portfolio Equity curve**: `outputs/portfolio_equity.csv`
* **Execution log file**: `logs/experiment.log`
"""
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
            
        return report_path
