# Numerai Crypto Auth & Submission Diagnostics

## Raw GraphQL queries for auth testing

These bypass the `numerapi` library to isolate credential issues from library bugs.

### Test credentials directly

```python
import requests, os
from dotenv import load_dotenv
load_dotenv()

pub = os.getenv('NUMERAI_PUBLIC_ID')
sec = os.getenv('NUMERAI_SECRET_KEY')
headers = {
    'Authorization': f'Token {pub}${sec}',
    'Content-type': 'application/json'
}

# Authenticated query — tests if credentials are valid
resp = requests.post('https://api-tournament.numer.ai/',
    json={'query': 'query { account { username email id status } }'},
    headers=headers)
print(resp.json())
```

**Interpreting the response:**
- `{"data":{"account":{"username":"...", ...}}}` → credentials VALID, the library has a bug
- `{"data":{"account":null},"errors":[{"error":"Session not found","code":"session_not_found"...}]}` → key pair exists but session expired. Regenerate key.
- `{"errors":[{"message":"..."}]}` with auth-related message → invalid format. Check copy-paste.
- Connection/timeout error → network issue, not auth.

### Check round deadlines (no auth needed)

```python
import requests

# Tournament 12 = Crypto, tournament 1 = Stocks, tournament 8 = Signals
# Replace ROUND_NUM with the round you're checking
resp = requests.post('https://api-tournament.numer.ai/',
    json={'query': 'query { rounds(tournament: 12, limit: 10) { number openTime closeTime } }'})
print(resp.json())
# Returns: {'data': {'rounds': [{'closeTime': '2026-06-04T12:00:00Z', 'number': 1281, 'resolveTime': '...'}]}}
```

The `closeTime` is the submission deadline. After this time, uploads auto-queue for the next round. `resolveTime` is when scores are finalized (~30 days later for Crypto).

**Current round lookup without hardcoding:**
```python
from numerapi import NumerAPI
api = NumerAPI()  # no auth needed for get_current_round()
`current = api.get_current_round(tournament=12)  # 12 = Crypto
print(f"Current round: {current}")
```

## Secret key format

- Real Numerai secret keys are **30-40 characters** of hex/base64
- A key shorter than 20 chars is almost certainly a copy-paste fragment
- **Keys containing literal `...` (three dots) are obfuscated placeholders** — NEVER treat them as valid. Example: `6DMYUK...QTRH` is clearly obfuscated. Flag immediately and ask for the full key.
- The key is the SECOND part shown on numer.ai/account → API Keys (the part after the public ID)
- Common copy errors: trailing newline, leading space, wrong field copied

## API key scopes

Different Numerai API operations need different scopes on the key. The error message names the missing scope:

| Error message | Missing scope | Needed for |
|---|---|---|
| `Insufficient permission for read_user_info` | `read_user_info` | `get_account()`, `get_models()` |
| `Insufficient permission for upload_submission` | `upload_submission` | `upload_predictions()` |
| `Insufficient permission for read_submission_info` | `read_submission_info` | `submission_status()`, `submission_performance()` |

Fix: Go to numer.ai/account → API Keys → edit the key and add the needed scope. No key regeneration needed — scopes can be added/removed on existing keys.

**Minimal scope set for submission-only workflow:** `upload_submission` + `read_submission_info`. You can skip `read_user_info` entirely if you know the model_id manually — `get_models()` auto-discovery is a convenience, not a requirement.

## Model ID requirement (Crypto-specific)

The stock Numerai tournament auto-resolves a default model. Crypto does NOT — you MUST:
1. Create a model at https://numer.ai/crypto
2. Get its UUID from the model settings page (or from the URL)
3. Pass it as `model_id="..."` to every `upload_predictions()` call

**Auto-discovery via `get_models()`:** Returns `{name: uuid}` dict, not a list. Access with `list(models.values())[0]`, not `[0]`.

**Note:** Different tournament IDs return different model registries. With `tournament_id=8` (Signals default), `get_models()` returns names like `cricrym`. With `tournament_id=12` (Crypto), it returns names like `m5_draft`. If `get_models()` returns models you don't recognize or empty, check `api.tournament_id`.

**`upload_submission` implementation pattern:** The project's `submit.py` originally had this function as a stub raising `NotImplementedError`. The actual implementation:

```python
def upload_submission(submission_path: Path) -> str:
    api = get_api()  # auto-sets tournament_id=12
    models = api.get_models()
    model_id = list(models.values())[0]

    submission_id = api.upload_predictions(
        file_path=str(submission_path),
        model_id=model_id,
    )
    logger.info("Uploaded! submission_id=%s", submission_id)
    return submission_id
```

`upload_predictions` returns a string submission_id, not a dict with a model_id key.

## Round schedule

Crypto rounds open/close daily Monday through Saturday at ~12:00 UTC. There are NO rounds on Sunday — the Saturday round stays open until Tuesday, creating a 3-day gap. Observed pattern (verified via GraphQL on 2026-06-06, tournament=12):

| Opens | Closes | Gap |
|-------|--------|-----|
| Mon | Tue | 1 day |
| Tue | Wed | 1 day |
| Wed | Thu | 1 day |
| Thu | Fri | 1 day |
| Fri | Sat | 1 day |
| Sat | Tue (next) | 3 days — no Sun/Mon rounds |

Rounds overlap — 24 concurrent rounds at any time, each with a ~30-day resolution window. Missing one deadline means your submission queues for the next open round. No penalty, no manual action needed.

**Cron scheduling implication:** Daily submission on Sun/Mon is wasted — both days submit to the Saturday-opened round. Schedule cron for **Tue–Sat only** (5 days/week).

## Submission column format

Crypto submissions need two columns:
- `symbol`: valid token ticker from the live universe (e.g. `"BTC"`, `"ETH"`)
- `prediction`: float between 0 and 1 (exclusive, percentile-ranked)
- Minimum 100 valid symbols required

**Common submission rejection causes:**

| Error | Cause | Fix |
|---|---|---|
| `invalid_submission_headers: headers must be one of ['symbol']` | Using `id` (stock format) or wrong column name | Use `symbol` column, not `id`. The stock tournament uses `id` + `prediction` — different schemas. |
| `invalid_submission_headers: headers must be one of ['id']` | API is routing to stock tournament (tournament_id=1 or 8) instead of Crypto (12) | Set `api.tournament_id = 12` before calling `upload_predictions()` |
| `invalid_submission_ids: Not enough stocks submitted` | Using `ucid` (numeric CMC IDs like `"1"` for BTC) instead of ticker names | Use `symbol` column (ticker names like `"BTC"`) from live.parquet |
| `Not enough stocks submitted` (and you used `symbol`) | Symbols don't match current live universe | Download latest live.parquet before building submission |
| Duplicate symbols error | Same ticker appears twice | Deduplicate before submitting |

The stock tournament uses `id` + `prediction` columns — don't confuse them. Crypto uses `symbol`.
