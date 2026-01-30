# Long-run Playbook

This playbook shows how to run a long paper harness with a large market_state feed and generate an audit summary.

## 1) Generate a large feed

```bash
python -m src.paper.feed_generate --out runs/feeds/feed_500k.jsonl --rows 500000 --seed 42
```

## 2) Run long paper harness (example: 6 hours)

```bash
python -m src.paper.cli_long_run \
  --run-id longrun_001 \
  --duration-seconds 21600 \
  --restart-every-seconds 900 \
  --rotate-every-records 50000 \
  --replay-every-records 20000 \
  --feed runs/feeds/feed_500k.jsonl
```

## 3) Generate audit summary

```bash
python -m src.audit.report_decisions \
  --run-dir runs/longrun_001 \
  --out runs/longrun_001/summary.json
```

## 4) Acceptance criteria

- summary.json exists
- replay_verification.mismatched == 0
- replay_verification.hash_mismatch == 0
- replay_verification.errors == 0
