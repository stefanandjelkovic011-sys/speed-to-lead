"""Tests for Claude CLI bridge with mocked subprocess."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from claude_bridge import ClaudeBridge, RateLimiter, BridgeMetrics


class TestRateLimiter(unittest.TestCase):

    def test_acquire_within_limit(self):
        limiter = RateLimiter(max_calls=5, period=60)
        for _ in range(5):
            limiter.acquire()
        self.assertEqual(len(limiter._calls), 5)


class TestBridgeMetrics(unittest.TestCase):

    def test_record_success(self):
        metrics = BridgeMetrics()
        metrics.record(True, 1.5)
        self.assertEqual(metrics.total, 1)
        self.assertEqual(metrics.success, 1)
        self.assertEqual(metrics.fail, 0)

    def test_record_failure(self):
        metrics = BridgeMetrics()
        metrics.record(False, 2.0)
        self.assertEqual(metrics.fail, 1)

    def test_avg_latency(self):
        metrics = BridgeMetrics()
        metrics.record(True, 1.0)
        metrics.record(True, 3.0)
        self.assertAlmostEqual(metrics.avg_latency, 2.0)

    def test_to_dict(self):
        metrics = BridgeMetrics()
        metrics.record(True, 1.0)
        d = metrics.to_dict()
        self.assertEqual(d["total_calls"], 1)
        self.assertIn("avg_latency_seconds", d)


class TestClaudeBridge(unittest.TestCase):

    def setUp(self):
        self.bridge = ClaudeBridge(timeout=10)

    @patch("claude_bridge.subprocess.run")
    def test_query_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Hello!", stderr="")
        result = self.bridge.query("test prompt")
        self.assertTrue(result["success"])
        self.assertEqual(result["response"], "Hello!")

    @patch("claude_bridge.subprocess.run")
    def test_query_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")
        result = self.bridge.query("test", max_retries=0)
        self.assertFalse(result["success"])

    @patch("claude_bridge.subprocess.run")
    def test_query_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=10)
        result = self.bridge.query("test")
        self.assertFalse(result["success"])
        self.assertIn("timed out", result["error"])

    @patch("claude_bridge.subprocess.run")
    def test_query_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        result = self.bridge.query("test")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    @patch("claude_bridge.subprocess.run")
    def test_health_check(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        self.assertTrue(self.bridge.health_check())

    @patch("claude_bridge.subprocess.run")
    def test_generate_lead_response(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Thanks for reaching out!", stderr="")
        result = self.bridge.generate_lead_response(
            {"customer_name": "John"}, "KB content", [{"sender": "Homeowner", "content": "Hi"}], "google_lsa"
        )
        self.assertTrue(result["success"])

    @patch("claude_bridge.subprocess.run")
    def test_classify_unbooked_valid_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"reason":"no response","business_unit":"HVAC","job_type":"repair","tags":["no_response"]}',
            stderr=""
        )
        result = self.bridge.classify_unbooked_lead([], "")
        self.assertTrue(result["success"])

    @patch("claude_bridge.subprocess.run")
    def test_classify_unbooked_invalid_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Not valid JSON here", stderr="")
        result = self.bridge.classify_unbooked_lead([], "")
        self.assertTrue(result["success"])
        # Should have been wrapped in valid JSON
        import json
        parsed = json.loads(result["response"])
        self.assertIn("reason", parsed)

    def test_truncate_kb(self):
        long_content = "x" * 10000
        truncated = self.bridge._truncate_kb(long_content)
        self.assertLessEqual(len(truncated), self.bridge.MAX_KB_CHARS + 100)

    @patch("claude_bridge.subprocess.run")
    def test_platform_simulation(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Response text", stderr="")
        results = self.bridge.generate_platform_simulation("Hello", ["google_lsa", "yelp"], "KB")
        self.assertIn("google_lsa", results)
        self.assertIn("yelp", results)


if __name__ == "__main__":
    unittest.main()
