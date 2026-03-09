"""
Chat Widget platform connector.
Public API for embeddable iframe widget on business websites.
"""

from .base import PlatformConnector


class ChatWidgetConnector(PlatformConnector):
    platform_name = "chat_widget"

    def parse_inbound(self, raw_data):
        """Parse chat widget message data."""
        return {
            "customer_name": raw_data.get("name", raw_data.get("visitor_name", "")),
            "customer_phone": raw_data.get("phone", ""),
            "customer_email": raw_data.get("email", ""),
            "customer_address": raw_data.get("address", ""),
            "service_type": raw_data.get("service_type", ""),
            "message": raw_data.get("message", ""),
            "platform_lead_id": raw_data.get("session_id", raw_data.get("widget_session_id", "")),
            "platform_message_id": raw_data.get("message_id"),
            "metadata": {
                "page_url": raw_data.get("page_url"),
                "user_agent": raw_data.get("user_agent"),
                "referrer": raw_data.get("referrer"),
            }
        }

    def format_outbound(self, message, lead_context):
        return {
            "session_id": lead_context.get("platform_lead_id"),
            "message": message,
            "sender": "AI Chat Agent",
        }
