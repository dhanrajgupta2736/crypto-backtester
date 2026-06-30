# Phase 15F Report: Black Swan / Catastrophic Event Stress Testing

**Portfolio**: BTC 4H (RR=2.0) + ETH 1H (RR=2.0) + ETH 4H (RR=2.0)
**Risk Level**: 2% per trade (Phase 15E production recommendation)
**Full Period**: 2023-01-01 → 2026-06-19 (3.465 years, 180 trades)

---

## Baseline (Phase 15D Reference)

| PF | Expectancy | Max DD | CAGR | RoR |
| :---: | :---: | :---: | :---: | :---: |
| 1.408 | 0.2462 | 29.83% | 25.74% | 0.0% |

---

## Scenario A: Stop Losses → 2R (Severe Slippage)

> All negative R-multiples replaced with -2R. Simulates systematic stop execution
> at 2× the expected loss (exchange slippage during high-volatility events).

| Metric | Baseline | Scenario A | Change |
| :--- | :---: | :---: | :---: |
| PF | 1.408 | 0.765 | -0.643 |
| Expectancy (R) | 0.2462 | -0.2612 | -0.5074 |
| Max DD | 29.83% | 73.45% | +43.62% |
| CAGR | 25.74% | -26.93% | -52.67% |
| Risk of Ruin | 0.0% | 25.22% | — |

> **Verdict**: Portfolio becomes unprofitable under 2R losses.

---

## Scenario B: Stop Losses → 3R (Flash Liquidity Failure)

> All negative R-multiples replaced with -3R. Simulates complete stop execution
> failure — exits triggered at market during a liquidity void.

| Metric | Baseline | Scenario B | Change |
| :--- | :---: | :---: | :---: |
| PF | 1.408 | 0.51 | -0.898 |
| Expectancy (R) | 0.2462 | -0.8167 | -1.0629 |
| Max DD | 29.83% | 96.68% | +66.85% |
| CAGR | 25.74% | -60.2% | -85.94% |
| Risk of Ruin | 0.0% | 99.6% | — |

> **Verdict**: Portfolio edge is destroyed under 3R loss model. Requires circuit breaker.

---

## Scenario C: Flash Crash (Synthetic Gap)

> Average stop distance (sl_pct): **2.185%** of entry price  
> Max concurrent positions: **3** | Avg concurrent: **0.76**  
> Formula: Loss per position = gap% / sl_pct% × risk%

| Gap | Avg SL | Add. R/Position | Loss/Position | Worst DD (3 pos) | Expected DD (0.76 pos) | Survivable |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 15% | 2.185% | 6.87R | 13.7% equity | 41.2% | 10.4% | ✅ Yes |
| 20% | 2.185% | 9.15R | 18.3% equity | 54.9% | 13.9% | ✅ Yes |
| 30% | 2.185% | 13.73R | 27.5% equity | 82.4% | 20.9% | ❌ No |

> [!WARNING]
> At -30% gap with 3 simultaneous positions, portfolio loss approaches or exceeds the 80% ruin threshold.
> **Emergency control**: maximum 1 concurrent position per exchange reduces worst-case flash crash DD by 3×.

---

## Scenario D: Exchange Outage (30-Minute)

> Assumes all active stops execute at next available bar open after 30-min outage.
> Additional loss = adverse price move during outage window, scaled from candle range via √(t/T).

| Instrument | Bar Size | Outage Fraction | 95th Pct Adverse Move | 99th Pct Adverse Move | Add. R (p99) | Add. Equity Loss (p99) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| BTC 4H | 240min | 0.125 | 1.154% | 1.845% | 0.844R | 1.689% |
| ETH 1H | 60min | 0.500 | 1.559% | 2.626% | 1.202R | 2.404% |
| ETH 4H | 240min | 0.125 | 1.573% | 2.535% | 1.160R | 2.320% |

---

## Scenario E: WebSocket Failure (15 / 30 / 60 Minutes)

> Position unmanaged during window. Worst observed damage from historical price action.

