# 03 — Data

Big system, lots of data. This file is the source of truth for data shape.

## Data sources
| Source | What | Format | Update freq | Access (url/auth) |
|--------|------|--------|-------------|-------------------|
| <e.g. PSX feed> | <prices/OHLC> | <csv/json/api> | <live/daily> | <...> |

## Storage
- Where raw data lives: <path / db / bucket>
- Where processed data lives: <...>
- DB engine + connection: <...>

## Schemas / tables
### <table_or_file name>
| Field | Type | Meaning | Example |
|-------|------|---------|---------|
| <...> | <...> | <...> | <...> |

## Data volume
<rows, size, growth rate — matters for big system>

## Gotchas
<missing days, splits, ticker changes, timezone, currency>
