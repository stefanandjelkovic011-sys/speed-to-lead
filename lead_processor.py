"""
Lead Processing Engine
Handles the full lead lifecycle: inbound processing, AI response, escalation, drip campaigns.
"""

import json
import threading
from datetime import datetime, timezone, timedelta
from models import Lead, Message, Business, KnowledgeBase, AuditLog, DripQueue
from claude_bridge import ClaudeBridge

bridge = ClaudeBridge(timeout=120)


def is_within_operating_hours(business):
    """Check if current time is within business operating hours (timezone-aware)."""
    try:
        tz_name = business.get("timezone", "America/New_York")
        # Use basic UTC offset approach for common US timezones
        tz_offsets = {
            "America/New_York": -5, "America/Chicago": -6,
            "America/Denver": -7, "America/Los_Angeles": -8,
            "America/Phoenix": -7,
        }
        offset = tz_offsets.get(tz_name, -5)
        now_utc = datetime.now(timezone.utc)
        local_time = now_utc + timedelta(hours=offset)

        if business.get("skip_weekends") and local_time.weekday() >= 5:
            return False

        hour = local_time.hour
        start = business.get("operating_hours_start", 9)
        end = business.get("operating_hours_end", 21)
        return start <= hour < end
    except Exception:
        return True


def process_inbound_message(business_id, platform, customer_message, customer_name=None,
                             customer_phone=None, customer_email=None, service_type=None,
                             platform_lead_id=None, platform_message_id=None, channel="Platform"):
    """Process a new inbound message from any platform. Returns the AI response or escalation info."""

    business = Business.get(business_id)
    if not business:
        return {"success": False, "error": "Business not found"}

    # Create or find lead (deduplication by platform_lead_id)
    lead_id = Lead.create(
        business_id=business_id,
        platform=platform,
        platform_lead_id=platform_lead_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        service_type=service_type,
    )

    lead = Lead.get(lead_id)

    # Update lead with any new customer info
    updates = {}
    if customer_name and not lead.get("customer_name"):
        updates["customer_name"] = customer_name
    if customer_phone and not lead.get("customer_phone"):
        updates["customer_phone"] = customer_phone
    if customer_email and not lead.get("customer_email"):
        updates["customer_email"] = customer_email
    if service_type and not lead.get("service_type"):
        updates["service_type"] = service_type

    # Track last customer message time
    updates["last_customer_message_at"] = datetime.now(timezone.utc).isoformat()

    if updates:
        Lead.update(lead_id, **updates)

    # Save inbound message (with dedup)
    msg_id = Message.create(
        lead_id=lead_id,
        sender="Homeowner",
        content=customer_message,
        channel=channel,
        platform_message_id=platform_message_id,
    )

    # Reset follow-up counter on customer response and cancel pending drips
    Lead.update(lead_id, follow_up_count=0, last_follow_up_sent_at=None)
    DripQueue.cancel_for_lead(lead_id)

    # Pre-checks: should we invoke AI?
    lead = Lead.get(lead_id)  # Refresh

    if not business.get("ai_chatbot_enabled"):
        return {
            "success": True,
            "lead_id": lead_id,
            "action": "queued_for_csr",
            "message": "AI chatbot disabled for this org. Lead queued for CSR."
        }

    if not lead.get("is_chatbot_enabled"):
        return {
            "success": True,
            "lead_id": lead_id,
            "action": "csr_handling",
            "message": "Lead is being handled by CSR. AI skipped."
        }

    if lead.get("is_escalated"):
        return {
            "success": True,
            "lead_id": lead_id,
            "action": "escalated",
            "message": "Lead is escalated. AI skipped."
        }

    # Update status to IN_PROGRESS
    if lead["status"] == "NEW":
        AuditLog.log("status_change", business_id=business_id, lead_id=lead_id,
                      old_value="NEW", new_value="IN_PROGRESS")
        Lead.update(lead_id, status="IN_PROGRESS")

    # Get knowledge base
    kb_content = KnowledgeBase.get_active_content(business_id)

    # Get conversation history
    messages = Message.list_for_lead(lead_id, include_notes=False)
    conversation = [{"sender": m["sender"], "content": m["content"]} for m in messages]

    # Invoke AI
    ai_result = bridge.generate_lead_response(
        lead_context={
            "customer_name": lead.get("customer_name"),
            "service_type": lead.get("service_type"),
            "platform": platform,
        },
        knowledge_base_content=kb_content if kb_content else "No knowledge base configured.",
        conversation_history=conversation,
        platform=platform,
    )

    if not ai_result["success"]:
        return {
            "success": True,
            "lead_id": lead_id,
            "action": "queued_for_csr",
            "message": "AI unavailable — lead saved and queued for CSR review."
        }

    response_text = ai_result["response"]

    # Track first response time
    if not lead.get("first_response_at"):
        Lead.update(lead_id, first_response_at=datetime.now(timezone.utc).isoformat())

    # Check for escalation signal
    if response_text.upper().startswith("ESCALATE:"):
        reason = response_text[9:].strip()
        Lead.update(lead_id, is_chatbot_enabled=0, is_escalated=1)
        DripQueue.cancel_for_lead(lead_id)
        AuditLog.log("escalated", business_id=business_id, lead_id=lead_id,
                      new_value=reason, performed_by="AI")
        Message.create(
            lead_id=lead_id,
            sender="System",
            content=f"AI escalated this lead: {reason}",
            is_internal_note=1,
        )
        return {
            "success": True,
            "lead_id": lead_id,
            "action": "escalated",
            "reason": reason,
            "message": "Lead escalated to CSR."
        }

    # Check for non-lead signal
    if response_text.upper().startswith("NON_LEAD:"):
        reason = response_text[9:].strip()
        Lead.update(lead_id, status="NON_LEAD")
        DripQueue.cancel_for_lead(lead_id)
        AuditLog.log("status_change", business_id=business_id, lead_id=lead_id,
                      old_value=lead["status"], new_value="NON_LEAD", performed_by="AI")
        Message.create(
            lead_id=lead_id,
            sender="System",
            content=f"AI classified as non-lead: {reason}",
            is_internal_note=1,
        )
        return {
            "success": True,
            "lead_id": lead_id,
            "action": "non_lead",
            "reason": reason,
        }

    # Save AI response
    Message.create(
        lead_id=lead_id,
        sender="AI Chat Agent",
        content=response_text,
        channel=channel,
    )

    return {
        "success": True,
        "lead_id": lead_id,
        "action": "responded",
        "response": response_text,
    }


