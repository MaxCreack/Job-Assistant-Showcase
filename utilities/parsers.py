#!/usr/bin/env python3
import logging
from datetime import datetime, timedelta
from lifecycle import load_excluded_words

logger = logging.getLogger("job_helper.scraper")

_EXCLUDE_TITLES, _EXCLUDE_COMPANIES = load_excluded_words()

def parse_time(time_str):
    """Parse Hebrew time string to ISO format timestamp."""
    hours = 0
    if "שעה" in time_str or "שעות" in time_str:
        try:
            hours = int(time_str.split()[1])
        except Exception:
            hours = 0

    timestamp = datetime.now() - timedelta(hours=hours)
    return timestamp.strftime('%Y-%m-%d %H:%M:%S')

def get_job_hours(time_str):
    """Extract hours from Hebrew time string; return 999 for days."""
    if "שעה" in time_str or "שעות" in time_str:
        try:
            num = int(time_str.split()[1])
            return num
        except Exception:
            return 0
    if "יום" in time_str or "ימים" in time_str:
        return 999
    return 0

def job_is_excluded(title, company):
    """Check if job matches any exclusion keywords."""
    title_lower = title.lower()
    company_lower = company.lower()

    # Special case: allow English jobs
    if title_lower == "אנגלית":
        return False

    for keyword in _EXCLUDE_TITLES:
        if keyword in title_lower:
            logger.info(f"Excluded due to title keyword: {keyword}")
            return True

    for keyword in _EXCLUDE_COMPANIES:
        if keyword in company_lower:
            logger.info(f"Excluded due to company keyword: {keyword}")
            return True

    return False