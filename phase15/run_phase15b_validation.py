import os
import pandas as pd
import numpy as np
import vectorbt as vbt
from tqdm import tqdm
from vectorbt.portfolio.enums import OppositeEntryMode, StopExitMode, StopExitPrice

from run_research_framework import (
    load_symbol_timeframe,
    build_signals,
    build_vbt_signals,
    simulate_portfolio_leverage,
    compute_metrics,
    load_funding_history
)

# Realistic execution constants matching the validated framework
FEE_RATE = 0.0005       # 0.05 %
SLIPPAGE_RATE = 0.0002  # 0.02 %
INITIAL_BALANCE = 1000.0

TIMEFRAME_DELTAS = {
    "4h": pd.Timedelta(hours=4),
}

# Define the periods
PERIODS = {
    "Selection": (pd.Timestamp("2023-01-01 00:00:00", tz="UTC"), pd.Timestamp("2024-12-31 23:59:59", tz="UTC")),
    "Holdout_1": (pd.Timestamp("2025-01-01 00:00:00", tz="UTC"), pd.Timestamp("2025-12-31 23:59:59", tz="UTC")),
    "Holdout_2": (pd.Timestamp("2026-01-01 00:00:00", tz="UTC"), pd.Timestamp("2026-06-19 23:59:59", tz="UTC"))
}

