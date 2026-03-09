"""
Error handling and logging for Speed-to-Lead system.
"""

import logging
import os
import traceback
from functools import wraps
from flask import jsonify

LOG_DIR = os.path.join(os.path.dirname(__file__), "data")
LOG_PATH = os.path.join(LOG_DIR, "speed_to_lead.log")


def setup_logging(app):
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = logging.FileHandler(LOG_PATH)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    ))
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    logging.getLogger('apscheduler').addHandler(file_handler)


def api_error_handler(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except KeyError as e:
            return jsonify({"success": False, "error": f"Missing required field: {e}"}), 400
        except ValueError as e:
            return jsonify({"success": False, "error": f"Invalid value: {e}"}), 400
        except Exception as e:
            logging.getLogger(__name__).error(f"API error in {f.__name__}: {traceback.format_exc()}")
            return jsonify({"success": False, "error": "Internal server error"}), 500
    return decorated
