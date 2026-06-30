import json
import os
import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Configure Streamlit Page
st.set_page_config(
    page_title="TAO Supertrend EMA200 - Live Paper Trading",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for Premium Styling
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .stAlert {
        border-radius: 12px;
    }
    
    .status-badge {
        padding: 5px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
        text-align: center;
        letter-spacing: 0.5px;
    }
    
    .status-connected {
        background-color: rgba(46, 204, 113, 0.15);
        color: #2ecc71;
        border: 1px solid rgba(46, 204, 113, 0.3);
    }
    
    .status-disconnected {
        background-color: rgba(231, 76, 60, 0.15);
        color: #e74c3c;
        border: 1px solid rgba(231, 76, 60, 0.3);
    }
    
    .status-paused {
        background-color: rgba(241, 196, 15, 0.15);
        color: #f1c40f;
        border: 1px solid rgba(241, 196, 15, 0.3);
    }
    </style>
    
    <!-- Auto-Refresh Meta Tag -->
    <meta http-equiv="refresh" content="60">
    """,
    unsafe_allow_html=True
)

# Paths
STATE_PATH = os.path.join("results", "engine_state.json")
LIVE_LOG_PATH = os.path.join("results", "live_trades.csv")
PAPER_LOG_PATH = os.path.join("results", "paper_trades.csv")
OLD_LOG_PATH = os.path.join("results", "paper_trade_log.csv")

# Load shared state
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Error loading state: {e}")
    return None

def normalize_columns(df):
    df = df.copy()
    col_map = {}
    for col in df.columns:
        c_clean = col.lower().replace(" ", "").replace("_", "")
        col_map[c_clean] = col
        
    norm_df = pd.DataFrame()
    
    # 1. Exit Timestamp
    ts_col = col_map.get("timestamp") or col_map.get("exittimestamp")
    if ts_col:
        norm_df["timestamp"] = pd.to_datetime(df[ts_col])
    else:
        norm_df["timestamp"] = pd.date_range(start="2026-01-01", periods=len(df), freq="h")
        
    # 2. Symbol
    sym_col = col_map.get("symbol")
    if sym_col:
        norm_df["symbol"] = df[sym_col].astype(str)
    else:
        norm_df["symbol"] = "TAO"
        
    # 3. Side / Direction
    side_col = col_map.get("side") or col_map.get("direction")
    if side_col:
        norm_df["side"] = df[side_col].astype(str).str.lower()
    else:
        norm_df["side"] = "long"
        
    # 4. Entry
    entry_col = col_map.get("entry") or col_map.get("entryprice")
    if entry_col:
        norm_df["entry"] = df[entry_col].astype(float)
    else:
        norm_df["entry"] = 100.0
        
    # 5. Stop
    stop_col = col_map.get("stop") or col_map.get("stoploss")
    if stop_col:
        norm_df["stop"] = df[stop_col].astype(float)
    else:
        norm_df["stop"] = 95.0
        
    # 6. Target / Take Profit
    target_col = col_map.get("target") or col_map.get("takeprofit")
    if target_col:
        norm_df["target"] = df[target_col].astype(float)
    else:
        norm_df["target"] = 115.0
        
    # 7. Exit
    exit_col = col_map.get("exit") or col_map.get("exitprice")
    if exit_col:
        norm_df["exit"] = df[exit_col].astype(float)
    else:
        norm_df["exit"] = 100.0
        
    # 8. PnL
    pnl_col = col_map.get("pnl") or col_map.get("tradepnl")
    if pnl_col:
        norm_df["pnl"] = df[pnl_col].astype(float)
    else:
        norm_df["pnl"] = 0.0
        
    # 9. Equity After
    bal_col = col_map.get("equityafter") or col_map.get("accountbalance")
    if bal_col:
        norm_df["equity_after"] = df[bal_col].astype(float)
    else:
        norm_df["equity_after"] = 10000.0 + norm_df["pnl"].cumsum()
        
    # 10. Equity Before
    eb_col = col_map.get("equitybefore")
    if eb_col:
        norm_df["equity_before"] = df[eb_col].astype(float)
    else:
        norm_df["equity_before"] = norm_df["equity_after"] - norm_df["pnl"]
        
    # 11. Fees
    fees_col = col_map.get("fees") or col_map.get("feespaid")
    if fees_col:
        norm_df["fees"] = df[fees_col].astype(float)
    else:
        norm_df["fees"] = 0.0
        
    # 12. Slippage
    slip_col = col_map.get("slippage") or col_map.get("slippagecost")
    if slip_col:
        norm_df["slippage"] = df[slip_col].astype(float)
    else:
        norm_df["slippage"] = 0.0
        
    # 13. Strategy Version
    ver_col = col_map.get("strategyversion")
    if ver_col:
        norm_df["strategy_version"] = df[ver_col].astype(str)
    else:
        norm_df["strategy_version"] = "v1.0"
        
    # 14. R-Multiple
    r_col = col_map.get("rmultiple")
    if r_col:
        norm_df["r_multiple"] = df[r_col].astype(float)
    else:
        r_list = []
        for idx, row in norm_df.iterrows():
            entry = row["entry"]
            stop = row["stop"]
            exit_p = row["exit"]
            side = row["side"]
            
            p_dist = abs(entry - stop)
            if p_dist > 0:
                p_r = (exit_p - entry) / p_dist if side in ("long", "l") else (entry - exit_p) / p_dist
            else:
                p_r = 0.0
            r_list.append(p_r)
        norm_df["r_multiple"] = r_list
        
    return norm_df

# Load trade log
def load_trade_log():
    log_path = None
    for path in [LIVE_LOG_PATH, PAPER_LOG_PATH, OLD_LOG_PATH]:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            log_path = path
            break
            
    if log_path is None:
        return None
        
    try:
        df = pd.read_csv(log_path)
        df_norm = normalize_columns(df)
        return df_norm
    except Exception as e:
        st.error(f"Error loading trade log: {e}")
    return None

# Render HTML Card
def render_card(title, value, color_gradient):
    st.markdown(
        f"""
        <div style="
            background: {color_gradient};
            padding: 24px;
            border-radius: 16px;
            color: white;
            box-shadow: 0 8px 30px rgba(0,0,0,0.2);
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.08);
            backdrop-filter: blur(8px);
        ">
            <div style="font-size: 0.85rem; opacity: 0.75; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px;">{title}</div>
            <div style="font-size: 2.2rem; font-weight: 700; margin-top: 8px; font-family: 'Outfit', sans-serif;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# Calculate Sharpe Ratio
