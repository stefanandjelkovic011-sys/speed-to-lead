"""
Speed-to-Lead — Main Flask Application
Multi-platform lead management with Claude CLI subprocess bridge.
"""

import csv
import io
import json
import os
import secrets
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response
from models import init_db, Business, KnowledgeBase, Lead, Message, TestSession, AuditLog, Customer, Cleaner, Job, Expense, Outreach
from claude_bridge import ClaudeBridge
from error_handlers import setup_logging, api_error_handler
from validators import validate_phone, validate_email, validate_platform, sanitize_message
from platforms import get_connector
import lead_processor

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

bridge = ClaudeBridge(timeout=120)

setup_logging(app)


@app.before_request
def ensure_db():
    init_db()


# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    businesses = Business.list_all()
    return render_template("index.html", businesses=businesses)


@app.route("/dashboard/<int:business_id>")
def dashboard(business_id):
    business = Business.get(business_id)
    if not business:
        flash("Business not found", "danger")
        return redirect(url_for("index"))
    stats = Lead.get_stats(business_id)
    leads = Lead.list_for_business(business_id, limit=50)

    # Gap 3: Calculate avg first-response time
    from models import get_db
    conn = get_db()
    rows = conn.execute("""
        SELECT created_at, first_response_at FROM leads
        WHERE business_id=? AND first_response_at IS NOT NULL
    """, (business_id,)).fetchall()

    response_times = []
    for r in rows:
        try:
            created = datetime.fromisoformat(r["created_at"])
            responded = datetime.fromisoformat(r["first_response_at"])
            diff = (responded - created).total_seconds()
            if diff > 0:
                response_times.append(diff)
        except (ValueError, TypeError):
            pass
    avg_response_seconds = round(sum(response_times) / len(response_times), 1) if response_times else None

    # Gap 4: Fetch last message preview for each lead
    lead_ids = [l["id"] for l in leads]
    last_messages = {}
    if lead_ids:
        placeholders = ",".join(["?"] * len(lead_ids))
        msg_rows = conn.execute(f"""
            SELECT m.lead_id, m.content FROM messages m
            INNER JOIN (
                SELECT lead_id, MAX(id) as max_id FROM messages
                WHERE lead_id IN ({placeholders}) AND is_internal_note=0
                GROUP BY lead_id
            ) latest ON m.id = latest.max_id
        """, lead_ids).fetchall()
        for mr in msg_rows:
            last_messages[mr["lead_id"]] = mr["content"][:60]
    conn.close()

    for lead in leads:
        lead["last_message"] = last_messages.get(lead["id"], "")

    return render_template("dashboard.html", business=business, stats=stats, leads=leads,
                           avg_response_seconds=avg_response_seconds)


# ─── Business Management ────────────────────────────────────────────────────

@app.route("/business/new", methods=["GET", "POST"])
def business_new():
    if request.method == "POST":
        data = request.form
        bid = Business.create(
            name=data["name"],
            org_id=data["org_id"],
            timezone=data.get("timezone", "America/New_York"),
            google_lsa_customer_id=data.get("google_lsa_customer_id", ""),
            yelp_business_id=data.get("yelp_business_id", ""),
            thumbtack_pro_id=data.get("thumbtack_pro_id", ""),
            angi_provider_id=data.get("angi_provider_id", ""),
            chat_widget_enabled=1 if data.get("chat_widget_enabled") else 0,
            contact_form_enabled=1 if data.get("contact_form_enabled") else 0,
            ai_chatbot_enabled=1 if data.get("ai_chatbot_enabled") else 0,
            operating_hours_start=int(data.get("operating_hours_start", 9)),
            operating_hours_end=int(data.get("operating_hours_end", 21)),
            max_follow_ups=int(data.get("max_follow_ups", 4)),
        )
        flash(f"Business created (ID: {bid})", "success")
        return redirect(url_for("dashboard", business_id=bid))
    return render_template("business_form.html", business=None)


@app.route("/business/<int:business_id>/edit", methods=["GET", "POST"])
def business_edit(business_id):
    business = Business.get(business_id)
    if not business:
        flash("Business not found", "danger")
        return redirect(url_for("index"))
    if request.method == "POST":
        data = request.form
        Business.update(
            business_id,
            name=data["name"],
            timezone=data.get("timezone", "America/New_York"),
            google_lsa_customer_id=data.get("google_lsa_customer_id", ""),
            yelp_business_id=data.get("yelp_business_id", ""),
            thumbtack_pro_id=data.get("thumbtack_pro_id", ""),
            angi_provider_id=data.get("angi_provider_id", ""),
            chat_widget_enabled=1 if data.get("chat_widget_enabled") else 0,
            contact_form_enabled=1 if data.get("contact_form_enabled") else 0,
            ai_chatbot_enabled=1 if data.get("ai_chatbot_enabled") else 0,
            operating_hours_start=int(data.get("operating_hours_start", 9)),
            operating_hours_end=int(data.get("operating_hours_end", 21)),
            max_follow_ups=int(data.get("max_follow_ups", 4)),
        )
        flash("Business updated", "success")
        return redirect(url_for("dashboard", business_id=business_id))
    return render_template("business_form.html", business=business)


