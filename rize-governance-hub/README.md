# RIZE Governance Hub — Data Pipeline

## File placement in repo

```
rize-governance-hub/
  scrape_governance.py     ← bootstrap (full erase + rewrite)
  update_governance.py     ← daily incremental (merge new 8d events)
  pool-config.json         ← generated
  bond-lifecycle.json      ← generated
  bond-broken.json         ← generated
  nft-transfers.json       ← generated
  bond-timemarker.json     ← generated
  bond-created.json        ← generated

.github/workflows/
  bootstrap-governance.yml ← manual trigger (workflow_dispatch)
  update-governance.yml    ← daily via cron-job.org
```

## Bootstrap (first time / full reset)

Run via GitHub Actions → Actions → "Bootstrap Governance JSONs" → Run workflow.
Leave "subgraph" input empty to run all 6.
To bootstrap a single subgraph: enter its name (e.g. `bond-created`).

## Daily update

- Trigger via cron-job.org at 02:30 UTC
- POST to: `https://api.github.com/repos/hcftrize/TOKERIZE/actions/workflows/update-governance.yml/dispatches`
- Body: `{"ref":"dev"}`
- Auth: GitHub PAT with `repo` scope

## Re-bootstrap when bond-created / bond-timemarker finish indexing

Just re-trigger "Bootstrap Governance JSONs" — it fully overwrites the JSON.

## JSON format

```json
{
  "subgraph": "bond-broken",
  "scraped_at": "2026-04-26T...",
  "bootstrap": true,
  "counts": { "bondBrokens": 97 },
  "data": {
    "bondBrokens": [...]
  }
}
```

## Future: single unified subgraph

Once all 6 subgraphs are stable, replace with one combined subgraph
indexing 8d rolling history. The JSON format stays identical —
just merge the 6 files into one and update the daily cron to call it.
