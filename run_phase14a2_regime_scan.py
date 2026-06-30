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
    "15m": pd.Timedelta(minutes=15),
    "1h":  pd.Timedelta(hours=1),
    "4h":  pd.Timedelta(hours=4),
}

def main():
    # Research universe definitions for Phase 14A.2A
    modes = ['RSI_BB']
    coins = ['ETH', 'AVAX', 'BNB']
    timeframes = ['1H', '4H']
    rr_values = [3.0]

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
    print(f"Starting Phase 14A.2A Regime Scan: running {total_runs} combinations...")

    for mode in modes:
        for coin in coins:
            for tf in timeframes:
                tf_mapped = tf_mapping[tf]
                
                # 1. Load data
                df = load_symbol_timeframe(coin, tf_mapped)
                if df is None or df.empty:
                    print(f"[!] Warning: missing data for {coin} {tf}. Skipping.")
                    continue

                # 2. Build signals on full history to avoid warm-up issues
                try:
                    signals = build_signals(df, 'Mean_Reversion', coin, tf_mapped, mode=mode)
                except Exception as e:
                    print(f"[!] Error building signals for {coin} {tf} ({mode}): {e}")
                    continue

                # 3. Slice to desired period
                mask = (df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)
                df_slice = df[mask]
                signals_slice = signals[mask]

                if len(df_slice) < 50 or signals_slice['side'].eq('').all():
                    for rr in rr_values:
                        results.append({
                            'coin': coin,
                            'timeframe': tf,
                            'rr': rr,
                            'trades': 0,
                            'win_rate': 0.0,
                            'pf': 0.0,
                            'sharpe': 0.0,
                            'drawdown': 0.0,
                            'expectancy': 0.0,
                            'net_return': 0.0
                        })
                    continue

                # 4. Generate inputs for vectorbt
                try:
                    entries_s, short_entries_s, sl_stop_s, tp_stop_all, sl_pct_map = build_vbt_signals(
                        df_slice, signals_slice, rr_values
                    )
                except Exception as e:
                    print(f"[!] Error building VBT signals for {coin} {tf} ({mode}): {e}")
                    continue

                if not entries_s.any() and not short_entries_s.any():
                    for rr in rr_values:
                        results.append({
                            'coin': coin,
                            'timeframe': tf,
                            'rr': rr,
                            'trades': 0,
                            'win_rate': 0.0,
                            'pf': 0.0,
                            'sharpe': 0.0,
                            'drawdown': 0.0,
                            'expectancy': 0.0,
                            'net_return': 0.0
                        })
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
                    print(f"[!] VBT execution error on {coin} {tf} ({mode}): {e}")
                    continue

                # 6. Simulate each RR sequentially through the sequential portfolio math loop
                for rr in rr_values:
                    try:
                        try:
                            sub_pf = pf[rr]
                        except Exception:
                            sub_pf = pf

                        if sub_pf.trades.count() == 0:
                            results.append({
                                'coin': coin,
                                'timeframe': tf,
                                'rr': rr,
                                'trades': 0,
                                'win_rate': 0.0,
                                'pf': 0.0,
                                'sharpe': 0.0,
                                'drawdown': 0.0,
                                'expectancy': 0.0,
                                'net_return': 0.0
                            })
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
                        
                        wins_r = [t['r_multiple'] for t in sim_trades if t['pnl'] > 0]
                        losses_r = [abs(t['r_multiple']) for t in sim_trades if t['pnl'] <= 0]
                        
                        avg_win_r = np.mean(wins_r) if wins_r else 0.0
                        avg_loss_r = np.mean(losses_r) if losses_r else 0.0

                        win_rate_dec = win_rate / 100.0
                        loss_rate_dec = 1.0 - win_rate_dec
                        expectancy = (win_rate_dec * avg_win_r) - (loss_rate_dec * avg_loss_r)

                        net_return = ((final_bal - INITIAL_BALANCE) / INITIAL_BALANCE) * 100.0

                        results.append({
                            'coin': coin,
                            'timeframe': tf,
                            'rr': rr,
                            'trades': trades,
                            'win_rate': round(win_rate, 2),
                            'pf': round(metrics['Profit Factor'], 2),
                            'sharpe': round(metrics['Sharpe Ratio'], 2),
                            'drawdown': round(metrics['Max Drawdown'], 2),
                            'expectancy': round(expectancy, 4),
                            'net_return': round(net_return, 2)
                        })
                    except Exception as e:
                        print(f"[!] Error calculating metrics for {coin} {tf} ({mode}, RR={rr}): {e}")
                        results.append({
                            'coin': coin,
                            'timeframe': tf,
                            'rr': rr,
                            'trades': 0,
                            'win_rate': 0.0,
                            'pf': 0.0,
                            'sharpe': 0.0,
                            'drawdown': 0.0,
                            'expectancy': 0.0,
                            'net_return': 0.0
                        })

    # Save to CSV
    os.makedirs("results", exist_ok=True)
    df_results = pd.DataFrame(results)
    df_results.to_csv("results/phase14a2_regime_scan.csv", index=False)
    df_results.to_csv("phase14a2_regime_scan.csv", index=False)
    
    print("\nSaved all results to results/phase14a2_regime_scan.csv and phase14a2_regime_scan.csv")
    print(df_results.to_string(index=False))

    # Evaluate Success Criterion
    # Criterion: At least one configuration achieves: PF > 1.10, Expectancy > 0, Trades >= 100
    print("\n" + "=" * 80)
    print("  EVALUATING SUCCESS CRITERIA")
    print("=" * 80)
    success = False
    for _, row in df_results.iterrows():
        if row['trades'] >= 100 and row['pf'] > 1.10 and row['expectancy'] > 0:
            print(f"SUCCESS MATCH: Coin {row['coin']} {row['timeframe']} | Trades: {row['trades']}, PF: {row['pf']}, Expectancy: {row['expectancy']} | Sharpe: {row['sharpe']}, Net Return: {row['net_return']}%")
            success = True
    
    if success:
        print("\nSUCCESS: At least one configuration met all criteria! Regime awareness saved the strategy.")
    else:
        print("\nFAILURE: Zero configurations met the criteria. Mean reversion should be deprioritized.")

if __name__ == "__main__":
    main()
