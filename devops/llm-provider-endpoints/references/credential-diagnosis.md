# Credential diagnosis - which key is in play, and did the provider block it?

Read-only ladder for "provider X stopped working, but the credits look fine". Never repoint a
provider or edit auth.json before presenting findings and getting a go-ahead - the user decides
on config changes. Everything here is a GET or a cheap probe.

## 1. Prove which credential the client actually uses

Never infer it from the config file. Several env vars can hold different keys of the same
provider, and the canonical var is often a shell REFERENCE to a suffixed one.

- auth.json pool entries carry `secret_fingerprint: sha256:<first 16 hex>`. Fingerprint each
  candidate env value and compare:

      python3 -c "
      import hashlib
      v = open('...').read().strip()          # candidate value, comment stripped
      print('sha256:' + hashlib.sha256(v.encode()).hexdigest()[:16])"

  A match proves that var is the key the client sends - identity established without printing
  any secret. A config's `api_key: ${VAR}` plus a pool entry whose fingerprint matches that VAR
  is conclusive.
- `.env` values often carry a trailing ` # comment`. Strip at `' #'` before fingerprinting.
  Whether the client stripped it too is answered by the response: a well-formed-but-blocked key
  returns 402/200-with-error, a malformed one returns 401.
- A canonical var can be `export VENICE_API_KEY=$VENICE_API_KEY_ex3` (a reference, not a
  literal). Resolve it with `bash -c 'source ~/.bashrc; echo $VAR'` or fingerprint the resolved
  value; a plain search for a literal under the canonical name finds nothing and looks like a missing key.

## 2. Read the key's own state (Venice)

    curl -s https://api.venice.ai/api/v1/api_keys/rate_limits -H "Authorization: Bearer $KEY"

Decisive fields: `accessPermitted`, `balances.{USD,DIEM,BUNDLED_CREDITS}`, `nextEpochBegins`.

- `balances.DIEM` is the key's REMAINING allowance for the current epoch. Zero remaining with a
  non-zero configured allowance means the allowance is spent - which is exactly what "spend limit
  exceeded" enforces. Do not read it as "0 used".
- This can contradict the dashboard's "used / daily allowance" counter. When the user reports such
  a contradiction, state the authoritative field and its value rather than restating the error
  message - the mismatch is the answer they are asking for.
- Take two readings minutes apart. A remaining balance that MOVES proves enforcement is live and
  the number is real, not a stale display. That observation is usually what resolves the
  confusion; without it the explanation reads as a guess.
- `nextEpochBegins` is 00:00Z daily. Re-probe just after the boundary: recovery means the limit is
  epoch-scoped, no recovery means it is a hard cap that needs a dashboard change.
- Two keys of one provider do NOT share a balance (one can show USD > 0 while the other shows
  DIEM 0). Before blaming the provider, confirm which key the GUI page you were shown belongs to.

## 3. Classify the response

| Signal | Meaning |
|---|---|
| 401 `Invalid API key` | malformed key, wrong var, or a trailing comment inside the value |
| 402 with JSON `error` | authenticated, then refused on billing (per-key cap / spend limit) |
| 200 with JSON `error` body | some gateways report caps this way - read the body, never the status alone |
| `x-ratelimit-remaining` present and non-zero | not throttling; the block is billing |
| 401 `Admin API key required` | the key is inference-only; account-level billing is unreadable with it |

An inference key cannot read account billing: `/api_keys`, `/billing/balance` and
`/billing/usage-history` all answer `401 Admin API key required`, and `/billing/usage` is sunset
(410). So "the account has credit but the key is blocked" cannot be cross-checked from that key -
state that limitation explicitly instead of guessing which side is right.

## 4. Sizing: a tiny allowance is unusable for an agent

When the cap is small, say so with numbers, because "raise the limit" only lands with arithmetic:

- The `e2ee-*` Venice models prepend ~1.5k prompt tokens to a one-word message.
- Flash-tier models run about $0.16/M input, so 0.1 DIEM (~$0.10) buys roughly 625k input tokens.
- A real Hermes turn (tool schemas + history, 30-100k tokens) costs 0.005-0.016 DIEM.

So a 0.1 DIEM/day cap is a handful of turns and one long session consumes the day. Recommend a cap
well above the daily burn, or pointing the client at a USD-funded key, before calling it fixed.

## 5. Same provider, different key per client

Search every client's config for the provider and fingerprint each resolved value. Two clients can
sit on two different keys of one provider, so "Kilo works, Hermes does not" is usually a key split,
not an endpoint problem or an outage. Check sibling Hermes profiles' `.env` too - each profile
carries its own copy of the key and fails identically.