def send_csr_message(lead_id, csr_name, message_content):
    """CSR manually sends a message, taking over from AI."""
    lead = Lead.get(lead_id)
    if not lead:
        return {"success": False, "error": "Lead not found"}

    # Auto-escalate on CSR takeover
    Lead.update(lead_id, is_chatbot_enabled=0, is_escalated=1, assigned_to=csr_name)
    DripQueue.cancel_for_lead(lead_id)
    AuditLog.log("csr_takeover", business_id=lead["business_id"], lead_id=lead_id,
                  new_value=csr_name, performed_by=csr_name)

    # Track first response if not yet set
    if not lead.get("first_response_at"):
        Lead.update(lead_id, first_response_at=datetime.now(timezone.utc).isoformat())

    Message.create(
        lead_id=lead_id,
        sender=f"CSR ({csr_name})",
        content=message_content,
        channel="Platform",
    )

    return {"success": True, "lead_id": lead_id, "action": "csr_replied"}


def mark_booked(lead_id, booked_by="MANUAL", st_job_link=None):
    """Mark a lead as booked."""
    lead = Lead.get(lead_id)
    if not lead:
        return {"success": False, "error": "Lead not found"}

    old_status = lead["status"]
    Lead.update(
        lead_id,
        status="BOOKED",
        job_booked_by=booked_by,
        st_job_link=st_job_link or "",
    )
    DripQueue.cancel_for_lead(lead_id)
    AuditLog.log("status_change", business_id=lead["business_id"], lead_id=lead_id,
                  old_value=old_status, new_value="BOOKED", performed_by=booked_by)
    return {"success": True, "lead_id": lead_id}


