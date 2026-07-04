# 07 — Glossary

Domain terms so any agent (and the owner) reads without guessing.
Owner is a beginner: UI must use the plain-English column, never bare jargon.

| Term | Plain English |
|------|---------------|
| PSX | Pakistan Stock Exchange — the market where Pakistani company shares trade |
| KSE-100 | Main index: combined score of 100 biggest PSX companies. Market's temperature. |
| KMI-30 | Index of 30 largest Shariah-compliant companies |
| KATS | PSX's electronic trading system (Karachi Automated Trading System) |
| Ticker/Symbol | Short code for a company, e.g. LUCK = Lucky Cement |
| OHLC | Open/High/Low/Close — day's first, highest, lowest, last price |
| Volume | How many shares changed hands |
| EPS | Earnings per share — profit the company makes per share per year |
| P/E | Price ÷ EPS — how many years of profit you pay for one share. Lower can mean cheaper. |
| Book value | Company's net worth per share on paper |
| Dividend yield | Cash the company pays you yearly, as % of share price |
| Debt ratio | How much the company owes vs owns. High = riskier. |
| Stop-loss | Auto-sell order if price falls to set level. Caps your loss. |
| Position | Shares you currently hold in one company |
| Exposure | Total money at risk in the market right now |
| Sector concentration | Too many eggs in one industry basket |
| Circuit breaker (exchange) | PSX halts a stock after extreme daily move (±10% or PKR 1) |
| Circuit breaker (ours) | Our system freezes all trading on anomaly (stale data, errors) |
| T+2 | You pay/receive shares 2 working days after the trade |
| CGT | Capital gains tax — tax on profit when you sell |
| Brokerage commission | Fee the broker charges per trade |
| Paper trading | Practice with fake money, real prices. No real rupees at risk. |
| P&L | Profit and loss |
| Drawdown | Biggest drop from a peak. How deep the hole got. |
| Hit rate | % of trades that made money |
| Bull case | Argument FOR buying |
| Bear case | Argument AGAINST buying |
| Liquidity | How easily you can sell without moving the price. Thin stock = hard exit. |
| Positional trading | Hold for days–weeks on a thesis, not minute-to-minute |
| Result season | Weeks when companies publish quarterly profits — prices jump around |
| Dividend capture | Buying before dividend entitlement date to collect payout |
| Sector rotation | Money flowing from one industry to another; ride the incoming one |

## Project-specific
| Term | Meaning |
|------|---------|
| Scout | Agent that finds trade opportunities (bull case) |
| Devil's Advocate | Agent that attacks each proposal (bear case, fresh context) |
| Judge | Agent that weighs both, verifies claims vs data, writes final report |
| Proposal | One trade idea + full debate awaiting owner decision |
| Approval gate | Server-side check: no execution without owner tap on THAT proposal |
| Risk layer | Deterministic guard code agents can't touch |
| Lessons store | One-file-per-lesson memory agents read before each session |
| Reflection job | Nightly post-close review that updates lessons + strategy weights |
| Strategy module | Named, source-cited trading idea (e.g. dividend-capture) with a weight |
| Mock-agent mode | Pipeline runs with canned agent responses when no API key set |
