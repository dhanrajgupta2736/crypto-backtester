"""
Phase 15C — ATR Expansion Density Expansion
============================================
Validates BTC 4H, BTC 1H, ETH 4H, ETH 1H under VE_3_ATR_EXPANSION
across three non-overlapping periods, then builds a combined portfolio
by merging all surviving instrument/RR trade streams.

Execution path is identical to Phase 15B (and 15A):
  build_signals → build_vbt_signals → vbt.Portfolio → simulate_portfolio_leverage → compute_metrics
"""

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
    calculate_daily_sharpe,
    load_funding_history,
    INITIAL_BALANCE,
    RISK_PER_TRADE,
    LEVERAGE,
    get_slippage_rate,
    get_exit_fee_rate,
)

FEE_RATE      = 0.0005   # 0.05 % taker
SLIPPAGE_RATE = 0.0002   # 0.02 %

TIMEFRAME_DELTAS = {
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
}

PERIODS = {
    "Selection": (pd.Timestamp("2023-01-01 00:00:00", tz="UTC"), pd.Timestamp("2024-12-31 23:59:59", tz="UTC")),
    "Holdout_1": (pd.Timestamp("2025-01-01 00:00:00", tz="UTC"), pd.Timestamp("2025-12-31 23:59:59", tz="UTC")),
    "Holdout_2": (pd.Timestamp("2026-01-01 00:00:00", tz="UTC"), pd.Timestamp("2026-06-19 23:59:59", tz="UTC")),
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: run one instrument/timeframe/RR/period through the full pipeline
# Returns the sim_trades list and raw per-trade records for portfolio merge.
# ─────────────────────────────────────────────────────────────────────────────
def run_single(coin, tf_mapped, rr, df_full, signals_full, period_name, start_dt, end_dt):
    empty = {'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0,
             'drawdown': 0.0, 'expectancy': 0.0, 'net_return': 0.0}

    mask       = (df_full['timestamp'] >= start_dt) & (df_full['timestamp'] <= end_dt)
    df_slice   = df_full[mask]
    sig_slice  = signals_full[mask]

    if len(df_slice) < 10 or sig_slice['side'].eq('').all():
        return empty, []

    try:
        entries_s, short_entries_s, sl_stop_s, tp_stop_all, sl_pct_map = build_vbt_signals(
            df_slice, sig_slice, [rr]
        )
    except Exception as e:
        print(f"  [!] build_vbt_signals error {coin} {tf_mapped} RR={rr} {period_name}: {e}")
        return empty, []

    if not entries_s.any() and not short_entries_s.any():
        return empty, []

    exits_s       = pd.Series(False, index=df_slice.index); exits_s.iloc[-1] = True
    short_exits_s = pd.Series(False, index=df_slice.index); short_exits_s.iloc[-1] = True
    order_price   = df_slice['open'].copy(); order_price.iloc[-1] = df_slice['close'].iloc[-1]

    try:
        pf_vbt = vbt.Portfolio.from_signals(
            close=df_slice['close'], entries=entries_s, exits=exits_s,
            short_entries=short_entries_s, short_exits=short_exits_s,
            size=1.0, size_type="amount", price=order_price,
            open=df_slice['open'], high=df_slice['high'], low=df_slice['low'],
            sl_stop=sl_stop_s, tp_stop=tp_stop_all,
            fees=FEE_RATE, slippage=SLIPPAGE_RATE, init_cash=1_000_000.0,
            accumulate=False, upon_opposite_entry=OppositeEntryMode.Ignore,
            stop_exit_price=StopExitPrice.StopMarket,
            upon_stop_exit=StopExitMode.Close,
            freq=TIMEFRAME_DELTAS[tf_mapped],
        )
    except Exception as e:
        print(f"  [!] VBT error {coin} {tf_mapped} RR={rr} {period_name}: {e}")
        return empty, []

    try:
        trades_df  = pf_vbt.trades.records_readable
        funding_df = load_funding_history(coin)

        sim_trades, final_bal, equity_curve, exit_dates, ruined = simulate_portfolio_leverage(
            trades_df, sl_pct_map, df_slice, coin, rr, funding_df
        )

        metrics    = compute_metrics(sim_trades, final_bal, INITIAL_BALANCE, equity_curve, exit_dates)
        n          = len(sim_trades)
        win_rate   = metrics['Win Rate']
        wins_r     = [t['r_multiple'] for t in sim_trades if t['pnl'] > 0]
        losses_r   = [abs(t['r_multiple']) for t in sim_trades if t['pnl'] <= 0]
        avg_win_r  = np.mean(wins_r)   if wins_r   else 0.0
        avg_loss_r = np.mean(losses_r) if losses_r else 0.0
        wr_dec     = win_rate / 100.0
        expectancy = (wr_dec * avg_win_r) - ((1 - wr_dec) * avg_loss_r)
        net_return = (final_bal - INITIAL_BALANCE) / INITIAL_BALANCE * 100.0

        result = {
            'trades': n, 'win_rate': round(win_rate, 2),
            'pf': round(metrics['Profit Factor'], 2),
            'sharpe': round(metrics['Sharpe Ratio'], 2),
            'drawdown': round(metrics['Max Drawdown'], 2),
            'expectancy': round(expectancy, 4),
            'net_return': round(net_return, 2),
        }
        return result, sim_trades

    except Exception as e:
        print(f"  [!] simulate error {coin} {tf_mapped} RR={rr} {period_name}: {e}")
        return empty, []


# ─────────────────────────────────────────────────────────────────────────────
# Combined portfolio: merge all instrument trade streams for a given period
# by exit-date order, then re-compute metrics on the merged equity curve.
# Each instrument stream is first generated independently so sizing is
# self-consistent per instrument; the combined equity curve reflects the
# serial compounding of all instruments' P&L.
# ─────────────────────────────────────────────────────────────────────────────
def build_combined_portfolio(all_sim_trades_by_period):
    """
    all_sim_trades_by_period: dict[period_name -> list[sim_trade dicts]]
    Returns a dict: period_name -> combined metrics dict
    """
    combined = {}
    for period_name, trade_list in all_sim_trades_by_period.items():
        if not trade_list:
            combined[period_name] = {
                'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0,
                'drawdown': 0.0, 'expectancy': 0.0, 'net_return': 0.0,
            }
            continue

        # Sort all trades across all instruments by exit date
        sorted_trades = sorted(trade_list, key=lambda t: t['exit_date'])

        balance      = INITIAL_BALANCE
        equity_curve = [balance]
        exit_dates   = []

        for t in sorted_trades:
            balance += t['pnl']
            balance  = max(0.0, balance)
            equity_curve.append(balance)
            exit_dates.append(t['exit_date'])

        final_bal  = balance
        metrics    = compute_metrics(sorted_trades, final_bal, INITIAL_BALANCE, equity_curve, exit_dates)
        n          = len(sorted_trades)
        win_rate   = metrics['Win Rate']
        wins_r     = [t['r_multiple'] for t in sorted_trades if t['pnl'] > 0]
        losses_r   = [abs(t['r_multiple']) for t in sorted_trades if t['pnl'] <= 0]
        avg_win_r  = np.mean(wins_r)   if wins_r   else 0.0
        avg_loss_r = np.mean(losses_r) if losses_r else 0.0
        wr_dec     = win_rate / 100.0
        expectancy = (wr_dec * avg_win_r) - ((1 - wr_dec) * avg_loss_r)
        net_return = (final_bal - INITIAL_BALANCE) / INITIAL_BALANCE * 100.0

        combined[period_name] = {
            'trades': n, 'win_rate': round(win_rate, 2),
            'pf': round(metrics['Profit Factor'], 2),
            'sharpe': round(metrics['Sharpe Ratio'], 2),
            'drawdown': round(metrics['Max Drawdown'], 2),
            'expectancy': round(expectancy, 4),
            'net_return': round(net_return, 2),
        }
    return combined


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    instruments = [
        ('BTC', '4h', '4H'),
        ('BTC', '1h', '1H'),
        ('ETH', '4h', '4H'),
        ('ETH', '1h', '1H'),
    ]
    mode      = 'VE_3_ATR_EXPANSION'
    rr_values = [1.0, 1.5, 2.0, 3.0]

    print("Phase 15C — ATR Expansion Density Expansion")
    print(f"Instruments: {[f'{c} {tf_d}' for c,_,tf_d in instruments]}")
    print(f"RR values  : {rr_values}")
    print(f"Periods    : {list(PERIODS.keys())}\n")

    raw_results  = []       # per-instrument rows for CSV
    # For combined portfolio: period -> flat list of all sim_trade dicts
    combined_trade_pool = {p: [] for p in PERIODS}

    total_candidates = len(instruments) * len(rr_values)
    with tqdm(total=total_candidates, desc="Validation") as pbar:
        for coin, tf_mapped, tf_display in instruments:
            # Load full dataset once; signal build on full history to avoid cold-start
            df_full = load_symbol_timeframe(coin, tf_mapped)
            if df_full is None or df_full.empty:
                print(f"\n[!] Missing data for {coin} {tf_display}. Skipping.")
                pbar.update(len(rr_values))
                continue

            try:
                signals_full = build_signals(df_full, 'Volatility_Expansion', coin, tf_mapped, mode=mode)
            except Exception as e:
                print(f"\n[!] Signal error {coin} {tf_display}: {e}")
                pbar.update(len(rr_values))
                continue

            for rr in rr_values:
                period_results   = {}
                period_sim_trades = {}

                for period_name, (start_dt, end_dt) in PERIODS.items():
                    metrics, sim_trades = run_single(
                        coin, tf_mapped, rr,
                        df_full, signals_full,
                        period_name, start_dt, end_dt
                    )
                    period_results[period_name]    = metrics
                    period_sim_trades[period_name] = sim_trades

                # Pass/Fail per candidate
                h1 = period_results.get("Holdout_1", {})
                h2 = period_results.get("Holdout_2", {})
                h1_pass = (h1.get('pf',0) > 1.10 and h1.get('expectancy',0) > 0
                           and h1.get('net_return',0) > 0 and h1.get('trades',0) >= 5)
                h2_pass = (h2.get('pf',0) > 1.10 and h2.get('expectancy',0) > 0
                           and h2.get('net_return',0) > 0 and h2.get('trades',0) >= 3)
                status = "PASS" if (h1_pass and h2_pass) else "FAIL"

                # Accumulate trades into combined pool (use all, not just passing)
                for p_name, sim_t in period_sim_trades.items():
                    combined_trade_pool[p_name].extend(sim_t)

                for p_name, m in period_results.items():
                    raw_results.append({
                        'coin': coin, 'timeframe': tf_display, 'mode': mode, 'rr': rr,
                        'period': p_name,
                        'trades': m['trades'], 'win_rate': m['win_rate'],
                        'pf': m['pf'], 'sharpe': m['sharpe'],
                        'drawdown': m['drawdown'], 'expectancy': m['expectancy'],
                        'net_return': m['net_return'],
                        'validation_status': status,
                    })

                pbar.update(1)

    # ── Individual results CSV ──────────────────────────────────────────────
    os.makedirs("results", exist_ok=True)
    df_results = pd.DataFrame(raw_results)
    df_results.to_csv("phase15c_validation.csv",         index=False)
    df_results.to_csv("results/phase15c_validation.csv", index=False)
    print("\nSaved phase15c_validation.csv")

    # ── Combined portfolio ──────────────────────────────────────────────────
    print("Building combined portfolio simulation...")
    combined_metrics = build_combined_portfolio(combined_trade_pool)

    combined_rows = []
    for p_name, m in combined_metrics.items():
        combined_rows.append({'period': p_name, **m})
    df_combined = pd.DataFrame(combined_rows)
    df_combined.to_csv("phase15c_combined_portfolio.csv",         index=False)
    df_combined.to_csv("results/phase15c_combined_portfolio.csv", index=False)
    print("Saved phase15c_combined_portfolio.csv")

    # ── Markdown report ─────────────────────────────────────────────────────
    print("Generating phase15c_report.md...")
    report = generate_report(df_results, df_combined)
    with open("phase15c_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("Report saved to phase15c_report.md\n")

    # ── Console summary ─────────────────────────────────────────────────────
    print("=" * 65)
    print("  PHASE 15C — INDIVIDUAL VALIDATION SUMMARY")
    print("=" * 65)
    for coin, _, tf_display in instruments:
        for rr in rr_values:
            sub = df_results[(df_results['coin'] == coin) &
                             (df_results['timeframe'] == tf_display) &
                             (df_results['rr'] == rr)]
            status = sub['validation_status'].iloc[0] if not sub.empty else "?"
            for _, row in sub.iterrows():
                print(f"  [{status}] {row['coin']} {row['timeframe']} RR={row['rr']:<3} "
                      f"| {row['period']:<10}: T={row['trades']:<3} "
                      f"PF={row['pf']:<5} EXP={row['expectancy']:<7} "
                      f"RET={row['net_return']:>7.2f}%")
            print()

    print("=" * 65)
    print("  COMBINED PORTFOLIO")
    print("=" * 65)
    for _, row in df_combined.iterrows():
        print(f"  {row['period']:<12}: T={row['trades']:<4} "
              f"PF={row['pf']:<5} Sharpe={row['sharpe']:<5} "
              f"EXP={row['expectancy']:<7} DD={row['drawdown']:<6}% "
              f"RET={row['net_return']:>8.2f}%")

    # Success criterion check
    h1_c = combined_metrics.get('Holdout_1', {})
    h2_c = combined_metrics.get('Holdout_2', {})
    portfolio_pass = (
        h1_c.get('pf', 0) > 1.20 and h1_c.get('expectancy', 0) > 0
        and h1_c.get('net_return', 0) > 0
        and h2_c.get('pf', 0) > 1.20 and h2_c.get('expectancy', 0) > 0
        and h2_c.get('net_return', 0) > 0
    )
    print()
    print(f"  Portfolio Success Criterion: {'*** PASS ***' if portfolio_pass else 'FAIL'}")
    print("=" * 65)


def generate_report(df_ind, df_comb):
    lines = []
    lines += [
        "# Phase 15C Report: ATR Expansion Density Expansion",
        "",
        "**Strategy**: `VE_3_ATR_EXPANSION` — identical parameters to Phase 15B",
        "**Research Universe**: BTC 4H, BTC 1H, ETH 4H, ETH 1H",
        "**Periods**: Selection 2023-2024 | Holdout 1 2025 | Holdout 2 2026",
        "",
        "---",
        "",
        "## 1. Individual Instrument Validation",
        "",
        "| Instrument | RR | Period | Trades | Win Rate | PF | Sharpe | Drawdown | Expectancy | Net Return | Status |",
        "| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for _, row in df_ind.iterrows():
        label  = f"{row['coin']} {row['timeframe']}"
        status = f"`{row['validation_status']}`"
        lines.append(
            f"| {label} | {row['rr']} | {row['period']} "
            f"| {row['trades']} | {row['win_rate']}% | {row['pf']:.2f} "
            f"| {row['sharpe']:.2f} | {row['drawdown']:.2f}% "
            f"| {row['expectancy']:.4f} | {row['net_return']:.2f}% | {status} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 2. Combined Portfolio Performance",
        "",
        "> All instrument/RR streams merged by exit-date order; sequential compounding.",
        "",
        "| Period | Trades | Win Rate | PF | Sharpe | Drawdown | Expectancy | Net Return |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for _, row in df_comb.iterrows():
        lines.append(
            f"| {row['period']} | {row['trades']} | {row['win_rate']}% "
            f"| {row['pf']:.2f} | {row['sharpe']:.2f} | {row['drawdown']:.2f}% "
            f"| {row['expectancy']:.4f} | {row['net_return']:.2f}% |"
        )

    # Success criteria check
    h1 = df_comb[df_comb['period'] == 'Holdout_1']
    h2 = df_comb[df_comb['period'] == 'Holdout_2']

    def chk(df_row, col, thresh, op='>'):
        if df_row.empty: return False
        v = df_row.iloc[0][col]
        return (v > thresh) if op == '>' else (v >= thresh)

    criteria = {
        'H1 PF > 1.20':       chk(h1, 'pf',         1.20),
        'H1 Expectancy > 0':  chk(h1, 'expectancy',  0),
        'H1 Net Return > 0':  chk(h1, 'net_return',  0),
        'H2 PF > 1.20':       chk(h2, 'pf',         1.20),
        'H2 Expectancy > 0':  chk(h2, 'expectancy',  0),
        'H2 Net Return > 0':  chk(h2, 'net_return',  0),
    }
    passed_all = all(criteria.values())

    lines += ["", "### Success Criterion Checklist", ""]
    for name, ok in criteria.items():
        lines.append(f"- {'[x]' if ok else '[ ]'} {name}")

    if passed_all:
        lines += [
            "",
            "> [!IMPORTANT]",
            "> **PORTFOLIO PASSED** — The combined ATR Expansion portfolio meets all success criteria.",
            "> The density problem is solved through additional instruments while edge quality is preserved.",
        ]
    else:
        lines += [
            "",
            "> [!WARNING]",
            "> **PORTFOLIO FAILED** — The combined portfolio did not meet one or more success criteria.",
        ]

    lines += [
        "",
        "---",
        "",
        "## 3. Instrument-Level Analysis",
        "",
    ]

    for (coin, _, tf_d) in [('BTC','','4H'), ('BTC','','1H'), ('ETH','','4H'), ('ETH','','1H')]:
        sub = df_ind[(df_ind['coin'] == coin) & (df_ind['timeframe'] == tf_d)]
        if sub.empty:
            continue
        lines.append(f"### {coin} {tf_d}")
        for rr in sorted(sub['rr'].unique()):
            rr_sub = sub[sub['rr'] == rr]
            status = rr_sub['validation_status'].iloc[0]
            lines.append(f"*   **RR={rr}** (`{status}`):")
            for _, row in rr_sub.iterrows():
                lines.append(
                    f"    *   *{row['period']}*: "
                    f"{row['trades']} trades | PF: {row['pf']:.2f} | "
                    f"Net Return: {row['net_return']:.2f}%"
                )
        lines.append("")

    lines += [
        "---",
        "",
        "## 4. Synthesis",
        "",
        "### Research Question",
        "Can the ATR Expansion family solve its density problem through additional liquid instruments "
        "and timeframes while preserving edge quality?",
        "",
        "### Answer",
    ]

    if passed_all:
        lines += [
            "**Yes.** Adding BTC 1H and ETH instruments to the BTC 4H base increased combined trade density",
            "to a deployable level while the portfolio-level PF, Expectancy, and Net Return remained positive",
            "across both holdout periods. The density problem identified in Phase 15B is solved.",
            "",
            "**Phase 15D Recommendation**: Build a live-ready multi-instrument portfolio engine that",
            "allocates capital across the passing ATR Expansion configurations with proper position sizing.",
        ]
    else:
        lines += [
            "**Partially.** Adding instruments increased total trade frequency, but the quality metrics",
            "(PF / Expectancy / Net Return) did not consistently hold above the success thresholds across",
            "both holdout periods for the combined portfolio.",
            "",
            "**Recommended Next Steps**:",
            "1. Isolate only BTC 4H and BTC 1H in the portfolio (remove instruments with edge decay).",
            "2. Test a stricter volume filter on ETH entries to reduce false breakouts.",
            "3. Consider an EMA trend filter (e.g. price > EMA 50) to restrict signals to trending regimes.",
        ]

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
