# ticker-sentiment-aggregator

Score the sentiment of news headlines for a stock ticker and write the results to a CSV — offline by default, stdlib-only, no API key needed.

## Quick start

```bash
python aggregator.py --ticker AAPL --feed sample_feed.xml --out sentiment.csv
```

To fetch a live public RSS feed instead of a local file:

```bash
python aggregator.py --ticker AAPL --url https://example.com/feed.xml --out sentiment.csv
```

Requires Python 3.10+. No dependencies to install — the standard library is all it uses.

## Example output

Real output from running the command above on the bundled sample feed (`sample_feed.xml`):

```csv
timestamp,headline,sentiment_score
"Mon, 10 Nov 2026 08:00:00 GMT",AAPL beats earnings expectations as iPhone sales surge to record high,0.8000
"Mon, 10 Nov 2026 09:15:00 GMT",AAPL shares fall after analysts warn of weak demand and supply delays,-0.8000
"Mon, 10 Nov 2026 10:30:00 GMT",AAPL unveils new chip with breakthrough performance and strong early reviews,0.8000
"Mon, 10 Nov 2026 11:45:00 GMT",Regulators open investigation into AAPL over app store fees,-0.8000
"Mon, 10 Nov 2026 13:00:00 GMT","AAPL announces $110 billion buyback and raises dividend, shares climb",0.8000
"Mon, 10 Nov 2026 14:20:00 GMT",AAPL faces lawsuit over battery claims as shares drop,-0.8000
"Mon, 10 Nov 2026 15:35:00 GMT","AAPL reports solid growth in services revenue, outlook remains optimistic",0.8000
```

Every score is clamped to `[-1.0, 1.0]`: positive means the headline reads bullish, negative bearish, `0.0` neutral.

## How scoring works

The default scorer is a **transparent lexicon mock**: a small built-in list of positive and negative finance words, counted deterministically. It is a demo baseline, not a trained model — it cannot understand nuance, sarcasm, or context. Its word lists live at the top of `aggregator.py` and are easy to inspect and extend.

To plug in a real model, point the tool at an external LLM endpoint:

```bash
python aggregator.py --ticker AAPL --feed sample_feed.xml --out sentiment.csv \
    --endpoint http://localhost:11434/score
```

The endpoint must accept `POST {"headline": "..."}` and return JSON `{"score": <float>}`. If the endpoint is unreachable or returns garbage, the tool exits with a clear error instead of silently falling back — the offline lexicon scorer is used only when no `--endpoint` is given.

## Sample data

`sample_feed.xml` contains 7 fictional headlines written for this demo. They are **sample data, not live market data** — they do not reflect real news or real prices. They exist so the tool can be tried fully offline.

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT — see [LICENSE](LICENSE).