@app.route("/business/<int:business_id>/delete", methods=["POST"])
def business_delete(business_id):
    Business.delete(business_id)
    flash("Business deleted", "success")
    return redirect(url_for("index"))


# ─── Knowledge Base ──────────────────────────────────────────────────────────

@app.route("/business/<int:business_id>/kb")
def knowledge_base(business_id):
    business = Business.get(business_id)
    kbs = KnowledgeBase.list_for_business(business_id)
    return render_template("knowledge_base.html", business=business, kbs=kbs)


@app.route("/business/<int:business_id>/kb/new", methods=["POST"])
def kb_create(business_id):
    data = request.form
    KnowledgeBase.create(
        business_id=business_id,
        name=data["name"],
        content=data["content"],
        category=data.get("category", "general"),
    )
    flash("Knowledge base entry created", "success")
    return redirect(url_for("knowledge_base", business_id=business_id))


@app.route("/kb/<int:kb_id>/edit", methods=["POST"])
def kb_edit(kb_id):
    kb = KnowledgeBase.get(kb_id)
    if not kb:
        return jsonify({"error": "Not found"}), 404
    data = request.form
    KnowledgeBase.update(
        kb_id,
        name=data.get("name", kb["name"]),
        content=data.get("content", kb["content"]),
        category=data.get("category", kb["category"]),
        is_active=1 if data.get("is_active") else 0,
    )
    flash("Knowledge base updated", "success")
    return redirect(url_for("knowledge_base", business_id=kb["business_id"]))


@app.route("/kb/<int:kb_id>/delete", methods=["POST"])
def kb_delete(kb_id):
    kb = KnowledgeBase.get(kb_id)
    if not kb:
        return jsonify({"error": "Not found"}), 404
    bid = kb["business_id"]
    KnowledgeBase.delete(kb_id)
    flash("Knowledge base entry deleted", "success")
    return redirect(url_for("knowledge_base", business_id=bid))


@app.route("/kb/share/<int:business_id>", methods=["POST"])
@api_error_handler
def kb_generate_share_token(business_id):
    """Generate a share token for the KB."""
    business = Business.get(business_id)
    if not business:
        return jsonify({"error": "Business not found"}), 404
    token = secrets.token_urlsafe(16)
    Business.update(business_id, share_token=token)
    share_url = url_for("kb_shared_view", token=token, _external=True)
    return jsonify({"success": True, "share_token": token, "share_url": share_url})


@app.route("/kb/view/<token>")
def kb_shared_view(token):
    """Shareable read-only KB view via token."""
    from models import get_db
    conn = get_db()
    row = conn.execute("SELECT id FROM businesses WHERE share_token=?", (token,)).fetchone()
    conn.close()
    if not row:
        return "Not found", 404
    business_id = row["id"]
    business = Business.get(business_id)
    kbs = KnowledgeBase.list_for_business(business_id)
    active_kbs = [kb for kb in kbs if kb.get("is_active")]
    return render_template("kb_shared_view.html", business=business, kbs=active_kbs)


# ─── Lead Management ────────────────────────────────────────────────────────

@app.route("/lead/<int:lead_id>")
def lead_detail(lead_id):
    lead = Lead.get(lead_id)
    if not lead:
        flash("Lead not found", "danger")
        return redirect(url_for("index"))
    business = Business.get(lead["business_id"])
    messages = Message.list_for_lead(lead_id)
    return render_template("lead_detail.html", lead=lead, business=business, messages=messages)


@app.route("/api/lead/<int:lead_id>/message", methods=["POST"])
@api_error_handler
def lead_send_message(lead_id):
    """CSR sends a manual message."""
    data = request.get_json()
    result = lead_processor.send_csr_message(
        lead_id=lead_id,
        csr_name=data.get("csr_name", "CSR"),
        message_content=sanitize_message(data["message"]),
    )
    return jsonify(result)


