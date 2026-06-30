"""
Phase 15E — Portfolio Monte Carlo Stress Testing
=================================================
Extracts the real trade R-multiple sequence from the Phase 15D
validated portfolio (BTC 4H + ETH 1H + ETH 4H, RR=2.0) and runs
10,000 bootstrap simulations per risk level.

Simulation method: Stratified bootstrap with replacement from the
empirical R-multiple distribution. All costs are embedded in the
R-multiples extracted from the Phase 15D simulation.

Risk levels: 0.5%, 1.0%, 1.5%, 2.0%, 3.0%

Ruin definition: Equity drawdown > 80% at any point in the path.
CAGR denominator: 3.465 years (full 2023-01-01 → 2026-06-19 period).
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_research_framework import (
    load_symbol_timeframe,
    build_signals,
    load_funding_history,
    INITIAL_BALANCE,
)

# Import Phase 15D helpers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_phase15d_portfolio import (
    CANDIDATES,
    TIMEFRAME_DELTAS,
    extract_raw_trades,
    simulate_portfolio_dynamic,
)

# ─── Configuration ────────────────────────────────────────────────────────────
FULL_START  = pd.Timestamp('2023-01-01 00:00:00', tz='UTC')
FULL_END    = pd.Timestamp('2026-06-19 23:59:59', tz='UTC')
FULL_YEARS  = 3.465        # 2023-01-01 → 2026-06-19 in decimal years

N_SIMS      = 10_000       # bootstrap simulations per risk level
RUIN_DD     = 0.80         # >80% drawdown = ruin
SEED        = 42           # reproducibility

RISK_LEVELS = [0.005, 0.010, 0.015, 0.020, 0.030]

BASE_RISK   = 0.020        # used for initial trade extraction


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 1: Extract real trade R-multiples from full-period simulation
# ═══════════════════════════════════════════════════════════════════════════════
def extract_r_multiples():
    """
    Runs the Phase 15D portfolio simulation over the full historical period
    (2023–2026) and extracts the ordered list of R-multiples.
    R-multiples are post-cost (include fees, slippage, funding).
    """
    print('Loading instrument data and extracting R-multiples...')

    instrument_data  = {}
    funding_by_symbol = {}

    for coin, tf_mapped, tf_display, rr in CANDIDATES:
        key = (coin, tf_mapped)
        if key not in instrument_data:
            df_full = load_symbol_timeframe(coin, tf_mapped)
            if df_full is None or df_full.empty:
                raise RuntimeError(f'Missing data: {coin} {tf_mapped}')
            signals_full = build_signals(
                df_full, 'Volatility_Expansion', coin, tf_mapped, mode='VE_3_ATR_EXPANSION'
            )
            funding_df = load_funding_history(coin)
            instrument_data[key]  = (df_full, signals_full, funding_df)
            funding_by_symbol[coin] = funding_df
            print(f'  Loaded {coin} {tf_display}: {len(df_full)} bars')

    # Extract raw trades for the full period
    all_raw = []
    for coin, tf_mapped, tf_display, rr in CANDIDATES:
        df_full, signals_full, _ = instrument_data[(coin, tf_mapped)]
        raw = extract_raw_trades(
            coin, tf_mapped, rr, df_full, signals_full, FULL_START, FULL_END
        )
        print(f'  {coin} {tf_display} RR={rr}: {len(raw)} raw trades')
        all_raw.extend(raw)

    print(f'  Total raw trades: {len(all_raw)}')

    # Run portfolio simulation at BASE_RISK to extract R-multiples
    sim_trades, final_bal, equity_curve, exit_dates = simulate_portfolio_dynamic(
        all_raw, funding_by_symbol
    )

    r_multiples = np.array([t['r_multiple'] for t in sim_trades])
    print(f'  Simulated trades: {len(r_multiples)} | '
          f'WR={np.mean(r_multiples > 0)*100:.1f}% | '
          f'Avg R={np.mean(r_multiples):.4f} | '
          f'Med R={np.median(r_multiples):.4f}')

    return r_multiples, sim_trades


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 2: Vectorized Monte Carlo bootstrap
# ═══════════════════════════════════════════════════════════════════════════════
def run_monte_carlo(r_multiples, risk_pct, n_sims=N_SIMS, seed=SEED):
    """
    Runs N_SIMS bootstrap simulations using the R-multiple pool.

    Equity update: equity_new = equity * (1 + risk_pct * r)
    This is equivalent to risking `risk_pct` of current equity per trade.

    Returns a dict of aggregate statistics.
    """
    n_trades = len(r_multiples)
    rng      = np.random.default_rng(seed)

    # Sample all simulations at once: shape (n_sims, n_trades)
    indices    = rng.integers(0, n_trades, size=(n_sims, n_trades))
    r_matrix   = r_multiples[indices]                          # (n_sims, n_trades)

    # Equity factors per trade: clamp to prevent negative equity
    factors    = np.clip(1.0 + risk_pct * r_matrix, 1e-6, None)  # (n_sims, n_trades)

    # Equity curves (normalized to 1.0 initial)
    cum_equity = np.cumprod(factors, axis=1)                    # (n_sims, n_trades)
    equity_curves = np.hstack([np.ones((n_sims, 1)), cum_equity])  # (n_sims, n_trades+1)

    # Running max for drawdown
    running_max = np.maximum.accumulate(equity_curves, axis=1)  # (n_sims, n_trades+1)
    dd_curves   = (running_max - equity_curves) / running_max   # fractional DD

    # Max drawdown per simulation
    max_dds = dd_curves.max(axis=1)                             # (n_sims,)

    # Final equity per simulation (normalized)
    final_equity = equity_curves[:, -1]                         # (n_sims,)

    # CAGR — n_trades trades span FULL_YEARS
    cagr_arr = np.power(np.maximum(final_equity, 1e-9), 1.0 / FULL_YEARS) - 1.0

    # Losing streaks — vectorized across simulations
    is_loss = (r_matrix < 0).astype(np.int32)                  # (n_sims, n_trades)
    streak   = np.zeros((n_sims, n_trades), dtype=np.int32)
    streak[:, 0] = is_loss[:, 0]
    for j in range(1, n_trades):
        streak[:, j] = np.where(is_loss[:, j] == 1, streak[:, j-1] + 1, 0)
    max_losing_streaks = streak.max(axis=1)                     # (n_sims,)

    # Ruin: max drawdown > RUIN_DD threshold
    ruined = max_dds > RUIN_DD                                  # (n_sims,)

    # ── Aggregate statistics ──────────────────────────────────────────────────
    p_dd20   = np.mean(max_dds > 0.20) * 100.0
    p_dd30   = np.mean(max_dds > 0.30) * 100.0
    p_dd50   = np.mean(max_dds > 0.50) * 100.0
    p_ruin   = np.mean(ruined)          * 100.0

    dd_sorted = np.sort(max_dds)

    return {
        'risk_pct':           risk_pct * 100.0,
        'n_trades':           n_trades,
        'median_cagr':        round(float(np.median(cagr_arr))  * 100.0, 2),
        'pct5_cagr':          round(float(np.percentile(cagr_arr, 5))  * 100.0, 2),
        'pct95_cagr':         round(float(np.percentile(cagr_arr, 95)) * 100.0, 2),
        'dd_95':              round(float(np.percentile(max_dds, 95))  * 100.0, 2),
        'dd_99':              round(float(np.percentile(max_dds, 99))  * 100.0, 2),
        'worst_dd':           round(float(max_dds.max())                * 100.0, 2),
        'worst_losing_streak': int(max_losing_streaks.max()),
        'avg_losing_streak':   round(float(np.mean(max_losing_streaks)), 2),
        'p_dd_gt_20':          round(p_dd20, 2),
        'p_dd_gt_30':          round(p_dd30, 2),
        'p_dd_gt_50':          round(p_dd50, 2),
        'p_ruin':              round(p_ruin, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Step 3: Report generation
# ═══════════════════════════════════════════════════════════════════════════════
def recommend_risk_level(results):
    """
    Select the highest risk level where:
      - P(DD > 30%) < 25%
      - P(Ruin)     < 1%
      - Median CAGR > 10%
    Returns the recommended dict and reasoning.
    """
    candidates = [
        r for r in results
        if r['p_dd_gt_30'] < 25.0
        and r['p_ruin']    < 1.0
        and r['median_cagr'] > 10.0
    ]
    if not candidates:
        # Fall back to safest level
        return results[0], 'No level met all criteria — recommending 0.5% (safest).'

    # Pick the one with highest median CAGR among qualifying candidates
    best = max(candidates, key=lambda r: r['median_cagr'])
    reason = (
        f"Risk={best['risk_pct']:.1f}% is the highest level where "
        f"P(DD>30%)={best['p_dd_gt_30']:.1f}% < 25%, "
        f"P(Ruin)={best['p_ruin']:.4f}% < 1%, and "
        f"Median CAGR={best['median_cagr']:.1f}% > 10%."
    )
    return best, reason


def generate_report(results, r_multiples, recommendation, rec_reason):
    n_trades = len(r_multiples)
    win_rate = np.mean(r_multiples > 0) * 100.0
    avg_r    = np.mean(r_multiples)
    med_r    = np.median(r_multiples)
    avg_win  = np.mean(r_multiples[r_multiples > 0]) if np.any(r_multiples > 0) else 0.0
    avg_loss = np.mean(r_multiples[r_multiples < 0]) if np.any(r_multiples < 0) else 0.0

    lines = [
        '# Phase 15E Report: Monte Carlo Stress Testing',
        '',
        '**Portfolio**: BTC 4H (RR=2.0) + ETH 1H (RR=2.0) + ETH 4H (RR=2.0)',
        f'**Bootstrap Population**: {n_trades} trades from 2023-01-01 to 2026-06-19 ({FULL_YEARS:.3f} years)',
        f'**Simulations**: {N_SIMS:,} per risk level ({N_SIMS * len(results):,} total)',
        '**Ruin Definition**: Equity drawdown > 80% at any point',
        '',
        '---',
        '',
        '## 1. Trade Distribution (Bootstrap Population)',
        '',
        f'| Metric | Value |',
        f'| :--- | :---: |',
        f'| Total Trades | {n_trades} |',
        f'| Win Rate | {win_rate:.1f}% |',
        f'| Average R | {avg_r:.4f} |',
        f'| Median R | {med_r:.4f} |',
        f'| Average Win (R) | {avg_win:.4f} |',
        f'| Average Loss (R) | {avg_loss:.4f} |',
        f'| Trades per Year | {n_trades / FULL_YEARS:.1f} |',
        '',
        '---',
        '',
        '## 2. Monte Carlo Results by Risk Level',
        '',
        '| Risk % | Median CAGR | 5th Pct CAGR | 95th Pct CAGR | 95% DD | 99% DD | Worst DD | Worst Streak | P(DD>20%) | P(DD>30%) | P(DD>50%) | P(Ruin) |',
        '| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |',
    ]

    for r in results:
        rec_marker = ' ⬅' if r['risk_pct'] == recommendation['risk_pct'] else ''
        lines.append(
            f"| **{r['risk_pct']:.1f}%**{rec_marker} "
            f"| {r['median_cagr']:.1f}% "
            f"| {r['pct5_cagr']:.1f}% "
            f"| {r['pct95_cagr']:.1f}% "
            f"| {r['dd_95']:.1f}% "
            f"| {r['dd_99']:.1f}% "
            f"| {r['worst_dd']:.1f}% "
            f"| {r['worst_losing_streak']} "
            f"| {r['p_dd_gt_20']:.1f}% "
            f"| {r['p_dd_gt_30']:.1f}% "
            f"| {r['p_dd_gt_50']:.1f}% "
            f"| {r['p_ruin']:.4f}% |"
        )

    lines += [
        '',
        '---',
        '',
        '## 3. Probability Risk Map',
        '',
        '| Risk % | P(DD>20%) | P(DD>30%) | P(DD>50%) | P(Ruin >80%) |',
        '| :---: | :---: | :---: | :---: | :---: |',
    ]
    for r in results:
        flag20 = '⚠️' if r['p_dd_gt_20'] > 50 else ('✅' if r['p_dd_gt_20'] < 20 else '🟡')
        flag30 = '⚠️' if r['p_dd_gt_30'] > 25 else ('✅' if r['p_dd_gt_30'] < 10 else '🟡')
        flag50 = '⚠️' if r['p_dd_gt_50'] > 10 else '✅'
        flagR  = '⚠️' if r['p_ruin']    > 1.0 else '✅'
        lines.append(
            f"| {r['risk_pct']:.1f}% "
            f"| {flag20} {r['p_dd_gt_20']:.1f}% "
            f"| {flag30} {r['p_dd_gt_30']:.1f}% "
            f"| {flag50} {r['p_dd_gt_50']:.1f}% "
            f"| {flagR} {r['p_ruin']:.4f}% |"
        )

    lines += [
        '',
        '---',
        '',
        '## 4. Recommended Production Risk Level',
        '',
        f'> [!IMPORTANT]',
        f'> **Recommended: {recommendation["risk_pct"]:.1f}% risk per trade**',
        f'>',
        f'> {rec_reason}',
        '',
        '### Rationale for Selection Criteria',
        '',
        '- **P(DD > 30%) < 25%**: A 30% drawdown requires ~43% recovery. Probabilities above 25% indicate unacceptable psychological and operational risk for a real trading account.',
        '- **P(Ruin) < 1%**: An 80% loss is operationally terminal. Any meaningful ruin probability disqualifies a risk level for production.',
        '- **Median CAGR > 10%**: Minimum return threshold for the strategy to justify its operational complexity over passive investing.',
        '',
        '### Key Observations',
        '',
    ]

    # Add observations based on data
    obs = []
    low  = results[0]
    high = results[-1]
    obs.append(
        f'1. **Return-Risk Scaling**: Median CAGR scales from {low["median_cagr"]:.1f}% '
        f'at {low["risk_pct"]:.1f}% risk to {high["median_cagr"]:.1f}% at {high["risk_pct"]:.1f}% risk. '
        f'Higher risk amplifies both gains and losses non-linearly.'
    )

    ruin_free = [r for r in results if r['p_ruin'] < 0.01]
    if ruin_free:
        obs.append(
            f'2. **Ruin Safety**: Risk levels up to {ruin_free[-1]["risk_pct"]:.1f}% maintain P(Ruin) effectively at 0%. '
            f'The positive expectancy of this portfolio creates a strong structural defense against ruin.'
        )
    else:
        obs.append('2. **Ruin Risk**: All tested levels carry non-negligible ruin probability. Significant caution required.')

    obs.append(
        f'3. **Worst Losing Streak**: The Monte Carlo found worst-case losing streaks of '
        f'{results[-1]["worst_losing_streak"]} consecutive losses at {results[-1]["risk_pct"]:.1f}% risk. '
        f'At {recommendation["risk_pct"]:.1f}% risk, this streak would cause a ~'
        f'{(1 - (1-recommendation["risk_pct"]/100)**results[-1]["worst_losing_streak"])*100:.1f}% drawdown '
        f'before recovery.'
    )

    obs.append(
        f'4. **95% DD Envelope**: Even in 95% of all simulated paths, the portfolio at '
        f'{recommendation["risk_pct"]:.1f}% risk stays within a {recommendation["dd_95"]:.1f}% '
        f'maximum drawdown. This is the realistic planning envelope for live deployment.'
    )

    lines += obs
    lines += [
        '',
        '---',
        '',
        '## 5. Deployment Guidance',
        '',
        f'**Start at {recommendation["risk_pct"]:.1f}% risk per trade.**',
        '',
        '| Phase | Risk Level | Condition |',
        '| :--- | :---: | :--- |',
        f'| Initial Deployment | {recommendation["risk_pct"]:.1f}% | Starting capital |',
        f'| After 15% Drawdown | {recommendation["risk_pct"]/2:.2f}% (halved) | Defensive mode until recovery |',
        f'| After 25% Profit | {min(recommendation["risk_pct"]*1.25, 3.0):.2f}% (scale-up) | Only if equity grows >25% |',
        '',
        '> [!NOTE]',
        '> The Monte Carlo distribution assumes trade R-multiples remain consistent with historical observations.',
        '> Major regime changes (e.g., prolonged low-volatility periods) could shift the distribution.',
        '> Reassess risk level every 6 months or after 50+ trades.',
    ]

    return '\n'.join(lines) + '\n'


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print('Phase 15E — Monte Carlo Stress Testing')
    print(f'N Simulations: {N_SIMS:,} per risk level')
    print(f'Risk Levels  : {[f"{r*100:.1f}%" for r in RISK_LEVELS]}')
    print(f'Ruin Threshold: DD > {RUIN_DD*100:.0f}%\n')

    # ── Step 1: Extract R-multiples ───────────────────────────────────────────
    r_multiples, sim_trades = extract_r_multiples()
    n_trades = len(r_multiples)

    print(f'\nBootstrap pool: {n_trades} trades over {FULL_YEARS:.3f} years '
          f'({n_trades/FULL_YEARS:.1f} trades/year)\n')

    # ── Step 2: Monte Carlo per risk level ────────────────────────────────────
    all_results = []
    for risk_pct in RISK_LEVELS:
        print(f'Running {N_SIMS:,} sims at risk={risk_pct*100:.1f}%...', end=' ', flush=True)
        stats = run_monte_carlo(r_multiples, risk_pct, N_SIMS, seed=SEED)
        all_results.append(stats)
        print(
            f'MedianCAGR={stats["median_cagr"]:.1f}% '
            f'DD95={stats["dd_95"]:.1f}% '
            f'P(DD>30%)={stats["p_dd_gt_30"]:.1f}% '
            f'P(Ruin)={stats["p_ruin"]:.4f}%'
        )

    # ── Step 3: Recommendation ────────────────────────────────────────────────
    recommendation, rec_reason = recommend_risk_level(all_results)
    print(f'\nRecommendation: {recommendation["risk_pct"]:.1f}% risk per trade')
    print(f'Rationale: {rec_reason}\n')

    # ── Step 4: Output files ──────────────────────────────────────────────────
    out_dir = os.path.dirname(os.path.abspath(__file__))

    csv_path    = os.path.join(out_dir, 'phase15e_monte_carlo.csv')
    report_path = os.path.join(out_dir, 'phase15e_report.md')

    pd.DataFrame(all_results).to_csv(csv_path, index=False)
    print(f'Saved {csv_path}')

    report = generate_report(all_results, r_multiples, recommendation, rec_reason)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'Saved {report_path}')

    # ── Final console table ───────────────────────────────────────────────────
    print()
    print('=' * 90)
    print(f'  {"Risk":>6}  {"Med CAGR":>9}  {"DD95":>6}  {"DD99":>6}  '
          f'{"WorstDD":>8}  {"WorstLoss":>9}  {"P(DD>30%)":>9}  {"P(Ruin)":>8}')
    print('=' * 90)
    for r in all_results:
        marker = ' ***' if r['risk_pct'] == recommendation['risk_pct'] else ''
        print(f'  {r["risk_pct"]:>5.1f}%  '
              f'{r["median_cagr"]:>8.1f}%  '
              f'{r["dd_95"]:>5.1f}%  '
              f'{r["dd_99"]:>5.1f}%  '
              f'{r["worst_dd"]:>7.1f}%  '
              f'{r["worst_losing_streak"]:>9}  '
              f'{r["p_dd_gt_30"]:>8.1f}%  '
              f'{r["p_ruin"]:>7.4f}%{marker}')
    print('=' * 90)
    print(f'  Recommended production risk level: {recommendation["risk_pct"]:.1f}%')
    print('=' * 90)


if __name__ == '__main__':
    main()
