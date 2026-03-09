"""
Yelp platform connector.
Webhook-based with form-encoded subscription quirk.
"""

from .base import PlatformConnector


class YelpConnector(PlatformConnector):
    platform_name = "yelp"

    def parse_inbound(self, raw_data):
        """Parse Yelp webhook data.
        Yelp sends leads via webhooks with lead details.
        """
        user_data = raw_data.get("user", {})
        request_data = raw_data.get("request", {})

        return {
            "customer_name": user_data.get("name", ""),
            "customer_phone": user_data.get("phone", ""),
            "customer_email": user_data.get("email", ""),
            "customer_address": request_data.get("address", ""),
            "service_type": request_data.get("category", request_data.get("service", "")),
            "message": request_data.get("message", raw_data.get("text", "New Yelp lead")),
            "platform_lead_id": raw_data.get("lead_id", raw_data.get("id", "")),
            "platform_message_id": raw_data.get("event_id"),
            "metadata": {
                "event_type": raw_data.get("event_type", "lead"),
                "business_id": raw_data.get("business_id"),
                "rating": user_data.get("rating"),
            }
        }

    def format_outbound(self, message, lead_context):
        return {
            "lead_id": lead_context.get("platform_lead_id"),
            "message": message,
        }

    def validate_webhook(self, request):
        # Yelp uses webhook secret for validation
        return True
