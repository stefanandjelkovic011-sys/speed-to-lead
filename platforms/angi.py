"""
Angi (formerly Angie's List / HomeAdvisor) platform connector.
Webhook-only. Auto-detect Leads vs Ads format.
"""

from .base import PlatformConnector


class AngiConnector(PlatformConnector):
    platform_name = "angi"

    def parse_inbound(self, raw_data):
        """Parse Angi webhook data. Handles both Leads and Ads formats."""
        # Detect format: Angi Leads vs Angi Ads
        is_ads = raw_data.get("type") == "ads" or "adId" in raw_data

        if is_ads:
            return self._parse_ads(raw_data)
        return self._parse_leads(raw_data)

    def _parse_leads(self, raw_data):
        consumer = raw_data.get("consumer", {})
        task = raw_data.get("task", raw_data)
        return {
            "customer_name": consumer.get("name", raw_data.get("customerName", "")),
            "customer_phone": consumer.get("phone", raw_data.get("phone", "")),
            "customer_email": consumer.get("email", ""),
            "customer_address": task.get("address", ""),
            "service_type": task.get("category", task.get("taskName", "")),
            "message": task.get("description", raw_data.get("comments", "New Angi lead")),
            "platform_lead_id": raw_data.get("leadId", raw_data.get("srOid", "")),
            "platform_message_id": raw_data.get("eventId"),
            "metadata": {
                "format": "leads",
                "urgency": task.get("urgency"),
                "fee": raw_data.get("fee"),
            }
        }

    def _parse_ads(self, raw_data):
        return {
            "customer_name": raw_data.get("customerName", ""),
            "customer_phone": raw_data.get("customerPhone", ""),
            "customer_email": raw_data.get("customerEmail", ""),
            "customer_address": raw_data.get("address", ""),
            "service_type": raw_data.get("service", ""),
            "message": raw_data.get("description", "New Angi Ads lead"),
            "platform_lead_id": raw_data.get("adId", ""),
            "platform_message_id": None,
            "metadata": {
                "format": "ads",
                "matchType": raw_data.get("matchType"),
            }
        }

    def format_outbound(self, message, lead_context):
        return {
            "leadId": lead_context.get("platform_lead_id"),
            "message": message,
        }
