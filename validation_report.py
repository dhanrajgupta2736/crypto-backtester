import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Expected Metrics (Baseline Research)
EXP_PF = 1.79
EXP_WR = 40.74
EXP_SHARPE = 1.96
EXP_MAX_DD = 21.94
RISK_PER_TRADE_PCT = 0.02

# Paths
LIVE_LOG_PATH = os.path.join("results", "live_trades.csv")
PAPER_LOG_PATH = os.path.join("results", "paper_trades.csv")
OLD_LOG_PATH = os.path.join("results", "paper_trade_log.csv")
REPORT_JSON_PATH = os.path.join("results", "validation_report.json")
CHART_PATH = os.path.join("results", "equity_comparison.png")

def load_log():
    # Prioritize live trades, then paper trades, then old log path
    log_path = None
    for path in [LIVE_LOG_PATH, PAPER_LOG_PATH, OLD_LOG_PATH]:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            log_path = path
            break
            
    if log_path is None:
        return None
        
    try:
        df = pd.read_csv(log_path)
        print(f"Reading trade records from: {log_path}")
        return df
    except Exception as e:
        print(f"Error reading trade log {log_path}: {e}")
        return None


def normalize_columns(df):
    df = df.copy()
    col_map = {}
    for col in df.columns:
        c_clean = col.lower().replace(" ", "").replace("_", "")
        col_map[c_clean] = col
        
    norm_df = pd.DataFrame()
    
    # 1. Exit Timestamp
    ts_col = col_map.get("timestamp") or col_map.get("exittimestamp")
    if ts_col:
        norm_df["timestamp"] = pd.to_datetime(df[ts_col])
    else:
        norm_df["timestamp"] = pd.date_range(start="2026-01-01", periods=len(df), freq="h")
        
    # 2. Symbol
    sym_col = col_map.get("symbol")
    if sym_col:
        norm_df["symbol"] = df[sym_col].astype(str)
    else:
        norm_df["symbol"] = "TAO"
        
    # 3. Side / Direction
    side_col = col_map.get("side") or col_map.get("direction")
    if side_col:
        norm_df["side"] = df[side_col].astype(str).str.lower()
    else:
        norm_df["side"] = "long"
        
    # 4. Entry
    entry_col = col_map.get("entry") or col_map.get("entryprice")
    if entry_col:
        norm_df["entry"] = df[entry_col].astype(float)
    else:
        norm_df["entry"] = 100.0
        
    # 5. Stop
    stop_col = col_map.get("stop") or col_map.get("stoploss")
    if stop_col:
        norm_df["stop"] = df[stop_col].astype(float)
    else:
        norm_df["stop"] = 95.0
        
    # 6. Target / Take Profit
    target_col = col_map.get("target") or col_map.get("takeprofit")
    if target_col:
        norm_df["target"] = df[target_col].astype(float)
    else:
        norm_df["target"] = 115.0
        
    # 7. Exit
    exit_col = col_map.get("exit") or col_map.get("exitprice")
    if exit_col:
        norm_df["exit"] = df[exit_col].astype(float)
    else:
        norm_df["exit"] = 100.0
        
    # 8. PnL
    pnl_col = col_map.get("pnl") or col_map.get("tradepnl")
    if pnl_col:
        norm_df["pnl"] = df[pnl_col].astype(float)
    else:
        norm_df["pnl"] = 0.0
        
    # 9. Equity After
    bal_col = col_map.get("equityafter") or col_map.get("accountbalance")
    if bal_col:
        norm_df["equity_after"] = df[bal_col].astype(float)
    else:
        norm_df["equity_after"] = 10000.0 + norm_df["pnl"].cumsum()
        
    # 10. Equity Before
    eb_col = col_map.get("equitybefore")
    if eb_col:
        norm_df["equity_before"] = df[eb_col].astype(float)
    else:
        norm_df["equity_before"] = norm_df["equity_after"] - norm_df["pnl"]
        
    # 11. Fees
    fees_col = col_map.get("fees") or col_map.get("feespaid")
    if fees_col:
        norm_df["fees"] = df[fees_col].astype(float)
    else:
        norm_df["fees"] = 0.0
        
    # 12. Slippage
    slip_col = col_map.get("slippage") or col_map.get("slippagecost")
    if slip_col:
        norm_df["slippage"] = df[slip_col].astype(float)
    else:
        norm_df["slippage"] = 0.0
        
    # 13. Strategy Version
    ver_col = col_map.get("strategyversion")
    if ver_col:
        norm_df["strategy_version"] = df[ver_col].astype(str)
    else:
        norm_df["strategy_version"] = "v1.0"
        
    # 14. R-Multiple
    r_col = col_map.get("rmultiple")
    if r_col:
        norm_df["r_multiple"] = df[r_col].astype(float)
    else:
        r_list = []
        for idx, row in norm_df.iterrows():
            entry = row["entry"]
            stop = row["stop"]
            exit_p = row["exit"]
            side = row["side"]
            
            p_dist = abs(entry - stop)
            if p_dist > 0:
                p_r = (exit_p - entry) / p_dist if side in ("long", "l") else (entry - exit_p) / p_dist
            else:
                p_r = 0.0
            r_list.append(p_r)
        norm_df["r_multiple"] = r_list
        
    return norm_df

