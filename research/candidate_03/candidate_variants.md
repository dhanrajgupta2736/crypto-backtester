# Candidate C003: Candidate Variants

**Strategy Name**: Session Open Range Breakout (SORB)
**Candidate ID**: C003
**Research Phase**: Phase 1 — Research Only
**Created**: 2026-07-01
**Status**: `VARIANTS_DEFINED`

---

## Overview

This document defines the concrete variants (sub-strategies) to be evaluated within the SORB parameter space. Each variant represents a meaningfully different interpretation of the core SORB hypothesis, allowing systematic comparison of the structural design choices before the full Discovery Sweep begins.

Variants are defined top-down from the most fundamental differences (session selection, exit style) to refinements (filters). Each variant receives a canonical ID that will be used in all subsequent research ledger and discovery matrix entries.

---

## Variant Matrix

| Variant ID | Name | Session | Timeframe | Open Range | Stop | Exit | Volume Filter | Trend Filter |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **C003-V01** | London Baseline | London | 15m | 60 min | Range Low | Session Close | No | No |
| **C003-V02** | New York Baseline | New York | 15m | 60 min | Range Low | Session Close | No | No |
| **C003-V03** | London + ATR Exit | London | 15m | 60 min | ATR 1.5× | ATR 2.0× Target | No | No |
| **C003-V04** | New York + ATR Exit | New York | 15m | 60 min | ATR 1.5× | ATR 2.0× Target | No | No |
| **C003-V05** | Dual Session | London + NY | 15m | 60 min | Range Low | Session Close | No | No |
| **C003-V06** | 1H Timeframe Baseline | New York | 1H | 60 min | Range Low | Session Close | No | No |
| **C003-V07** | Narrow Range (30 min) | New York | 15m | 30 min | Range Low | Session Close | No | No |
| **C003-V08** | Wide Range (90 min) | New York | 15m | 90 min | Range Low | Session Close | No | No |
| **C003-V09** | Volume-Confirmed | New York | 15m | 60 min | Range Low | Session Close | Yes (P50) | No |
| **C003-V10** | Trend-Filtered | New York | 15m | 60 min | Range Low | Session Close | No | Yes (EMA50) |
| **C003-V11** | Full Conviction Filter | New York | 15m | 60 min | ATR 1.5× | ATR 2.0× Target | Yes (P75) | Yes (EMA50) |
| **C003-V12** | Fixed R:R Exit | New York | 15m | 60 min | Range Low | Fixed R:R 2.0 | No | No |

---

## Detailed Variant Specifications

### C003-V01 — London Baseline
**Purpose**: Establish the purest baseline for the London session. No filters, no ATR stops, simple exit at session close.

**Entry Signal**:
- Session start: 07:00 UTC.
- Open Range: First 60 minutes (4 × 15m candles).
- Entry: Long when price closes above Open Range High with zero ATR buffer.

**Exit**: Close position at 11:00 UTC (4 hours after session open).

**Stop Loss**: Low of the Open Range.

**Expected trade frequency**: ~3–8 trades/week/asset (London session only).

---

### C003-V02 — New York Baseline
**Purpose**: Establish the purest baseline for the New York session. US equities open drives the highest global crypto volume.

**Entry Signal**:
- Session start: 13:00 UTC.
- Open Range: First 60 minutes (4 × 15m candles).
- Entry: Long when price closes above Open Range High.

**Exit**: Close position at 17:00 UTC (4 hours after session open).

**Stop Loss**: Low of the Open Range.

**Expected trade frequency**: ~4–10 trades/week/asset (NY session only).

---

### C003-V03 — London + ATR Exit
**Purpose**: Test whether ATR-based stops and targets outperform the natural open range stop on the London session.

**Stop Loss**: Entry Price − 1.5 × ATR(14).

**Take Profit**: Entry Price + 2.0 × ATR(14) (Risk-adjusted symmetric target).

---

### C003-V04 — New York + ATR Exit
**Purpose**: Same as V03 but applied to the New York session.

---

### C003-V05 — Dual Session
**Purpose**: Determine whether trading both London and New York sessions simultaneously improves total annual return and Sharpe via trade volume increase, or degrades performance due to session interference.

**Note**: If a London trade is still open when the NY session opens, the NY session breakout is skipped for that asset.

---

### C003-V06 — 1H Timeframe Baseline
**Purpose**: Test whether 1H candle granularity (which reduces execution sensitivity and fee drag from frequent 15m candle checks) delivers comparable performance to the 15m baseline.

**Open Range**: First single 1H candle of the session (equivalent to the first 60 minutes).

---

### C003-V07 — Narrow Range (30 min)
**Purpose**: Test whether a tighter, more concentrated 30-minute open range produces cleaner breakout signals with higher conviction (less probability of a breakout occurring trivially from candle noise).

---

### C003-V08 — Wide Range (90 min)
**Purpose**: Test whether a wider 90-minute open range better reflects the full session establishment phase, reducing false breakouts triggered in the first 30 minutes of chaotic price discovery.

---

### C003-V09 — Volume-Confirmed
**Purpose**: Directly test Hypothesis H2. Entry is only taken if the Open Range candles show cumulative volume above the 50th percentile of the prior 20-session volumes for that asset.

---

### C003-V10 — Trend-Filtered
**Purpose**: Directly test Hypothesis H3. Entry is only taken if the closing price of the asset is above its 50-period EMA on the session timeframe at the time of the open range breakout.

---

### C003-V11 — Full Conviction Filter
**Purpose**: Combine both filters (V09 + V10) plus ATR-based stops and targets to produce the highest-conviction subset of SORB signals. Expected to have the lowest trade frequency but potentially the highest per-trade expectancy.

---

### C003-V12 — Fixed Risk:Reward Exit
**Purpose**: Test whether a fixed 2:1 R:R exit (TP at 2× initial risk from entry, SL at range low) outperforms the time-based session close exit or ATR-based targets.

---

## Variant Progression Logic

The following phase promotion logic applies:

```
1. Discovery Sweep across full parameter space
2. Rank all configurations by Sharpe ≥ 0.8 + Trade Count ≥ 50
3. Select Top-N candidates for Walk-Forward Validation
4. If Variants are ambiguous, promote the simplest variant (fewest parameters wins, Occam's Razor)
5. Apply filters (V09/V10/V11) as "Top-N refinements" ONLY after core edge is validated in bare-bones variants
```

---

## Short Variant Future Note (C003-S)

This document covers only the long-only variants. Once the long-only system passes Walk-Forward validation, a mirror short version will be developed as:

**C003-S**: Short when price closes **below** the Open Range Low of the session, with mirrored stops and exits.

C003-S is **NOT** part of this research phase.
