# Research Ledger

This document serves as the institutional ledger tracking all research phases, decisions, and assumptions for strategy candidates.

---

## Candidate 01: Relative Strength

### Current Status
* **Current Stage**: Stage 5–9 — Final Validation
* **Current Status**: `READY_FOR_PAPER_TRADING` (Validation pipeline executed; promoted as BORDERLINE to Paper Trading)
* **Last Updated**: 2026-06-27

---

### Key Information

#### Documents Created
* `research/candidate_01_relative_strength/README.md`
* `research/candidate_01_relative_strength/hypothesis.md`
* `research/candidate_01_relative_strength/research_spec.md`
* `research/candidate_01_relative_strength/signal_design_spec.md`

#### Key Assumptions
1. **Dispersion Driven**: Cryptocurrency markets contain cross-sectional leader-laggard trends driven by capital flows.
2. **Rebalance Rotation**: Regularly rotating capital to top-ranked assets extracts structural momentum alpha.
3. **Friction Inclusion**: High turnover necessitates modeling hyper-realistic fees ($0.045\%$ taker) and slippage ($0.05\%$).

#### Locked Hypotheses
* **Long-Only**: Positions are restricted to long direction.
* **No Indicator Stacking**: Indicators such as EMA, RSI, Bollinger Bands, Volume, and ADX are systematically banned during the Discovery sweeps.
* **Closed Candle Execution**: Calculations occur strictly on the close of candle $t$; orders execute at the open of candle $t+1$.
* **Fixed Universe**: Fixed to the 25 specified crypto assets.

#### Outstanding Questions
1. How does the live paper trading engine replicate the 4H rebalance timing under websocket connectivity?
2. Can Version 2 design (volatility-adjusted ranking and regime filtering) successfully restrict drawdown to under 30%?

#### Decision
`READY_FOR_PAPER_TRADING` (Promoted configuration C001-E00077 to Paper Trading with a reduced capital allocation of 10% - 15% due to its borderline 53-63% drawdowns, after passing all other final validation pipeline stages).


---

## Candidate 02: Volatility Contraction Pattern (VCP)

### Current Status (Version 1)
* **Current Stage**: Pareto Analysis
* **Current Status**: `COMPLETED` (Completed Multi-Objective Pareto Analysis comparing V1, V2, and V3 configurations)
* **Last Updated**: 2026-06-30

### Current Status (Version 2)
* **Current Stage**: Stage 2 — Discovery Sweep (V2)
* **Current Status**: `ARCHIVED` (V2 Discovery sweep complete; winner was TF=4H, SW=7; archived in favor of V3)
* **Last Updated**: 2026-06-30

### Current Status (Version 3)
* **Current Stage**: Stage 2 — Discovery Sweep (V3)
* **Current Status**: `COMPLETED` (V3 Discovery sweep complete; winner is TF=4H, Waves=3)
* **Last Updated**: 2026-06-30

---

### Key Information

#### Documents Created
* `research/candidate_02_vcp/vcp_research_spec.md`
* `research/candidate_02_vcp/objective_definition.md`
* `research/candidate_02_vcp/parameter_space.md`
* `research/candidate_02_vcp/candidate_variants.md`
* `research/candidate_02_vcp/reports/hardware_optimization_report.md`
* `research/candidate_02_vcp/reports/checkpoint_spec.md`
* `research/candidate_02_vcp/reports/resume_validation.md`

#### Key Assumptions
1. **Volatility Compression**: Consolidations in strong uptrends absorb selling pressure, leading to volatility compression before price expansion.
2. **Breakout Catalyst**: Price breakout above the consolidation resistance marks the entry of aggressive momentum buyers.
3. **Asymmetric Risk**: Entering at the apex of contraction allows placing very tight stops, maximizing risk-to-reward ratio.

#### Locked Hypotheses
* **Long-Only**: Positions are restricted to the long direction.
* **Stage 2 Trend Gate**: Trades are only taken in assets whose prices are in a structural uptrend (e.g. above EMA 200).
* **Two-Wave Price Contraction**: Version 1 requires exactly two successive price pullback waves with decreasing depths ($D_2 < D_1$).

#### Outstanding Questions
1. How does the swing detection algorithm handle high-frequency tick noise in crypto markets on lower timeframes (e.g., 15m)?
2. Will volume contraction significantly reduce false breakouts in crypto perp markets, or does it overly restrict trade count?

#### Decision
`UNDER_REVIEW` (Deliverables created. Recommending V1 price-action swing contraction model with simple exits for discovery approval).

---


## QRP Framework v2.0 (Universal Discovery Engine)

