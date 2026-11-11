"""Unit tests for ticker-sentiment-aggregator (stdlib unittest only)."""

import csv
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aggregator  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SAMPLE_FEED = os.path.join(PROJECT, "sample_feed.xml")


class TestLexiconScorer(unittest.TestCase):
    def test_scores_within_range(self):
        headlines = [
            "AAPL beats earnings expectations as iPhone sales surge to record high",
            "AAPL shares fall after analysts warn of weak demand and supply delays",
            "AAPL unveils new chip with breakthrough performance",
            "Regulators open investigation into AAPL over app store fees",
            "AAPL announces buyback and raises dividend, shares climb",
            "AAPL faces lawsuit over battery claims as shares drop",
            "AAPL reports solid growth in services revenue",
            "AAPL holds its annual shareholder meeting on Tuesday",
        ]
        for headline in headlines:
            score = aggregator.lexicon_score(headline)
            self.assertGreaterEqual(score, -1.0, headline)
            self.assertLessEqual(score, 1.0, headline)

    def test_positive_above_negative(self):
        positive = "AAPL beats earnings as sales surge to record high"
        negative = "AAPL shares fall after analysts warn of weak demand"
        self.assertGreater(
            aggregator.lexicon_score(positive),
            aggregator.lexicon_score(negative),
        )
        self.assertGreater(aggregator.lexicon_score(positive), 0.0)
        self.assertLess(aggregator.lexicon_score(negative), 0.0)

    def test_neutral_headline_scores_zero(self):
        self.assertEqual(
            aggregator.lexicon_score("AAPL holds its annual shareholder meeting"),
            0.0,
        )


class TestFeedParsing(unittest.TestCase):
    def test_sample_feed_parses(self):
        with open(SAMPLE_FEED, encoding="utf-8") as fh:
            items = aggregator.parse_rss(fh.read())
        self.assertEqual(len(items), 7)
        for item in items:
            self.assertIn("timestamp", item)
            self.assertIn("headline", item)
            self.assertTrue(item["headline"])

    def test_empty_feed_yields_no_items(self):
        items = aggregator.parse_rss(
            '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        )
        self.assertEqual(items, [])


class TestCLIEndToEnd(unittest.TestCase):
    def _run_cli(self, feed_path, out_path, extra=None):
        cmd = [
            sys.executable,
            os.path.join(PROJECT, "aggregator.py"),
            "--ticker", "AAPL",
            "--feed", feed_path,
            "--out", out_path,
        ] + (extra or [])
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_cli_on_sample_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "sentiment.csv")
            result = self._run_cli(SAMPLE_FEED, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(out, encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(
                list(rows[0].keys()) if rows else [],
                ["timestamp", "headline", "sentiment_score"],
            )
            self.assertEqual(len(rows), 7)  # one row per headline
            for row in rows:
                score = float(row["sentiment_score"])
                self.assertGreaterEqual(score, -1.0)
                self.assertLessEqual(score, 1.0)

    def test_csv_header_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "sentiment.csv")
            result = self._run_cli(SAMPLE_FEED, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(out, encoding="utf-8") as fh:
                header = fh.readline().strip()
            self.assertEqual(header, "timestamp,headline,sentiment_score")

    def test_empty_feed_yields_header_only_csv(self):
        empty_feed = os.path.join(PROJECT, "tests", "empty_feed.xml")
        with open(empty_feed, "w", encoding="utf-8") as fh:
            fh.write(
                '<?xml version="1.0"?><rss version="2.0">'
                "<channel><title>empty</title></channel></rss>"
            )
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "sentiment.csv")
                result = self._run_cli(empty_feed, out)
                self.assertEqual(result.returncode, 0, result.stderr)
                with open(out, encoding="utf-8") as fh:
                    content = fh.read()
                self.assertEqual(
                    content.strip(), "timestamp,headline,sentiment_score"
                )
        finally:
            os.remove(empty_feed)

    def test_unreachable_endpoint_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "sentiment.csv")
            result = self._run_cli(
                SAMPLE_FEED, out,
                extra=["--endpoint", "http://127.0.0.1:9/score"],
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("could not reach sentiment endpoint", result.stderr)


if __name__ == "__main__":
    unittest.main()