@app.route("/api/lead/<int:lead_id>/book", methods=["POST"])
@api_error_handler
def lead_book(lead_id):
    data = request.get_json() or {}
    result = lead_processor.mark_booked(
        lead_id=lead_id,
        booked_by=data.get("booked_by", "MANUAL"),
        st_job_link=data.get("st_job_link"),
    )
    return jsonify(result)


@app.route("/api/lead/<int:lead_id>/unbook", methods=["POST"])
@api_error_handler
def lead_unbook(lead_id):
    lead = Lead.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found"}), 404
    result = lead_processor.mark_unbooked(lead_id, lead["business_id"])
    return jsonify(result)


@app.route("/api/lead/<int:lead_id>/non-lead", methods=["POST"])
@api_error_handler
def lead_non_lead(lead_id):
    result = Lead.update(lead_id, status="NON_LEAD")
    return jsonify({"success": result})


@app.route("/api/lead/<int:lead_id>/re-enable-chatbot", methods=["POST"])
@api_error_handler
def lead_re_enable(lead_id):
    result = lead_processor.re_enable_chatbot(lead_id)
    return jsonify(result)


@app.route("/api/lead/<int:lead_id>/note", methods=["POST"])
@api_error_handler
def lead_add_note(lead_id):
    data = request.get_json()
    Message.create(
        lead_id=lead_id,
        sender=data.get("author", "CSR"),
        content=sanitize_message(data["note"]),
        is_internal_note=1,
    )
    return jsonify({"success": True})


# ─── Inbound Processing API ─────────────────────────────────────────────────

@app.route("/api/inbound", methods=["POST"])
@api_error_handler
def inbound_message():
    """Process an inbound lead/message from any platform."""
    data = request.get_json()
    result = lead_processor.process_inbound_message(
        business_id=data["business_id"],
        platform=data["platform"],
        customer_message=sanitize_message(data["message"]),
        customer_name=data.get("customer_name"),
        customer_phone=validate_phone(data.get("customer_phone")),
        customer_email=validate_email(data.get("customer_email")),
        service_type=data.get("service_type"),
        platform_lead_id=data.get("platform_lead_id"),
        platform_message_id=data.get("platform_message_id"),
        channel=data.get("channel", "Platform"),
    )
    return jsonify(result)


# ─── Platform Webhooks ────────────────────────────────────────────────────────

