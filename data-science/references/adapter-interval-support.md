# Exchange Adapter Interval Support

All adapters accept `interval` parameter in `fetch_ohlcv()`. Default is `"1h"`.

## Interval Mapping by Exchange

| Interval | Binance | Bybit | OKX | Hyperliquid | dYdX |
|---|---|---|---|---|---|
| `1h` | `"1h"` | `"60"` | `"1H"` | `"1h"` | `"1h"` (resolution param) |
| `4h` | `"4h"` | `"240"` | `"4H"` | `"4h"` | `"1h"` (limited) |
| `1d` | `"1d"` | `"D"` | `"1D"` | `"1d"` | `"1D"` |

## Adapter-Specific Notes

### Binance
- Passes interval string directly to API (`interval` param)
- No conversion needed
- OI API uses separate `period` param (always `"1h"` for `openInterestHist`)

### Bybit
- Converts to numeric: `{"1h": "60", "4h": "240", "1d": "D"}`
- Map defined in `bybit_interval_map` dict

### OKX
- Uppercase conversion: `interval.replace("h", "H").replace("d", "D")`
- `"1h"` → `"1H"`, `"4h"` → `"4H"`

### Hyperliquid
- Uses resolution map: `{"1h": "1h", "4h": "4h"}`
- Fallback to `"1d"` if interval not in map
- Falls back to daily if 1h returns no data

### dYdX
- Uses `resolution` param (not `interval`)
- Limited interval support; mostly `"1h"` and `"1D"`

## Impact of 1h → 4h Switch

| Metric | 1h | 4h | Change |
|---|---|---|---|
| Bars/symbol/180d | ~4,320 | ~1,080 | -75% |
| API calls/symbol | ~36 pages | ~9 pages | -75% |
| DB rows (100 symbols) | 432K | 108K | -75% |
| OI backfill alignment | `DATE_TRUNC('hour', ts)` | `DATE_TRUNC('4 hours', ts)` or nearest 4h boundary | Must update |

## OI Backfill Alignment

When switching to 4h bars, the OI backfill `DATE_TRUNC` must match the bar boundaries:

```sql
-- For 1h bars:
WHERE DATE_TRUNC('hour', ts) = DATE_TRUNC('hour', $3::timestamptz)

-- For 4h bars (bars at 00:00, 04:00, 08:00, ...):
WHERE DATE_TRUNC('4 hours', ts) = DATE_TRUNC('4 hours', $3::timestamptz)
```

Binance OI API returns hourly snapshots regardless — the matching logic must snap to the nearest 4h bar.

## Coverage Heuristic

`_has_sufficient_existing_data()` checks bars/day threshold:
- 1h: expect ≥20 bars/day (24 expected)
- 4h: expect ≥5 bars/day (6 expected)