def get_max_consecutive_losses(pnl_series):
    max_streak = 0
    current_streak = 0
    for pnl in pnl_series:
        if pnl <= 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    return max_streak

def calculate_sharpe(df_trades, start_equity=10000.0):
    if len(df_trades) < 2:
        return 0.0
    
    df_trades = df_trades.copy()
    df_trades["date"] = df_trades["timestamp"].dt.normalize()
    
    daily_balances = df_trades.groupby("date")["equity_after"].last()
    first_date = daily_balances.index.min()
    prev_date = first_date - pd.Timedelta(days=1)
    daily_balances[prev_date] = start_equity
    daily_balances = daily_balances.sort_index()
    
    all_dates = pd.date_range(start=daily_balances.index.min(), end=daily_balances.index.max(), freq="D")
    daily_balances = daily_balances.reindex(all_dates).ffill()
    
    daily_returns = daily_balances.pct_change().dropna()
    if daily_returns.empty or daily_returns.std() == 0:
        return 0.0
    
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    return round(float(sharpe), 4)

def calculate_max_drawdown(equity_series):
    if len(equity_series) == 0:
        return 0.0
    eq = pd.Series(equity_series)
    cummax = eq.cummax()
    dd = (eq - cummax) / cummax * 100
    return round(float(dd.min()), 2)

def get_subset_metrics(df, n_trades=None, start_equity=10000.0):
    if df is None or len(df) == 0:
        return None
        
    if n_trades is not None:
        df_sub = df.tail(n_trades).copy()
    else:
        df_sub = df.copy()
        
    trade_count = len(df_sub)
    if trade_count == 0:
        return None
        
    wins = df_sub[df_sub["pnl"] > 0]["pnl"]
    losses = df_sub[df_sub["pnl"] <= 0]["pnl"]
    
    win_rate = len(wins) / trade_count * 100
    pf = sum(wins) / abs(sum(losses)) if len(losses) > 0 else (99.9 if sum(wins) > 0 else 0.0)
    
    avg_r = df_sub["r_multiple"].mean()
    consec_losses = get_max_consecutive_losses(df_sub["pnl"].values)
    
    # Drawdown & Sharpe
    equities = df_sub["equity_after"].tolist()
    if n_trades is not None and len(df) > n_trades:
        # Starting equity for drawdown should be the equity before this block started
        idx_before = len(df) - n_trades - 1
        equity_before = df["equity_after"].iloc[idx_before]
    else:
        equity_before = start_equity
        
    equity_curve = [equity_before] + equities
    max_dd = calculate_max_drawdown(equity_curve)
    
    sharpe = calculate_sharpe(df_sub, equity_before)
    
    return {
        "trade_count": trade_count,
        "win_rate": round(win_rate, 2),
        "profit_factor": round(pf, 4),
        "avg_r": round(avg_r, 4),
        "max_drawdown_pct": abs(max_dd),
        "sharpe": round(sharpe, 4),
        "consecutive_losses": consec_losses
    }

