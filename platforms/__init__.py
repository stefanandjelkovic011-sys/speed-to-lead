"""
Platform connectors for Speed-to-Lead.
Each connector handles parsing inbound messages and formatting outbound responses
for a specific lead source platform.
"""

from .base import PlatformConnector
from .google_lsa import GoogleLSAConnector
from .yelp import YelpConnector
from .thumbtack import ThumbtackConnector
from .angi import AngiConnector
from .chat_widget import ChatWidgetConnector
from .contact_form import ContactFormConnector
from .duke_energy import DukeEnergyConnector

CONNECTORS = {
    "google_lsa": GoogleLSAConnector,
    "yelp": YelpConnector,
    "thumbtack": ThumbtackConnector,
    "angi": AngiConnector,
    "chat_widget": ChatWidgetConnector,
    "contact_form": ContactFormConnector,
    "duke_energy": DukeEnergyConnector,
}


def get_connector(platform):
    cls = CONNECTORS.get(platform)
    if cls:
        return cls()
    return None
