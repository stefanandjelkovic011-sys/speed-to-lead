"""
APScheduler configuration for drip campaigns and platform polling.
"""

import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from models import Business, Lead, get_db
import lead_processor

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(daemon=True)


def run_all_follow_ups():
    """Process drip queue for all businesses."""
    try:
        businesses = Business.list_all()
        total_sent = 0
        for biz in businesses:
            if not biz.get("ai_chatbot_enabled"):
                continue
            results = lead_processor.process_follow_ups(biz["id"])
            total_sent += len(results)
        if total_sent > 0:
            logger.info(f"Drip campaign: sent {total_sent} follow-ups")
    except Exception as e:
        logger.error(f"Error in run_all_follow_ups: {e}")


def poll_platforms():
    """Placeholder for platform polling connectors."""
    pass


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(run_all_follow_ups, 'interval', minutes=15, id='drip_follow_ups',
                      replace_existing=True, max_instances=1)
    scheduler.add_job(poll_platforms, 'interval', minutes=5, id='platform_polling',
                      replace_existing=True, max_instances=1)
    scheduler.start()
    logger.info("Scheduler started: drip campaigns (15min), platform polling (5min)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
