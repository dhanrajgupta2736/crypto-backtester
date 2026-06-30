import os
import sys
import numpy as np
import pandas as pd
import vectorbt as vbt
from vectorbt.portfolio.enums import OppositeEntryMode, StopExitMode, StopExitPrice

# Force UTF-8 output so box-drawing / special chars don't crash on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
DATA_DIR    = "data"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

# Sizing & Leverage
INITIAL_BALANCE = 1000.0
RISK_PER_TRADE  = 100.0
LEVERAGE        = 5.0

# Timeframe definitions
TIMEFRAME_DELTAS = {
    "5m":  pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h":  pd.Timedelta(hours=1),
    "4h":  pd.Timedelta(hours=4),
    "1d":  pd.Timedelta(days=1),
}

# Date Periods
HOLDOUT_1_PERIOD = {
    "start": pd.Timestamp("2025-01-01 00:00:00", tz="UTC"),
    "end":   pd.Timestamp("2025-12-31 23:59:59", tz="UTC"),
}
HOLDOUT_2_PERIOD = {
    "start": pd.Timestamp("2026-01-01 00:00:00", tz="UTC"),
    "end":   pd.Timestamp("2026-06-19 23:59:59", tz="UTC"),
}

# Hyperliquid Fee & Cost Parameters
TAKER_FEE = 0.00045   # 0.045%
MAKER_FEE = 0.00015   # 0.015%
FUNDING_RATE = 0.0001 # 0.01% per hour

SLIPPAGE_MAP = {
    'BTC':    0.0002, 'ETH': 0.0002,
    'AVAX':   0.0005, 'DOT': 0.0005, 'XRP': 0.0005, 'DOGE': 0.0005, 'RENDER': 0.0005,
    'WLD':    0.0008, 'ZEC': 0.0008, 'AAVE': 0.0008
}

# Add custom path to sys.path to import from workspace
sys.path.append(r"c:\Users\HP\Desktop\crypto-backtester - Copy (2)")
from run_research_framework import load_symbol_timeframe, build_signals, build_vbt_signals, calculate_daily_sharpe