def generate_comparison(metrics):
    if metrics is None:
        return {}
        
    # Sizing dynamic compounding warning check
    # Check metric drift from research
    pf_drift = (EXP_PF - metrics["profit_factor"]) / EXP_PF * 100
    wr_drift = (EXP_WR - metrics["win_rate"]) / EXP_WR * 100
    sharpe_drift = (EXP_SHARPE - metrics["sharpe"]) / EXP_SHARPE * 100
    dd_drift = (metrics["max_drawdown_pct"] - EXP_MAX_DD)  # absolute difference
    
    # Establish Alerts
    alerts = {}
    
    # Win Rate Alert
    if wr_drift <= 5.0:
        alerts["win_rate"] = "GREEN"
    elif wr_drift <= 15.0:
        alerts["win_rate"] = "YELLOW"
    else:
        alerts["win_rate"] = "RED"
        
    # Profit Factor Alert
    if pf_drift <= 15.0:
        alerts["profit_factor"] = "GREEN"
    elif pf_drift <= 35.0:
        alerts["profit_factor"] = "YELLOW"
    else:
        alerts["profit_factor"] = "RED"
        
    # Sharpe Alert
    if sharpe_drift <= 25.0:
        alerts["sharpe"] = "GREEN"
    elif sharpe_drift <= 50.0:
        alerts["sharpe"] = "YELLOW"
    else:
        alerts["sharpe"] = "RED"
        
    # Drawdown Alert
    if dd_drift <= 0.0:
        alerts["max_drawdown"] = "GREEN"
    elif dd_drift <= 10.0:
        alerts["max_drawdown"] = "YELLOW"
    else:
        alerts["max_drawdown"] = "RED"
        
    # Overall status
    if "RED" in alerts.values():
        overall = "RED"
    elif "YELLOW" in alerts.values():
        overall = "YELLOW"
    else:
        overall = "GREEN"
        
    # Force Yellow warning if sample size is too low for statistical confidence
    if metrics["trade_count"] < 15:
        overall = "YELLOW"
        alerts["sample_size"] = "YELLOW (Low Sample Size Confidence)"
        
    return {
        "overall_status": overall,
        "alerts": alerts,
        "drifts": {
            "pnl_pf_drift_pct": round(pf_drift, 2),
            "win_rate_drift_pct": round(wr_drift, 2),
            "sharpe_drift_pct": round(sharpe_drift, 2),
            "drawdown_diff_pct": round(dd_drift, 2)
        }
    }

def estimate_confidence_intervals(win_rate, n):
    if n <= 0:
        return 0.0, 0.0
    p = win_rate / 100.0
    se = np.sqrt(p * (1 - p) / n)
    margin = 1.96 * se * 100
    ci_lower = max(0.0, win_rate - margin)
    ci_upper = min(100.0, win_rate + margin)
    return round(ci_lower, 2), round(ci_upper, 2)

def calculate_readiness_score(metrics, comparison):
    if metrics is None or comparison is None:
        return 0
        
    score = 0
    trade_count = metrics["trade_count"]
    pf = metrics["profit_factor"]
    wr = metrics["win_rate"]
    sharpe = metrics["sharpe"]
    max_dd = metrics["max_drawdown_pct"]
    
    # 1. Sample Size (Max 20 points)
    score += min(trade_count / 50 * 20, 20)
    
    # 2. Profit Factor (Max 30 points)
    if pf >= EXP_PF:
        score += 30
    elif pf >= 1.0:
        score += 10 + 20 * (pf - 1.0) / (EXP_PF - 1.0)
        
    # 3. Win Rate (Max 20 points)
    if wr >= EXP_WR:
        score += 20
    elif wr >= 25.0:
        score += 5 + 15 * (wr - 25.0) / (EXP_WR - 25.0)
        
    # 4. Sharpe Ratio (Max 15 points)
    if sharpe >= EXP_SHARPE:
        score += 15
    elif sharpe >= 0.5:
        score += 15 * (sharpe / EXP_SHARPE)
        
    # 5. Drawdown (Max 15 points)
    if max_dd <= EXP_MAX_DD:
        score += 15
    elif max_dd <= 35.0:
        score += 15 * (1 - (max_dd - EXP_MAX_DD) / (35.0 - EXP_MAX_DD))
        
    # Cap score at 50 if metrics are RED (statistically inconsistent)
    if comparison["overall_status"] == "RED":
        score = min(score, 50.0)
        
    return int(round(score))

