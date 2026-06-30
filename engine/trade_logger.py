import pandas as pd

class TradeLogger:

    def __init__(self):
        self.trades = []

    def add_trade(
        self,
        entry_time,
        side,
        entry,
        stop_loss,
        take_profit,
        result,
        pnl
    ):

        self.trades.append({
            "entry_time": entry_time,
            "side": side,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "result": result,
            "pnl": pnl
        })

    def save(self, filename="trades.csv"):

        pd.DataFrame(
            self.trades
        ).to_csv(
            filename,
            index=False
        )