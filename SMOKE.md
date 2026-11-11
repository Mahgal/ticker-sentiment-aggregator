# Smoke test — ticker-sentiment-aggregator

Run on 2026-11-10 (UTC) with Python 3.12.3, from inside the project directory.
All commands below were actually run; exit codes are real.

## 1. Unit tests

```
python3 -m unittest discover -s tests -v
```

- Exit code: **0**
- Result: **9 tests ran, OK** (lexicon range/ordering/neutral, feed parsing incl.
  empty feed, CLI on sample feed, exact CSV header, empty-feed header-only CSV,
  unreachable `--endpoint` fails cleanly with a clear error)

## 2. CLI end-to-end on the sample feed

```
python3 aggregator.py --ticker AAPL --feed sample_feed.xml --out sentiment.csv
```

- Exit code: **0**
- Output: `AAPL: scored 7 headline(s) -> sentiment.csv`
- `sentiment.csv` contains the exact header `timestamp,headline,sentiment_score`
  plus 7 rows, one per headline; all scores in [-1.0, 1.0]
  (4 positive at 0.8000, 3 negative at -0.8000). The same output is pasted
  verbatim into README.md (verified programmatically: README example text
  matches `sentiment.csv` byte-for-byte).

## 3. Unreachable endpoint check (covered by unit test `test_unreachable_endpoint_fails_cleanly`)

```
python3 aggregator.py --ticker AAPL --feed sample_feed.xml --out /tmp/x.csv \
    --endpoint http://127.0.0.1:9/score
```

- Exit code: non-zero (test asserts `!= 0`)
- stderr: `error: could not reach sentiment endpoint http://127.0.0.1:9/score: ...`
  plus a hint to drop `--endpoint` for the offline scorer.

## Failures

None. No smoke test failed.