def build_comparison_chart(df, start_equity=10000.0):
    if df is None or len(df) == 0:
        return
        
    # Normalizing curve
    paper_curve = [100.0]
    for eq in df["equity_after"]:
        paper_curve.append(eq / start_equity * 100.0)
        
    # Generate theoretical expected growth path (research benchmark baseline)
    # Expected return per trade = WR% * 3R + (100 - WR%) * -1R
    # With 40.74% WR, expected return per trade = 0.4074 * 3 - 0.5926 * 1 = 1.2222 - 0.5926 = +0.6296 R-multiple
    # Since risk is 2% per trade, expected compounding return rate is approx 0.6296 * 2% = 1.26% per trade
    expected_curve = [100.0]
    r_mult_expected = (EXP_WR / 100.0) * 3.0 - (1 - EXP_WR / 100.0) * 1.0
    comp_rate = r_mult_expected * RISK_PER_TRADE_PCT
    
    for i in range(len(df)):
        expected_curve.append(100.0 * ((1 + comp_rate) ** (i + 1)))
        
    # Plotting
    plt.figure(figsize=(10, 5))
    plt.plot(paper_curve, label="Actual Normalized Paper Equity (Compounding)", color="#00ffcc", linewidth=2.5)
    plt.plot(expected_curve, label="Expected Growth Path (Research Baseline)", color="#ff5555", linestyle="--", linewidth=2)
    
    plt.title("Paper Trading Equity vs. Research Growth Path", fontsize=12, fontweight="bold", pad=15)
    plt.xlabel("Trade Count", fontsize=10)
    plt.ylabel("Normalized Value (Base 100)", fontsize=10)
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="upper left")
    
    os.makedirs(os.path.dirname(CHART_PATH), exist_ok=True)
    plt.savefig(CHART_PATH, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Comparison chart exported successfully to {CHART_PATH}")

def main():
    print("=" * 80)
    print("  LIVE PAPER TRADING VALIDATION FRAMEWORK")
    print("=" * 80)
    
    df_raw = load_log()
    if df_raw is None or len(df_raw) == 0:
        print("[WARNING] No trade logs found. Generate validation report after execution.")
        return
        
    df = normalize_columns(df_raw)
    
    # Dynamically extract the correct starting equity
    start_equity = float(df["equity_after"].iloc[0] - df["pnl"].iloc[0])
    print(f"Loaded {len(df)} trades successfully from journal. Detected starting equity: ${start_equity:.2f}")
    
    # 1. Calculate Metrics for all subsets
    all_metrics = get_subset_metrics(df, n_trades=None, start_equity=start_equity)
    metrics_10 = get_subset_metrics(df, n_trades=10, start_equity=start_equity)
    metrics_20 = get_subset_metrics(df, n_trades=20, start_equity=start_equity)
    metrics_50 = get_subset_metrics(df, n_trades=50, start_equity=start_equity)
    
    # 2. Get comparison drifts and alerts for overall metrics
    comparison = generate_comparison(all_metrics)
    
    # 3. Win rate confidence intervals
    ci_lower, ci_upper = estimate_confidence_intervals(all_metrics["win_rate"], all_metrics["trade_count"])
    all_metrics["win_rate_95_confidence_interval"] = [ci_lower, ci_upper]
    
    # 4. Readiness Score
    readiness_score = calculate_readiness_score(all_metrics, comparison)
    
    # Assemble final report
    report = {
        "summary": {
            "validation_timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "readiness_score": readiness_score,
            "overall_status": comparison["overall_status"],
            "alerts": comparison["alerts"],
            "drifts": comparison["drifts"]
        },
        "rolling_statistics": {
            "all_trades": all_metrics,
            "last_10_trades": metrics_10,
            "last_20_trades": metrics_20,
            "last_50_trades": metrics_50
        }
    }
    
    # Save validation_report.json
    os.makedirs(os.path.dirname(REPORT_JSON_PATH), exist_ok=True)
    with open(REPORT_JSON_PATH, "w") as f:
        json.dump(report, f, indent=4)
    print(f"Validation report saved successfully to {REPORT_JSON_PATH}")
    
    # 5. Build comparison chart
    build_comparison_chart(df, start_equity=start_equity)
    
    # Print console summary
    print("\n" + "=" * 60)
    print("  VALIDATION SUMMARY REPORT")
    print("=" * 60)
    print(f"  Overall Status:  {comparison['overall_status']}")
    print(f"  Readiness Score: {readiness_score} / 100")
    print(f"  Trades Logged:   {all_metrics['trade_count']}")
    print("-" * 60)
    print(f"  Metric       | Expected  | Actual    | Alert Status")
    print("-" * 60)
    print(f"  Win Rate     | {EXP_WR:<9}% | {all_metrics['win_rate']:<9}% | {comparison['alerts']['win_rate']}")
    print(f"  Profit Factor| {EXP_PF:<9} | {all_metrics['profit_factor']:<9} | {comparison['alerts']['profit_factor']}")
    print(f"  Sharpe       | {EXP_SHARPE:<9} | {all_metrics['sharpe']:<9} | {comparison['alerts']['sharpe']}")
    print(f"  Max Drawdown | {EXP_MAX_DD:<9}% | {all_metrics['max_drawdown_pct']:<9}% | {comparison['alerts']['max_drawdown']}")
    print("-" * 60)
    print(f"  Win Rate 95% Confidence Interval: [{ci_lower}%, {ci_upper}%]")
    print("=" * 60)

if __name__ == "__main__":
    main()
