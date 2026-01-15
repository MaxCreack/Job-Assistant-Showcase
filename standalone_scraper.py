#!/usr/bin/env python3
import atexit
import signal
import logging
import sys
import os
from pathlib import Path

import driver as driver_module
from lifecycle import (
    signal_handler,
    update_status,
    cleanup_files,
    CONFIG,  
)
from browser_utils import load_selected_hours
from scrapers import get_scraper 

logger = logging.getLogger("job_helper.scraper")
logger.setLevel(logging.DEBUG)
log_dir = Path("logs")

if not logger.handlers:
    log_file = log_dir / "job_helper_AJscraper.log"
    fh = logging.FileHandler(log_file, encoding='utf-8')
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)

import lifecycle

_driver = None

def main():
    global _driver

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(driver_module.cleanup_driver)
    atexit.register(lambda: update_status("stopped", "Process exited"))

    cleanup_files()
    update_status("starting", "Initializing Chrome driver...")

    try:
        logger.info("Starting standalone scraper process...")
        logger.info(f"PID: {os.getpid()}")
        logger.info(f"Site: {lifecycle.SITE}")

        _driver = driver_module.setup_stealth_headless_driver()
        update_status("running", "Chrome driver started, beginning scrape...")
        logger.info("Chrome driver started successfully")

        scraper = get_scraper(lifecycle.SITE, _driver, CONFIG, lifecycle)
        selected_hours = load_selected_hours()
        scraper.selected_hours = selected_hours

        scraper.run(selected_hours)

    except Exception as e:
        update_status("error", f"Scraper error: {e}")
        logger.error(f"Scraper error: {e}")
    finally:
        logger.info("Scraper cleanup starting...")
        driver_module.cleanup_driver()
        logger.info("Standalone scraper process exiting")

if __name__ == "__main__":
    main()