def calculate_sharpe(df_trades, start_equity=10000.0):
    if df_trades is None or len(df_trades) < 2:
        return 0.0
    
    # Reconstruct daily equity curve
    df_trades = df_trades.copy()
    df_trades["date"] = df_trades["timestamp"].dt.normalize()
    
    # Get last balance for each day
    daily_balances = df_trades.groupby("date")["equity_after"].last()
    
    # Fill in starting balance for the day before first trade
    first_date = daily_balances.index.min()
    prev_date = first_date - pd.Timedelta(days=1)
    daily_balances[prev_date] = start_equity
    daily_balances = daily_balances.sort_index()
    
    # Reindex to fill all missing calendar days
    all_dates = pd.date_range(start=daily_balances.index.min(), end=daily_balances.index.max(), freq="D")
    daily_balances = daily_balances.reindex(all_dates).ffill()
    
    # Daily returns
    daily_returns = daily_balances.pct_change().dropna()
    if daily_returns.empty or daily_returns.std() == 0:
        return 0.0
    
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    return round(float(sharpe), 4)

# Calculate Max Drawdown
def calculate_max_drawdown(equity_series):
    if len(equity_series) == 0:
        return 0.0
    eq = pd.Series(equity_series)
    cummax = eq.cummax()
    dd = (eq - cummax) / cummax * 100
    return round(float(dd.min()), 2)

