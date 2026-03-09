"""
Contact Form platform connector.
Email ingestion via SendGrid parse webhook or direct form submission.
"""

from .base import PlatformConnector


class ContactFormConnector(PlatformConnector):
    platform_name = "contact_form"

    def parse_inbound(self, raw_data):
        """Parse contact form submission or email parse data."""
        # Handle SendGrid inbound parse format
        if "from" in raw_data and "subject" in raw_data:
            return self._parse_email(raw_data)
        return self._parse_form(raw_data)

    def _parse_email(self, raw_data):
        from_field = raw_data.get("from", "")
        name = from_field.split("<")[0].strip().strip('"') if "<" in from_field else ""
        email = from_field.split("<")[1].rstrip(">") if "<" in from_field else from_field

        return {
            "customer_name": name,
            "customer_phone": "",
            "customer_email": email,
            "customer_address": "",
            "service_type": raw_data.get("subject", ""),
            "message": raw_data.get("text", raw_data.get("html", "")),
            "platform_lead_id": raw_data.get("message_id", ""),
            "platform_message_id": raw_data.get("message_id"),
            "metadata": {
                "subject": raw_data.get("subject"),
                "source": "email_parse",
            }
        }

    def _parse_form(self, raw_data):
        return {
            "customer_name": raw_data.get("name", ""),
            "customer_phone": raw_data.get("phone", ""),
            "customer_email": raw_data.get("email", ""),
            "customer_address": raw_data.get("address", ""),
            "service_type": raw_data.get("service_type", raw_data.get("subject", "")),
            "message": raw_data.get("message", raw_data.get("comments", "")),
            "platform_lead_id": raw_data.get("form_id", ""),
            "platform_message_id": None,
            "metadata": {
                "form_name": raw_data.get("form_name"),
                "source": "contact_form",
            }
        }

    def format_outbound(self, message, lead_context):
        return {
            "to": lead_context.get("customer_email"),
            "subject": "Re: Your Service Request",
            "body": message,
        }
