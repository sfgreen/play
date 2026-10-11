# Gate 1: Requirements

Status: **DRAFT, awaiting owner approval.** Date: 2026-10-11.

The governing design is the RAIM prompt the owner supplied. Where the source text was
illegible, this document lists the gap in §9 rather than guessing.

---

## 0. Pre-gate finding: the economics gate likely fails on the obvious default

The first hard gate is, per fill:

```
maker_fee + E[adverse_selection]  <  ½ · typical_quoted_spread      (all in bps of mid)
```

On **Binance spot BTCUSDT at the base (VIP 0) tier** this fails before measuring anything:

| Term | Value | Source / status |
|---|---|---|
| Maker fee | 10 bps (7.5 bps paying in BNB) | Third-party fee tables; not confirmed against Binance's own page, which this environment can't reach |
| Typical quoted spread | About 1 tick (0.01 USDT) at a five-figure price, so far below 0.1 bp | Known market structure; must be measured (§4) |
| ½ spread | Far below 0.05 bp | — |
| Result | The fee alone is more than 100× the budget | **FAIL** |

USDⓈ-M perpetual maker fees (around 2 bps at the low tiers, minus a 10% BNB discount
according to Binance's support article) also fail on BTC and ETH perps, where the spread
is also about 1 tick.

**Implication:** with retail fees, a liquid major is the wrong place to start. The gate can only pass where
(a) the effective maker fee is about zero or a rebate (a VIP tier, a market-maker program,
or a zero-maker-fee pair), or (b) the relative spread is wide enough. Wide spreads usually
come with high adverse selection, so (b) has to be checked with markouts and not assumed.

**Requirement R-0 (the first build work, if approved):** before any strategy code, build
a read-only data capture for a shortlist of candidate instruments. Measure:
- the time-weighted median relative spread,
- E[AS] as signed mid-price markouts after our hypothetical passive fills at 1s, 5s,
  30s and 60s,
- the owner's actual fee tier.

Then pick the venue and instrument, or stop. Gate 1 cannot choose the instrument without
the owner's fee tier and jurisdiction (§9, Q1–Q2).

## 1. Objective

Build a regime-adaptive market maker that:
- estimates short-horizon fair value,
- quotes dynamically,
- controls inventory,
- detects toxic flow,
- adapts to regimes.

The priorities are capital preservation and verifiable net edge after costs. Start from
data capture, a simulator and a measurable baseline, and add complexity only when
out-of-sample evidence justifies it.

## 2. Scope

**In scope (this program):**
- one venue and one instrument, chosen by R-0,
- read-only market data capture,
- a tick-level simulator,
- a baseline Avellaneda–Stoikov / Guéant–Lehalle–Fernandez-Tapia quoter,
- the regime engine, risk governor, slow-brain adapter, research and validation tooling,
- `SIMULATION` and `PAPER` modes.

**Out of scope until separately approved:**
- live order placement,
- multiple venues or instruments,
- statistical arbitrage legs (see Q6),
- any LLM in the tick path.

## 3. Architecture requirements (two isolated layers)

### FAST BODY

Deterministic, no LLM, millisecond scale. The pipeline is:

WebSocket L2 book and trades → venue adapter → features → regime posterior → quotes →
order manager → risk governor.

- **FB-1** The fast body must run, and stay safe, with the slow brain absent, stale or
  erroring.
- **FB-2** It must be deterministic. The same recorded input plus the same config and
  seed gives byte-identical decisions. This is required for replay and audit.
- **FB-3** The venue adapter must be pluggable. The exchange spec (tick size, lot size,
  fees, rate limits) comes from the venue's primary API docs and is version-pinned in
  config.

### SLOW BRAIN

Runs on a scale of seconds to minutes and uses `tradingview-mcp`. Its output is a
schema-validated state:

```
{ z_VIX, TrendAlign ∈ {-1,0,1}, VolExpansion ∈ {0,1}, EventRisk ∈ {0,1},
  UniverseScore, risk_multiplier m ∈ [0,1], confidence c, as_of }
```

- **SB-1** The slow brain is polled, at most about once per second in total. It never
  sits in the tick loop.
- **SB-2** It has no order, cancel or pricing authority. The LLM never prices, places or
  cancels orders.
- **SB-3** The applied multiplier is `min(m_LLM, m_rules)`. The slow brain can only
  **tighten** risk. Any value that would loosen risk is clamped and logged as a violation.
- **SB-4** Error handling uses the MCP error envelope `{error:{code, message, retryable,…}}`:
  - If `retryable`, back off and keep the last good state.
  - Otherwise decay confidence as `c = exp(-age/τ)` and fall back toward `m_rules`.
  - Schema-invalid output is treated as an outage, never as data.
- **SB-5** Supply-chain controls:
  - Install only the official PyPI package, with
    `uvx --from tradingview-mcp-server tradingview-mcp`, on Python 3.10–3.13 (pin 3.13).
  - The version is pinned and hash-locked.
  - Never use npm or `package.json` clones. The upstream README warns that malicious
    copies install malware through npm.
- **SB-6** Respect upstream limits:
  - 60s screener cache,
  - at most 4 concurrent TA calls, with starts at least 0.8s apart,
  - optional `MARKETAUX_API_TOKEN` (free tier: 100 requests/day, 4h cache).
- **SB-7** The tool provides no order book, no trade tape and no order placement, and its
  backtests use daily or hourly bars only. It can supply context only, never
  microstructure signals.

## 4. Regime engine requirements

- **RE-1** A four-state HMM:

  | State | Meaning |
  |---|---|
  | R1 | Calm, mean-reverting |
  | R2 | Trending or informed flow |
  | R3 | High volatility or stress |
  | R4 | See Q3 (presumed toxic or dislocated, quotes pulled) |

- **RE-2** Observations:
  - bipower-variation volatility,
  - spread,
  - depth,
  - VPIN,
  - OFI predictiveness,
  - variance ratio,
  - Hawkes branching ratio n = α/β,
  - slow-state context (z_VIX, event flag), which only tilts the transition matrix.
- **RE-3** Fitting and filtering:
  - Fit offline with Baum–Welch.
  - Run a forward filter online: `π_t(k) ∝ f_k(x_t) · Σ_j π_{t-1}(j) A_{jk}`.
  - Use Bayesian change-point detection as an override alarm.
- **RE-4** Parameter blending is `θ = Σ_k π_k θ_k`, with a conservative bias toward
  R3/R4.
- **RE-5** Discrete actions use hysteresis: pull quotes when π(R4) > 0.7 for N
  consecutive updates (N is in Q3), and release below 0.4.
- **RE-6** Each regime has a specified quoting policy, and the system must not depend
  on R1 to be profitable overall. Only the R1 policy is legible in the source (see Q3).

## 5. Inventory and risk requirements

Deterministic limits sit outside all models and outside the LLM.

- **IR-1** The inventory limit is `Q_max = min(B / (z·σ·√h_unwind), c·depth)`.
- **IR-2** Hard limits and controls:
  - max gross exposure,
  - drawdown halt,
  - stale-feed cancel-all (the threshold is a config value, with a sequence-gap check),
  - reject-rate and message-rate backoff kept below venue limits,
  - widen-then-pause on a loss streak,
  - auto-disable when a cointegration relationship breaks (see Q6).
- **IR-3** The LLM may recommend tighter settings. It may never:
  - loosen a hard limit,
  - override a halt,
  - increase exposure.

  This is enforced in code and covered by tests.
- **IR-4** Disable unprofitable sides and unsupported strategies automatically.
- **IR-5** Compliance:
  - no spoofing, layering or wash trading;
  - self-trade prevention enabled;
  - every order must have intent to trade.

## 6. Research and validation requirements

- **RV-1** A tick-level simulator that models:
  - queue position, partial fills, cancel latency and ack delay with jitter,
  - fees and rebates, slippage,
  - a stress mode at 2× measured latency.
- **RV-2** A leakage audit for each feature:
  - look-ahead,
  - survivorship bias,
  - exchange vs. local timestamp errors.
- **RV-3** Purged and embargoed walk-forward evaluation.
- **RV-4** Reporting:
  - per-regime PnL attribution (spread capture, adverse selection, inventory PnL, fees),
  - markout reports at several horizons,
  - a parameter registry with provenance (see Q7).
- **RV-5** Never report performance figures that weren't produced by this pipeline, and
  never present a design document as a working system.

## 7. Operational requirements

- **OP-1** Default mode is `SIMULATION`, then `PAPER`. Live trading stays **disabled**
  and has no code path enabled until the owner approves it separately in writing (see Q4).
- **OP-2** No API keys or secrets in git. Use read-only keys for data capture.
- **OP-3** Append-only audit logs, recorded inputs, config hashes, reproducible runs and
  one-command rollback.
- **OP-4** Before any deployment, the owner confirms fees and legality in their
  jurisdiction.

## 8. Acceptance criteria for the whole program (`final_check`)

Each of these must be answered with evidence before any implementation is approved:

1. Is the edge still positive after fees, adverse selection, slippage and realistic
   queue fills?
2. Is the alpha predictive out of sample?
3. Does each regime behave as intended, and does the system make money outside R1?
4. Does it survive:
   - feed failures,
   - volatility spikes,
   - adverse inventory,
   - structural breaks?
5. Is the slow brain isolated from execution?
6. Did the LLM ever loosen a limit? This is answered by an audit-log query, and the
   answer must be "never".
7. What could we be wrong about?

## 9. Open questions (blocking, because parts of the source were illegible)

| # | Question | Default proposed if no answer |
|---|---|---|
| Q1 | What is your jurisdiction? (binance.com is unavailable in some, including the US.) | Do not choose a venue |
| Q2 | What is your actual maker fee tier, and can you get rebates or join an MM program? | Assume VIP 0, which means §0 fails on majors |
| Q3 | What is the full regime policy table for R2–R4, and N for the R4 hysteresis? Only "R1: passive two-sided…" is legible. | R2: skew and widen against the flow, one-sided allowed. R3: widen and cut size. R4: pull quotes. N = 3. |
| Q4 | "Live order placement stays ___ ___ profitability" is garbled. | Disabled until validated profitability **and** your written approval |
| Q5 | The "reserve an empty adapter slot … reserve one test …" passage is illegible. | One stub adapter, plus a test asserting the slow brain cannot loosen risk |
| Q6 | "Auto-disabled when cointegration breaks" implies a pairs or stat-arb leg. Is it in scope? | Out of scope for v1 |
| Q7 | The RV passage ("living parameter …", "… cost of invalidation …") is illegible. | Parameter registry, plus a documented invalidation trigger for each parameter |
| Q8 | The AgenKit `/agenkit` harness is not installed in this environment. | Run the same gates manually, as docs in this repo |

## 10. Next step if approved

Gate 2 (architecture), then R-0 data capture: read-only, no keys with trade permission.
