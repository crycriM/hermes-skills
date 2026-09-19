# GitHub Developer Activity Provider

Built during Numerai Crypto bot development (2026-06) as a Tier-2 (unique)
data source. Fetches developer activity metrics (commits, contributors, stars,
forks) from GitHub's public REST API for each cryptocurrency's primary repo.

**Base URL:** `https://api.github.com`

## Rate Limits

| Authentication | Limit | Window |
|---|---|---|
| Unauthenticated | 60 req/hr | 1 hour |
| Personal access token | 5,000 req/hr | 1 hour |

With 39 repos at 3 calls each + 1s delay = ~2 min backfill time. Unauthenticated
is adequate for a one-time backfill of ~40 repos.

## Provider Architecture

`GitHubProvider` in `src/data_sources/github_dev.py` follows the same
backfill + incremental pattern as other providers, storing data in the
PIT store's `social` JSON column with source=`"github"`.

### Repo Mapping

Each Numerai UCID must be mapped to a GitHub `(org, repo)` pair. Source
types for building the map:

1. **DefiLlama protocol endpoint** — Some protocols have a `github` field
   (e.g., Cardano → `["input-output-hk"]`)
2. **Manual mapping** — Most repos are well-known:
   `bitcoin/bitcoin`, `ethereum/go-ethereum`, `solana-labs/solana`
3. **CoinMarketCap info API** — `/v2/cryptocurrency/info` has `urls` field
   including `source_code` URLs. (Requires valid Pro API key.)

Maintain a `REPO_MAP` dict:

```python
REPO_MAP: dict[str, tuple[str, str]] = {
    "1": ("bitcoin", "bitcoin"),                    # BTC
    "1027": ("ethereum", "go-ethereum"),            # ETH
    "5426": ("solana-labs", "solana"),              # SOL
    "52": ("ripple", "rippled"),                    # XRP
    "2010": ("input-output-hk", "cardano-node"),    # ADA
    "6636": ("polkadot-evaluate", "polkadot-sdk"),  # DOT
    # ...
}
```

### API Endpoints Used

| Endpoint | Data | Reliability |
|---|---|---|
| `GET /repos/{org}/{repo}` | Stars, forks, open issues, language | Always works |
| `GET /repos/{org}/{repo}/stats/commit_activity` | Weekly commits (52 weeks) | Returns 202/422 if cache not ready; ok if cached |
| `GET /repos/{org}/{repo}/contributors?per_page=1&anon=true` | Total contributor count (via Link header pagination) | Mostly works |

### Features Stored

Stored as JSON in the `social` column:

| Field | Source | Description |
|---|---|---|
| `weekly_commits` | `/stats/commit_activity` | Total commits in that week |
| `total_stars` | `GET /repos/{org}/{repo}` | Star count at fetch time |
| `total_forks` | `GET /repos/{org}/{repo}` | Fork count at fetch time |
| `open_issues` | `GET /repos/{org}/{repo}` | Open issue count |
| `contributor_count` | `GET /repos/.../contributors` | Total unique contributors |
| `language` | `GET /repos/{org}/{repo}` | Primary language |

## Known Issues

### Stats API Returns 422 (Cache Not Ready)

GitHub's `/stats/*` endpoints can return HTTP 202 (Accepted) or 422
(Unprocessable) when the aggregate data cache hasn't been generated yet.
The provider handles this gracefully by falling back to a single snapshot
row (current stats only, no weekly history).

**If you need the weekly history:** make a preliminary request to
`/repos/{org}/{repo}/stats/code_frequency` a few minutes before the
real backfill to trigger cache generation.

### Repo Name Drift

Projects rename orgs/repos over time (e.g., `maticnetwork` → Polygon,
`polkadot-evaluate` → `paritytech`). The `REPO_MAP` needs periodic
maintenance. Monitor 404 errors in backfill logs.

### Training Impact

GitHub features have weak predictive power on their own because:
- They update weekly (too slow for daily trading signals)
- They're correlated with market cap (bigger coins have more developers)
- Historical data is limited (GitHub only caches 52 weeks of commit stats)
