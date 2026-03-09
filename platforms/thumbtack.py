"""
Thumbtack platform connector.
Webhook-based with dual environment (prod/staging) and file attachment support.
"""

from .base import PlatformConnector


class ThumbtackConnector(PlatformConnector):
    platform_name = "thumbtack"

    def parse_inbound(self, raw_data):
        """Parse Thumbtack webhook data."""
        customer = raw_data.get("customer", {})
        request_data = raw_data.get("request", raw_data)

        return {
            "customer_name": customer.get("name", raw_data.get("customerName", "")),
            "customer_phone": customer.get("phone", raw_data.get("customerPhone", "")),
            "customer_email": customer.get("email", ""),
            "customer_address": request_data.get("location", {}).get("city", ""),
            "service_type": request_data.get("category", request_data.get("service", "")),
            "message": raw_data.get("description", raw_data.get("message", "New Thumbtack lead")),
            "platform_lead_id": raw_data.get("leadID", raw_data.get("requestID", "")),
            "platform_message_id": raw_data.get("messageID"),
            "metadata": {
                "travel_preferences": request_data.get("travelPreferences"),
                "schedule": request_data.get("schedule"),
                "attachments": raw_data.get("attachments", []),
                "environment": raw_data.get("environment", "production"),
            }
        }

    def format_outbound(self, message, lead_context):
        return {
            "leadID": lead_context.get("platform_lead_id"),
            "message": message,
            "type": "reply",
        }