# Streamlit App Execution
def main():
    # Header Section
    col_title, col_status = st.columns([4, 1])
    
    with col_title:
        st.markdown(
            """
            <h1 style='margin-bottom:0; font-weight: 700; letter-spacing:-1px;'>
                TAO Live Paper Trading Dashboard
            </h1>
            <p style='color:#a0a0a0; font-size:1.1rem; margin-top:5px;'>
                Strategy: Supertrend EMA200 (1H Timeframe) | Paper Validation Environment
            </p>
            """,
            unsafe_allow_html=True
        )
        
    state = load_state()
    df_trades = load_trade_log()
    
    with col_status:
        st.write("") # Spacer
        if state is None:
            st.markdown("<span class='status-badge status-disconnected'>ENGINE SHUTDOWN</span>", unsafe_allow_html=True)
        else:
            conn_status = state.get("websocket_connected", False)
            is_paused = state.get("is_paused", False)
            
            if is_paused:
                st.markdown("<span class='status-badge status-paused'>⚠️ ENGINE PAUSED</span>", unsafe_allow_html=True)
            elif conn_status:
                st.markdown("<span class='status-badge status-connected'>● FEED CONNECTED</span>", unsafe_allow_html=True)
            else:
                st.markdown("<span class='status-badge status-disconnected'>○ FEED OFFLINE</span>", unsafe_allow_html=True)
        
        st.markdown(f"<p style='font-size:0.8rem; color:#888; margin-top:5px; text-align:right;'>Last updated: {time.strftime('%H:%M:%S')} UTC</p>", unsafe_allow_html=True)

    st.markdown("---")

    # Safety Guard Trip Alert Banners
    if state is not None and state.get("is_paused", False):
        st.error(f"🛑 **TRADING SYSTEM PAUSED**: {state.get('pause_reason', 'Unknown reason')}")
    
    # ------------------ PRE-DATA WARNING ------------------
    if state is None:
        st.warning("Waiting for the `paper_trading_engine.py` process to start and share status...")
        return
        
    # Calculate performance metrics
    starting_balance = 10000.0  # Default baseline
    if df_trades is not None and len(df_trades) > 0:
        starting_balance = float(df_trades["equity_after"].iloc[0] - df_trades["pnl"].iloc[0])
        
    current_cash = state.get("balance", starting_balance)

    
    # Process open position values
    pos = state.get("position", None)
    unrealized_pnl = 0.0
    last_price = state.get("last_price", 0.0)
    
    if pos is not None:
        side = pos["side"]
        qty = pos["qty"]
        ep = pos["entry"]
        
        # Calculate real-time unrealized PnL including taker exit fee
        real_entry = ep * (1.0 + 0.0002) if side == "long" else ep * (1.0 - 0.0002)
        real_exit = last_price * (1.0 - 0.0002) if side == "long" else last_price * (1.0 + 0.0002)
        entry_fees = pos.get("entry_fee", qty * ep * 0.00045)
        exit_fees = qty * last_price * 0.00045
        
        if side == "long":
            unrealized_pnl = (qty * real_exit - qty * real_entry) - entry_fees - exit_fees
        else:
            unrealized_pnl = (qty * real_entry - qty * real_exit) - entry_fees - exit_fees

    current_equity = current_cash + unrealized_pnl
    
    # Historical performance from logs
    trade_count = 0
    win_rate = 0.0
    profit_factor = 0.0
    sharpe = 0.0
    max_dd = 0.0
    avg_r = 0.0
    
    equity_progression = [starting_balance]
    equity_timestamps = [pd.Timestamp.now() - pd.Timedelta(days=30)] # Placeholder
    
    if df_trades is not None and len(df_trades) > 0:
        trade_count = len(df_trades)
        wins = df_trades[df_trades["pnl"] > 0]["pnl"]
        losses = df_trades[df_trades["pnl"] <= 0]["pnl"]
        
        win_rate = len(wins) / trade_count * 100
        profit_factor = sum(wins) / abs(sum(losses)) if len(losses) > 0 else (99.9 if sum(wins) > 0 else 0.0)
        
        # Calculate Sharpe and average R
        sharpe = calculate_sharpe(df_trades, starting_balance)
        avg_r = df_trades["r_multiple"].mean()
        
        # Drawdown calculations from progression
        trade_equities = df_trades["equity_after"].tolist()
        equity_progression = [starting_balance] + trade_equities
        
        max_dd = calculate_max_drawdown(equity_progression)
        equity_timestamps = [df_trades["timestamp"].iloc[0] - pd.Timedelta(hours=1)] + df_trades["timestamp"].tolist()
        
    # Append current equity if position is active
    if pos is not None:
        equity_progression.append(current_equity)
        equity_timestamps.append(pd.Timestamp.now())
        max_dd = calculate_max_drawdown(equity_progression)

    # ------------------ STATS SECTION ------------------
    col_eq, col_wr, col_pf, col_sh, col_dd, col_streak = st.columns(6)
    
    # Render Stat Cards with premium color gradients
    with col_eq:
        eq_formatted = f"${current_equity:,.2f}"
        render_card("Current Equity", eq_formatted, "linear-gradient(135deg, #130CB7 0%, #52E5E7 100%)")
    with col_wr:
        wr_formatted = f"{win_rate:.1f}%"
        render_card("Win Rate", wr_formatted, "linear-gradient(135deg, #091E3A 0%, #2F80ED 50%, #2D9CDB 100%)")
    with col_pf:
        pf_formatted = f"{profit_factor:.2f}"
        render_card("Profit Factor", pf_formatted, "linear-gradient(135deg, #11998e 0%, #38ef7d 100%)")
    with col_sh:
        sh_formatted = f"{sharpe:.2f}"
        render_card("Sharpe Ratio", sh_formatted, "linear-gradient(135deg, #4568DC 0%, #B06AB3 100%)")
    with col_dd:
        dd_formatted = f"{max_dd:.2f}%"
        render_card("Max Drawdown", dd_formatted, "linear-gradient(135deg, #b20a2c 0%, #f953c6 100%)")
    with col_streak:
        streak_val = f"{state.get('consecutive_losses', 0)} / 5"
        render_card("Loss Streak", streak_val, "linear-gradient(135deg, #8A2387 0%, #E94057 50%, #F27121 100%)")

    # ------------------ OPEN POSITION CONTAINER ------------------
    st.subheader("Active Trade Status")
    if pos is None:
        st.info("No active positions. Monitoring market signals...")
    else:
        st.markdown(
            f"""
            <div style="
                background: #1e1e24;
                border: 1px solid rgba(255,255,255,0.06);
                border-left: 6px solid {'#2ecc71' if pos['side'] == 'long' else '#e74c3c'};
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0 10px 20px rgba(0,0,0,0.15);
                margin-bottom: 30px;
                font-family: 'Outfit', sans-serif;
            ">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="
                            background: {'rgba(46, 204, 113, 0.15)' if pos['side'] == 'long' else 'rgba(231, 76, 60, 0.15)'};
                            color: {'#2ecc71' if pos['side'] == 'long' else '#e74c3c'};
                            padding: 4px 10px;
                            border-radius: 4px;
                            font-weight: 700;
                            text-transform: uppercase;
                            font-size: 0.85rem;
                            letter-spacing: 1px;
                        ">
                            {pos['side'].upper()}
                        </span>
                        <span style="font-weight:700; font-size:1.4rem; color:white; margin-left:12px;">TAO PERPETUAL</span>
                        <span style="color:#888; font-size:0.9rem; margin-left:10px;">Entered on: {pos['entry_date']}</span>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:0.8rem; color:#888; text-transform:uppercase; font-weight:600; letter-spacing:1px;">Unrealized PnL</div>
                        <div style="font-size:1.6rem; font-weight:700; color:{'#2ecc71' if unrealized_pnl >= 0 else '#e74c3c'};">
                            {'+' if unrealized_pnl >= 0 else ''}${unrealized_pnl:.2f}
                        </div>
                    </div>
                </div>
                <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.06); margin: 15px 0;">
                <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap: 15px;">
                    <div>
                        <div style="font-size:0.75rem; color:#888; text-transform:uppercase; letter-spacing:0.5px;">Position Size</div>
                        <div style="font-size:1.1rem; font-weight:600; color:white; font-family:'JetBrains Mono', monospace; margin-top:3px;">{pos['qty']:.3f} TAO</div>
                    </div>
                    <div>
                        <div style="font-size:0.75rem; color:#888; text-transform:uppercase; letter-spacing:0.5px;">Entry Price</div>
                        <div style="font-size:1.1rem; font-weight:600; color:white; font-family:'JetBrains Mono', monospace; margin-top:3px;">${pos['entry']:.4f}</div>
                    </div>
                    <div>
                        <div style="font-size:0.75rem; color:#888; text-transform:uppercase; letter-spacing:0.5px;">Active Stop Loss</div>
                        <div style="font-size:1.1rem; font-weight:600; color:#e74c3c; font-family:'JetBrains Mono', monospace; margin-top:3px;">${pos['sl']:.4f} { ' (BE)' if pos.get('moved_to_be', False) else '' }</div>
                    </div>
                    <div>
                        <div style="font-size:0.75rem; color:#888; text-transform:uppercase; letter-spacing:0.5px;">Take Profit Target</div>
                        <div style="font-size:1.1rem; font-weight:600; color:#2ecc71; font-family:'JetBrains Mono', monospace; margin-top:3px;">${pos['tp']:.4f}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # ------------------ CHARTS SECTION ------------------
    col_chart_left, col_chart_right = st.columns([3, 1])
    
    with col_chart_left:
        st.subheader("Equity Curve & Drawdown Track")
        
        # Interactive Plotly Equity Curve
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=equity_timestamps,
            y=equity_progression,
            mode='lines+markers',
            name='Account Equity',
            line=dict(color='#00ffcc', width=3),
            fill='tozeroy',
            fillcolor='rgba(0, 255, 204, 0.05)',
            hoverinfo='x+y'
        ))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#eaeaea',
            margin=dict(l=0, r=0, t=10, b=0),
            height=380,
            xaxis=dict(
                showgrid=True,
                gridcolor='rgba(255,255,255,0.05)',
                zeroline=False
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='rgba(255,255,255,0.05)',
                zeroline=False,
                tickformat='$,.2f'
            )
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_chart_right:
        st.subheader("Signal Indicators")
        ind = state.get("indicators", {})
        if not ind:
            st.info("Indicators not primed yet.")
        else:
            # Display current indicator calculations
            st.metric(label="Last Traded Price", value=f"${last_price:,.2f}")
            st.metric(label="EMA 200", value=f"${ind.get('ema200', 0.0):,.2f}")
            st.metric(label="ATR (10)", value=f"${ind.get('atr', 0.0):,.4f}")
            
            # Supertrend State Indicator
            uptrend = ind.get("uptrend", True)
            st.markdown(
                f"""
                <div style="
                    background: {'rgba(46, 204, 113, 0.12)' if uptrend else 'rgba(231, 76, 60, 0.12)'};
                    border: 1px solid {'rgba(46, 204, 113, 0.25)' if uptrend else 'rgba(231, 76, 60, 0.25)'};
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                    margin-top: 15px;
                ">
                    <div style="font-size:0.75rem; color:#aaa; text-transform:uppercase; font-weight:600; letter-spacing:1px;">Supertrend Trend</div>
                    <div style="font-size:1.2rem; font-weight:700; color:{'#2ecc71' if uptrend else '#e74c3c'}; margin-top:5px;">
                        {'📈 BULLISH' if uptrend else '📉 BEARISH'}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    # ------------------ JOURNAL LOGS SECTION ------------------
    st.subheader("Closed Trades History")
    if df_trades is None or len(df_trades) == 0:
        st.info("No closed trades logged in paper journal database.")
    else:
        required_cols = ["timestamp", "pnl", "r_multiple", "entry", "exit", "stop", "target", "fees", "slippage"]
        missing_cols = [col for col in required_cols if col not in df_trades.columns]
        
        if missing_cols:
            st.warning(f"⚠️ **Trade History Schema Alert**: The loaded log is missing standard columns: {missing_cols}. "
                       f"Available columns: {df_trades.columns.tolist()}")
            st.dataframe(df_trades, use_container_width=True)
            return
            
        df_display = df_trades.copy()
        
        # Formatting for table display
        df_display["timestamp"] = df_display["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        df_display["pnl"] = df_display["pnl"].apply(lambda x: f"${x:+.2f}")
        df_display["r_multiple"] = df_display["r_multiple"].apply(lambda x: f"{x:+.2f}R")
        df_display["entry"] = df_display["entry"].map("${:,.4f}".format)
        df_display["exit"] = df_display["exit"].map("${:,.4f}".format)
        df_display["stop"] = df_display["stop"].map("${:,.4f}".format)
        df_display["target"] = df_display["target"].map("${:,.4f}".format)
        df_display["fees"] = df_display["fees"].map("${:,.4f}".format)
        df_display["slippage"] = df_display["slippage"].map("${:,.4f}".format)

        
        # Sort desc by timestamp
        df_display = df_display.sort_values(by="timestamp", ascending=False)
        
        # Rename for clean table display
        df_display = df_display.rename(columns={
            "timestamp": "Exit Timestamp",
            "side": "Direction",
            "entry": "Entry Price",
            "stop": "Stop Loss",
            "target": "Take Profit",
            "exit": "Exit Price",
            "r_multiple": "R-Multiple",
            "pnl": "Net PnL",
            "fees": "Fees Paid",
            "slippage": "Slippage Cost",
            "equity_before": "Equity Before",
            "equity_after": "Equity After"
        })
        
        st.dataframe(
            df_display[["Exit Timestamp", "Direction", "Entry Price", "Stop Loss", "Take Profit", "Exit Price", "R-Multiple", "Net PnL", "Fees Paid", "Slippage Cost"]],
            use_container_width=True
        )

if __name__ == "__main__":
    main()