def _process_platform_webhook(platform_name, raw_data, business_id_lookup_field):
    """Generic webhook processor using platform connectors."""
    connector = get_connector(platform_name)
    if not connector:
        return jsonify({"error": f"Unknown platform: {platform_name}"}), 400

    parsed = connector.parse_inbound(raw_data)

    # Look up business by platform-specific ID
    from models import get_db
    conn = get_db()
    row = conn.execute(
        f"SELECT id FROM businesses WHERE {business_id_lookup_field}=?",
        (raw_data.get("business_id", raw_data.get("account_id", "")),)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Business not found for this platform ID"}), 404

    result = lead_processor.process_inbound_message(
        business_id=row["id"],
        platform=platform_name,
        customer_message=sanitize_message(parsed["message"]),
        customer_name=parsed.get("customer_name"),
        customer_phone=validate_phone(parsed.get("customer_phone")),
        customer_email=validate_email(parsed.get("customer_email")),
        service_type=parsed.get("service_type"),
        platform_lead_id=parsed.get("platform_lead_id"),
        platform_message_id=parsed.get("platform_message_id"),
    )
    return jsonify(result)


@app.route("/webhook/google-lsa", methods=["POST"])
@api_error_handler
def webhook_google_lsa():
    return _process_platform_webhook("google_lsa", request.get_json(), "google_lsa_customer_id")


@app.route("/webhook/yelp", methods=["POST"])
@api_error_handler
def webhook_yelp():
    data = request.get_json() or request.form.to_dict()
    return _process_platform_webhook("yelp", data, "yelp_business_id")


@app.route("/webhook/thumbtack", methods=["POST"])
@api_error_handler
def webhook_thumbtack():
    return _process_platform_webhook("thumbtack", request.get_json(), "thumbtack_pro_id")


@app.route("/webhook/angi", methods=["POST"])
@api_error_handler
def webhook_angi():
    return _process_platform_webhook("angi", request.get_json(), "angi_provider_id")


@app.route("/webhook/duke-energy", methods=["POST"])
@api_error_handler
def webhook_duke_energy():
    return _process_platform_webhook("duke_energy", request.get_json(), "duke_energy_account_id")


@app.route("/api/widget/<int:business_id>/message", methods=["POST", "OPTIONS"])
@api_error_handler
def widget_message(business_id):
    """Chat widget endpoint with CORS support."""
    if request.method == "OPTIONS":
        resp = jsonify({})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    data = request.get_json()
    connector = get_connector("chat_widget")
    parsed = connector.parse_inbound(data)

    result = lead_processor.process_inbound_message(
        business_id=business_id,
        platform="chat_widget",
        customer_message=sanitize_message(parsed["message"]),
        customer_name=parsed.get("customer_name"),
        customer_phone=validate_phone(parsed.get("customer_phone")),
        customer_email=validate_email(parsed.get("customer_email")),
        service_type=parsed.get("service_type"),
        platform_lead_id=parsed.get("platform_lead_id"),
        channel="Chat Widget",
    )

    resp = jsonify(result)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/api/form/<int:business_id>/submit", methods=["POST"])
@api_error_handler
def form_submit(business_id):
    """Contact form submission endpoint."""
    data = request.get_json() or request.form.to_dict()
    connector = get_connector("contact_form")
    parsed = connector.parse_inbound(data)

    result = lead_processor.process_inbound_message(
        business_id=business_id,
        platform="contact_form",
        customer_message=sanitize_message(parsed["message"]),
        customer_name=parsed.get("customer_name"),
        customer_phone=validate_phone(parsed.get("customer_phone")),
        customer_email=validate_email(parsed.get("customer_email")),
        service_type=parsed.get("service_type"),
        platform_lead_id=parsed.get("platform_lead_id"),
        channel="Contact Form",
    )
    return jsonify(result)


# ─── Testing Platform ───────────────────────────────────────────────────────

@app.route("/business/<int:business_id>/test")
def testing_platform(business_id):
    business = Business.get(business_id)
    if not business:
        flash("Business not found", "danger")
        return redirect(url_for("index"))
    kbs = KnowledgeBase.list_for_business(business_id)
    sessions = TestSession.list_for_business(business_id)
    return render_template("testing.html", business=business, kbs=kbs, sessions=sessions)


@app.route("/api/test/lead-simulation", methods=["POST"])
@api_error_handler
def test_lead_simulation():
    """Simulate an inbound lead for testing."""
    data = request.get_json()
    business_id = data["business_id"]
    platform = data.get("platform", "test_simulation")

    session_id = TestSession.create(business_id, "lead_simulation", platform)

    result = lead_processor.process_inbound_message(
        business_id=business_id,
        platform=platform,
        customer_message=sanitize_message(data["message"]),
        customer_name=data.get("customer_name", "Test Customer"),
        customer_phone=data.get("customer_phone", "555-0100"),
        customer_email=data.get("customer_email", "test@example.com"),
        service_type=data.get("service_type", "General"),
        platform_lead_id=f"test_{session_id}_{datetime.now().timestamp()}",
    )

    TestSession.update(session_id, results_json=json.dumps(result))
    result["session_id"] = session_id
    return jsonify(result)


@app.route("/api/test/conversation", methods=["POST"])
@api_error_handler
def test_conversation():
    """Continue a test conversation on an existing lead."""
    data = request.get_json()
    lead_id = data["lead_id"]
    lead = Lead.get(lead_id)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found"})

    result = lead_processor.process_inbound_message(
        business_id=lead["business_id"],
        platform=lead["platform"],
        customer_message=sanitize_message(data["message"]),
        platform_lead_id=lead["platform_lead_id"],
    )
    return jsonify(result)


@app.route("/api/test/kb", methods=["POST"])
@api_error_handler
def test_knowledge_base():
    """Test knowledge base with a specific question."""
    data = request.get_json()
    business_id = data["business_id"]

    kb_content = KnowledgeBase.get_active_content(business_id)
    if not kb_content:
        return jsonify({
            "success": False,
            "error": "No active knowledge base entries found for this business."
        })

    result = bridge.test_knowledge_base(kb_content, data["question"])
    return jsonify(result)


@app.route("/api/test/kb-batch", methods=["POST"])
@api_error_handler
def test_kb_batch():
    """Run batch knowledge base tests."""
    data = request.get_json()
    business_id = data["business_id"]
    questions = data["questions"]

    kb_content = KnowledgeBase.get_active_content(business_id)
    if not kb_content:
        return jsonify({"success": False, "error": "No active knowledge base."})

    session_id = TestSession.create(business_id, "kb_batch_test")
    results = []

    for q in questions:
        result = bridge.test_knowledge_base(kb_content, q["question"])
        passed = True
        if result["success"] and q.get("expected_keywords"):
            response_lower = result["response"].lower()
            for kw in q["expected_keywords"]:
                if kw.lower() not in response_lower:
                    passed = False
                    break

        results.append({
            "question": q["question"],
            "expected_keywords": q.get("expected_keywords", []),
            "response": result.get("response", result.get("error", "")),
            "success": result["success"],
            "passed": passed,
        })

    TestSession.update(session_id, results_json=json.dumps(results), status="completed")
    return jsonify({"success": True, "session_id": session_id, "results": results})


@app.route("/api/test/health", methods=["GET"])
def test_health():
    """Check Claude CLI health."""
    healthy = bridge.health_check()
    return jsonify({"claude_cli_available": healthy})


@app.route("/api/test/metrics", methods=["GET"])
def test_metrics():
    """Get Claude bridge metrics."""
    return jsonify({"metrics": bridge.metrics.to_dict()})


@app.route("/api/test/follow-ups/<int:business_id>", methods=["POST"])
@api_error_handler
def test_follow_ups(business_id):
    """Trigger follow-up processing for testing."""
    results = lead_processor.process_follow_ups(business_id)
    return jsonify({"success": True, "follow_ups_sent": results})


@app.route("/api/test/platform-comparison", methods=["POST"])
@api_error_handler
def test_platform_comparison():
    """Compare AI responses across platforms."""
    data = request.get_json()
    business_id = data["business_id"]
    message = data["message"]
    platforms = data.get("platforms", ["google_lsa", "yelp", "thumbtack", "chat_widget"])

    kb_content = KnowledgeBase.get_active_content(business_id)
    results = bridge.generate_platform_simulation(message, platforms, kb_content or "No knowledge base configured.")
    return jsonify({"success": True, "results": results})


# ─── API: List leads (for AJAX) ────────────────────────────────────────────

@app.route("/api/leads/<int:business_id>")
def api_leads(business_id):
    status = request.args.get("status")
    platform = request.args.get("platform")
    leads = Lead.list_for_business(business_id, status=status, platform=platform)

    # Add last message preview
    lead_ids = [l["id"] for l in leads]
    if lead_ids:
        from models import get_db
        conn = get_db()
        placeholders = ",".join(["?"] * len(lead_ids))
        msg_rows = conn.execute(f"""
            SELECT m.lead_id, m.content FROM messages m
            INNER JOIN (
                SELECT lead_id, MAX(id) as max_id FROM messages
                WHERE lead_id IN ({placeholders}) AND is_internal_note=0
                GROUP BY lead_id
            ) latest ON m.id = latest.max_id
        """, lead_ids).fetchall()
        conn.close()
        last_messages = {mr["lead_id"]: mr["content"][:60] for mr in msg_rows}
        for lead in leads:
            lead["last_message"] = last_messages.get(lead["id"], "")

    return jsonify(leads)


@app.route("/api/lead/<int:lead_id>/messages")
def api_lead_messages(lead_id):
    messages = Message.list_for_lead(lead_id)
    return jsonify(messages)


# ─── Metrics & Analytics ──────────────────────────────────────────────────────

@app.route("/api/metrics/<int:business_id>")
@api_error_handler
def api_metrics(business_id):
    """Business analytics: booking rate, lead volume, avg first response."""
    stats = Lead.get_stats(business_id)

    # Calculate avg first response time
    from models import get_db
    conn = get_db()
    rows = conn.execute("""
        SELECT created_at, first_response_at FROM leads
        WHERE business_id=? AND first_response_at IS NOT NULL
    """, (business_id,)).fetchall()
    conn.close()

    response_times = []
    for r in rows:
        try:
            created = datetime.fromisoformat(r["created_at"])
            responded = datetime.fromisoformat(r["first_response_at"])
            diff = (responded - created).total_seconds()
            if diff > 0:
                response_times.append(diff)
        except (ValueError, TypeError):
            pass

    avg_response = round(sum(response_times) / len(response_times), 1) if response_times else None

    # Platform breakdown
    conn = get_db()
    platform_rows = conn.execute("""
        SELECT platform, status, COUNT(*) as count FROM leads
        WHERE business_id=? GROUP BY platform, status
    """, (business_id,)).fetchall()
    conn.close()

    platforms = {}
    for r in platform_rows:
        p = r["platform"]
        if p not in platforms:
            platforms[p] = {"total": 0, "booked": 0}
        platforms[p]["total"] += r["count"]
        if r["status"] == "BOOKED":
            platforms[p]["booked"] += r["count"]

    return jsonify({
        "stats": stats,
        "avg_first_response_seconds": avg_response,
        "platform_breakdown": platforms,
    })


# ─── Data Export ──────────────────────────────────────────────────────────────

@app.route("/api/export/<int:business_id>/leads")
@api_error_handler
def export_leads(business_id):
    """Export leads as CSV."""
    leads = Lead.list_for_business(business_id, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Platform", "Status", "Customer Name", "Phone", "Email",
        "Address", "Service Type", "Chatbot Enabled", "Escalated",
        "Assigned To", "Follow-ups", "Booked By", "ST Job Link",
        "Created At", "Updated At"
    ])

    for lead in leads:
        writer.writerow([
            lead["id"], lead["platform"], lead["status"],
            lead.get("customer_name", ""), lead.get("customer_phone", ""),
            lead.get("customer_email", ""), lead.get("customer_address", ""),
            lead.get("service_type", ""), lead.get("is_chatbot_enabled", ""),
            lead.get("is_escalated", ""), lead.get("assigned_to", ""),
            lead.get("follow_up_count", ""), lead.get("job_booked_by", ""),
            lead.get("st_job_link", ""), lead.get("created_at", ""),
            lead.get("updated_at", ""),
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=leads_{business_id}.csv"}
    )


@app.after_request
def add_cors_headers(response):
    """Gap 7: Add CORS headers to widget API responses."""
    if request.path.startswith("/api/widget/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ─── Chat Widget Embed ────────────────────────────────────────────────────────

@app.route("/widget/embed/<int:business_id>")
def widget_embed(business_id):
    """Serve standalone chat widget page."""
    business = Business.get(business_id)
    if not business:
        return "Business not found", 404
    return render_template("chat_widget_embed.html", business=business)


@app.route("/widget/script/<int:business_id>")
def widget_script(business_id):
    """Return JS snippet that injects a chat widget iframe."""
    script = f"""(function() {{
  var iframe = document.createElement('iframe');
  iframe.src = '{url_for("widget_embed", business_id=business_id, _external=True)}';
  iframe.style.cssText = 'position:fixed;bottom:0;right:0;width:400px;height:600px;border:none;z-index:99999;';
  document.body.appendChild(iframe);
}})();"""
    return Response(script, mimetype="application/javascript")


# ─── Cleaning Business: Pricing ──────────────────────────────────────────────

from pricing import calculate_price, get_all_service_types, SERVICE_TYPES, CONDITION_MULTIPLIERS


@app.route("/business/<int:business_id>/pricing")
def pricing_page(business_id):
    business = Business.get(business_id)
    if not business:
        flash("Business not found", "danger")
        return redirect(url_for("index"))
    return render_template("pricing.html", business=business,
                           service_types=SERVICE_TYPES, conditions=CONDITION_MULTIPLIERS)


@app.route("/api/pricing/calculate", methods=["POST"])
@api_error_handler
def api_calculate_price():
    data = request.get_json()
    result = calculate_price(
        service_type=data["service_type"],
        bedrooms=int(data.get("bedrooms", 0)),
        bathrooms=float(data.get("bathrooms", 0)),
        condition=data.get("condition", "average"),
        sqft=int(data["sqft"]) if data.get("sqft") else None,
    )
    return jsonify(result)


# ─── Cleaning Business: Jobs ────────────────────────────────────────────────

@app.route("/business/<int:business_id>/jobs")
def jobs_page(business_id):
    business = Business.get(business_id)
    if not business:
        flash("Business not found", "danger")
        return redirect(url_for("index"))
    status_filter = request.args.get("status")
    jobs = Job.list_for_business(business_id, status=status_filter)
    cleaners = Cleaner.list_for_business(business_id)
    customers = Customer.list_for_business(business_id)
    job_stats = Job.get_stats(business_id)
    return render_template("jobs.html", business=business, jobs=jobs,
                           cleaners=cleaners, customers=customers, job_stats=job_stats,
                           service_types=SERVICE_TYPES, conditions=CONDITION_MULTIPLIERS)


@app.route("/api/jobs/<int:business_id>", methods=["POST"])
@api_error_handler
def api_create_job(business_id):
    data = request.get_json()
    pricing = calculate_price(
        service_type=data["service_type"],
        bedrooms=int(data.get("bedrooms", 0)),
        bathrooms=float(data.get("bathrooms", 0)),
        condition=data.get("condition", "average"),
        sqft=int(data["sqft"]) if data.get("sqft") else None,
    )
    job_id = Job.create(
        business_id=business_id,
        service_type=data["service_type"],
        quoted_price=pricing["price"],
        customer_id=int(data["customer_id"]) if data.get("customer_id") else None,
        cleaner_id=int(data["cleaner_id"]) if data.get("cleaner_id") else None,
        bedrooms=int(data.get("bedrooms", 0)),
        bathrooms=float(data.get("bathrooms", 0)),
        sqft=int(data["sqft"]) if data.get("sqft") else None,
        condition=data.get("condition", "average"),
        estimated_hours=pricing["estimated_hours"],
        labor_cost=pricing["costs"]["labor"],
        supply_cost=pricing["costs"]["supplies"],
        address=data.get("address", ""),
        scheduled_date=data.get("scheduled_date"),
        scheduled_time=data.get("scheduled_time"),
        notes=data.get("notes", ""),
        pricing_breakdown_json=json.dumps(pricing["breakdown"]),
    )
    return jsonify({"success": True, "job_id": job_id, "pricing": pricing})


@app.route("/api/jobs/<int:job_id>/update", methods=["POST"])
@api_error_handler
def api_update_job(job_id):
    data = request.get_json()
    kwargs = {}
    for field in ["status", "cleaner_id", "actual_price", "actual_hours",
                   "scheduled_date", "scheduled_time", "notes", "address"]:
        if field in data:
            kwargs[field] = data[field]
    if data.get("status") == "COMPLETED" and "completed_at" not in kwargs:
        kwargs["completed_at"] = datetime.now().isoformat()
    if data.get("actual_hours") and data.get("cleaner_id"):
        cleaner = Cleaner.get(int(data["cleaner_id"]))
        if cleaner:
            kwargs["labor_cost"] = round(float(data["actual_hours"]) * cleaner["hourly_rate"], 2)
    Job.update(job_id, **kwargs)
    return jsonify({"success": True})


@app.route("/api/jobs/<int:job_id>/delete", methods=["POST"])
@api_error_handler
def api_delete_job(job_id):
    Job.delete(job_id)
    return jsonify({"success": True})


# ─── Cleaning Business: Customers ───────────────────────────────────────────

@app.route("/business/<int:business_id>/customers")
def customers_page(business_id):
    business = Business.get(business_id)
    if not business:
        flash("Business not found", "danger")
        return redirect(url_for("index"))
    customers = Customer.list_for_business(business_id)
    for c in customers:
        c["ltv"] = Customer.get_lifetime_value(c["id"])
    return render_template("customers.html", business=business, customers=customers)


@app.route("/api/customers/<int:business_id>", methods=["POST"])
@api_error_handler
def api_create_customer(business_id):
    data = request.get_json()
    cid = Customer.create(
        business_id=business_id,
        name=data["name"],
        email=data.get("email", ""),
        phone=data.get("phone", ""),
        address=data.get("address", ""),
        notes=data.get("notes", ""),
    )
    return jsonify({"success": True, "customer_id": cid})


@app.route("/api/customers/<int:customer_id>/update", methods=["POST"])
@api_error_handler
def api_update_customer(customer_id):
    data = request.get_json()
    kwargs = {}
    for field in ["name", "email", "phone", "address", "notes"]:
        if field in data:
            kwargs[field] = data[field]
    Customer.update(customer_id, **kwargs)
    return jsonify({"success": True})


@app.route("/api/customers/<int:customer_id>/delete", methods=["POST"])
@api_error_handler
def api_delete_customer(customer_id):
    Customer.delete(customer_id)
    return jsonify({"success": True})


# ─── Cleaning Business: Cleaners ────────────────────────────────────────────

@app.route("/api/cleaners/<int:business_id>", methods=["POST"])
@api_error_handler
def api_create_cleaner(business_id):
    data = request.get_json()
    cid = Cleaner.create(
        business_id=business_id,
        name=data["name"],
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        hourly_rate=float(data.get("hourly_rate", 18.00)),
    )
    return jsonify({"success": True, "cleaner_id": cid})


@app.route("/api/cleaners/<int:cleaner_id>/update", methods=["POST"])
@api_error_handler
def api_update_cleaner(cleaner_id):
    data = request.get_json()
    kwargs = {}
    for field in ["name", "phone", "email", "hourly_rate", "is_active"]:
        if field in data:
            kwargs[field] = data[field]
    Cleaner.update(cleaner_id, **kwargs)
    return jsonify({"success": True})


# ─── Cleaning Business: Expenses ────────────────────────────────────────────

@app.route("/api/expenses/<int:business_id>", methods=["POST"])
@api_error_handler
def api_create_expense(business_id):
    data = request.get_json()
    eid = Expense.create(
        business_id=business_id,
        category=data["category"],
        amount=float(data["amount"]),
        description=data.get("description", ""),
        expense_date=data.get("expense_date"),
    )
    return jsonify({"success": True, "expense_id": eid})


@app.route("/api/expenses/<int:expense_id>/delete", methods=["POST"])
@api_error_handler
def api_delete_expense(expense_id):
    Expense.delete(expense_id)
    return jsonify({"success": True})


# ─── Cleaning Business: Analytics ───────────────────────────────────────────

@app.route("/business/<int:business_id>/analytics")
def analytics_page(business_id):
    business = Business.get(business_id)
    if not business:
        flash("Business not found", "danger")
        return redirect(url_for("index"))
    job_stats = Job.get_stats(business_id)
    monthly = Job.get_revenue_by_month(business_id)
    by_service = Job.get_revenue_by_service(business_id)
    cleaner_stats = Job.get_cleaner_stats(business_id)
    expense_summary = Expense.get_summary(business_id)
    expenses = Expense.list_for_business(business_id, limit=50)
    total_expenses = sum(e["amount"] for e in expenses)
    return render_template("analytics.html", business=business, job_stats=job_stats,
                           monthly=monthly, by_service=by_service, cleaner_stats=cleaner_stats,
                           expense_summary=expense_summary, expenses=expenses,
                           total_expenses=round(total_expenses, 2))


# ─── Cleaning Business: Schedule Calendar ───────────────────────────────────

@app.route("/business/<int:business_id>/schedule")
def schedule_page(business_id):
    business = Business.get(business_id)
    if not business:
        flash("Business not found", "danger")
        return redirect(url_for("index"))
    cleaners = Cleaner.list_for_business(business_id)
    customers = Customer.list_for_business(business_id)
    return render_template("schedule.html", business=business, cleaners=cleaners,
                           customers=customers, service_types=SERVICE_TYPES,
                           conditions=CONDITION_MULTIPLIERS)


@app.route("/api/schedule/<int:business_id>")
def api_schedule(business_id):
    start = request.args.get("start")
    end = request.args.get("end")
    cleaner_id = request.args.get("cleaner_id")
    if not start or not end:
        return jsonify({"error": "start and end required"}), 400
    jobs = Job.list_by_date_range(
        business_id, start, end,
        cleaner_id=int(cleaner_id) if cleaner_id else None
    )
    return jsonify(jobs)


# ─── Cleaning Business: Outreach & Networking ───────────────────────────────

@app.route("/business/<int:business_id>/outreach")
def outreach_page(business_id):
    business = Business.get(business_id)
    if not business:
        flash("Business not found", "danger")
        return redirect(url_for("index"))
    status_filter = request.args.get("status")
    outreach_list = Outreach.list_for_business(business_id, status=status_filter)
    stats = Outreach.get_stats(business_id)
    return render_template("outreach.html", business=business,
                           outreach_list=outreach_list, stats=stats)


@app.route("/api/outreach/<int:business_id>", methods=["POST"])
@api_error_handler
def api_create_outreach(business_id):
    data = request.get_json()
    oid = Outreach.create(
        business_id=business_id,
        contact_name=data["contact_name"],
        company=data.get("company", ""),
        outreach_type=data.get("outreach_type", "cold_call"),
        channel=data.get("channel", "phone"),
        notes=data.get("notes", ""),
        follow_up_date=data.get("follow_up_date"),
        contacted_at=data.get("contacted_at"),
    )
    return jsonify({"success": True, "outreach_id": oid})


@app.route("/api/outreach/<int:outreach_id>/status", methods=["POST"])
@api_error_handler
def api_update_outreach_status(outreach_id):
    data = request.get_json()
    Outreach.update(outreach_id, status=data["status"])
    return jsonify({"success": True})


@app.route("/api/outreach/<int:outreach_id>/update", methods=["POST"])
@api_error_handler
def api_update_outreach(outreach_id):
    data = request.get_json()
    kwargs = {}
    for field in ["contact_name", "company", "outreach_type", "channel", "notes", "follow_up_date", "status"]:
        if field in data:
            kwargs[field] = data[field]
    Outreach.update(outreach_id, **kwargs)
    return jsonify({"success": True})


@app.route("/api/outreach/<int:outreach_id>/delete", methods=["POST"])
@api_error_handler
def api_delete_outreach(outreach_id):
    Outreach.delete(outreach_id)
    return jsonify({"success": True})




if __name__ == "__main__":
    init_db()

    # Start scheduler
    from scheduler import start_scheduler
    start_scheduler()

    print("\n  Speed-to-Lead is running!")
    print("  Open http://127.0.0.1:5001 in your browser\n")
    app.run(debug=True, port=5001, host="127.0.0.1", use_reloader=False)
