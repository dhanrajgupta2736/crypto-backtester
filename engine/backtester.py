import vectorbt as vbt


def run_backtest(close, entries, exits):

    pf = vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        init_cash=10000,
        fees=0.001
    )

    return {
        "return_pct": round(float(pf.total_return()) * 100, 2),
        "trades": int(pf.trades.count()),
        "win_rate": round(float(pf.trades.win_rate()) * 100, 2),
        "max_dd": round(float(abs(pf.max_drawdown())) * 100, 2)
    }