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
    "5m":  pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h":  pd.Timedelta(hours=1),
    "4h":  pd.Timedelta(hours=4),
    "1d":  pd.Timedelta(days=1),
}

def main():
    # Research universe definitions
    modes = ['RSI', 'BB', 'RSI_BB']
    coins = ['BTC', 'ETH', 'SOL', 'BNB', 'LINK', 'AVAX', 'XRP']
    timeframes = ['15m', '1H', '4H']
    rr_values = [1.0, 1.5, 2.0, 3.0]

    tf_mapping = {
        '15m': '15m',
        '1H': '1h',
        '4H': '4h'
    }

    # Slicing dates (full historical available dataset)
    start_dt = pd.Timestamp("2023-01-01 00:00:00", tz="UTC")
    end_dt = pd.Timestamp("2026-06-19 23:59:59", tz="UTC")

    results = []

    total_runs = len(modes) * len(coins) * len(timeframes) * len(rr_values)
    print(f"Starting Mean Reversion Discovery Scanner: running {total_runs} combinations...")

    with tqdm(total=total_runs, desc="Backtesting") as pbar:
        for mode in modes:
            for coin in coins:
                for tf in timeframes:
                    tf_mapped = tf_mapping[tf]
                    
                    # 1. Load data
                    df = load_symbol_timeframe(coin, tf_mapped)
                    if df is None or df.empty:
                        print(f"\n[!] Warning: missing data for {coin} {tf}. Skipping.")
                        pbar.update(len(rr_values))
                        continue

                    # 2. Build signals on full history to avoid warm-up issues
                    try:
                        signals = build_signals(df, 'Mean_Reversion', coin, tf_mapped, mode=mode)
                    except Exception as e:
                        print(f"\n[!] Error building signals for {coin} {tf} ({mode}): {e}")
                        pbar.update(len(rr_values))
                        continue

                    # 3. Slice to desired period
                    mask = (df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)
                    df_slice = df[mask]
                    signals_slice = signals[mask]

                    if len(df_slice) < 50 or signals_slice['side'].eq('').all():
                        # Record blank results for this asset combo across all RR
                        for rr in rr_values:
                            results.append({
                                'strategy': 'Mean_Reversion',
                                'mode': mode,
                                'coin': coin,
                                'timeframe': tf,
                                'rr': rr,
                                'trades': 0,
                                'win_rate': 0.0,
                                'pf': 0.0,
                                'sharpe': 0.0,
                                'drawdown': 0.0,
                                'avg_r': 0.0,
                                'median_r': 0.0,
                                'expectancy': 0.0,
                                'avg_duration_hours': 0.0,
                                'net_return': 0.0
                            })
                            pbar.update(1)
                        continue

                    # 4. Generate inputs for vectorbt (run all RRs for this slice together to save compute)
                    try:
                        entries_s, short_entries_s, sl_stop_s, tp_stop_all, sl_pct_map = build_vbt_signals(
                            df_slice, signals_slice, rr_values
                        )
                    except Exception as e:
                        print(f"\n[!] Error building VBT signals for {coin} {tf} ({mode}): {e}")
                        pbar.update(len(rr_values))
                        continue

                    if not entries_s.any() and not short_entries_s.any():
                        for rr in rr_values:
                            results.append({
                                'strategy': 'Mean_Reversion',
                                'mode': mode,
                                'coin': coin,
                                'timeframe': tf,
                                'rr': rr,
                                'trades': 0,
                                'win_rate': 0.0,
                                'pf': 0.0,
                                'sharpe': 0.0,
                                'drawdown': 0.0,
                                'avg_r': 0.0,
                                'median_r': 0.0,
                                'expectancy': 0.0,
                                'avg_duration_hours': 0.0,
                                'net_return': 0.0
                            })
                            pbar.update(1)
                        continue

                    exits_s = pd.Series(False, index=df_slice.index)
                    exits_s.iloc[-1] = True
                    short_exits_s = pd.Series(False, index=df_slice.index)
                    short_exits_s.iloc[-1] = True

                    order_price = df_slice['open'].copy()
                    order_price.iloc[-1] = df_slice['close'].iloc[-1]

                    # 5. Run VectorBT to extract trade entries and exits
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
                        print(f"\n[!] VBT execution error on {coin} {tf} ({mode}): {e}")
                        pbar.update(len(rr_values))
                        continue

                    # 6. Simulate each RR sequentially through the sequential portfolio math loop
                    for rr in rr_values:
                        try:
                            try:
                                sub_pf = pf[rr]
                            except Exception:
                                sub_pf = pf  # single column fallback

                            if sub_pf.trades.count() == 0:
                                results.append({
                                    'strategy': 'Mean_Reversion',
                                    'mode': mode,
                                    'coin': coin,
                                    'timeframe': tf,
                                    'rr': rr,
                                    'trades': 0,
                                    'win_rate': 0.0,
                                    'pf': 0.0,
                                    'sharpe': 0.0,
                                    'drawdown': 0.0,
                                    'avg_r': 0.0,
                                    'median_r': 0.0,
                                    'expectancy': 0.0,
                                    'avg_duration_hours': 0.0,
                                    'net_return': 0.0
                                })
                                pbar.update(1)
                                continue

                            trades_df = sub_pf.trades.records_readable
                            funding_df = load_funding_history(coin)

                            sim_trades, final_bal, equity_curve, exit_dates, ruined = simulate_portfolio_leverage(
                                trades_df, sl_pct_map, df_slice, coin, rr, funding_df
                            )

                            # Calculate basic metrics
                            metrics = compute_metrics(sim_trades, final_bal, INITIAL_BALANCE, equity_curve, exit_dates)

                            # Calculate custom reversion metrics
                            trades = len(sim_trades)
                            win_rate = metrics['Win Rate']
                            
                            # Slicing winning and losing trades for R-multiples
                            wins_r = [t['r_multiple'] for t in sim_trades if t['pnl'] > 0]
                            losses_r = [abs(t['r_multiple']) for t in sim_trades if t['pnl'] <= 0]
                            
                            avg_win_r = np.mean(wins_r) if wins_r else 0.0
                            avg_loss_r = np.mean(losses_r) if losses_r else 0.0

                            # Fixed subtraction-based expectancy formula:
                            win_rate_dec = win_rate / 100.0
                            loss_rate_dec = 1.0 - win_rate_dec
                            expectancy = (win_rate_dec * avg_win_r) - (loss_rate_dec * avg_loss_r)

                            avg_r = np.mean([t['r_multiple'] for t in sim_trades]) if sim_trades else 0.0
                            median_r = np.median([t['r_multiple'] for t in sim_trades]) if sim_trades else 0.0
                            avg_duration = np.mean([t['duration_hours'] for t in sim_trades]) if sim_trades else 0.0
                            net_return = ((final_bal - INITIAL_BALANCE) / INITIAL_BALANCE) * 100.0

                            results.append({
                                'strategy': 'Mean_Reversion',
                                'mode': mode,
                                'coin': coin,
                                'timeframe': tf,
                                'rr': rr,
                                'trades': trades,
                                'win_rate': round(win_rate, 2),
                                'pf': round(metrics['Profit Factor'], 2),
                                'sharpe': round(metrics['Sharpe Ratio'], 2),
                                'drawdown': round(metrics['Max Drawdown'], 2),
                                'avg_r': round(avg_r, 4),
                                'median_r': round(median_r, 4),
                                'expectancy': round(expectancy, 4),
                                'avg_duration_hours': round(avg_duration, 2),
                                'net_return': round(net_return, 2)
                            })
                        except Exception as e:
                            print(f"\n[!] Error calculating metrics for {coin} {tf} ({mode}, RR={rr}): {e}")
                            results.append({
                                'strategy': 'Mean_Reversion',
                                'mode': mode,
                                'coin': coin,
                                'timeframe': tf,
                                'rr': rr,
                                'trades': 0,
                                'win_rate': 0.0,
                                'pf': 0.0,
                                'sharpe': 0.0,
                                'drawdown': 0.0,
                                'avg_r': 0.0,
                                'median_r': 0.0,
                                'expectancy': 0.0,
                                'avg_duration_hours': 0.0,
                                'net_return': 0.0
                            })
                        pbar.update(1)

    # 7. Save to CSV
    os.makedirs("results", exist_ok=True)
    df_results = pd.DataFrame(results)
    csv_path = "results/mean_reversion_scan.csv"
    df_results.to_csv(csv_path, index=False)
    print(f"\nSaved all results to {csv_path}")

    # 8. Rankings Printing
    print("\n" + "=" * 80)
    print("  RANKING REPORT")
    print("=" * 80)

    # Rank 1: Top 25 results ranked by Profit Factor (PF), minimum 100 trades, then Sharpe
    print("\n--- TOP 25 RESULTS (PF, Min 100 Trades, then Sharpe) ---")
    df_min100 = df_results[df_results['trades'] >= 100].copy()
    if not df_min100.empty:
        df_rank_pf = df_min100.sort_values(by=['pf', 'sharpe'], ascending=[False, False])
        print(df_rank_pf.head(25)[['mode', 'coin', 'timeframe', 'rr', 'trades', 'pf', 'sharpe', 'expectancy', 'net_return']].to_string(index=False))
    else:
        print("No combinations met the minimum threshold of 100 trades.")

    # Rank 2: Top 10 by Win Rate
    print("\n--- TOP 10 BY WIN RATE ---")
    df_rank_wr = df_results.sort_values(by='win_rate', ascending=False)
    print(df_rank_wr.head(10)[['mode', 'coin', 'timeframe', 'rr', 'trades', 'win_rate', 'pf', 'expectancy']].to_string(index=False))

    # Rank 3: Top 10 by Expectancy
    print("\n--- TOP 10 BY EXPECTANCY ---")
    df_rank_exp = df_results.sort_values(by='expectancy', ascending=False)
    print(df_rank_exp.head(10)[['mode', 'coin', 'timeframe', 'rr', 'trades', 'pf', 'expectancy', 'net_return']].to_string(index=False))

    # 9. Summary Report Generation
    print("\nGenerating phase14a_summary.txt...")
    summary_path = "results/phase14a_summary.txt"
    
    # Calculate best metrics
    best_pf = df_results.loc[df_results['pf'].idxmax()] if not df_results.empty else None
    best_sharpe = df_results.loc[df_results['sharpe'].idxmax()] if not df_results.empty else None
    best_exp = df_results.loc[df_results['expectancy'].idxmax()] if not df_results.empty else None
    best_wr = df_results.loc[df_results['win_rate'].idxmax()] if not df_results.empty else None

    # Helper function to generate quick description string
    def desc(row):
        if row is None: return "N/A"
        return f"{row['coin']} {row['timeframe']} ({row['mode']}, RR={row['rr']}) | Trades: {row['trades']}, PF: {row['pf']}, Sharpe: {row['sharpe']}, WR: {row['win_rate']}%, Expectancy: {row['expectancy']}, Net Return: {row['net_return']}%"

    summary_content = []
    summary_content.append("=" * 80)
    summary_content.append("  PHASE 14A.1 MEAN REVERSION SCAN SUMMARY")
    summary_content.append("=" * 80)
    summary_content.append(f"Best PF Result:         {desc(best_pf)}")
    summary_content.append(f"Best Sharpe Result:     {desc(best_sharpe)}")
    summary_content.append(f"Best Expectancy Result: {desc(best_exp)}")
    summary_content.append(f"Highest Win Rate:       {desc(best_wr)}")
    summary_content.append("\n" + "-" * 80)
    summary_content.append("  BEST RESULT PER STRATEGY MODE")
    summary_content.append("-" * 80)
    for m in modes:
        df_m = df_results[df_results['mode'] == m]
        best_m = df_m.loc[df_m['pf'].idxmax()] if not df_m.empty and df_m['pf'].max() > 0 else None
        summary_content.append(f"Mode {m:<8}: {desc(best_m)}")

    summary_content.append("\n" + "-" * 80)
    summary_content.append("  BEST RESULT PER TIMEFRAME")
    summary_content.append("-" * 80)
    for tf in timeframes:
        df_tf = df_results[df_results['timeframe'] == tf]
        best_tf = df_tf.loc[df_tf['pf'].idxmax()] if not df_tf.empty and df_tf['pf'].max() > 0 else None
        summary_content.append(f"TF {tf:<8}: {desc(best_tf)}")

    summary_content.append("\n" + "-" * 80)
    summary_content.append("  BEST RESULT PER COIN")
    summary_content.append("-" * 80)
    for coin in coins:
        df_c = df_results[df_results['coin'] == coin]
        best_c = df_c.loc[df_c['pf'].idxmax()] if not df_c.empty and df_c['pf'].max() > 0 else None
        summary_content.append(f"Coin {coin:<8}: {desc(best_c)}")

    summary_content.append("\n" + "=" * 80)
    
    with open(summary_path, 'w') as f:
        f.write("\n".join(summary_content))
    print(f"Summary written to {summary_path}")
    print("\nScan completed successfully!")

if __name__ == "__main__":
    main()
