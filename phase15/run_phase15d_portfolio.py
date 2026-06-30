"""
Phase 15D — Portfolio Construction Validation
==============================================
Surviving ATR Expansion candidates:
  BTC 4H  RR=2.0
  ETH 1H  RR=2.0
  ETH 4H  RR=2.0

Builds a REAL single-account portfolio:
  - Risk per trade = 2% of current portfolio equity (dynamic)
  - Simultaneous positions allowed
  - Single equity curve across all instruments
  - Full cost model: fees, slippage, funding

New metrics vs Phase 15C:
  CAGR, Ulcer Index, Risk of Ruin, Avg Concurrent Positions
"""

import os
import sys
import pandas as pd
import numpy as np
import vectorbt as vbt
from vectorbt.portfolio.enums import OppositeEntryMode, StopExitMode, StopExitPrice

# Allow import from parent directory when run from phase15/ subfolder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_research_framework import (
    load_symbol_timeframe,
    build_signals,
    build_vbt_signals,
    load_funding_history,
    calculate_daily_sharpe,
    INITIAL_BALANCE,
    LEVERAGE,
    get_slippage_rate,
    get_exit_fee_rate,
)

# ─── Configuration ────────────────────────────────────────────────────────────
RISK_PCT  = 0.02    # 2% of current equity per trade
FEE_ENTRY = 0.00045 # maker entry fee
FEE_TAKER = 0.00045 # taker entry fee (same exchange)

CANDIDATES = [
    ('BTC', '4h', '4H', 2.0),
    ('ETH', '1h', '1H', 2.0),
    ('ETH', '4h', '4H', 2.0),
]

PERIODS = {
    'Selection': (
        pd.Timestamp('2023-01-01 00:00:00', tz='UTC'),
        pd.Timestamp('2024-12-31 23:59:59', tz='UTC'),
        2.0,   # years
    ),
    'Holdout_1': (
        pd.Timestamp('2025-01-01 00:00:00', tz='UTC'),
        pd.Timestamp('2025-12-31 23:59:59', tz='UTC'),
        1.0,
    ),
    'Holdout_2': (
        pd.Timestamp('2026-01-01 00:00:00', tz='UTC'),
        pd.Timestamp('2026-06-19 23:59:59', tz='UTC'),
        0.465,  # ~6 months
    ),
}

