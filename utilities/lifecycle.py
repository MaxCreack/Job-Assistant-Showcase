#!/usr/bin/env python3
import json
import os
import logging
import signal
import sys
from datetime import datetime
from config import ScraperConfig
import driver as driver_module

logger = logging.getLogger("job_helper.scraper")

# Load config dynamically based on SCRAPER_SITE env var
SITE = os.getenv("SCRAPER_SITE", "alljobs")
CONFIG = ScraperConfig.from_json(SITE)

def signal_handler(signum, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {signum}, cleaning up...")
    update_status("stopped", "Process terminated by signal")
    driver_module.cleanup_driver()
    sys.exit(0)

def update_status(status, message="", jobs_scraped=0, current_page=1):
    """Update status file for GUI communication"""
    status_data = {
        "status": status,
        "message": message,
        "jobs_scraped": jobs_scraped,
        "current_page": current_page,
        "timestamp": datetime.now().isoformat(),
        "pid": os.getpid()
    }

    try:
        with open(CONFIG.status_file, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error updating status file: {e}")

def should_stop():
    """Check if stop flag file exists"""
    return os.path.exists(CONFIG.stop_file)

def write_job_data(job_data):
    """Append job data to JSONL file"""
    try:
        with open(CONFIG.jobs_file, 'a', encoding='utf-8') as f:
            json.dump(job_data, f, ensure_ascii=False)
            f.write('\n')
    except Exception as e:
        logger.error(f"Error writing job data: {e}")

def load_excluded_words():
    """Load excluded titles and companies from the JSON file."""
    if not os.path.exists(CONFIG.excluded_words_file):
        logger.warning("Scraper: Excluded words file not found, using defaults.")
        return [], []

    with open(CONFIG.excluded_words_file, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            titles = data.get("RAW_KEYWORDS_TO_EXCLUDE_TITLES", [])
            companies = data.get("RAW_KEYWORDS_TO_EXCLUDE_COMPANIES", [])
        except json.JSONDecodeError:
            logger.warning("Scraper: Error decoding excluded words file.")
            return [], []

    titles = [t.lower() for t in titles]
    companies = [c.lower() for c in companies]

    return titles, companies

def cleanup_files():
    """Remove scraper output files at startup"""
    for file in [CONFIG.status_file, CONFIG.jobs_file]:
        if os.path.exists(file):
            try:
                os.remove(file)
            except Exception as e:
                logger.warning(f"Could not remove {file}: {e}")