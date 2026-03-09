"""
Base platform connector class.
All platform connectors inherit from this and implement the abstract methods.
"""

from abc import ABC, abstractmethod


class PlatformConnector(ABC):
    """Base class for all platform connectors."""

    platform_name = "unknown"

    @abstractmethod
    def parse_inbound(self, raw_data):
        """Parse raw inbound data into a standardized lead dict.

        Returns:
            dict with keys: customer_name, customer_phone, customer_email,
                           customer_address, service_type, message,
                           platform_lead_id, platform_message_id, metadata
        """
        pass

    @abstractmethod
    def format_outbound(self, message, lead_context):
        """Format an outbound message for this platform.

        Returns:
            dict with platform-specific format for sending
        """
        pass

    def validate_webhook(self, request):
        """Validate that an incoming webhook is authentic.

        Returns:
            bool indicating if the webhook is valid
        """
        return True

    def extract_platform_lead_id(self, raw_data):
        """Extract the platform-specific lead ID from raw data."""
        return None
