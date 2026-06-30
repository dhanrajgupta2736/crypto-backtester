"""Discovery Engine Run Driver / Verification Script.

Executes a single end-to-end backtest verification run for Candidate C001
on the 1H timeframe, computes performance metrics, and exports all reports.
"""

import os
from pathlib import Path
import sys
import pandas as pd
import yaml

# Add workspace directory to python path for dynamic imports
workspace_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_dir))

from research_engine.core.discovery_engine import DiscoveryEngine
from research_engine.core.experiment_manager import ExperimentManager
from research_engine.core.metrics_engine import MetricsEngine
from research_engine.core.reporting import ReportingEngine
from research_engine.core.logger import CustomLogger
from research_engine.core.experiment_registry import ExperimentRegistry
from research_engine.core.candidate_dashboard import CandidateDashboard


def run_verification_experiment():
    print("======================================================================")
    print("  QRP Framework v2.0 — Candidate C001 Discovery Verification Run")
    print("======================================================================")
    
    # 1. Paths Setup
    candidate_id = "candidate_01_relative_strength"
    candidate_dir = workspace_dir / "research" / candidate_id
    configs_dir = candidate_dir / "configs"
    
    framework_config_path = workspace_dir / "research_engine" / "configs" / "framework_config.yaml"
    candidate_yaml_path = configs_dir / "candidate.yaml"
    experiment_yaml_path = configs_dir / "experiment.yaml"
    validation_rules_path = workspace_dir / "research_engine" / "configs" / "validation_rules.yaml"

    # 2. Ingest Configurations
    with open(framework_config_path, "r", encoding="utf-8") as f:
        framework_cfg = yaml.safe_load(f)
    with open(candidate_yaml_path, "r", encoding="utf-8") as f:
        candidate_cfg = yaml.safe_load(f)
    with open(experiment_yaml_path, "r", encoding="utf-8") as f:
        experiment_cfg = yaml.safe_load(f)
    with open(validation_rules_path, "r", encoding="utf-8") as f:
        validation_cfg = yaml.safe_load(f)

    # 3. Setup Loggers & Dashboard
    outputs_dir = workspace_dir / "research_engine" / "outputs"
    dashboard_path = outputs_dir / "dashboard_state.json"
    registry_path = outputs_dir / "experiment_registry.json"
    
    custom_logger = CustomLogger(log_dir=workspace_dir / "research")
    logger = custom_logger.get_experiment_logger(candidate_id, "experiment")
    
    dashboard = CandidateDashboard(state_file_path=dashboard_path)
    registry = ExperimentRegistry(database_path=registry_path)
    
    # Assign Experiment ID
    experiment_id = "C001-E0001"
    logger.info(f"Initializing Experiment {experiment_id} for Candidate C001.")
    dashboard.update_candidate_progress(
        candidate_id="Candidate 01",
        stage="Discovery Sweep",
        status="RUNNING",
        progress_pct=10.0,
        current_experiment=experiment_id,
        notes="Starting Pre-Flight Validation checks."
    )

    # 4. Pre-Flight Validation Check
    logger.info("Executing Pre-Flight Validation gates...")
    try:
        # A. Metadata verification
        assert candidate_cfg.get("candidate", {}).get("metadata", {}).get("id") == "C001", "Candidate ID must be C001"
        assert candidate_cfg.get("candidate", {}).get("metadata", {}).get("framework_version") == "QRP Framework v2.0", "Mismatched Framework Version"
        
        # B. Timeframe check
        timeframes = candidate_cfg.get("candidate", {}).get("timeframes", [])
        supported_timeframes = validation_cfg.get("validation_gates", {}).get("timeframes", {}).get("supported", [])
        for tf in timeframes:
            assert tf in supported_timeframes, f"Unsupported timeframe: {tf}"
            
        # C. Universe size check
        symbols = candidate_cfg.get("candidate", {}).get("universe", {}).get("symbols", [])
        max_pos = candidate_cfg.get("candidate", {}).get("portfolio", {}).get("max_active_positions", 3)
        assert max_pos <= len(symbols), "Portfolio size K cannot exceed universe symbol count"
        
        logger.info("Pre-Flight Validation PASSED successfully.")
    except AssertionError as e:
        logger.error(f"Pre-Flight Validation FAILED: {e}")
        dashboard.update_candidate_progress(
            candidate_id="Candidate 01",
            stage="Discovery Sweep",
            status="FAILED",
            progress_pct=10.0,
            notes=f"Validation failed: {e}"
        )
        sys.exit(1)

    # 5. Initialize Core Engine & Load Plugin
    logger.info("Loading Discovery Engine and dynamic strategy plugin...")
    engine = DiscoveryEngine(config_path=framework_config_path)
    plugin = engine.load_plugin(candidate_id)
    logger.info(f"Plugin dynamic import successful: {plugin.metadata.get('name')} v{plugin.metadata.get('version')}")

    # 6. Load Datasets
    logger.info(f"Loading historical datasets for {len(symbols)} symbols on 1H resolution...")
    universe_data = engine.load_dataset(symbols, "1H")
    logger.info(f"Successfully loaded data for {len(universe_data)} out of {len(symbols)} universe symbols.")
    
    # Verify loaded symbols count
    if len(universe_data) < len(symbols):
        logger.warning(f"Missing data folders for: {set(symbols) - set(universe_data.keys())}")

    # 7. Preprocess & Generate Signals
    logger.info("Executing Strategy Preprocessing hook...")
    preprocessed_data = plugin.preprocess(universe_data)
    
    logger.info("Computing relative strength ranks and binary signal vectors...")
    parameters = {
        "lookback_window": experiment_cfg.get("experiment_sweep", {}).get("parameter_space", {}).get("lookback_window", [50])[0],
        "portfolio_size_k": experiment_cfg.get("experiment_sweep", {}).get("parameter_space", {}).get("portfolio_size_k", [3])[0],
        "rebalance_frequency_r": experiment_cfg.get("experiment_sweep", {}).get("parameter_space", {}).get("rebalance_frequency_r", [1])[0]
    }
    signaled_data = plugin.generate_signals(preprocessed_data, parameters)
    
    # 8. Simulate Backtest Execution Loop
    logger.info("Executing rebalancing backtest simulation loop...")
    results = engine.simulate_backtest(signaled_data, parameters)
    
    trade_ledger = results["trade_ledger"]
    equity_curve = results["equity_curve"]
    num_rebalances = results["number_of_rebalances"]
    total_volume = results["total_volume_traded"]
    avg_port_val = results["average_portfolio_value"]
    
    logger.info(f"Simulation completed. Generated {len(trade_ledger)} round-trip trades.")

    # 9. Compute Performance Metrics
    logger.info("Compiling quantitative performance metrics...")
    metrics_engine = MetricsEngine()
    metrics = metrics_engine.calculate_metrics(
        trade_ledger=trade_ledger,
        daily_equity=equity_curve,
        number_of_rebalances=num_rebalances,
        total_volume_traded=total_volume,
        average_portfolio_value=avg_port_val
    )
    logger.info(f"Expectancy: {metrics['expectancy_r']:.4f} USD | Profit Factor: {metrics['profit_factor']:.4f}")
    logger.info(f"Max Drawdown: {metrics['max_drawdown']['drawdown_pct']:.2f}% | Sharpe Ratio: {metrics['sharpe_ratio']:.4f}")

    # 10. Generate Output Files & Reports
    logger.info("Exporting trade ledgers, equity curves, manifests, and performance reports...")
    reporting = ReportingEngine(outputs_dir=candidate_dir)
    
    # Create experiment folder directory structure
    exp_dir = reporting.create_experiment_directory("", "")
    
    # Save CSV and JSON logs
    reporting.export_trade_ledger(exp_dir, trade_ledger)
    reporting.export_portfolio_equity(exp_dir, equity_curve)
    
    # Save manifest
    manager = ExperimentManager(candidate_id="Candidate 01")
    manifest = manager.create_manifest(
        experiment_id=experiment_id,
        parameters=parameters,
        timeframe="1H",
        universe=symbols,
        termination_status=results["status"],
        termination_reason=results["termination_reason"]
    )
    # Put actual git hash if git is available
    import subprocess
    try:
        git_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        manifest["git_commit"] = git_hash
    except Exception:
        pass
        
    manager.save_manifest(exp_dir, manifest)
    
    # Save metrics JSON
    reporting.export_metrics_json(exp_dir, metrics)
    
    # Save experiment summary CSV
    summary_data = []
    summary_data.append({
        "Experiment ID": experiment_id,
        "Lookback": parameters["lookback_window"],
        "Portfolio Size": parameters["portfolio_size_k"],
        "Rebalance Freq": parameters["rebalance_frequency_r"],
        "Trades": metrics["trade_count"],
        "Win Rate": f"{metrics['win_rate']:.2f}%",
        "Profit Factor": f"{metrics['profit_factor']:.4f}",
        "Sharpe": f"{metrics['sharpe_ratio']:.4f}",
        "Max Drawdown": f"{metrics['max_drawdown']['drawdown_pct']:.2f}%",
        "Expectancy (USD)": f"{metrics['expectancy_r']:.4f}"
    })
    summary_df = pd.DataFrame(summary_data)
    reporting.export_experiment_summary(exp_dir, summary_df)
    
    # Auto-compile markdown performance report
    log_path = candidate_dir / "logs" / "experiment.log"
    reporting.compile_markdown_report(exp_dir, manifest, metrics, log_path)
    
    # 11. Register & Update Dashboard
    logger.info("Registering experiment run to DB index and updating dashboards...")
    registry.register_experiment(candidate_id, experiment_id, manifest, metrics)
    
    dashboard.update_candidate_progress(
        candidate_id="Candidate 01",
        stage="Discovery Sweep",
        status=results["status"],
        progress_pct=100.0,
        current_experiment=experiment_id,
        notes=f"Verification experiment complete. Status: {results['status']}. Reason: {results['termination_reason']}"
    )
    
    custom_logger.success(logger, f"Verification experiment {experiment_id} executed successfully. Outputs stored under {candidate_dir}.")
    print("======================================================================")
    print("  VERIFICATION COMPLETED SUCCESSFULY!")
    print(f"  All deliverables saved inside: {candidate_dir}")
    print("======================================================================")


if __name__ == "__main__":
    run_verification_experiment()
