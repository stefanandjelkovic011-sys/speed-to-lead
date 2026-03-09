"""
Database models for Speed-to-Lead system.
Uses SQLite for zero-dependency persistence.
"""

import sqlite3
import os
import json
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "speed_to_lead.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            org_id TEXT UNIQUE NOT NULL,
            timezone TEXT DEFAULT 'America/New_York',
            google_lsa_customer_id TEXT,
            yelp_business_id TEXT,
            thumbtack_pro_id TEXT,
            angi_provider_id TEXT,
            chat_widget_enabled INTEGER DEFAULT 0,
            contact_form_enabled INTEGER DEFAULT 0,
            ai_chatbot_enabled INTEGER DEFAULT 1,
            operating_hours_start INTEGER DEFAULT 9,
            operating_hours_end INTEGER DEFAULT 21,
            skip_weekends INTEGER DEFAULT 0,
            max_follow_ups INTEGER DEFAULT 4,
            follow_up_cadence_json TEXT DEFAULT '[1,3,7,14]',
            share_token TEXT,
            first_message_template TEXT,
            duke_energy_account_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS knowledge_bases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id)
        );

        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            platform_lead_id TEXT,
            channel TEXT DEFAULT 'Platform',
            status TEXT DEFAULT 'NEW',
            customer_name TEXT,
            customer_phone TEXT,
            customer_email TEXT,
            customer_address TEXT,
            service_type TEXT,
            is_chatbot_enabled INTEGER DEFAULT 1,
            is_escalated INTEGER DEFAULT 0,
            assigned_to TEXT,
            follow_up_count INTEGER DEFAULT 0,
            last_follow_up_sent_at TEXT,
            job_booked_by TEXT,
            st_job_link TEXT,
            first_response_at TEXT,
            last_customer_message_at TEXT,
            classification_json TEXT,
            notes TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id),
            UNIQUE(business_id, platform, platform_lead_id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            platform_message_id TEXT,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            channel TEXT DEFAULT 'Platform',
            is_internal_note INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );

        CREATE TABLE IF NOT EXISTS test_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            session_type TEXT NOT NULL,
            platform TEXT DEFAULT 'test',
            status TEXT DEFAULT 'active',
            results_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id)
        );

        CREATE TABLE IF NOT EXISTS platform_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            tone TEXT DEFAULT 'professional',
            first_message_template TEXT,
            polling_interval_minutes INTEGER DEFAULT 5,
            is_active INTEGER DEFAULT 1,
            config_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id),
            UNIQUE(business_id, platform)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER,
            lead_id INTEGER,
            action TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            performed_by TEXT DEFAULT 'system',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS drip_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            business_id INTEGER NOT NULL,
            follow_up_number INTEGER NOT NULL,
            scheduled_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            sent_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (lead_id) REFERENCES leads(id),
            FOREIGN KEY (business_id) REFERENCES businesses(id)
        );

        CREATE INDEX IF NOT EXISTS idx_leads_business_status ON leads(business_id, status);
        CREATE INDEX IF NOT EXISTS idx_leads_platform ON leads(platform, platform_lead_id);
        CREATE INDEX IF NOT EXISTS idx_messages_lead ON messages(lead_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_kb_business ON knowledge_bases(business_id, is_active);
        CREATE INDEX IF NOT EXISTS idx_drip_queue_status ON drip_queue(status, scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_audit_log_lead ON audit_log(lead_id, created_at);

        -- Cleaning business tables
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id)
        );

        CREATE TABLE IF NOT EXISTS cleaners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            hourly_rate REAL DEFAULT 18.00,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id)
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            customer_id INTEGER,
            lead_id INTEGER,
            cleaner_id INTEGER,
            service_type TEXT NOT NULL,
            status TEXT DEFAULT 'SCHEDULED',
            bedrooms INTEGER DEFAULT 0,
            bathrooms REAL DEFAULT 0,
            sqft INTEGER,
            condition TEXT DEFAULT 'average',
            quoted_price REAL NOT NULL,
            actual_price REAL,
            labor_cost REAL DEFAULT 0,
            supply_cost REAL DEFAULT 0,
            estimated_hours REAL DEFAULT 0,
            actual_hours REAL,
            address TEXT,
            scheduled_date TEXT,
            scheduled_time TEXT,
            completed_at TEXT,
            notes TEXT,
            pricing_breakdown_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id),
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (lead_id) REFERENCES leads(id),
            FOREIGN KEY (cleaner_id) REFERENCES cleaners(id)
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            expense_date TEXT DEFAULT (date('now')),
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id)
        );

        CREATE TABLE IF NOT EXISTS outreach (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            contact_name TEXT NOT NULL,
            company TEXT,
            outreach_type TEXT DEFAULT 'cold_call',
            channel TEXT DEFAULT 'phone',
            status TEXT DEFAULT 'PENDING',
            notes TEXT,
            follow_up_date TEXT,
            contacted_at TEXT DEFAULT (datetime('now')),
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (business_id) REFERENCES businesses(id)
        );

        CREATE INDEX IF NOT EXISTS idx_outreach_business ON outreach(business_id, status);
        CREATE INDEX IF NOT EXISTS idx_customers_business ON customers(business_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_business ON jobs(business_id, status);
        CREATE INDEX IF NOT EXISTS idx_jobs_customer ON jobs(customer_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_cleaner ON jobs(cleaner_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_date ON jobs(scheduled_date);
        CREATE INDEX IF NOT EXISTS idx_expenses_business ON expenses(business_id, expense_date);
    """)
    conn.commit()
    conn.close()


class Business:
    @staticmethod
    def create(name, org_id, **kwargs):
        conn = get_db()
        fields = ["name", "org_id"] + list(kwargs.keys())
        values = [name, org_id] + list(kwargs.values())
        placeholders = ",".join(["?"] * len(values))
        field_names = ",".join(fields)
        cursor = conn.execute(f"INSERT INTO businesses ({field_names}) VALUES ({placeholders})", values)
        conn.commit()
        bid = cursor.lastrowid
        conn.close()
        return bid

    @staticmethod
    def get(business_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_by_org_id(org_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM businesses WHERE org_id=?", (org_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_all():
        conn = get_db()
        rows = conn.execute("SELECT * FROM businesses ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update(business_id, **kwargs):
        conn = get_db()
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ",".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [business_id]
        conn.execute(f"UPDATE businesses SET {sets} WHERE id=?", values)
        conn.commit()
        conn.close()

    @staticmethod
    def delete(business_id):
        conn = get_db()
        conn.execute("DELETE FROM drip_queue WHERE business_id=?", (business_id,))
        conn.execute("DELETE FROM audit_log WHERE business_id=?", (business_id,))
        conn.execute("DELETE FROM platform_configs WHERE business_id=?", (business_id,))
        conn.execute("DELETE FROM messages WHERE lead_id IN (SELECT id FROM leads WHERE business_id=?)", (business_id,))
        conn.execute("DELETE FROM leads WHERE business_id=?", (business_id,))
        conn.execute("DELETE FROM knowledge_bases WHERE business_id=?", (business_id,))
        conn.execute("DELETE FROM test_sessions WHERE business_id=?", (business_id,))
        conn.execute("DELETE FROM businesses WHERE id=?", (business_id,))
        conn.commit()
        conn.close()


class KnowledgeBase:
    @staticmethod
    def create(business_id, name, content, category="general"):
        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO knowledge_bases (business_id, name, content, category) VALUES (?,?,?,?)",
            (business_id, name, content, category)
        )
        conn.commit()
        kid = cursor.lastrowid
        conn.close()
        return kid

    @staticmethod
    def get(kb_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM knowledge_bases WHERE id=?", (kb_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_for_business(business_id):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM knowledge_bases WHERE business_id=? ORDER BY category, name",
            (business_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_active_content(business_id):
        conn = get_db()
        rows = conn.execute(
            "SELECT name, category, content FROM knowledge_bases WHERE business_id=? AND is_active=1",
            (business_id,)
        ).fetchall()
        conn.close()
        if not rows:
            return ""
        sections = []
        for r in rows:
            sections.append(f"## {r['category'].upper()} — {r['name']}\n{r['content']}")
        return "\n\n".join(sections)

    @staticmethod
    def update(kb_id, **kwargs):
        conn = get_db()
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ",".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [kb_id]
        conn.execute(f"UPDATE knowledge_bases SET {sets} WHERE id=?", values)
        conn.commit()
        conn.close()

    @staticmethod
    def delete(kb_id):
        conn = get_db()
        conn.execute("DELETE FROM knowledge_bases WHERE id=?", (kb_id,))
        conn.commit()
        conn.close()


class Lead:
    @staticmethod
    def create(business_id, platform, platform_lead_id=None, **kwargs):
        conn = get_db()
        if platform_lead_id:
            existing = conn.execute(
                "SELECT id FROM leads WHERE business_id=? AND platform=? AND platform_lead_id=?",
                (business_id, platform, platform_lead_id)
            ).fetchone()
            if existing:
                conn.close()
                return existing["id"]

        fields = ["business_id", "platform", "platform_lead_id"] + list(kwargs.keys())
        values = [business_id, platform, platform_lead_id] + list(kwargs.values())
        placeholders = ",".join(["?"] * len(values))
        field_names = ",".join(fields)
        cursor = conn.execute(f"INSERT INTO leads ({field_names}) VALUES ({placeholders})", values)
        conn.commit()
        lid = cursor.lastrowid
        conn.close()
        return lid

    @staticmethod
    def get(lead_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_for_business(business_id, status=None, platform=None, limit=50, offset=0):
        conn = get_db()
        query = "SELECT * FROM leads WHERE business_id=?"
        params = [business_id]
        if status:
            query += " AND status=?"
            params.append(status)
        if platform:
            query += " AND platform=?"
            params.append(platform)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update(lead_id, **kwargs):
        conn = get_db()
        lead = conn.execute("SELECT status FROM leads WHERE id=?", (lead_id,)).fetchone()
        if lead and lead["status"] == "BOOKED" and kwargs.get("status") in ("UNBOOKED", "NON_LEAD"):
            conn.close()
            return False
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ",".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [lead_id]
        conn.execute(f"UPDATE leads SET {sets} WHERE id=?", values)
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def get_stats(business_id):
        conn = get_db()
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM leads WHERE business_id=? GROUP BY status",
            (business_id,)
        ).fetchall()
        conn.close()
        stats = {"NEW": 0, "IN_PROGRESS": 0, "BOOKED": 0, "UNBOOKED": 0, "NON_LEAD": 0}
        for r in rows:
            stats[r["status"]] = r["count"]
        stats["total"] = sum(stats.values())
        stats["booking_rate"] = (
            round(stats["BOOKED"] / (stats["BOOKED"] + stats["UNBOOKED"]) * 100, 1)
            if (stats["BOOKED"] + stats["UNBOOKED"]) > 0 else 0
        )
        return stats


class Message:
    @staticmethod
    def create(lead_id, sender, content, channel="Platform", platform_message_id=None, is_internal_note=0):
        conn = get_db()
        if platform_message_id:
            existing = conn.execute(
                "SELECT id FROM messages WHERE lead_id=? AND platform_message_id=?",
                (lead_id, platform_message_id)
            ).fetchone()
            if existing:
                conn.close()
                return existing["id"]
        cursor = conn.execute(
            "INSERT INTO messages (lead_id, sender, content, channel, platform_message_id, is_internal_note) VALUES (?,?,?,?,?,?)",
            (lead_id, sender, content, channel, platform_message_id, is_internal_note)
        )
        conn.commit()
        mid = cursor.lastrowid
        conn.close()
        return mid

    @staticmethod
    def list_for_lead(lead_id, include_notes=True):
        conn = get_db()
        query = "SELECT * FROM messages WHERE lead_id=?"
        if not include_notes:
            query += " AND is_internal_note=0"
        query += " ORDER BY created_at ASC"
        rows = conn.execute(query, (lead_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class TestSession:
    @staticmethod
    def create(business_id, session_type, platform="test"):
        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO test_sessions (business_id, session_type, platform) VALUES (?,?,?)",
            (business_id, session_type, platform)
        )
        conn.commit()
        sid = cursor.lastrowid
        conn.close()
        return sid

    @staticmethod
    def get(session_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM test_sessions WHERE id=?", (session_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update(session_id, **kwargs):
        conn = get_db()
        sets = ",".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [session_id]
        conn.execute(f"UPDATE test_sessions SET {sets} WHERE id=?", values)
        conn.commit()
        conn.close()

    @staticmethod
    def list_for_business(business_id, limit=20):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM test_sessions WHERE business_id=? ORDER BY created_at DESC LIMIT ?",
            (business_id, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class PlatformConfig:
    @staticmethod
    def create(business_id, platform, **kwargs):
        conn = get_db()
        fields = ["business_id", "platform"] + list(kwargs.keys())
        values = [business_id, platform] + list(kwargs.values())
        placeholders = ",".join(["?"] * len(values))
        field_names = ",".join(fields)
        cursor = conn.execute(
            f"INSERT OR REPLACE INTO platform_configs ({field_names}) VALUES ({placeholders})", values
        )
        conn.commit()
        pid = cursor.lastrowid
        conn.close()
        return pid

    @staticmethod
    def get(business_id, platform):
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM platform_configs WHERE business_id=? AND platform=?",
            (business_id, platform)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_for_business(business_id):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM platform_configs WHERE business_id=? ORDER BY platform",
            (business_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class AuditLog:
    @staticmethod
    def log(action, business_id=None, lead_id=None, old_value=None, new_value=None, performed_by="system"):
        conn = get_db()
        conn.execute(
            "INSERT INTO audit_log (business_id, lead_id, action, old_value, new_value, performed_by) VALUES (?,?,?,?,?,?)",
            (business_id, lead_id, action, old_value, new_value, performed_by)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def list_for_lead(lead_id, limit=50):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE lead_id=? ORDER BY created_at DESC LIMIT ?",
            (lead_id, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class DripQueue:
    @staticmethod
    def create(lead_id, business_id, follow_up_number, scheduled_at):
        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO drip_queue (lead_id, business_id, follow_up_number, scheduled_at) VALUES (?,?,?,?)",
            (lead_id, business_id, follow_up_number, scheduled_at)
        )
        conn.commit()
        did = cursor.lastrowid
        conn.close()
        return did

    @staticmethod
    def get_pending(business_id=None):
        conn = get_db()
        query = "SELECT * FROM drip_queue WHERE status='pending' AND scheduled_at <= datetime('now')"
        params = []
        if business_id:
            query += " AND business_id=?"
            params.append(business_id)
        query += " ORDER BY scheduled_at ASC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def mark_sent(queue_id):
        conn = get_db()
        conn.execute(
            "UPDATE drip_queue SET status='sent', sent_at=datetime('now') WHERE id=?",
            (queue_id,)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def cancel_for_lead(lead_id):
        conn = get_db()
        conn.execute(
            "UPDATE drip_queue SET status='cancelled' WHERE lead_id=? AND status='pending'",
            (lead_id,)
        )
        conn.commit()
        conn.close()


class Customer:
    @staticmethod
    def create(business_id, name, **kwargs):
        conn = get_db()
        fields = ["business_id", "name"] + list(kwargs.keys())
        values = [business_id, name] + list(kwargs.values())
        placeholders = ",".join(["?"] * len(values))
        field_names = ",".join(fields)
        cursor = conn.execute(f"INSERT INTO customers ({field_names}) VALUES ({placeholders})", values)
        conn.commit()
        cid = cursor.lastrowid
        conn.close()
        return cid

    @staticmethod
    def get(customer_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_for_business(business_id):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM customers WHERE business_id=? ORDER BY name", (business_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update(customer_id, **kwargs):
        conn = get_db()
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ",".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [customer_id]
        conn.execute(f"UPDATE customers SET {sets} WHERE id=?", values)
        conn.commit()
        conn.close()

    @staticmethod
    def delete(customer_id):
        conn = get_db()
        conn.execute("DELETE FROM customers WHERE id=?", (customer_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_lifetime_value(customer_id):
        conn = get_db()
        row = conn.execute("""
            SELECT COUNT(*) as job_count,
                   COALESCE(SUM(actual_price), SUM(quoted_price), 0) as total_revenue,
                   COALESCE(SUM(labor_cost + supply_cost), 0) as total_cost,
                   MIN(scheduled_date) as first_job,
                   MAX(scheduled_date) as last_job
            FROM jobs WHERE customer_id=? AND status IN ('COMPLETED', 'SCHEDULED', 'IN_PROGRESS')
        """, (customer_id,)).fetchone()
        conn.close()
        if not row:
            return {"job_count": 0, "total_revenue": 0, "total_cost": 0, "total_profit": 0}
        revenue = row["total_revenue"] or 0
        cost = row["total_cost"] or 0
        return {
            "job_count": row["job_count"],
            "total_revenue": round(revenue, 2),
            "total_cost": round(cost, 2),
            "total_profit": round(revenue - cost, 2),
            "first_job": row["first_job"],
            "last_job": row["last_job"],
        }


class Cleaner:
    @staticmethod
    def create(business_id, name, **kwargs):
        conn = get_db()
        fields = ["business_id", "name"] + list(kwargs.keys())
        values = [business_id, name] + list(kwargs.values())
        placeholders = ",".join(["?"] * len(values))
        field_names = ",".join(fields)
        cursor = conn.execute(f"INSERT INTO cleaners ({field_names}) VALUES ({placeholders})", values)
        conn.commit()
        cid = cursor.lastrowid
        conn.close()
        return cid

    @staticmethod
    def get(cleaner_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM cleaners WHERE id=?", (cleaner_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_for_business(business_id, active_only=True):
        conn = get_db()
        query = "SELECT * FROM cleaners WHERE business_id=?"
        if active_only:
            query += " AND is_active=1"
        query += " ORDER BY name"
        rows = conn.execute(query, (business_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update(cleaner_id, **kwargs):
        conn = get_db()
        sets = ",".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [cleaner_id]
        conn.execute(f"UPDATE cleaners SET {sets} WHERE id=?", values)
        conn.commit()
        conn.close()


class Job:
    @staticmethod
    def create(business_id, service_type, quoted_price, **kwargs):
        conn = get_db()
        fields = ["business_id", "service_type", "quoted_price"] + list(kwargs.keys())
        values = [business_id, service_type, quoted_price] + list(kwargs.values())
        placeholders = ",".join(["?"] * len(values))
        field_names = ",".join(fields)
        cursor = conn.execute(f"INSERT INTO jobs ({field_names}) VALUES ({placeholders})", values)
        conn.commit()
        jid = cursor.lastrowid
        conn.close()
        return jid

    @staticmethod
    def get(job_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_for_business(business_id, status=None, limit=100):
        conn = get_db()
        query = "SELECT * FROM jobs WHERE business_id=?"
        params = [business_id]
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY scheduled_date DESC, scheduled_time DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update(job_id, **kwargs):
        conn = get_db()
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ",".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [job_id]
        conn.execute(f"UPDATE jobs SET {sets} WHERE id=?", values)
        conn.commit()
        conn.close()

    @staticmethod
    def delete(job_id):
        conn = get_db()
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_stats(business_id):
        conn = get_db()
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM jobs WHERE business_id=? GROUP BY status",
            (business_id,)
        ).fetchall()
        stats = {"SCHEDULED": 0, "IN_PROGRESS": 0, "COMPLETED": 0, "CANCELLED": 0}
        for r in rows:
            stats[r["status"]] = r["count"]
        stats["total"] = sum(stats.values())

        rev_row = conn.execute("""
            SELECT COALESCE(SUM(COALESCE(actual_price, quoted_price)), 0) as revenue,
                   COALESCE(SUM(labor_cost + supply_cost), 0) as costs
            FROM jobs WHERE business_id=? AND status='COMPLETED'
        """, (business_id,)).fetchone()
        stats["total_revenue"] = round(rev_row["revenue"], 2)
        stats["total_costs"] = round(rev_row["costs"], 2)
        stats["total_profit"] = round(rev_row["revenue"] - rev_row["costs"], 2)
        conn.close()
        return stats

    @staticmethod
    def get_revenue_by_month(business_id, months=12):
        conn = get_db()
        rows = conn.execute("""
            SELECT strftime('%%Y-%%m', scheduled_date) as month,
                   COUNT(*) as job_count,
                   COALESCE(SUM(COALESCE(actual_price, quoted_price)), 0) as revenue,
                   COALESCE(SUM(labor_cost + supply_cost), 0) as costs
            FROM jobs WHERE business_id=? AND status='COMPLETED'
                AND scheduled_date >= date('now', ? || ' months')
            GROUP BY month ORDER BY month
        """, (business_id, f"-{months}")).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_revenue_by_service(business_id):
        conn = get_db()
        rows = conn.execute("""
            SELECT service_type,
                   COUNT(*) as job_count,
                   COALESCE(SUM(COALESCE(actual_price, quoted_price)), 0) as revenue,
                   COALESCE(SUM(labor_cost + supply_cost), 0) as costs,
                   ROUND(AVG(COALESCE(actual_price, quoted_price)), 2) as avg_price
            FROM jobs WHERE business_id=? AND status='COMPLETED'
            GROUP BY service_type ORDER BY revenue DESC
        """, (business_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def list_by_date_range(business_id, start_date, end_date, cleaner_id=None):
        conn = get_db()
        query = """SELECT j.*, c.name as cleaner_name, cu.name as customer_name
            FROM jobs j
            LEFT JOIN cleaners c ON j.cleaner_id=c.id
            LEFT JOIN customers cu ON j.customer_id=cu.id
            WHERE j.business_id=? AND j.scheduled_date >= ? AND j.scheduled_date <= ?
            AND j.status != 'CANCELLED'"""
        params = [business_id, start_date, end_date]
        if cleaner_id:
            query += " AND j.cleaner_id=?"
            params.append(cleaner_id)
        query += " ORDER BY j.scheduled_date, j.scheduled_time"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_cleaner_stats(business_id):
        conn = get_db()
        rows = conn.execute("""
            SELECT c.id, c.name, c.hourly_rate,
                   COUNT(j.id) as job_count,
                   COALESCE(SUM(COALESCE(j.actual_price, j.quoted_price)), 0) as revenue,
                   COALESCE(SUM(j.actual_hours), SUM(j.estimated_hours), 0) as total_hours
            FROM cleaners c
            LEFT JOIN jobs j ON j.cleaner_id=c.id AND j.status='COMPLETED'
            WHERE c.business_id=? AND c.is_active=1
            GROUP BY c.id ORDER BY revenue DESC
        """, (business_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class Expense:
    @staticmethod
    def create(business_id, category, amount, **kwargs):
        conn = get_db()
        fields = ["business_id", "category", "amount"] + list(kwargs.keys())
        values = [business_id, category, amount] + list(kwargs.values())
        placeholders = ",".join(["?"] * len(values))
        field_names = ",".join(fields)
        cursor = conn.execute(f"INSERT INTO expenses ({field_names}) VALUES ({placeholders})", values)
        conn.commit()
        eid = cursor.lastrowid
        conn.close()
        return eid

    @staticmethod
    def list_for_business(business_id, limit=100):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM expenses WHERE business_id=? ORDER BY expense_date DESC LIMIT ?",
            (business_id, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_summary(business_id, months=12):
        conn = get_db()
        rows = conn.execute("""
            SELECT category, SUM(amount) as total
            FROM expenses WHERE business_id=?
                AND expense_date >= date('now', ? || ' months')
            GROUP BY category ORDER BY total DESC
        """, (business_id, f"-{months}")).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def delete(expense_id):
        conn = get_db()
        conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        conn.commit()
        conn.close()


class Outreach:
    @staticmethod
    def create(business_id, contact_name, **kwargs):
        conn = get_db()
        fields = ["business_id", "contact_name"] + list(kwargs.keys())
        values = [business_id, contact_name] + list(kwargs.values())
        placeholders = ",".join(["?"] * len(values))
        field_names = ",".join(fields)
        cursor = conn.execute(f"INSERT INTO outreach ({field_names}) VALUES ({placeholders})", values)
        conn.commit()
        oid = cursor.lastrowid
        conn.close()
        return oid

    @staticmethod
    def get(outreach_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM outreach WHERE id=?", (outreach_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_for_business(business_id, status=None, limit=200):
        conn = get_db()
        query = "SELECT * FROM outreach WHERE business_id=?"
        params = [business_id]
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update(outreach_id, **kwargs):
        conn = get_db()
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ",".join([f"{k}=?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [outreach_id]
        conn.execute(f"UPDATE outreach SET {sets} WHERE id=?", values)
        conn.commit()
        conn.close()

    @staticmethod
    def delete(outreach_id):
        conn = get_db()
        conn.execute("DELETE FROM outreach WHERE id=?", (outreach_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_stats(business_id):
        conn = get_db()
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM outreach WHERE business_id=? GROUP BY status",
            (business_id,)
        ).fetchall()
        conn.close()
        stats = {"PENDING": 0, "SUCCESS": 0, "NO_RESPONSE": 0, "DECLINED": 0}
        for r in rows:
            if r["status"] in stats:
                stats[r["status"]] = r["count"]
        stats["total"] = sum(stats.values())
        stats["success_rate"] = round(
            stats["SUCCESS"] / (stats["SUCCESS"] + stats["NO_RESPONSE"] + stats["DECLINED"]) * 100, 1
        ) if (stats["SUCCESS"] + stats["NO_RESPONSE"] + stats["DECLINED"]) > 0 else 0
        return stats