TIMEFRAME_DELTAS = {
    '1h': pd.Timedelta(hours=1),
    '4h': pd.Timedelta(hours=4),
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 1: Extract raw trade records from VBT for one instrument/period
# ═══════════════════════════════════════════════════════════════════════════════
def extract_raw_trades(coin, tf_mapped, rr, df_full, signals_full,
                       start_dt, end_dt):
    """
    Returns a list of raw trade dicts ready for portfolio simulation.
    Each dict contains all info needed for dynamic sizing and cost computation.
    """
    mask      = (df_full['timestamp'] >= start_dt) & (df_full['timestamp'] <= end_dt)
    df_slice  = df_full[mask]
    sig_slice = signals_full[mask]

    if len(df_slice) < 10 or sig_slice['side'].eq('').all():
        return []

    try:
        entries_s, short_entries_s, sl_stop_s, tp_stop_all, sl_pct_map = build_vbt_signals(
            df_slice, sig_slice, [rr]
        )
    except Exception as e:
        print(f'  [!] build_vbt_signals error {coin} {tf_mapped} RR={rr}: {e}')
        return []

    if not entries_s.any() and not short_entries_s.any():
        return []

    exits_s       = pd.Series(False, index=df_slice.index); exits_s.iloc[-1] = True
    short_exits_s = pd.Series(False, index=df_slice.index); short_exits_s.iloc[-1] = True
    order_price   = df_slice['open'].copy(); order_price.iloc[-1] = df_slice['close'].iloc[-1]

    try:
        pf_vbt = vbt.Portfolio.from_signals(
            close=df_slice['close'], entries=entries_s, exits=exits_s,
            short_entries=short_entries_s, short_exits=short_exits_s,
            size=1.0, size_type='amount', price=order_price,
            open=df_slice['open'], high=df_slice['high'], low=df_slice['low'],
            sl_stop=sl_stop_s, tp_stop=tp_stop_all,
            fees=0.0005, slippage=0.0002, init_cash=1_000_000.0,
            accumulate=False, upon_opposite_entry=OppositeEntryMode.Ignore,
            stop_exit_price=StopExitPrice.StopMarket,
            upon_stop_exit=StopExitMode.Close,
            freq=TIMEFRAME_DELTAS[tf_mapped],
        )
    except Exception as e:
        print(f'  [!] VBT error {coin} {tf_mapped}: {e}')
        return []

    trades_df = pf_vbt.trades.records_readable
    if trades_df.empty:
        return []

    raw_trades = []
    for _, row in trades_df.iterrows():
        entry_idx = row['Entry Timestamp']
        exit_idx  = row['Exit Timestamp']
        sl_pct    = sl_pct_map.get(entry_idx)
        if sl_pct is None or sl_pct <= 0:
            continue

        ep         = float(row['Avg Entry Price'])
        exit_price = float(row['Avg Exit Price'])
        if ep <= 0:
            continue

        # Look up actual wall-clock timestamps from df_slice
        try:
            entry_time = df_slice.loc[entry_idx, 'timestamp']
            exit_time  = df_slice.loc[exit_idx,  'timestamp']
        except KeyError:
            continue

        raw_trades.append({
            'symbol':      coin,
            'timeframe':   tf_mapped,
            'rr':          rr,
            'entry_price': ep,
            'exit_price':  exit_price,
            'direction':   row['Direction'],
            'sl_pct':      sl_pct,
            'entry_time':  entry_time,
            'exit_time':   exit_time,
        })

    return raw_trades


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 2: Portfolio simulation — dynamic 2% risk, single equity curve
# ═══════════════════════════════════════════════════════════════════════════════
def simulate_portfolio_dynamic(raw_trades, funding_by_symbol):
    """
    Runs a single-account portfolio simulation over a merged list of raw trades.

    Sizing rule: risk = RISK_PCT * current_equity per trade.
    Simultaneous positions are allowed; equity updates only at exit.
    Trades are processed in exit-time order so equity state is correct.
    """
    if not raw_trades:
        return [], INITIAL_BALANCE, [INITIAL_BALANCE], []

    sorted_trades = sorted(raw_trades, key=lambda t: t['exit_time'])

    balance      = INITIAL_BALANCE
    equity_curve = [balance]
    exit_dates   = []
    sim_trades   = []
    ruined       = False

    for trade in sorted_trades:
        if balance <= 0:
            ruined = True
            break

        coin       = trade['symbol']
        ep         = trade['entry_price']
        exit_price = trade['exit_price']
        direction  = trade['direction']
        sl_pct     = trade['sl_pct']
        rr         = trade['rr']
        entry_time = trade['entry_time']
        exit_time  = trade['exit_time']

        slippage_rate   = get_slippage_rate(coin)
        exit_fee_rate   = get_exit_fee_rate(direction, ep, exit_price, sl_pct, rr)
        sizing_friction = ep * (FEE_ENTRY + 0.00045 + 2 * slippage_rate)

        # Dynamic risk sizing — 2% of current equity
        risk_amount = RISK_PCT * balance
        dist        = ep * sl_pct
        risk_qty    = risk_amount / (dist + sizing_friction)
        max_qty     = (balance * LEVERAGE) / ep

        # Ruin check — if leverage is exhausted we cannot size even 30% of target
        if max_qty < 0.3 * risk_qty:
            ruined = True
            break

        qty = min(risk_qty, max_qty)

        # Gross P&L
        if direction in ('Long', 1, 1.0):
            gross_pnl        = (exit_price - ep) * qty
            funding_mult     = -1.0
        else:
            gross_pnl        = (ep - exit_price) * qty
            funding_mult     = 1.0

        # Transaction costs
        entry_fee      = qty * ep         * FEE_ENTRY
        exit_fee       = qty * exit_price * exit_fee_rate
        entry_slip     = qty * ep         * slippage_rate
        exit_slip      = 0.0 if exit_fee_rate == 0.00015 else qty * exit_price * slippage_rate

        # Funding carry
        funding_pnl = 0.0
        fdf = funding_by_symbol.get(coin)
        if fdf is not None and not fdf.empty:
            mask = (fdf['timestamp'] > entry_time) & (fdf['timestamp'] <= exit_time)
            sum_funding = fdf.loc[mask, 'funding_rate'].sum()
            funding_pnl = funding_mult * qty * ep * sum_funding
        else:
            duration_h  = (exit_time - entry_time).total_seconds() / 3600.0
            sum_funding = duration_h * 0.0001      # fallback: 0.01%/hr
            funding_pnl = funding_mult * qty * ep * sum_funding

        net_pnl  = gross_pnl - entry_fee - exit_fee - entry_slip - exit_slip + funding_pnl
        balance += net_pnl
        balance  = max(0.0, balance)

        equity_curve.append(balance)
        exit_dates.append(exit_time)

        duration_h   = (exit_time - entry_time).total_seconds() / 3600.0
        initial_risk = qty * (ep * sl_pct)
        r_mult       = net_pnl / initial_risk if initial_risk > 0 else 0.0

        sim_trades.append({
            'pnl':            net_pnl,
            'direction':      direction,
            'symbol':         coin,
            'timeframe':      trade['timeframe'],
            'entry_price':    ep,
            'exit_price':     exit_price,
            'qty':            qty,
            'entry_date':     entry_time,
            'exit_date':      exit_time,
            'r_multiple':     r_mult,
            'duration_hours': duration_h,
        })

        if balance <= 0:
            ruined = True
            break

    return sim_trades, balance, equity_curve, exit_dates


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 3: Metrics computation (extends Phase 15C with new metrics)
# ═══════════════════════════════════════════════════════════════════════════════
def compute_portfolio_metrics(sim_trades, final_balance, equity_curve, exit_dates, years):
    n = len(sim_trades)

    empty = {
        'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0,
        'expectancy': 0.0, 'cagr': 0.0, 'max_drawdown': 0.0,
        'ulcer_index': 0.0, 'risk_of_ruin': 100.0,
        'avg_concurrent': 0.0, 'max_concurrent': 0,
        'net_return': 0.0,
    }
    if n == 0:
        return empty

    pnls    = [t['pnl'] for t in sim_trades]
    wins    = [p for p in pnls if p > 0]
    losses  = [p for p in pnls if p <= 0]

    win_rate  = len(wins) / n * 100.0
    avg_win   = np.mean(wins)   if wins   else 0.0
    avg_loss  = np.mean(losses) if losses else 0.0

    pf = (abs(sum(wins)) / abs(sum(losses))) if losses and sum(losses) != 0 else (999.9 if wins else 1.0)

    # R-multiple expectancy
    wins_r   = [t['r_multiple'] for t in sim_trades if t['pnl'] > 0]
    losses_r = [abs(t['r_multiple']) for t in sim_trades if t['pnl'] <= 0]
    avg_win_r  = np.mean(wins_r)   if wins_r   else 0.0
    avg_loss_r = np.mean(losses_r) if losses_r else 0.0
    wr_dec     = win_rate / 100.0
    expectancy = (wr_dec * avg_win_r) - ((1 - wr_dec) * avg_loss_r)

    # CAGR
    net_return = (final_balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100.0
    if final_balance > 0 and years > 0:
        cagr = ((final_balance / INITIAL_BALANCE) ** (1.0 / years) - 1.0) * 100.0
    else:
        cagr = -100.0

    # Max Drawdown
    eq_series = pd.Series(equity_curve)
    running_max = eq_series.cummax()
    dd_series = (eq_series - running_max) / running_max.replace(0, 1e-9)
    max_dd = abs(dd_series.min()) * 100.0

    # Ulcer Index — RMS of % drawdown from running peak
    pct_dd_sq = (dd_series ** 2).values
    ulcer_index = float(np.sqrt(np.mean(pct_dd_sq)) * 100.0)

    # Sharpe (daily)
    sharpe = calculate_daily_sharpe(equity_curve, exit_dates)

    # Risk of Ruin (classical formula, N = 1/RISK_PCT risk units in bankroll)
    N = 1.0 / RISK_PCT   # = 50 units
    edge = (wr_dec * avg_win_r) - ((1 - wr_dec) * avg_loss_r)
    if edge >= 1.0:
        ror = 0.0
    elif edge <= -1.0:
        ror = 100.0
    else:
        ror = max(0.0, min(100.0, ((1 - edge) / (1 + edge)) ** N * 100.0))

    # Concurrent Positions — sweep entry/exit events
    events = []
    for t in sim_trades:
        events.append((t['entry_date'], +1, t['symbol']))
        events.append((t['exit_date'],  -1, t['symbol']))
    events.sort(key=lambda x: x[0])

    count = 0
    counts_over_time = []
    for _, delta, _ in events:
        count = max(0, count + delta)
        counts_over_time.append(count)

    avg_concurrent = float(np.mean(counts_over_time)) if counts_over_time else 0.0
    max_concurrent = int(max(counts_over_time)) if counts_over_time else 0

    return {
        'trades':         n,
        'win_rate':       round(win_rate,    2),
        'pf':             round(pf,          2),
        'sharpe':         round(sharpe,      2),
        'expectancy':     round(expectancy,  4),
        'cagr':           round(cagr,        2),
        'max_drawdown':   round(max_dd,      2),
        'ulcer_index':    round(ulcer_index, 4),
        'risk_of_ruin':   round(ror,         4),
        'avg_concurrent': round(avg_concurrent, 2),
        'max_concurrent': max_concurrent,
        'net_return':     round(net_return,  2),
    }


def compute_per_instrument_stats(sim_trades):
    """Count trades and win rates per instrument for the report."""
    stats = {}
    for t in sim_trades:
        key = f"{t['symbol']} {t['timeframe'].upper()}"
        if key not in stats:
            stats[key] = {'trades': 0, 'wins': 0}
        stats[key]['trades'] += 1
        if t['pnl'] > 0:
            stats[key]['wins'] += 1
    result = {}
    for k, v in stats.items():
        result[k] = {
            'trades':   v['trades'],
            'win_rate': round(v['wins'] / v['trades'] * 100, 1) if v['trades'] > 0 else 0.0,
        }
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 4: Report generation
# ═══════════════════════════════════════════════════════════════════════════════
def generate_report(period_results, instrument_breakdown):
    lines = [
        '# Phase 15D Portfolio Validation Report',
        '',
        '**Strategy**: `VE_3_ATR_EXPANSION`',
        '**Portfolio**: BTC 4H (RR=2.0) + ETH 1H (RR=2.0) + ETH 4H (RR=2.0)',
        '**Risk per Trade**: 2% of current portfolio equity (dynamic)',
        '**Simultaneous Positions**: Allowed',
        '**Periods**: Selection 2023-2024 | Holdout 1 (2025) | Holdout 2 (2026)',
        '',
        '---',
        '',
        '## 1. Portfolio Performance by Period',
        '',
        '| Period | Trades | Win Rate | PF | Sharpe | Expectancy | CAGR | Max DD | Ulcer Index | Risk of Ruin | Avg Concurrent |',
        '| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |',
    ]

    for period_name, m in period_results.items():
        lines.append(
            f"| {period_name} | {m['trades']} | {m['win_rate']}% "
            f"| {m['pf']:.2f} | {m['sharpe']:.2f} | {m['expectancy']:.4f} "
            f"| {m['cagr']:.2f}% | {m['max_drawdown']:.2f}% "
            f"| {m['ulcer_index']:.4f} | {m['risk_of_ruin']:.4f}% "
            f"| {m['avg_concurrent']:.2f} |"
        )

    # Success criteria check
    h1 = period_results.get('Holdout_1', {})
    h2 = period_results.get('Holdout_2', {})

    criteria = {
        'H1 PF > 1.20':        h1.get('pf', 0) > 1.20,
        'H1 Expectancy > 0':   h1.get('expectancy', -1) > 0,
        'H1 Net Return > 0':   h1.get('net_return', -1) > 0,
        'H2 PF > 1.20':        h2.get('pf', 0) > 1.20,
        'H2 Expectancy > 0':   h2.get('expectancy', -1) > 0,
        'H2 Net Return > 0':   h2.get('net_return', -1) > 0,
    }
    passed_all = all(criteria.values())

    lines += [
        '',
        '## 2. Success Criteria',
        '',
    ]
    for name, ok in criteria.items():
        lines.append(f"- {'[x]' if ok else '[ ]'} {name}")

    if passed_all:
        lines += [
            '',
            '> [!IMPORTANT]',
            '> **PORTFOLIO PASSED** — All success criteria met. The ATR Expansion family',
            '> demonstrates robust, deployable edge as a real multi-instrument portfolio.',
        ]
    else:
        lines += [
            '',
            '> [!WARNING]',
            '> **PORTFOLIO FAILED** — One or more success criteria not met.',
        ]

    lines += ['', '---', '', '## 3. Instrument Contribution by Period', '']

    for period_name, breakdown in instrument_breakdown.items():
        lines.append(f'### {period_name}')
        lines.append('')
        lines.append('| Instrument | Trades | Win Rate |')
        lines.append('| :--- | :---: | :---: |')
        for inst, stats in sorted(breakdown.items()):
            lines.append(f"| {inst} | {stats['trades']} | {stats['win_rate']}% |")
        lines.append('')

    lines += [
        '---',
        '',
        '## 4. Key Observations',
        '',
        '### Risk of Ruin Interpretation',
        'Risk of Ruin is computed using the classical formula:',
        '```',
        'RoR = ((1 - edge) / (1 + edge))^N',
        'where edge = win_rate * avg_win_R - loss_rate * avg_loss_R',
        '      N    = 1 / risk_pct = 50 units of risk in the starting bankroll',
        '```',
        'Values < 5% are considered acceptable for live deployment.',
        '',
        '### Ulcer Index Interpretation',
        'Ulcer Index weights prolonged drawdowns more severely than Max Drawdown.',
        'Values < 5 indicate low stress on the account; values > 15 indicate high prolonged pain.',
        '',
        '### Average Concurrent Positions',
        'Indicates how many positions were open simultaneously on average.',
        'Higher values increase correlated-loss risk during adverse regimes.',
        '',
        '### Dynamic Sizing Note',
        'Each trade is sized at 2% of equity AT THE TIME OF THE PREVIOUS EXIT.',
        'A winning run compounds gains; a losing run reduces exposure naturally.',
        'This is the most realistic sizing model for live portfolio deployment.',
    ]

    return '\n'.join(lines) + '\n'


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print('Phase 15D — Portfolio Construction Validation')
    print(f'Candidates: {[(c, tf, rr) for c, tf, _, rr in CANDIDATES]}')
    print(f'Periods   : {list(PERIODS.keys())}')
    print(f'Risk/Trade: {RISK_PCT*100:.0f}% of current equity\n')

    # Pre-load all instrument data and signals (once, across all periods)
    print('Loading instrument data and signals...')
    instrument_data = {}   # (coin, tf_mapped) -> (df_full, signals_full, funding_df)
    for coin, tf_mapped, tf_display, rr in CANDIDATES:
        key = (coin, tf_mapped)
        if key in instrument_data:
            continue
        df_full = load_symbol_timeframe(coin, tf_mapped)
        if df_full is None or df_full.empty:
            print(f'  [!] Missing data: {coin} {tf_mapped}. Aborting.')
            return
        try:
            signals_full = build_signals(df_full, 'Volatility_Expansion', coin, tf_mapped,
                                         mode='VE_3_ATR_EXPANSION')
        except Exception as e:
            print(f'  [!] Signal error {coin} {tf_mapped}: {e}')
            return
        funding_df = load_funding_history(coin)
        instrument_data[key] = (df_full, signals_full, funding_df)
        print(f'  Loaded {coin} {tf_display} — {len(df_full)} bars')

    # Pre-load funding data by symbol name for portfolio simulator
    funding_by_symbol = {}
    for coin, tf_mapped, _, _ in CANDIDATES:
        if coin not in funding_by_symbol:
            funding_by_symbol[coin] = instrument_data[(coin, tf_mapped)][2]

    print()

    # Run period-by-period
    period_results      = {}
    instrument_breakdown = {}
    csv_rows            = []

    for period_name, (start_dt, end_dt, years) in PERIODS.items():
        print(f'--- Period: {period_name} ({start_dt.date()} → {end_dt.date()}) ---')

        # Collect raw trades for all 3 instruments in this period
        all_raw = []
        per_instrument_counts = {}

        for coin, tf_mapped, tf_display, rr in CANDIDATES:
            df_full, signals_full, _ = instrument_data[(coin, tf_mapped)]
            raw = extract_raw_trades(coin, tf_mapped, rr, df_full, signals_full,
                                     start_dt, end_dt)
            label = f'{coin} {tf_display}'
            per_instrument_counts[label] = len(raw)
            all_raw.extend(raw)
            print(f'  {label} RR={rr}: {len(raw)} raw trades extracted')

        print(f'  Total raw trades this period: {len(all_raw)}')

        if not all_raw:
            print(f'  [!] No trades for {period_name}. Skipping.')
            period_results[period_name] = {k: 0 for k in [
                'trades', 'win_rate', 'pf', 'sharpe', 'expectancy',
                'cagr', 'max_drawdown', 'ulcer_index', 'risk_of_ruin',
                'avg_concurrent', 'max_concurrent', 'net_return',
            ]}
            continue

        # Portfolio simulation
        sim_trades, final_bal, equity_curve, exit_dates = simulate_portfolio_dynamic(
            all_raw, funding_by_symbol
        )

        metrics = compute_portfolio_metrics(sim_trades, final_bal, equity_curve,
                                            exit_dates, years)
        period_results[period_name] = metrics

        # Per-instrument breakdown from sim_trades
        inst_stats = compute_per_instrument_stats(sim_trades)
        instrument_breakdown[period_name] = inst_stats

        csv_rows.append({'period': period_name, **metrics})

        # Console output
        print(f'  Simulated: {metrics["trades"]} trades | '
              f'PF={metrics["pf"]:.2f} | Sharpe={metrics["sharpe"]:.2f} | '
              f'Exp={metrics["expectancy"]:.4f}')
        print(f'  CAGR={metrics["cagr"]:.2f}% | MaxDD={metrics["max_drawdown"]:.2f}% | '
              f'UlcerIdx={metrics["ulcer_index"]:.4f} | RoR={metrics["risk_of_ruin"]:.4f}%')
        print(f'  AvgConcurrent={metrics["avg_concurrent"]:.2f} | '
              f'MaxConcurrent={metrics["max_concurrent"]} | '
              f'NetReturn={metrics["net_return"]:.2f}%')
        for inst, st in inst_stats.items():
            print(f'    [{inst}] {st["trades"]} trades | WR={st["win_rate"]}%')
        print()

    # ── Output files ──────────────────────────────────────────────────────────
    out_dir = os.path.dirname(os.path.abspath(__file__))  # same folder as this script
    os.makedirs(out_dir, exist_ok=True)

    csv_path    = os.path.join(out_dir, 'portfolio_validation.csv')
    report_path = os.path.join(out_dir, 'portfolio_validation_report.md')

    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    print(f'Saved {csv_path}')

    report = generate_report(period_results, instrument_breakdown)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'Saved {report_path}')

    # ── Final summary ─────────────────────────────────────────────────────────
    print()
    print('=' * 70)
    print('  PHASE 15D — PORTFOLIO SUMMARY')
    print('=' * 70)
    for period_name, m in period_results.items():
        print(f'  {period_name:<12}: '
              f'T={m["trades"]:<4} PF={m["pf"]:<5.2f} '
              f'Sharpe={m["sharpe"]:<5.2f} CAGR={m["cagr"]:>7.2f}% '
              f'DD={m["max_drawdown"]:>6.2f}% RoR={m["risk_of_ruin"]:.4f}%')

    h1 = period_results.get('Holdout_1', {})
    h2 = period_results.get('Holdout_2', {})
    passed = (h1.get('pf', 0) > 1.20 and h1.get('expectancy', -1) > 0
              and h1.get('net_return', -1) > 0
              and h2.get('pf', 0) > 1.20 and h2.get('expectancy', -1) > 0
              and h2.get('net_return', -1) > 0)
    print()
    print(f'  Portfolio Success Criterion: {"*** PASS ***" if passed else "FAIL"}')
    print('=' * 70)


if __name__ == '__main__':
    main()