| Instrument | Window | 95th Pct Adverse | 99th Pct Adverse | Add. R (p99) | Add. Equity Loss (p99) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| BTC 4H | 15min | 0.816% | 1.304% | 0.597R | 1.194% |
| ETH 1H | 15min | 1.102% | 1.857% | 0.850R | 1.700% |
| ETH 4H | 15min | 1.113% | 1.792% | 0.820R | 1.641% |
| BTC 4H | 30min | 1.154% | 1.845% | 0.844R | 1.689% |
| ETH 1H | 30min | 1.559% | 2.626% | 1.202R | 2.404% |
| ETH 4H | 30min | 1.573% | 2.535% | 1.160R | 2.320% |
| BTC 4H | 60min | 1.632% | 2.609% | 1.194R | 2.388% |
| ETH 1H | 60min | 2.204% | 3.714% | 1.700R | 3.400% |
| ETH 4H | 60min | 2.225% | 3.585% | 1.641R | 3.282% |

> **Key finding**: ETH 1H is most vulnerable to short outages (30min = 50% of bar).
> BTC 4H is far more robust (30min = 12.5% of bar, minimal adverse drift).

---

## Scenario F: Funding Shock

> Funding rates multiplied by 2×/5×/10×. Re-simulates full portfolio with scaled carry costs.

| Multiplier | PF | Expectancy | Max DD | CAGR | Net Return | vs Baseline |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 2× | 1.364 | 0.2332 | 28.08% | 22.04% | 99.43% | -3.70% CAGR |
| 5× | 1.291 | 0.1940 | 27.65% | 17.37% | 74.20% | -8.37% CAGR |
| 10× | 1.165 | 0.1288 | 28.59% | 9.82% | 38.35% | -15.92% CAGR |

---

## Required Conclusions

### 1. Largest Realistic Loss

| Event | Worst-Case Equity Loss | Probability |
| :--- | :---: | :---: |
| Stop slippage (2R model) | DD: 73.5% | Possible in any volatile period |
| Stop slippage (3R model) | DD: 96.7% | Rare (illiquid spikes) |
| Flash crash -30%, 3 positions | DD: 82.4% | Tail event |
| WebSocket failure 60min (ETH 1H) | +1-3R additional loss | Possible during API failures |

> [!IMPORTANT]
> **The largest realistic single-event loss under the 2% risk rule is a flash crash of -30% with 3 concurrent positions.**
> This produces a **82.4% drawdown** in one event.
> The expected (0.76 concurrent) flash crash loss at -30% is only **20.9%**.

### 2. Portfolio Survival Probability

- **Scenario A (2R stops)**: ❌ Endangered — CAGR=-26.9%, RoR=25.2200%
- **Scenario B (3R stops)**: ❌ Endangered — CAGR=-60.2%, RoR=99.6000%
- **Scenario C (-30% flash crash)**: ✅ Survives (expected case) — Expected DD=20.9%
- **Scenarios D/E (outage)**: ✅ Survives — additional loss is incremental (1-3R), not catastrophic
- **Scenario F (10× funding)**: ✅ Survives — CAGR=9.82% at 10× funding

### 3. Recommended Emergency Controls

| Risk | Control | Trigger |
| :--- | :--- | :--- |
| Flash Crash | **Max 1 simultaneous position per exchange** | Always enforce at position open |
| Outage / WebSocket | **Dead-man switch**: market-close all positions if no heartbeat for 5 min | System startup |
| Stop Slippage | **Guaranteed stop orders** (not limit) for stop-loss exits | System config |
| Funding Shock | **Daily funding cost monitor**: halt if daily funding > 0.5% of equity | Daily check |
| General DD | **Circuit breaker at 20% drawdown**: halve risk. At 30%: stop trading and review | Automatic |

### 4. Is Live Paper Deployment Justified?

> [!WARNING]
> **CONDITIONAL** — Paper deployment is justified but requires the emergency controls above
> to be implemented before going live.