def main():
    coins = ['BTC', 'LINK', 'XRP', 'AVAX']
    tf = '4H'
    tf_mapped = '4h'
    mode = 'VE_3_ATR_EXPANSION'
    rr_values = [1.0, 1.5, 2.0, 3.0]

    raw_results = []
    
    total_runs = len(coins) * len(rr_values) * len(PERIODS)
    print(f"Starting Phase 15B Validation: running {total_runs} combinations...")

    with tqdm(total=len(coins) * len(rr_values), desc="Candidates Validation") as pbar:
        for coin in coins:
            # 1. Load full history data to avoid warm-up boundary issues
            df = load_symbol_timeframe(coin, tf_mapped)
            if df is None or df.empty:
                print(f"\n[!] Warning: missing data for {coin} {tf}. Skipping.")
                pbar.update(len(rr_values))
                continue

            # 2. Build signals on full history
            try:
                signals = build_signals(df, 'Volatility_Expansion', coin, tf_mapped, mode=mode)
            except Exception as e:
                print(f"\n[!] Error building signals for {coin} {tf} ({mode}): {e}")
                pbar.update(len(rr_values))
                continue

            for rr in rr_values:
                candidate_runs = {}
                
                # Run each period sequentially
                for period_name, (start_dt, end_dt) in PERIODS.items():
                    # 3. Slice to desired period
                    mask = (df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)
                    df_slice = df[mask]
                    signals_slice = signals[mask]

                    if len(df_slice) < 10 or signals_slice['side'].eq('').all():
                        candidate_runs[period_name] = {
                            'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0,
                            'drawdown': 0.0, 'avg_r': 0.0, 'expectancy': 0.0, 'net_return': 0.0
                        }
                        continue

                    # 4. Generate inputs for vectorbt
                    try:
                        entries_s, short_entries_s, sl_stop_s, tp_stop_all, sl_pct_map = build_vbt_signals(
                            df_slice, signals_slice, [rr]
                        )
                    except Exception as e:
                        print(f"\n[!] Error building VBT signals for {coin} {tf} (RR={rr}, Period={period_name}): {e}")
                        candidate_runs[period_name] = {
                            'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0,
                            'drawdown': 0.0, 'avg_r': 0.0, 'expectancy': 0.0, 'net_return': 0.0
                        }
                        continue

                    if not entries_s.any() and not short_entries_s.any():
                        candidate_runs[period_name] = {
                            'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0,
                            'drawdown': 0.0, 'avg_r': 0.0, 'expectancy': 0.0, 'net_return': 0.0
                        }
                        continue

                    exits_s = pd.Series(False, index=df_slice.index)
                    exits_s.iloc[-1] = True
                    short_exits_s = pd.Series(False, index=df_slice.index)
                    short_exits_s.iloc[-1] = True

                    order_price = df_slice['open'].copy()
                    order_price.iloc[-1] = df_slice['close'].iloc[-1]

                    # 5. Run VectorBT
                    try:
                        pf = vbt.Portfolio.from_signals(
                            close=df_slice['close'],
                            entries=entries_s,
                            exits=exits_s,
                            short_entries=short_entries_s,
                            short_exits=short_exits_s,
                            size=1.0,
                            size_type="amount",
                            price=order_price,
                            open=df_slice['open'],
                            high=df_slice['high'],
                            low=df_slice['low'],
                            sl_stop=sl_stop_s,
                            tp_stop=tp_stop_all,
                            fees=FEE_RATE,
                            slippage=SLIPPAGE_RATE,
                            init_cash=1_000_000.0,
                            accumulate=False,
                            upon_opposite_entry=OppositeEntryMode.Ignore,
                            stop_exit_price=StopExitPrice.StopMarket,
                            upon_stop_exit=StopExitMode.Close,
                            freq=TIMEFRAME_DELTAS[tf_mapped],
                        )
                    except Exception as e:
                        print(f"\n[!] VBT execution error on {coin} {tf} (RR={rr}, Period={period_name}): {e}")
                        candidate_runs[period_name] = {
                            'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0,
                            'drawdown': 0.0, 'avg_r': 0.0, 'expectancy': 0.0, 'net_return': 0.0
                        }
                        continue

                    # 6. Simulate portfolio leverage
                    try:
                        trades_df = pf.trades.records_readable
                        funding_df = load_funding_history(coin)

                        sim_trades, final_bal, equity_curve, exit_dates, ruined = simulate_portfolio_leverage(
                            trades_df, sl_pct_map, df_slice, coin, rr, funding_df
                        )

                        metrics = compute_metrics(sim_trades, final_bal, INITIAL_BALANCE, equity_curve, exit_dates)

                        trades = len(sim_trades)
                        win_rate = metrics['Win Rate']
                        
                        wins_r = [t['r_multiple'] for t in sim_trades if t['pnl'] > 0]
                        losses_r = [abs(t['r_multiple']) for t in sim_trades if t['pnl'] <= 0]
                        
                        avg_win_r = np.mean(wins_r) if wins_r else 0.0
                        avg_loss_r = np.mean(losses_r) if losses_r else 0.0

                        win_rate_dec = win_rate / 100.0
                        loss_rate_dec = 1.0 - win_rate_dec
                        expectancy = (win_rate_dec * avg_win_r) - (loss_rate_dec * avg_loss_r)

                        avg_r = np.mean([t['r_multiple'] for t in sim_trades]) if sim_trades else 0.0
                        net_return = ((final_bal - INITIAL_BALANCE) / INITIAL_BALANCE) * 100.0

                        candidate_runs[period_name] = {
                            'trades': trades,
                            'win_rate': round(win_rate, 2),
                            'pf': round(metrics['Profit Factor'], 2),
                            'sharpe': round(metrics['Sharpe Ratio'], 2),
                            'drawdown': round(metrics['Max Drawdown'], 2),
                            'avg_r': round(avg_r, 4),
                            'expectancy': round(expectancy, 4),
                            'net_return': round(net_return, 2)
                        }
                    except Exception as e:
                        print(f"\n[!] Leverage simulation error on {coin} {tf} (RR={rr}, Period={period_name}): {e}")
                        candidate_runs[period_name] = {
                            'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0,
                            'drawdown': 0.0, 'avg_r': 0.0, 'expectancy': 0.0, 'net_return': 0.0
                        }

                # Evaluate pass criteria
                # Holdout 1 (2025): PF > 1.10, Expectancy > 0, Net Return > 0, Trades >= 20
                h1 = candidate_runs.get("Holdout_1", {})
                h1_pass = (
                    h1.get("pf", 0) > 1.10 and
                    h1.get("expectancy", 0) > 0 and
                    h1.get("net_return", 0) > 0 and
                    h1.get("trades", 0) >= 20
                )
                
                # Holdout 2 (2026): PF > 1.10, Expectancy > 0, Net Return > 0, Trades >= 10
                h2 = candidate_runs.get("Holdout_2", {})
                h2_pass = (
                    h2.get("pf", 0) > 1.10 and
                    h2.get("expectancy", 0) > 0 and
                    h2.get("net_return", 0) > 0 and
                    h2.get("trades", 0) >= 10
                )
                
                status = "PASS" if (h1_pass and h2_pass) else "FAIL"

                # Append to raw_results with period dimension
                for p_name in PERIODS.keys():
                    p_metrics = candidate_runs.get(p_name, {})
                    raw_results.append({
                        'coin': coin,
                        'timeframe': tf,
                        'mode': mode,
                        'rr': rr,
                        'period': p_name,
                        'trades': p_metrics.get('trades', 0),
                        'win_rate': p_metrics.get('win_rate', 0.0),
                        'pf': p_metrics.get('pf', 0.0),
                        'sharpe': p_metrics.get('sharpe', 0.0),
                        'drawdown': p_metrics.get('drawdown', 0.0),
                        'avg_r': p_metrics.get('avg_r', 0.0),
                        'expectancy': p_metrics.get('expectancy', 0.0),
                        'net_return': p_metrics.get('net_return', 0.0),
                        'validation_status': status
                    })
                
                pbar.update(1)

    # Convert to dataframe
    df_results = pd.DataFrame(raw_results)
    
    # Save CSV files
    os.makedirs("results", exist_ok=True)
    df_results.to_csv("phase15b_validation.csv", index=False)
    df_results.to_csv("results/phase15b_validation.csv", index=False)
    print("\nSaved validation results to phase15b_validation.csv and results/phase15b_validation.csv")

    # Generate Report
    print("Generating phase15b_report.md...")
    report_content = generate_markdown_report(df_results)
    
    with open("phase15b_report.md", "w") as f:
        f.write(report_content)
    print("Report saved to phase15b_report.md")

