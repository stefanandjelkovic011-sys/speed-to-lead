"""
Duke Energy platform connector.
Email ingestion for utility rebate referrals.
"""

from .base import PlatformConnector


class DukeEnergyConnector(PlatformConnector):
    platform_name = "duke_energy"

    def parse_inbound(self, raw_data):
        """Parse Duke Energy rebate referral data (typically via email ingestion)."""
        return {
            "customer_name": raw_data.get("customer_name", raw_data.get("homeowner_name", "")),
            "customer_phone": raw_data.get("phone", raw_data.get("customer_phone", "")),
            "customer_email": raw_data.get("email", raw_data.get("customer_email", "")),
            "customer_address": raw_data.get("address", raw_data.get("service_address", "")),
            "service_type": raw_data.get("program_type", raw_data.get("rebate_type", "Energy Efficiency")),
            "message": raw_data.get("message", raw_data.get("referral_details", "New Duke Energy rebate referral")),
            "platform_lead_id": raw_data.get("referral_id", raw_data.get("case_number", "")),
            "platform_message_id": raw_data.get("email_id"),
            "metadata": {
                "program_name": raw_data.get("program_name"),
                "rebate_amount": raw_data.get("rebate_amount"),
                "account_number": raw_data.get("account_number"),
                "utility_provider": "Duke Energy",
            }
        }

    def format_outbound(self, message, lead_context):
        return {
            "to": lead_context.get("customer_email"),
            "subject": "Re: Duke Energy Rebate Program",
            "body": message,
        }