# ═══════════════════════════════════════════════════════════════════════════════
#  HYPERLIQUID COST PORTFOLIO SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════════
def simulate_portfolio_hyperliquid(symbol, tf, trades_df, sl_pct_map, df_slice, apply_costs=True):
    balance      = INITIAL_BALANCE
    equity_curve = [balance]
    exit_dates   = []
    sim_trades   = []

    if trades_df.empty:
        return sim_trades, balance, equity_curve, exit_dates

    # Get local rates based on apply_costs
    slippage_rate = SLIPPAGE_MAP.get(symbol.upper(), 0.0008) if apply_costs else 0.0
    fee_taker     = TAKER_FEE if apply_costs else 0.0
    fee_maker     = MAKER_FEE if apply_costs else 0.0
    rate_funding  = FUNDING_RATE if apply_costs else 0.0

    trades_sorted = trades_df.sort_values(by='Entry Timestamp').reset_index(drop=True)

    for _, row in trades_sorted.iterrows():
        if balance <= 0:
            break

        entry_idx  = int(row['Entry Timestamp'])
        exit_idx   = int(row['Exit Timestamp'])
        ep         = float(row['Avg Entry Price'])
        exit_price = float(row['Avg Exit Price'])
        vbt_qty    = float(row['Size'])
        direction  = row['Direction'] # 'Long' or 'Short'

        entry_time = df_slice.loc[entry_idx, 'timestamp']
        exit_time  = df_slice.loc[exit_idx, 'timestamp']

        # Get stop loss percentage
        sl_pct = sl_pct_map.get(entry_idx)
        if sl_pct is None or sl_pct <= 0:
            continue

        # Position Sizing incorporating stop loss distance and entry/exit friction
        # Stop loss triggers market order (taker fee + slippage)
        dist = ep * sl_pct
        entry_friction = ep * (fee_taker + slippage_rate)
        exit_friction  = ep * (fee_taker + slippage_rate)
        friction       = entry_friction + exit_friction

        # If friction is 0 (gross), sizing is based on stop distance only
        if dist + friction <= 0:
            continue
        risk_qty = RISK_PER_TRADE / (dist + friction)
        max_qty  = (balance * LEVERAGE) / ep
        qty      = min(risk_qty, max_qty)

        # 1. Gross PnL
        if direction.lower() == 'long':
            gross_pnl = qty * (exit_price - ep)
        else:
            gross_pnl = qty * (ep - exit_price)

        # 2. Entry Costs (market order: taker fee + slippage)
        entry_fee_cost = fee_taker * qty * ep
        entry_slip_cost = slippage_rate * qty * ep

        # 3. Exit Costs (slippage + conditional fee)
        exit_slip_cost = slippage_rate * qty * exit_price
        
        # Check exit type:
        # If exit_idx is the final candle of the dataframe slice, it's a market close (taker)
        is_end_of_period = (exit_idx == df_slice.index[-1])
        
        if is_end_of_period:
            exit_fee_rate = fee_taker
            exit_type = "End_of_Period"
        else:
            # Check if trade closed in profit (TP) or loss (SL)
            is_profit = False
            if direction.lower() == 'long':
                is_profit = (exit_price >= ep)
            else:
                is_profit = (exit_price <= ep)

            if is_profit:
                exit_fee_rate = fee_maker # Take-Profit is resting limit order (maker)
                exit_type = "TP"
            else:
                exit_fee_rate = fee_taker # Stop-Loss is market stop order (taker)
                exit_type = "SL"

        exit_fee_cost = exit_fee_rate * qty * exit_price

        # 4. Hourly Funding Cost
        # Count hourly mark crossings during the trade duration
        funding_ticks = pd.date_range(start=entry_time, end=exit_time, freq='h', inclusive='right')
        num_funding_payments = len(funding_ticks)

        # For 1h timeframe, position must be held longer than 1 candle (i.e. num_funding_payments > 1)
        if tf.lower() == '1h' and num_funding_payments <= 1:
            num_funding_payments = 0

        funding_cost = rate_funding * num_funding_payments * qty * ep

        # Total Cost Drag
        total_costs = entry_fee_cost + entry_slip_cost + exit_fee_cost + exit_slip_cost + funding_cost
        net_pnl = gross_pnl - total_costs

        balance += net_pnl
        balance = max(0.0, balance)

        equity_curve.append(balance)
        exit_dates.append(exit_time)

        sim_trades.append({
            'pnl':         net_pnl,
            'gross_pnl':   gross_pnl,
            'direction':   direction,
            'entry_price': ep,
            'exit_price':  exit_price,
            'qty':         qty,
            'exit_date':   exit_time,
            'hold_hours':  (exit_time - entry_time).total_seconds() / 3600.0,
            'entry_fee':   entry_fee_cost,
            'entry_slip':  entry_slip_cost,
            'exit_fee':    exit_fee_cost,
            'exit_slip':   exit_slip_cost,
            'funding':     funding_cost,
            'total_cost':  total_costs,
            'exit_type':   exit_type,
        })

        if balance <= 0:
            break

    return sim_trades, balance, equity_curve, exit_dates