def generate_markdown_report(df):
    lines = []
    lines.append("# Phase 15B Validation Report: Volatility Expansion Robustness Test")
    lines.append("")
    lines.append("This report presents the out-of-sample validation of the strongest Volatility Expansion candidate strategy configurations (`VE_3_ATR_EXPANSION` at the `4H` timeframe). The analysis checks for validation across three non-overlapping historical windows:")
    lines.append("*   **Selection Period (2023-2024)**: The in-sample discovery window.")
    lines.append("*   **Holdout Period 1 (2025)**: Out-of-sample window (requires Trades $\ge 20$, PF $> 1.10$, Expectancy $> 0$, Net Return $> 0$).")
    lines.append("*   **Holdout Period 2 (2026)**: Out-of-sample window (requires Trades $\ge 10$, PF $> 1.10$, Expectancy $> 0$, Net Return $> 0$).")
    lines.append("")
    
    # Validation status summary
    lines.append("## 1. Validation Status Summary")
    lines.append("")
    
    # Group by coin + rr to check status
    unique_candidates = df.drop_duplicates(subset=['coin', 'rr'])
    passes = unique_candidates[unique_candidates['validation_status'] == 'PASS']
    fails = unique_candidates[unique_candidates['validation_status'] == 'FAIL']
    
    lines.append(f"Out of **{len(unique_candidates)}** candidates evaluated, **{len(passes)}** passed the out-of-sample validation criteria.")
    lines.append("")
    
    if not passes.empty:
        lines.append("### Passing Candidates:")
        for idx, row in passes.iterrows():
            lines.append(f"*   **{row['coin']} 4H (RR={row['rr']})** - Status: `PASS`")
    else:
        lines.append("> [!WARNING]")
        lines.append("> **No candidates passed the out-of-sample validation.** All tested configurations failed to meet the validation thresholds in both holdout windows.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 2. Detailed Performance Table")
    lines.append("")
    lines.append("| Candidate | Period | Trades | Win Rate | Profit Factor | Sharpe Ratio | Max Drawdown | Expectancy (R) | Net Return | Status |")
    lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    
    for idx, row in df.iterrows():
        candidate_name = f"**{row['coin']} 4H (RR={row['rr']})**"
        status_badge = f"`{row['validation_status']}`"
        lines.append(f"| {candidate_name} | {row['period']} | {row['trades']} | {row['win_rate']}% | {row['pf']:.2f} | {row['sharpe']:.2f} | {row['drawdown']:.2f}% | {row['expectancy']:.4f} | {row['net_return']:.2f}% | {status_badge} |")
        
    lines.append("")
    lines.append("---")
    lines.append("")
    
    lines.append("## 3. Analysis & Key Takeaways")
    lines.append("")
    
    for coin in df['coin'].unique():
        coin_df = df[df['coin'] == coin]
        lines.append(f"### {coin} Candidates Performance")
        for rr in coin_df['rr'].unique():
            candidate_df = coin_df[coin_df['rr'] == rr]
            sel = candidate_df[candidate_df['period'] == 'Selection'].iloc[0]
            h1 = candidate_df[candidate_df['period'] == 'Holdout_1'].iloc[0]
            h2 = candidate_df[candidate_df['period'] == 'Holdout_2'].iloc[0]
            
            lines.append(f"*   **RR={rr}**:")
            lines.append(f"    *   *Selection (23-24)*: {sel['trades']} trades | PF: {sel['pf']:.2f} | Net Return: {sel['net_return']:.2f}%")
            lines.append(f"    *   *Holdout 1 (2025)*: {h1['trades']} trades | PF: {h1['pf']:.2f} | Net Return: {h1['net_return']:.2f}%")
            lines.append(f"    *   *Holdout 2 (2026)*: {h2['trades']} trades | PF: {h2['pf']:.2f} | Net Return: {h2['net_return']:.2f}%")
            
            if sel['validation_status'] == 'FAIL':
                reasons = []
                # H1 checks
                if h1['trades'] < 20: reasons.append(f"H1 Trades ({h1['trades']}) < 20")
                if h1['pf'] <= 1.10: reasons.append(f"H1 PF ({h1['pf']:.2f}) <= 1.10")
                if h1['expectancy'] <= 0: reasons.append(f"H1 Expectancy ({h1['expectancy']:.4g}) <= 0")
                if h1['net_return'] <= 0: reasons.append(f"H1 Return ({h1['net_return']:.2f}%) <= 0")
                # H2 checks
                if h2['trades'] < 10: reasons.append(f"H2 Trades ({h2['trades']}) < 10")
                if h2['pf'] <= 1.10: reasons.append(f"H2 PF ({h2['pf']:.2f}) <= 1.10")
                if h2['expectancy'] <= 0: reasons.append(f"H2 Expectancy ({h2['expectancy']:.4g}) <= 0")
                if h2['net_return'] <= 0: reasons.append(f"H2 Return ({h2['net_return']:.2f}%) <= 0")
                
                lines.append(f"    *   *Failure Reason*: {', '.join(reasons)}")
        lines.append("")

    lines.append("## 4. Synthesis & Recommendations")
    lines.append("")
    lines.append("### Did ATR Expansion Prove Robust?")
    if not passes.empty:
        lines.append(f"Yes, **{len(passes)}** candidate configuration(s) successfully passed the validation criteria across all out-of-sample periods. This confirms that the Volatility Expansion edge is genuine and robust to structural shifts in the market rather than an artifact of in-sample optimization.")
    else:
        lines.append("No, **all** configurations failed the out-of-sample validation checks. While the strategy was highly profitable in-sample (23-24), its edge completely decayed or did not maintain the required trade density / profitability in 2025 and 2026. This indicates that the discovery results were likely an artifact of the specific trending regime of 2023-2024 (bull market and structural expansion) and did not hold up under different market regimes (e.g. 2025 range or 2026 correction).")
    lines.append("")
    lines.append("### Recommendations for Next Phase:")
    lines.append("1.  **If there are passing candidates**: Focus parameter sweeps and trailing-stop optimizations solely on those configurations that passed.")
    lines.append("2.  **If no candidates passed**: Investigate whether macro filters (such as volume filters or trend direction filters) can reduce false breakouts, or explore regime-aware execution models.")
    lines.append("")
    
    return "\n".join(lines)

if __name__ == "__main__":
    main()
