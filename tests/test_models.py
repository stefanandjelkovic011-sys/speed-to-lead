"""Tests for database models."""

import os
import sys
import sqlite3
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import models


class NoCloseConnection:
    """Wrapper around sqlite3 connection that makes close() a no-op."""
    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass  # no-op for in-memory testing

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


class TestModels(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        global _real_conn
        _real_conn = None
        models.get_db = _get_test_db
        models.init_db()

    @classmethod
    def tearDownClass(cls):
        global _real_conn
        if _real_conn:
            _real_conn.close()
            _real_conn = None

    def test_business_crud(self):
        bid = models.Business.create("Test Co", "test-001", timezone="America/New_York")
        self.assertIsNotNone(bid)

        biz = models.Business.get(bid)
        self.assertEqual(biz["name"], "Test Co")
        self.assertEqual(biz["org_id"], "test-001")

        models.Business.update(bid, name="Updated Co")
        biz = models.Business.get(bid)
        self.assertEqual(biz["name"], "Updated Co")

    def test_business_list(self):
        businesses = models.Business.list_all()
        self.assertIsInstance(businesses, list)

    def test_business_by_org_id(self):
        # Ensure business exists first
        models.Business.create("OrgId Co", "orgid-test-001", timezone="America/New_York")
        biz = models.Business.get_by_org_id("orgid-test-001")
        self.assertIsNotNone(biz)

    def test_kb_crud(self):
        biz = models.Business.get_by_org_id("orgid-test-001") or {"id": models.Business.create("KB Co", "kb-test-org")}
        kid = models.KnowledgeBase.create(biz["id"], "Test KB", "Test content", "services")
        self.assertIsNotNone(kid)

        kb = models.KnowledgeBase.get(kid)
        self.assertEqual(kb["name"], "Test KB")

        kbs = models.KnowledgeBase.list_for_business(biz["id"])
        self.assertTrue(len(kbs) >= 1)

        content = models.KnowledgeBase.get_active_content(biz["id"])
        self.assertIn("Test content", content)

    def test_lead_create_and_dedup(self):
        biz = models.Business.get_by_org_id("orgid-test-001") or {"id": models.Business.create("Dedup Co", "dedup-org")}
        lid1 = models.Lead.create(biz["id"], "test", "plat-123", customer_name="John")
        lid2 = models.Lead.create(biz["id"], "test", "plat-123", customer_name="John")
        self.assertEqual(lid1, lid2)

    def test_lead_status_protection(self):
        biz = models.Business.get_by_org_id("orgid-test-001") or {"id": models.Business.create("Prot Co", "prot-org")}
        lid = models.Lead.create(biz["id"], "test", customer_name="Protected")
        models.Lead.update(lid, status="BOOKED")
        result = models.Lead.update(lid, status="UNBOOKED")
        self.assertFalse(result)
        lead = models.Lead.get(lid)
        self.assertEqual(lead["status"], "BOOKED")

    def test_lead_stats(self):
        biz = models.Business.get_by_org_id("orgid-test-001") or {"id": models.Business.create("Stats Co", "stats-org")}
        stats = models.Lead.get_stats(biz["id"])
        self.assertIn("total", stats)
        self.assertIn("booking_rate", stats)

    def test_message_crud(self):
        biz = models.Business.get_by_org_id("orgid-test-001") or {"id": models.Business.create("MsgCrud Co", "msgcrud-org")}
        lid = models.Lead.create(biz["id"], "test", customer_name="MsgTest")
        mid = models.Message.create(lid, "Homeowner", "Hello")
        self.assertIsNotNone(mid)

        msgs = models.Message.list_for_lead(lid)
        self.assertTrue(len(msgs) >= 1)

    def test_message_dedup(self):
        biz = models.Business.get_by_org_id("orgid-test-001") or {"id": models.Business.create("MsgDed Co", "msgded-org")}
        lid = models.Lead.create(biz["id"], "test", customer_name="DedupTest")
        mid1 = models.Message.create(lid, "Homeowner", "Hello", platform_message_id="msg-1")
        mid2 = models.Message.create(lid, "Homeowner", "Hello", platform_message_id="msg-1")
        self.assertEqual(mid1, mid2)

    def test_audit_log(self):
        models.AuditLog.log("test_action", business_id=1, lead_id=1, old_value="old", new_value="new")
        logs = models.AuditLog.list_for_lead(1)
        self.assertTrue(len(logs) >= 1)

    def test_drip_queue(self):
        biz = models.Business.get_by_org_id("orgid-test-001") or {"id": models.Business.create("Drip Co", "drip-org")}
        lid = models.Lead.create(biz["id"], "test", customer_name="DripTest")
        did = models.DripQueue.create(lid, biz["id"], 1, "2020-01-01T00:00:00")
        self.assertIsNotNone(did)

        pending = models.DripQueue.get_pending()
        self.assertTrue(len(pending) >= 1)

        models.DripQueue.cancel_for_lead(lid)
        pending_after = models.DripQueue.get_pending()
        cancelled_count = sum(1 for p in pending_after if p["lead_id"] == lid)
        self.assertEqual(cancelled_count, 0)

    def test_cascade_delete(self):
        bid = models.Business.create("DeleteMe", "delete-test-001")
        kid = models.KnowledgeBase.create(bid, "KB", "content")
        lid = models.Lead.create(bid, "test", customer_name="DeleteTest")
        models.Message.create(lid, "Homeowner", "Hello")
        models.AuditLog.log("test", business_id=bid, lead_id=lid)
        models.DripQueue.create(lid, bid, 1, "2020-01-01T00:00:00")

        models.Business.delete(bid)
        self.assertIsNone(models.Business.get(bid))


if __name__ == "__main__":
    unittest.main()
