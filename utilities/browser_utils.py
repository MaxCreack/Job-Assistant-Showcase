#!/usr/bin/env python3
import json
import logging

logger = logging.getLogger("job_helper.scraper")

def load_selected_hours():
    """Load user-selected hours from scraper_config.json."""
    try:
        with open("scraper_config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            return int(config.get("hours"))
    except FileNotFoundError:
        logger.warning("scraper_config.json not found, using default hours")
    except Exception as e:
        logger.error(f"Error loading selected_hours: {e}")

    return None