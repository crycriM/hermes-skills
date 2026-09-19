# pCloud publink — manifest + whole-folder download

pCloud's published folder link (`e.pcloud.link/publink/show?code=<CODE>`) is a
JS-driven SPA: the listing isn't in the HTML, so plain `curl`/HTTP gets an empty
shell. But the page body embeds a `var publinkData = {...};` blob carrying the
full folder manifest AND a single-request way to grab every file at once.

## What's in `publinkData`

- `metadata.contents[]` — full manifest: `name`, `size`, `fileid`, `isfolder`.
  This is the authoritative file list; the UI truncates names
  (`okx_btc_fut...arquet`) and may paginate.
- `downloadlink` — zips the ENTIRE folder in one request:
  `https://eapi.pcloud.com/getpubzip?code=<CODE>`
- `candownload` (bool) — if false the owner disabled download; stop.
- `ownerispremium`, `usercanupload`, etc. — not needed for download.

## Exact recipe

```
1. mcp__playwright__browser_navigate {url: "https://e.pcloud.link/publink/show?code=<CODE>"}
2. mcp__playwright__browser_evaluate → parse the manifest, print names+sizes:
     const m = document.body.innerHTML.match(/var publinkData = (\{[\s\S]*?\});/);
     const d = JSON.parse(m[1]);
     // d.metadata.contents = files; d.downloadlink = whole-folder zip
3. wget -c -t 5 -O folder.zip "<downloadlink>"     ← resumable (-c)
4. unzip -t folder.zip                             ← verify integrity first
5. unzip -q folder.zip                             ← extract (files sit under
                                                      <folder>/ prefix — mv up
                                                      if you want them flat)
```

## Verification

- Manifest count (step 2) === `unzip -l` file count === extracted `*.ext | wc -l`.
  In the reference run (OKX BTC data folder): 112 = 112 = 112 across 4 types
  (futures/options/perpetuals/future_spreads, 28 each).
- Parquet spot-check: file must start with 4-byte magic `PAR1`
  (`head -c 4 file | xxd`).

## Notes / pitfalls

- `#/login` in the URL hash does NOT necessarily gate the folder — it may be
  readable without a password (confirmed in the reference run; `candownload`
  was true). Confirm via snapshot before asking the user for credentials.
- `getpubzip` returns the whole folder as one zip — far cheaper than N
  per-file downloads. It may be unavailable for very large folders.
- The `downloadlink` host is `eapi.pcloud.com` (the API endpoint), distinct
  from the `e.pcloud.link` UI host.