def mark_unbooked(lead_id, business_id):
    """Mark a lead as unbooked and trigger classification."""
    lead = Lead.get(lead_id)
    if not lead:
        return {"success": False, "error": "Lead not found"}
    if lead["status"] == "BOOKED":
        return {"success": False, "error": "Cannot change a BOOKED lead to UNBOOKED"}

    old_status = lead["status"]
    Lead.update(lead_id, status="UNBOOKED")
    DripQueue.cancel_for_lead(lead_id)
    AuditLog.log("status_change", business_id=business_id, lead_id=lead_id,
                  old_value=old_status, new_value="UNBOOKED")

    # Async classification
    def classify():
        messages = Message.list_for_lead(lead_id, include_notes=False)
        conversation = [{"sender": m["sender"], "content": m["content"]} for m in messages]
        kb_content = KnowledgeBase.get_active_content(business_id)
        result = bridge.classify_unbooked_lead(conversation, kb_content)
        if result["success"]:
            Lead.update(lead_id, classification_json=result["response"])

    threading.Thread(target=classify, daemon=True).start()
    return {"success": True, "lead_id": lead_id}


def process_follow_ups(business_id):
    """Check and send follow-ups for leads that need them."""
    business = Business.get(business_id)
    if not business:
        return []

    if not is_within_operating_hours(business):
        return []

    cadence = json.loads(business.get("follow_up_cadence_json", "[1,3,7,14]"))
    max_follow_ups = business.get("max_follow_ups", 4)
    kb_content = KnowledgeBase.get_active_content(business_id)

    leads = Lead.list_for_business(business_id, status="IN_PROGRESS", limit=200)
    results = []

    now = datetime.now(timezone.utc)

    for lead in leads:
        if not lead.get("is_chatbot_enabled"):
            continue
        if lead["follow_up_count"] >= max_follow_ups:
            continue
        if lead["follow_up_count"] >= len(cadence):
            continue

        days_to_wait = cadence[lead["follow_up_count"]]
        last_msg_time = lead.get("last_follow_up_sent_at") or lead.get("updated_at")
        if last_msg_time:
            try:
                last_dt = datetime.fromisoformat(last_msg_time.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if (now - last_dt).days < days_to_wait:
                    continue
            except (ValueError, TypeError):
                continue

        # Generate and send follow-up
        fu_result = bridge.generate_follow_up(
            lead_context={
                "customer_name": lead.get("customer_name", "there"),
                "service_type": lead.get("service_type", "home service"),
                "platform": lead.get("platform", "unknown"),
            },
            knowledge_base_content=kb_content,
            follow_up_number=lead["follow_up_count"] + 1,
        )

        if fu_result["success"]:
            Message.create(
                lead_id=lead["id"],
                sender="Drip Campaign",
                content=fu_result["response"],
            )
            Lead.update(
                lead["id"],
                follow_up_count=lead["follow_up_count"] + 1,
                last_follow_up_sent_at=now.isoformat(),
            )
            AuditLog.log("follow_up_sent", business_id=business_id, lead_id=lead["id"],
                          new_value=str(lead["follow_up_count"] + 1), performed_by="drip_campaign")
            results.append({"lead_id": lead["id"], "follow_up_number": lead["follow_up_count"] + 1})

    return results


def re_enable_chatbot(lead_id):
    """Re-enable AI chatbot for a lead."""
    lead = Lead.get(lead_id)
    Lead.update(lead_id, is_chatbot_enabled=1, is_escalated=0)
    if lead:
        AuditLog.log("chatbot_re_enabled", business_id=lead["business_id"], lead_id=lead_id)
    return {"success": True}
