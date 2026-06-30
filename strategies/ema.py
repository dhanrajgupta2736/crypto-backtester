import vectorbt as vbt


def ema_strategy(close, fast=20, slow=50):

    fast_ma = vbt.MA.run(close, window=fast)

    slow_ma = vbt.MA.run(close, window=slow)

    entries = fast_ma.ma_crossed_above(slow_ma)

    exits = fast_ma.ma_crossed_below(slow_ma)

    return entries, exits