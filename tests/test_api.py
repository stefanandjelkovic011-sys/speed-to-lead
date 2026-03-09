"""Tests for Flask API endpoints."""

import os
import sys
import json
import sqlite3
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import models


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn
    def close(self):
        pass
    def __getattr__(self, name):
        return getattr(self._conn, name)


_real_conn = None

def _get_test_db():
    global _real_conn
    if _real_conn is None:
        _real_conn = sqlite3.connect(":memory:")
        _real_conn.row_factory = sqlite3.Row
        _real_conn.execute("PRAGMA foreign_keys=ON")
    return NoCloseConnection(_real_conn)

models.get_db = _get_test_db

from app import app


class TestAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        models.init_db()
        cls.bid = models.Business.create("API Test Co", "api-test-001", ai_chatbot_enabled=1)
        models.KnowledgeBase.create(cls.bid, "Test KB", "We offer AC repair for $99.", "services")
        cls.client = app.test_client()
        app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        global _real_conn
        if _real_conn:
            _real_conn.close()
            _real_conn = None

    def test_index(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_dashboard(self):
        resp = self.client.get(f"/dashboard/{self.bid}")
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_not_found(self):
        resp = self.client.get("/dashboard/99999")
        self.assertEqual(resp.status_code, 302)

    def test_api_leads(self):
        resp = self.client.get(f"/api/leads/{self.bid}")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIsInstance(data, list)

    def test_api_leads_with_filter(self):
        resp = self.client.get(f"/api/leads/{self.bid}?status=NEW&platform=test")
        self.assertEqual(resp.status_code, 200)

    @patch("lead_processor.bridge.generate_lead_response")
    def test_inbound_message(self, mock_gen):
        mock_gen.return_value = {"success": True, "response": "Test response", "error": None}
        resp = self.client.post("/api/inbound", json={
            "business_id": self.bid,
            "platform": "test",
            "message": "I need help",
            "customer_name": "API Tester",
        })
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data["success"])

    def test_inbound_missing_fields(self):
        resp = self.client.post("/api/inbound", json={"business_id": self.bid})
        self.assertEqual(resp.status_code, 400)

    def test_lead_detail(self):
        lid = models.Lead.create(self.bid, "test", customer_name="Detail Test")
        models.Message.create(lid, "Homeowner", "Hello")
        resp = self.client.get(f"/lead/{lid}")
        self.assertEqual(resp.status_code, 200)

    def test_lead_note(self):
        lid = models.Lead.create(self.bid, "test", customer_name="Note Test")
        resp = self.client.post(f"/api/lead/{lid}/note", json={"note": "Test note", "author": "Tester"})
        self.assertEqual(resp.status_code, 200)

    def test_lead_book(self):
        lid = models.Lead.create(self.bid, "test", customer_name="Book Test")
        resp = self.client.post(f"/api/lead/{lid}/book", json={"booked_by": "MANUAL"})
        self.assertEqual(resp.status_code, 200)

    def test_lead_messages(self):
        lid = models.Lead.create(self.bid, "test", customer_name="Msg API Test")
        models.Message.create(lid, "Homeowner", "Hello")
        resp = self.client.get(f"/api/lead/{lid}/messages")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(len(data) >= 1)

    def test_kb_generate_share_token(self):
        resp = self.client.post(f"/kb/share/{self.bid}")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data["success"])
        self.assertIn("share_token", data)
        self.assertIn("share_url", data)
        return data["share_token"]

    def test_kb_shared_view_by_token(self):
        # Generate a token first
        resp = self.client.post(f"/kb/share/{self.bid}")
        data = json.loads(resp.data)
        token = data["share_token"]
        # View by token
        resp = self.client.get(f"/kb/view/{token}")
        self.assertEqual(resp.status_code, 200)

    def test_kb_shared_view_invalid_token(self):
        resp = self.client.get("/kb/view/invalid_token_xyz")
        self.assertEqual(resp.status_code, 404)

    def test_knowledge_base_page(self):
        resp = self.client.get(f"/business/{self.bid}/kb")
        self.assertEqual(resp.status_code, 200)

    def test_testing_page(self):
        resp = self.client.get(f"/business/{self.bid}/test")
        self.assertEqual(resp.status_code, 200)

    def test_health_endpoint(self):
        with patch("app.bridge.health_check", return_value=True):
            resp = self.client.get("/api/test/health")
            self.assertEqual(resp.status_code, 200)
            data = json.loads(resp.data)
            self.assertTrue(data["claude_cli_available"])

    def test_metrics_endpoint(self):
        resp = self.client.get("/api/test/metrics")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("metrics", data)

    def test_export_csv(self):
        resp = self.client.get(f"/api/export/{self.bid}/leads")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.content_type)

    def test_business_metrics(self):
        resp = self.client.get(f"/api/metrics/{self.bid}")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("stats", data)

    def test_widget_cors(self):
        resp = self.client.options(f"/api/widget/{self.bid}/message")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")

    def test_widget_cors_after_request(self):
        """Verify global CORS after_request handler adds headers on widget POST."""
        with patch("lead_processor.bridge.generate_lead_response") as mock_gen:
            mock_gen.return_value = {"success": True, "response": "Hi!", "error": None}
            resp = self.client.post(f"/api/widget/{self.bid}/message", json={
                "message": "Hello", "session_id": "test123"
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))

    @patch("lead_processor.bridge.generate_lead_response")
    def test_graceful_degradation_ai_failure(self, mock_gen):
        """When AI fails, lead should still be created and queued for CSR."""
        mock_gen.return_value = {"success": False, "response": None, "error": "CLI unavailable"}
        resp = self.client.post("/api/inbound", json={
            "business_id": self.bid,
            "platform": "test",
            "message": "Need help with AC",
            "customer_name": "Degradation Test",
        })
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["action"], "queued_for_csr")
        self.assertIn("lead_id", data)
        # Verify the lead exists
        lead = models.Lead.get(data["lead_id"])
        self.assertIsNotNone(lead)

    def test_dashboard_avg_response_time(self):
        resp = self.client.get(f"/dashboard/{self.bid}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Avg Response Time", resp.data)

    def test_widget_embed(self):
        resp = self.client.get(f"/widget/embed/{self.bid}")
        self.assertEqual(resp.status_code, 200)

    def test_widget_script(self):
        resp = self.client.get(f"/widget/script/{self.bid}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/javascript", resp.content_type)


if __name__ == "__main__":
    unittest.main()
