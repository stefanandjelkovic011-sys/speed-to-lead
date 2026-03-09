"""Tests for lead processor with mocked Claude bridge."""

import os
import sys
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

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

import lead_processor


class TestLeadProcessor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        models.init_db()
        cls.bid = models.Business.create("Test Biz", "proc-test-001", ai_chatbot_enabled=1)
        models.KnowledgeBase.create(cls.bid, "Services", "We do HVAC repairs.", "services")

    @classmethod
    def tearDownClass(cls):
        global _real_conn
        if _real_conn:
            _real_conn.close()
            _real_conn = None

    @patch.object(lead_processor.bridge, 'generate_lead_response')
    def test_process_inbound_new_lead(self, mock_gen):
        mock_gen.return_value = {"success": True, "response": "Hi! How can I help?", "error": None}
        result = lead_processor.process_inbound_message(
            business_id=self.bid, platform="test", customer_message="I need AC repair",
            customer_name="Alice", platform_lead_id="proc-test-1"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "responded")

    @patch.object(lead_processor.bridge, 'generate_lead_response')
    def test_escalation_detection(self, mock_gen):
        mock_gen.return_value = {"success": True, "response": "ESCALATE: Customer is angry", "error": None}
        result = lead_processor.process_inbound_message(
            business_id=self.bid, platform="test", customer_message="I am furious!",
            customer_name="Angry Bob", platform_lead_id="proc-test-esc"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "escalated")

    @patch.object(lead_processor.bridge, 'generate_lead_response')
    def test_non_lead_detection(self, mock_gen):
        mock_gen.return_value = {"success": True, "response": "NON_LEAD: This is spam", "error": None}
        result = lead_processor.process_inbound_message(
            business_id=self.bid, platform="test", customer_message="Buy our SEO services",
            customer_name="Spammer", platform_lead_id="proc-test-spam"
        )
        self.assertEqual(result["action"], "non_lead")

    def test_csr_takeover(self):
        lid = models.Lead.create(self.bid, "test", "proc-test-csr", customer_name="CSR Test")
        result = lead_processor.send_csr_message(lid, "Jane", "Hi, I'm taking over this lead.")
        self.assertTrue(result["success"])
        lead = models.Lead.get(lid)
        self.assertEqual(lead["is_chatbot_enabled"], 0)
        self.assertEqual(lead["is_escalated"], 1)

    def test_mark_booked(self):
        lid = models.Lead.create(self.bid, "test", customer_name="Booker")
        result = lead_processor.mark_booked(lid, "MANUAL", "http://st.link/123")
        self.assertTrue(result["success"])
        lead = models.Lead.get(lid)
        self.assertEqual(lead["status"], "BOOKED")

    def test_mark_unbooked_protection(self):
        lid = models.Lead.create(self.bid, "test", customer_name="Protected")
        models.Lead.update(lid, status="BOOKED")
        result = lead_processor.mark_unbooked(lid, self.bid)
        self.assertFalse(result["success"])

    def test_re_enable_chatbot(self):
        lid = models.Lead.create(self.bid, "test", customer_name="ReEnable")
        models.Lead.update(lid, is_chatbot_enabled=0, is_escalated=1)
        result = lead_processor.re_enable_chatbot(lid)
        self.assertTrue(result["success"])
        lead = models.Lead.get(lid)
        self.assertEqual(lead["is_chatbot_enabled"], 1)

    def test_ai_disabled_skips_response(self):
        bid2 = models.Business.create("No AI Biz", "proc-test-noai", ai_chatbot_enabled=0)
        result = lead_processor.process_inbound_message(
            business_id=bid2, platform="test", customer_message="Hello",
            customer_name="NoAI", platform_lead_id="proc-test-noai"
        )
        self.assertEqual(result["action"], "queued_for_csr")

    def test_operating_hours_check(self):
        business = models.Business.get(self.bid)
        result = lead_processor.is_within_operating_hours(business)
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