# ═══════════════════════════════════════════════════════════════════════════════
#  METRIC COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════
def compute_metrics_hyperliquid(sim_trades, final_balance, initial_balance, equity_curve, exit_dates):
    net_profit   = final_balance - initial_balance
    total_trades = len(sim_trades)

    if total_trades == 0:
        return {
            'Final Balance':   final_balance,
            'Net Profit':      net_profit,
            'Profit Factor':   0.0,
            'Sharpe Ratio':    0.0,
            'Expectancy':      0.0,
            'Max Drawdown':    0.0,
            'Win Rate':        0.0,
            'Average Win':     0.0,
            'Average Loss':    0.0,
            'Number of Trades': 0,
        }

    wins   = [t['pnl'] for t in sim_trades if t['pnl'] > 0]
    losses = [t['pnl'] for t in sim_trades if t['pnl'] <= 0]

    win_rate  = len(wins) / total_trades * 100
    avg_win   = np.mean(wins)   if wins   else 0.0
    avg_loss  = np.mean(losses) if losses else 0.0

    sum_wins   = sum(wins)
    sum_losses = sum(losses)
    if sum_losses == 0:
        profit_factor = 999.9 if sum_wins > 0 else 1.0
    else:
        profit_factor = abs(sum_wins / sum_losses)

    expectancy = (win_rate / 100.0 * avg_win) + ((100 - win_rate) / 100.0 * avg_loss)

    eq_series  = pd.Series(equity_curve)
    cummax     = eq_series.cummax()
    drawdown   = (eq_series - cummax) / cummax.replace(0, 1e-9)
    max_dd     = abs(drawdown.min()) * 100

    daily_sharpe = calculate_daily_sharpe(equity_curve, exit_dates)

    return {
        'Final Balance':    round(final_balance,  2),
        'Net Profit':       round(net_profit,      2),
        'Profit Factor':    round(profit_factor,   2),
        'Sharpe Ratio':     round(daily_sharpe,    2),
        'Expectancy':       round(expectancy,      2),
        'Max Drawdown':     round(max_dd,          2),
        'Win Rate':         round(win_rate,        2),
        'Average Win':      round(avg_win,         2),
        'Average Loss':     round(avg_loss,        2),
        'Number of Trades': total_trades,
    }

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    qualified_path = os.path.join(RESULTS_DIR, "qualified_results.csv")
    if not os.path.exists(qualified_path):
        print(f"Error: {qualified_path} not found. Please run the research framework first.")
        return

    df_qualified = pd.read_csv(qualified_path)
    if df_qualified.empty:
        print("No qualified combinations found in qualified_results.csv.")
        return

    print("=" * 72)
    print("  HYPERLIQUID COST STRESS TESTING ENGINE")
    print("=" * 72)
    print(f"  Loaded {len(df_qualified)} qualified combinations for stress testing.")

    results_after_costs = []

    for idx, row in df_qualified.iterrows():
        coin = row['Coin']
        strategy = row['Strategy']
        tf = row['Timeframe']
        rr_str = row['RR Value']
        rr = float(rr_str.split(':')[1])

        print(f"\n  [Comb {idx+1}/{len(df_qualified)}] Processing {coin} | {strategy} | {tf} | {rr_str} ...")

        # Load historical data
        df = load_symbol_timeframe(coin, tf)
        if df is None or df.empty:
            print(f"    Failed to load data for {coin} {tf}. Skipping.")
            continue

        # Build signals on full history
        signals = build_signals(df, strategy)

        # Run for both Holdout periods
        periods = [
            ("H1", HOLDOUT_1_PERIOD['start'], HOLDOUT_1_PERIOD['end']),
            ("H2", HOLDOUT_2_PERIOD['start'], HOLDOUT_2_PERIOD['end'])
        ]

        metrics_for_combo = {
            'Coin': coin,
            'Strategy': strategy,
            'Timeframe': tf,
            'RR Value': rr_str
        }

        combo_total_gross_pnl = 0.0
        combo_total_costs = 0.0
        combo_total_trades = 0
        combo_total_hold_hours = 0.0

        for label, start_dt, end_dt in periods:
            mask = (df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)
            df_slice = df[mask]

            if len(df_slice) < 50:
                print(f"    Warning: less than 50 data bars in {label} period. Skipping period.")
                continue

            signals_slice = signals[mask]

            # 1. Run zero-cost VBT backtest
            entries_s, short_entries_s, sl_stop_s, tp_stop_all, sl_pct_map = build_vbt_signals(
                df_slice, signals_slice, [rr]
            )

            if not entries_s.any() and not short_entries_s.any():
                # Zero trades in period
                # Copy gross values from input qualified_results
                gross_net_profit = row[f'{label}_Net Profit']
                gross_pf = row[f'{label}_Profit Factor']
                gross_sharpe = row[f'{label}_Sharpe Ratio']
                gross_trades = row[f'{label}_Number of Trades']
                
                metrics_for_combo.update({
                    f'{label}_NetProfit_gross': gross_net_profit,
                    f'{label}_NetProfit_net':   0.0,
                    f'{label}_PF_gross':        gross_pf,
                    f'{label}_PF_net':          0.0,
                    f'{label}_Sharpe_gross':    gross_sharpe,
                    f'{label}_Sharpe_net':      0.0,
                    f'{label}_Trades_net':      0,
                })
                continue

            exits_s = pd.Series(False, index=df_slice.index)
            exits_s.iloc[-1] = True
            short_exits_s = pd.Series(False, index=df_slice.index)
            short_exits_s.iloc[-1] = True

            order_price = df_slice['open'].copy()
            order_price.iloc[-1] = df_slice['close'].iloc[-1]

            pf = vbt.Portfolio.from_signals(
                close          = df_slice['close'],
                entries        = entries_s,
                exits          = exits_s,
                short_entries  = short_entries_s,
                short_exits    = short_exits_s,
                size           = 1.0,
                size_type      = "amount",
                price          = order_price,
                open           = df_slice['open'],
                high           = df_slice['high'],
                low            = df_slice['low'],
                sl_stop        = sl_stop_s,
                tp_stop        = tp_stop_all[[rr]],
                fees           = 0.0,
                slippage       = 0.0,
                init_cash      = 1_000_000.0,
                accumulate     = False,
                upon_opposite_entry = OppositeEntryMode.Ignore,
                stop_exit_price     = StopExitPrice.StopMarket,
                upon_stop_exit      = StopExitMode.Close,
                freq           = TIMEFRAME_DELTAS[tf],
            )

            # Extract trades
            sub_pf = pf[rr] if hasattr(pf, '__getitem__') else pf
            trades_df = sub_pf.trades.records_readable

            # 1. Run sequential leverage simulation WITHOUT costs (gross)
            sim_trades_gross, final_bal_gross, eq_curve_gross, exit_dates_gross = simulate_portfolio_hyperliquid(
                coin, tf, trades_df, sl_pct_map, df_slice, apply_costs=False
            )
            metrics_gross = compute_metrics_hyperliquid(sim_trades_gross, final_bal_gross, INITIAL_BALANCE, eq_curve_gross, exit_dates_gross)

            # 2. Run sequential leverage simulation WITH Hyperliquid costs (net)
            sim_trades_net, final_bal_net, eq_curve_net, exit_dates_net = simulate_portfolio_hyperliquid(
                coin, tf, trades_df, sl_pct_map, df_slice, apply_costs=True
            )
            metrics_net = compute_metrics_hyperliquid(sim_trades_net, final_bal_net, INITIAL_BALANCE, eq_curve_net, exit_dates_net)

            # Aggregate stats across H1 and H2 for total drag, avg hold time, and trades per day
            for t in sim_trades_net:
                combo_total_gross_pnl += t['gross_pnl']
                combo_total_costs += t['total_cost']
                combo_total_trades += 1
                combo_total_hold_hours += t['hold_hours']

            metrics_for_combo.update({
                f'{label}_NetProfit_gross': metrics_gross['Net Profit'],
                f'{label}_NetProfit_net':   metrics_net['Net Profit'],
                f'{label}_PF_gross':        metrics_gross['Profit Factor'],
                f'{label}_PF_net':          metrics_net['Profit Factor'],
                f'{label}_Sharpe_gross':    metrics_gross['Sharpe Ratio'],
                f'{label}_Sharpe_net':      metrics_net['Sharpe Ratio'],
                f'{label}_Trades_net':      metrics_net['Number of Trades'],
            })

        # Calculate averages and drag percentages
        # Combined period days: H1 (365) + H2 (170) = 535 days
        avg_trades_per_day = combo_total_trades / 535.0
        avg_hold_time_hours = (combo_total_hold_hours / combo_total_trades) if combo_total_trades > 0 else 0.0
        
        # Drag calculation: (Total Costs / Total Gross Profit) * 100
        # To avoid division by zero or negative gross profit:
        if combo_total_gross_pnl > 0:
            drag_pct = (combo_total_costs / combo_total_gross_pnl) * 100.0
        else:
            drag_pct = 100.0 if combo_total_costs > 0 else 0.0

        metrics_for_combo.update({
            'Avg_Trades_Per_Day':  round(avg_trades_per_day, 4),
            'Avg_Hold_Time_Hours': round(avg_hold_time_hours, 2),
            'Total_Cost_Drag_Pct': round(drag_pct, 2)
        })

        # Check qualification gates on NET metrics for BOTH periods
        h1_pass = (
            metrics_for_combo['H1_NetProfit_net'] > 0.0 and
            metrics_for_combo['H1_PF_net'] >= 1.10 and
            metrics_for_combo['H1_Sharpe_net'] >= 0.0 and
            metrics_for_combo['H1_Trades_net'] >= 50
        )
        h2_pass = (
            metrics_for_combo['H2_NetProfit_net'] > 0.0 and
            metrics_for_combo['H2_PF_net'] >= 1.10 and
            metrics_for_combo['H2_Sharpe_net'] >= 0.0 and
            metrics_for_combo['H2_Trades_net'] >= 50
        )
        metrics_for_combo['Survives_Costs'] = (h1_pass and h2_pass)

        # Print quick recap for the combo
        status = "✅ SURVIVES" if metrics_for_combo['Survives_Costs'] else "❌ FAILS GATES"
        print(f"    Result: {status}")
        print(f"      H1 Gross Net: {metrics_for_combo['H1_NetProfit_gross']:+.2f} | Net: {metrics_for_combo['H1_NetProfit_net']:+.2f} (PF: {metrics_for_combo['H1_PF_net']:.2f}, Sharpe: {metrics_for_combo['H1_Sharpe_net']:.2f}, Trades: {metrics_for_combo['H1_Trades_net']})")
        print(f"      H2 Gross Net: {metrics_for_combo['H2_NetProfit_gross']:+.2f} | Net: {metrics_for_combo['H2_NetProfit_net']:+.2f} (PF: {metrics_for_combo['H2_PF_net']:.2f}, Sharpe: {metrics_for_combo['H2_Sharpe_net']:.2f}, Trades: {metrics_for_combo['H2_Trades_net']})")
        print(f"      Avg Hold: {avg_hold_time_hours:.1f}h | Drag: {drag_pct:.1f}% | Trades/Day: {avg_trades_per_day:.3f}")

        results_after_costs.append(metrics_for_combo)

    df_out = pd.DataFrame(results_after_costs)
    out_path = os.path.join(RESULTS_DIR, "qualified_results_after_costs.csv")
    df_out.to_csv(out_path, index=False)
    print(f"\n  Saved all stress test results to {out_path} ({len(df_out)} rows).")

    # Display final summary table
    print("\n" + "=" * 120)
    print("  FINAL STRESS TEST SUMMARY TABLE (Sorted by Net H2 Sharpe Descending)")
    print("=" * 120)
    
    # Sort survivors first, then by H2_Sharpe_net descending
    df_out_sorted = df_out.sort_values(by=['Survives_Costs', 'H2_Sharpe_net'], ascending=[False, False])
    
    summary_cols = [
        'Coin', 'Strategy', 'Timeframe', 'RR Value', 
        'H1_PF_gross', 'H1_PF_net', 'H1_Sharpe_net', 'H1_Trades_net',
        'H2_PF_gross', 'H2_PF_net', 'H2_Sharpe_net', 'H2_Trades_net',
        'Total_Cost_Drag_Pct', 'Survives_Costs'
    ]
    
    pd.set_option('display.max_columns', 30)
    pd.set_option('display.width', 160)
    pd.set_option('display.float_format', '{:.2f}'.format)
    print(df_out_sorted[summary_cols].to_string(index=False))
    print("=" * 120)

if __name__ == "__main__":
    main()