### Current Status
* **Current Stage**: Framework Stage 0.5 — Universal Configuration & Experiment System
* **Current Status**: `COMPLETED` (Framework Configuration Approved / Architecture Stable)
* **Last Updated**: 2026-06-27

---

### Key Information

#### Documents Created
* **Architecture Docs**:
  * `research_engine/docs/discovery_engine_architecture.md`
  * `research_engine/docs/framework_design.md`
  * `research_engine/docs/plugin_specification.md`
  * `research_engine/docs/experiment_lifecycle.md`
  * `research_engine/docs/implementation_plan.md`
  * `research_engine/docs/configuration_architecture.md`
  * `research_engine/docs/configuration_schema.md`
  * `research_engine/docs/experiment_generation.md`
  * `research_engine/docs/configuration_validation.md`
  * `research_engine/docs/future_extension.md`
* **Configuration Files**:
  * `research_engine/configs/framework_config.yaml`
  * `research_engine/configs/candidate_template.yaml`
  * `research_engine/configs/experiment_template.yaml`
  * `research_engine/configs/validation_rules.yaml`

#### Skeletons Exposed
* `research_engine/core/strategy_interface.py`
* `research_engine/core/discovery_engine.py`
* `research_engine/core/experiment_manager.py`
* `research_engine/core/metrics_engine.py`
* `research_engine/core/reporting.py`
* `research_engine/core/logger.py`
* `research_engine/core/experiment_registry.py`
* `research_engine/core/candidate_dashboard.py`

#### Key Architectural Principles
1. **Strategy Agnostic**: The core engine loads plugins, executes loops, compiles metrics, and reports without knowledge of specific indicator logic or entry/exit rules.
2. **Standardized Re-producibility**: Every execution generates a structured manifest (`C{ID}-E{ID}`) containing git commit hash, configuration, timeframe, universe, and parameters to ensure complete path reproduction.
3. **Multi-Asset Interface Compatibility**: The framework must natively process data and execute simulations for Crypto, Equities, and Commodities without structural modifications.
4. **Configuration-Driven Execution**: No engine code is modified to run new strategies; execution is driven entirely by declarative plugins and YAML sheets.

#### Outstanding Items
1. Candidate C001 (Relative Strength) plugin implementation in code
2. Candidate C001 discovery execution sweeps

#### Decision
`Framework Configuration Approved` (Framework architecture is stable. Development is paused. Future work will focus on candidate plugin execution).

---

### Research Log

