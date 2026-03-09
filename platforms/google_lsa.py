"""
Google Local Services Ads (LSA) connector.
Polling-based with OAuth. Supports SMS fallback.
"""

from .base import PlatformConnector


class GoogleLSAConnector(PlatformConnector):
    platform_name = "google_lsa"

    def parse_inbound(self, raw_data):
        """Parse Google LSA lead data.
        Google LSA sends leads via their API (polling-based).
        """
        return {
            "customer_name": raw_data.get("customerName", ""),
            "customer_phone": raw_data.get("phoneNumber", ""),
            "customer_email": raw_data.get("email", ""),
            "customer_address": raw_data.get("postalAddress", ""),
            "service_type": raw_data.get("jobType", raw_data.get("categoryId", "")),
            "message": raw_data.get("message", raw_data.get("jobDetails", "New Google LSA lead")),
            "platform_lead_id": raw_data.get("leadId", raw_data.get("conversationId", "")),
            "platform_message_id": raw_data.get("messageId"),
            "metadata": {
                "geo_location": raw_data.get("geoLocation"),
                "lead_type": raw_data.get("leadType", "MESSAGE"),
                "booking_time": raw_data.get("bookingTime"),
            }
        }

    def format_outbound(self, message, lead_context):
        """Format outbound for Google LSA (message reply or SMS fallback)."""
        return {
            "leadId": lead_context.get("platform_lead_id"),
            "text": message,
            "type": "REPLY",
        }

    def validate_webhook(self, request):
        # Google LSA uses polling, not webhooks. Validation is via OAuth token.
        return True
