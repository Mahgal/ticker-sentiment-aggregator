#!/usr/bin/env python3
"""ticker-sentiment-aggregator: score the sentiment of news headlines for a
stock ticker and write the results to CSV.

Stdlib-only, Python 3.10+. The default path is fully offline: it reads a local
sample RSS/XML or JSON file, or fetches a public RSS feed URL, and scores each
headline with a transparent lexicon-based mock scorer (small built-in
positive/negative word lists, deterministic, no model download, no API key).

An external LLM endpoint can be plugged in with --endpoint <url> -- the
endpoint must accept POST {"headline": ...} and return JSON
{"score": <float in [-1, 1]>} -- but that path is never the default and fails
cleanly with a clear message when the endpoint is unreachable.

Usage:
    python aggregator.py --ticker AAPL --feed sample_feed.xml --out sentiment.csv
    python aggregator.py --ticker AAPL --url https://example.com/feed.xml --out sentiment.csv
    python aggregator.py --ticker AAPL --feed sample_feed.xml --out sentiment.csv \
        --endpoint http://localhost:11434/score

Output CSV columns: timestamp,headline,sentiment_score
Every score is clamped to [-1.0, 1.0].
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Default scorer: transparent lexicon mock (deterministic, offline).
# ---------------------------------------------------------------------------

POSITIVE_WORDS = {
    "beat", "beats", "beating", "record", "surge", "surges", "soar", "soars",
    "rally", "growth", "grow", "grows", "strong", "stronger", "bullish",
    "upgrade", "upgraded", "outperform", "profit", "profits", "profitable",
    "gain", "gains", "gained", "rise", "rises", "rising", "up", "high",
    "higher", "success", "successful", "win", "wins", "optimistic", "buy",
    "expand", "expansion", "launch", "launches", "breakthrough", "approve",
    "approved", "boost", "boosts", "jump", "jumps", "climb", "climbs",
    "exceed", "exceeds", "exceeded", "solid", "robust", "milestone",
}

NEGATIVE_WORDS = {
    "miss", "misses", "missed", "fall", "falls", "fell", "drop", "drops",
    "dropped", "decline", "declines", "declined", "loss", "losses", "lose",
    "loses", "weak", "weaker", "bearish", "downgrade", "downgraded",
    "underperform", "slump", "plunge", "crash", "crisis", "risk", "risks",
    "cut", "cuts", "layoff", "layoffs", "investigation", "lawsuit", "fine",
    "fined", "concern", "concerns", "warning", "warns", "down", "lower",
    "disappoint", "disappoints", "disappointing", "recall", "delay",
    "delayed", "shortage", "fraud", "scandal", "bankrupt", "bankruptcy",
    "fail", "fails", "failed", "slump", "tumble", "tumbles", "sink", "sinks",
}

_WORD_RE = re.compile(r"[a-z]+")


def lexicon_score(headline: str) -> float:
    """Deterministic lexicon score in [-1.0, 1.0].

    score = (positive hits - negative hits) / max(1, total sentiment hits),
    scaled by 0.8 so a single-word headline never hits the extremes.
    A headline with no lexicon words scores 0.0 (neutral).
    """
    words = _WORD_RE.findall(headline.lower())
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    raw = (pos - neg) / total
    return round(max(-1.0, min(1.0, raw * 0.8)), 4)


def endpoint_score(headline: str, endpoint: str, timeout: float = 10.0) -> float:
    """Score one headline via an external LLM endpoint.

    The endpoint must accept POST {"headline": ...} and return JSON
    {"score": <float>}. Raises EndpointError on any failure.
    """
    payload = json.dumps({"headline": headline}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise EndpointError(
            f"could not reach sentiment endpoint {endpoint}: {exc.reason}"
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EndpointError(
            f"sentiment endpoint {endpoint} returned an invalid response: {exc}"
        ) from exc
    try:
        score = float(body["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EndpointError(
            f"sentiment endpoint {endpoint} did not return a numeric "
            f"'score' field: {body!r}"
        ) from exc
    return max(-1.0, min(1.0, score))


class EndpointError(RuntimeError):
    """Raised when the external --endpoint scorer cannot be used."""


# ---------------------------------------------------------------------------
# Feed parsing (RSS/XML or JSON, local file or URL).
# ---------------------------------------------------------------------------

def parse_rss(text: str) -> list[dict]:
    """Parse RSS/XML text into a list of {'timestamp': str, 'headline': str}."""
    root = ET.fromstring(text)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        title = title.strip()
        if not title:
            continue
        pub_date = item.findtext("pubDate") or ""
        items.append({"timestamp": pub_date.strip(), "headline": title})
    return items


def parse_json(text: str) -> list[dict]:
    """Parse JSON text: a list of objects with 'headline' (+ optional
    'timestamp'), or an object with a 'headlines' list."""
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("headlines", [])
    items = []
    for entry in data:
        if isinstance(entry, str):
            items.append({"timestamp": "", "headline": entry})
        elif isinstance(entry, dict) and entry.get("headline"):
            items.append({
                "timestamp": str(entry.get("timestamp", "")),
                "headline": str(entry["headline"]),
            })
    return items


def load_feed(feed_path: str | None, url: str | None) -> list[dict]:
    """Load headlines from a local file (--feed) or a public RSS URL (--url)."""
    if url:
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                text = response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise SystemExit(
                f"error: could not fetch feed URL {url}: {exc.reason}"
            )
    else:
        assert feed_path is not None
        try:
            with open(feed_path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise SystemExit(f"error: could not read feed file {feed_path}: {exc}")
    text = text.strip()
    if not text:
        return []
    if text.startswith("<"):
        try:
            return parse_rss(text)
        except ET.ParseError as exc:
            raise SystemExit(f"error: could not parse feed as RSS/XML: {exc}")
    try:
        return parse_json(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            "error: feed is neither valid RSS/XML nor JSON "
            f"(JSON error: {exc})"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score news-headline sentiment for a stock ticker."
    )
    parser.add_argument("--ticker", required=True, help="stock ticker, e.g. AAPL")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--feed", help="local RSS/XML or JSON file of headlines")
    group.add_argument("--url", help="public RSS feed URL to fetch")
    parser.add_argument("--out", required=True, help="output CSV path")
    parser.add_argument(
        "--endpoint",
        default=None,
        help="optional external LLM scoring endpoint "
             "(POST {\"headline\": ...} -> {\"score\": float}); "
             "default is the offline lexicon scorer",
    )
    args = parser.parse_args(argv)

    items = load_feed(args.feed, args.url)

    if args.endpoint:
        scorer = lambda h: endpoint_score(h, args.endpoint)  # noqa: E731
    else:
        scorer = lexicon_score

    rows = []
    for item in items:
        try:
            score = scorer(item["headline"])
        except EndpointError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print(
                "hint: the default offline lexicon scorer needs no endpoint; "
                "drop --endpoint to use it.",
                file=sys.stderr,
            )
            return 2
        score = max(-1.0, min(1.0, float(score)))
        rows.append({
            "timestamp": item["timestamp"],
            "headline": item["headline"],
            "sentiment_score": f"{score:.4f}",
        })

    try:
        with open(args.out, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["timestamp", "headline", "sentiment_score"]
            )
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        print(f"error: could not write output CSV {args.out}: {exc}",
              file=sys.stderr)
        return 2

    print(f"{args.ticker}: scored {len(rows)} headline(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
