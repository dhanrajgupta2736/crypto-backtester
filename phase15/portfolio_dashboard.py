"""
Phase 15G — Portfolio Paper Trading Dashboard
=============================================
Reads live/ CSV and JSON files and displays a refreshing terminal dashboard.
Run independently of the main engine (read-only, never writes state).

Usage:
    python phase15/portfolio_dashboard.py           # Refresh every 30s
    python phase15/portfolio_dashboard.py --once    # Print once and exit
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_DIR = os.path.join(BASE_DIR, 'live')

STATE_PATH   = os.path.join(LIVE_DIR, 'portfolio_state.json')
TRADE_LOG    = os.path.join(LIVE_DIR, 'portfolio_trade_log.csv')
METRICS_CSV  = os.path.join(LIVE_DIR, 'portfolio_metrics.csv')
SLIPPAGE_CSV = os.path.join(LIVE_DIR, 'slippage_audit.csv')
DRIFT_CSV    = os.path.join(LIVE_DIR, 'drift_alerts.csv')

REFRESH_SECS  = 30
INITIAL_EQ    = 10_000.0
RESEARCH_PF   = 1.40
RESEARCH_EXP  = 0.246
RESEARCH_WR   = 44.4   # percent


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _load_csv(path) -> pd.DataFrame:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _bar(value, min_v, max_v, width=20, char='█', fill='░'):
    """Simple ASCII bar chart segment."""
    clamped = max(min_v, min(max_v, value))
    filled  = int((clamped - min_v) / (max_v - min_v + 1e-9) * width)
    return char * filled + fill * (width - filled)


def _color(text, code):
    """ANSI color wrapper."""
    return f"\033[{code}m{text}\033[0m"


def _green(t):  return _color(t, '92')
def _red(t):    return _color(t, '91')
def _yellow(t): return _color(t, '93')
def _cyan(t):   return _color(t, '96')
def _bold(t):   return _color(t, '1')
def _dim(t):    return _color(t, '2')


def render(once: bool = False):
    state   = _load_json(STATE_PATH)
    trades  = _load_csv(TRADE_LOG)
    metrics = _load_csv(METRICS_CSV)
    slips   = _load_csv(SLIPPAGE_CSV)
    drifts  = _load_csv(DRIFT_CSV)

    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    equity  = state.get('equity', INITIAL_EQ)
    peak_eq = state.get('peak_equity', equity)
    cur_dd  = (peak_eq - equity) / peak_eq * 100 if peak_eq > 0 else 0.0
    net_ret = (equity / INITIAL_EQ - 1) * 100

    positions = state.get('positions', {})
    last_px   = state.get('last_price', {})

    n_trades = len(trades) if not trades.empty else 0

    # ── Header ────────────────────────────────────────────────────────────────
    os.system('cls' if os.name == 'nt' else 'clear')
    print(_bold(_cyan("╔══════════════════════════════════════════════════════════════╗")))
    print(_bold(_cyan("║     Phase 15G · ATR Expansion Portfolio Dashboard            ║")))
    print(_bold(_cyan(f"║     {now_str:<55}║")))
    print(_bold(_cyan("╚══════════════════════════════════════════════════════════════╝")))
    print()

    # ── Equity & Drawdown ─────────────────────────────────────────────────────
    eq_color = _green if net_ret >= 0 else _red
    dd_color = _red if cur_dd > 20 else (_yellow if cur_dd > 10 else _green)

    print(_bold("═══  PORTFOLIO EQUITY  ═══════════════════════════════════════════"))
    print(f"  Current Equity  : {eq_color(_bold(f'${equity:,.2f}'))}")
    print(f"  Starting Equity : ${INITIAL_EQ:,.2f}")
    print(f"  Net Return      : {eq_color(f'{net_ret:+.2f}%')}")
    print(f"  Peak Equity     : ${peak_eq:,.2f}")
    print(f"  Current DD      : {dd_color(f'{cur_dd:.2f}%')}  {_bar(cur_dd, 0, 40)}")
    cb_status = "HALVED" if state.get('risk_halved') else ("HALTED" if not state.get('trading_allowed', True) else "NORMAL")
    cb_color  = _red if cb_status == "HALTED" else (_yellow if cb_status == "HALVED" else _green)
    print(f"  Circuit Breaker : {cb_color(_bold(cb_status))}")
    print()

    # ── Open Positions ────────────────────────────────────────────────────────
    print(_bold("═══  OPEN POSITIONS  ═════════════════════════════════════════════"))
    if positions:
        print(f"  {'Trade ID':<28} {'Side':<6} {'Entry':>10} {'Stop':>10} {'TP':>10} {'Unrl R':>8}")
        print("  " + "─" * 72)
        for tid, pos in positions.items():
            side    = pos.get('side', '?')
            ep      = pos.get('entry_price', 0.0)
            sl      = pos.get('stop_price', 0.0)
            tp      = pos.get('target_price', 0.0)
            sym     = pos.get('symbol', '?')
            cur_px  = last_px.get(sym, ep)
            dist    = abs(ep - sl)
            if side == 'long':
                unrl_r = (cur_px - ep) / dist if dist > 0 else 0.0
            else:
                unrl_r = (ep - cur_px) / dist if dist > 0 else 0.0
            r_color = _green if unrl_r >= 0 else _red
            side_str = (_green("LONG") if side == 'long' else _red("SHORT"))
            print(f"  {tid:<28} {side_str:<15} {ep:>10.4f} {sl:>10.4f} {tp:>10.4f} "
                  f"{r_color(f'{unrl_r:>+7.2f}R')}")
    else:
        print(f"  {_dim('No open positions.')}")
    print()

    # ── Performance vs Research Baseline ──────────────────────────────────────
    print(_bold("═══  LIVE PERFORMANCE vs RESEARCH BASELINE  ══════════════════════"))
    if not metrics.empty:
        last_m = metrics.iloc[-1]
        live_pf   = float(last_m.get('profit_factor', 0))
        live_wr   = float(last_m.get('win_rate', 0))
        live_exp  = float(last_m.get('expectancy', 0))
        live_md   = float(last_m.get('max_drawdown', 0))
        live_shp  = float(last_m.get('sharpe_approx', 0))
        live_avgr = float(last_m.get('avg_R', 0))

        def cmp(live, base, higher_better=True):
            if higher_better:
                return _green(f'{live:.3f}') if live >= base * 0.8 else _red(f'{live:.3f}')
            return _green(f'{live:.3f}') if live <= base * 1.2 else _red(f'{live:.3f}')

        print(f"  {'Metric':<22} {'Live':>10} {'Research':>10} {'Status':>10}")
        print("  " + "─" * 54)
        print(f"  {'Profit Factor':<22} {cmp(live_pf, RESEARCH_PF):>20} {RESEARCH_PF:>10.3f} "
              f"{'  ✅' if live_pf >= 1.0 else '  ❌'}")
        print(f"  {'Expectancy (R)':<22} {cmp(live_exp, RESEARCH_EXP):>20} {RESEARCH_EXP:>10.3f} "
              f"{'  ✅' if live_exp >= 0 else '  ❌'}")
        print(f"  {'Win Rate %':<22} {cmp(live_wr, RESEARCH_WR):>20} {RESEARCH_WR:>10.1f} "
              f"{'  ✅' if live_wr >= 35 else '  ❌'}")
        print(f"  {'Max Drawdown %':<22} {_red(f'{live_md:.2f}') if live_md > 25 else _green(f'{live_md:.2f}'):>20} {'N/A':>10}")
        print(f"  {'Sharpe (approx)':<22} {live_shp:>10.3f} {'N/A':>10}")
        print(f"  {'Avg R/trade':<22} {live_avgr:>10.4f} {RESEARCH_EXP:>10.3f}")
        print(f"  {'Total Trades':<22} {n_trades:>10}")
    else:
        print(f"  {_dim('No closed trades yet.')}")
    print()

    # ── Recent Closed Trades ──────────────────────────────────────────────────
    print(_bold("═══  RECENT CLOSED TRADES (last 8)  ══════════════════════════════"))
    if not trades.empty:
        show = trades.tail(8)
        print(f"  {'Symbol':<8} {'TF':<5} {'Side':<6} {'R':>7} {'PnL':>10} {'Exit Reason':<22}")
        print("  " + "─" * 62)
        for _, row in show.iterrows():
            r   = float(row.get('realized_r', 0))
            pnl = float(row.get('realized_pnl', 0))
            s   = str(row.get('side', ''))
            col = _green if r > 0 else _red
            print(f"  {str(row.get('symbol','')):<8} {str(row.get('timeframe','')):<5} "
                  f"{s:<6} {col(f'{r:+.2f}R'):>17} {col(f'${pnl:+.2f}'):>17} "
                  f"{str(row.get('exit_reason','')):<22}")
    else:
        print(f"  {_dim('No closed trades yet.')}")
    print()

    # ── Slippage Statistics ───────────────────────────────────────────────────
    print(_bold("═══  SLIPPAGE AUDIT (Phase 15F Critical Check)  ══════════════════"))
    if not slips.empty and 'stop_slippage_r' in slips.columns:
        avg_slip   = float(slips['stop_slippage_r'].mean())
        worst_slip = float(slips['stop_slippage_r'].max())
        roll20     = float(slips['stop_slippage_r'].tail(20).mean()) if len(slips) >= 5 else avg_slip
        n_sl       = len(slips)
        slip_color = _red if avg_slip > 0.50 else (_yellow if avg_slip > 0.25 else _green)
        print(f"  Stop-loss exits    : {n_sl}")
        print(f"  Avg slippage (R)   : {slip_color(f'{avg_slip:.4f}R')}  (threshold: 0.50R)")
        print(f"  Worst slippage (R) : {_red(f'{worst_slip:.4f}R') if worst_slip > 0.5 else f'{worst_slip:.4f}R'}")
        print(f"  Rolling 20-trade   : {slip_color(f'{roll20:.4f}R')}")
    else:
        print(f"  {_dim('No stop-loss exits recorded yet.')}")
    print()

    # ── Drift Alerts ──────────────────────────────────────────────────────────
    print(_bold("═══  DRIFT ALERTS  ════════════════════════════════════════════════"))
    if not drifts.empty:
        recent_alerts = drifts.tail(5)
        for _, row in recent_alerts.iterrows():
            sev = str(row.get('severity', 'INFO'))
            col = _red if sev == 'HIGH' else _yellow
            print(f"  {col(_bold(f'[{sev}]'))} {row.get('timestamp','')} | "
                  f"{row.get('metric','')} = {row.get('live','')} "
                  f"(threshold={row.get('threshold','')})")
    else:
        print(f"  {_green('✅ No drift alerts — live metrics within research bounds.')}")
    print()

    # ── Footer ────────────────────────────────────────────────────────────────
    refresh_msg = f"Auto-refresh every {REFRESH_SECS}s · Ctrl+C to exit" if not once else "One-shot display"
    print(_dim(f"  {refresh_msg} · Live data: {LIVE_DIR}"))
    print(_bold(_cyan("═" * 66)))


def main():
    parser = argparse.ArgumentParser(description='Phase 15G Portfolio Dashboard')
    parser.add_argument('--once', action='store_true', help='Print once and exit')
    parser.add_argument('--refresh', type=int, default=REFRESH_SECS,
                        help=f'Refresh interval in seconds (default: {REFRESH_SECS})')
    args = parser.parse_args()

    if args.once:
        render(once=True)
        return

    print("Starting dashboard... Press Ctrl+C to exit.")
    try:
        while True:
            render()
            time.sleep(args.refresh)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")


if __name__ == '__main__':
    main()
