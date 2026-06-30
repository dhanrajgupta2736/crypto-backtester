def simulate_trade(signal, future_candles):

    entry = signal.entry
    sl = signal.stop_loss
    tp = signal.take_profit

    side = signal.side

    for _, candle in future_candles.iterrows():

        high = candle["high"]
        low = candle["low"]

        if side == "long":

            if low <= sl:

                pnl_pct = (
                    sl - entry
                ) / entry

                return (
                    "loss",
                    pnl_pct
                )

            if high >= tp:

                pnl_pct = (
                    tp - entry
                ) / entry

                return (
                    "win",
                    pnl_pct
                )

        else:

            if high >= sl:

                pnl_pct = (
                    entry - sl
                ) / entry

                return (
                    "loss",
                    -pnl_pct
                )

            if low <= tp:

                pnl_pct = (
                    entry - tp
                ) / entry

                return (
                    "win",
                    pnl_pct
                )

    return None, 0