| Date | Candidate | Stage | Status | Documents Created | Decision / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-06-27 | Candidate 01 | Stage 1: Spec | `COMPLETED` | `README.md`, `hypothesis.md`, `research_spec.md` | Research folder structure and hypothesis approved. |
| 2026-06-27 | Candidate 01 | Stage 2: Signal Spec | `COMPLETED` | `signal_design_spec.md` | Completed Signal Design Specification. READY FOR STAGE 3. |
| 2026-06-27 | QRP Framework v2.0 | Stage 0: Architecture | `COMPLETED` | docs/discovery_engine_architecture.md, docs/framework_design.md, docs/plugin_specification.md, docs/experiment_lifecycle.md, docs/implementation_plan.md, core/ strategy_interface.py, core/discovery_engine.py, etc. | Core interface and architecture skeletons finalized and approved. |
| 2026-06-27 | QRP Framework v2.0 | Stage 0.5: Config | `COMPLETED` | configs/framework_config.yaml, configs/candidate_template.yaml, configs/experiment_template.yaml, configs/validation_rules.yaml, docs/configuration_architecture.md, docs/configuration_schema.md, docs/experiment_generation.md, docs/configuration_validation.md, docs/future_extension.md | Universal Configuration System and Experiment Sweep Generation designed and locked. Framework architecture approved as stable. |
| 2026-06-27 | Candidate 01 | Sprint 1: Verification | `COMPLETED` | outputs/trade_log.csv, outputs/portfolio_equity.csv, outputs/experiment_summary.csv, outputs/metrics.json, reports/experiment_report.md, logs/experiment.log, manifest/experiment_manifest.json | Verification experiment C001-E0001 completed successfully. Framework components function correctly. Strategy shows high turnover friction. READY FOR SPRINT 2. |
| 2026-06-27 | Candidate 01 | Sprint 1.5: Audit | `COMPLETED` | audit_report.md | Analysis of C001-E0001 complete. Extreme trading cost friction identified (fees and slippage = 2.5x initial capital). A negative equity bug was discovered in the framework. READY FOR SPRINT 2 (post framework bug fix). |
| 2026-06-27 | QRP Framework v2.0.1 | Framework Safety Patch | `COMPLETED` | docs/framework_bugfix_report.md, docs/regression_test_report.md, docs/verification_comparison.md, tests/test_regression.py | Safeguards for negative equity and NaN accounting implemented. Trade ledger matching corrected. All regression tests passing. READY_FOR_DISCOVERY_MATRIX. |
| 2026-06-27 | Candidate 01 | Sprint 2: Discovery | `READY_FOR_WALK_FORWARD_SELECTION` | outputs/discovery_matrix_results.csv, outputs/ranked_candidates.csv, reports/candidate_summary.md, reports/discovery_analysis.md | Executed 81-configuration sweep. The strategy is viable on 4H (Sharpe up to 2.04) but suffers from high drawdowns (60-90%). 15m and 1H timeframes are rejected due to transaction fee drag. Two configurations promote as BORDERLINE. |
| 2026-06-27 | Candidate 01 | Stage 3: Walk-Forward | `READY_FOR_FINAL_HOLDOUT` | validation/walk_forward/walk_forward_results.csv, validation/walk_forward/walk_forward_equity.csv, validation/walk_forward/walk_forward_summary.md, validation/walk_forward/walk_forward_report.md | Validated configuration C001-E00077. The discovery edge survived Walk-Forward testing with out-of-sample Sharpe ratios of 1.08 (Holdout 1) and 1.69 (Holdout 2), and no evidence of overfitting. Drawdowns of 53-63% trigger a BORDERLINE classification. |
| 2026-06-27 | Candidate 01 | Stages 5-9: Validation | `READY_FOR_PAPER_TRADING` | validation/final_validation/final_holdout_results.csv, validation/final_validation/event_simulation_report.md, validation/final_validation/monte_carlo_report.md, validation/final_validation/portfolio_correlation_report.md, validation/final_validation/production_readiness_report.md | Executed Stage 5 to 9 validation. Holdout Sharpe of 1.69, event-driven comparison proves fee/slippage expectancy, Monte Carlo shows ruin probability of 4.98%, daily correlation to production strategies is very low (<0.21), providing significant diversification benefits. Promoted to Paper Trading. |
| 2026-06-29 | Candidate 02 | Stage 1: Spec | `UNDER_REVIEW` | `vcp_research_spec.md`, `objective_definition.md`, `parameter_space.md`, `candidate_variants.md` | Recommending V1 price-action swing contraction model with simple exits for discovery approval. |
| 2026-06-30 | Candidate 02 | Stage 2: Discovery Sweep | `COMPLETED` | outputs/discovery_matrix_results.csv, outputs/ranked_candidates.csv, reports/candidate_summary.md, reports/discovery_analysis.md | Discovery matrix sweep completed successfully. READY_FOR_WALK_FORWARD_SELECTION. |
| 2026-06-30 | Candidate 02 | Stage 2: Discovery Audit | `COMPLETED` | reports/discovery_audit.md | Completed statistical discovery audit. 58 pass, 1,032 borderline configurations. Recommended promotion to Walk-Forward out-of-sample testing. |
| 2026-06-30 | Candidate 02 | Stage 3: Walk-Forward | `VALIDATION_FAILED` | walk_forward/walk_forward_results.csv, walk_forward/walk_forward_equity.csv, walk_forward/walk_forward_summary.md, walk_forward/walk_forward_report.md | Walk-forward validation failed for configuration C002-E04426 due to insufficient trade counts (<30) in Selection and Holdout 2. Strategy is rejected. |
| 2026-06-30 | Candidate 02 V2 | Stage 2: Discovery Sweep | `ARCHIVED` | candidate_02_vcp_v2/outputs/discovery_matrix_results.csv, candidate_02_vcp_v2/outputs/ranked_candidates.csv, candidate_02_vcp_v2/reports/candidate_summary.md | Executed 6-experiment V2 parameter sweep varying swing window [3, 5, 7] on 1H/4H. Winner was 4H, SW=7 (V1 Baseline). Archived in favor of V3. |
| 2026-06-30 | Candidate 02 V3 | Stage 2: Discovery Sweep | `COMPLETED` | candidate_02_vcp_v3/outputs/discovery_matrix_results.csv, candidate_02_vcp_v3/outputs/ranked_candidates.csv, candidate_02_vcp_v3/reports/candidate_summary.md | Executed 6-experiment V3 parameter sweep varying contraction waves [2, 3, "adaptive"] on 1H/4H. Winner is 4H, Waves=3 (control). Adaptive waves generated 288 trades with Sharpe 0.85. |
| 2026-06-30 | Candidate 02 | Pareto Analysis | `COMPLETED` | candidate_02_vcp/reports/pareto_analysis.md | Conducted multi-objective Pareto Frontier analysis across V1, V2, and V3 sweeps. Proposed a revised V2 Quality Score to prevent Profit Factor distortion and reward trade density. |

