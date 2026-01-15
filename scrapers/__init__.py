#!/usr/bin/env python3
"""Scraper module for job sites."""

from .alljobs import AllJobsScraper
from .jobmaster import JobmasterScraper

__all__ = ["AllJobsScraper", "JobmasterScraper", "get_scraper", "list_available_scrapers"]

def get_scraper(site: str, driver, config, lifecycle):
    """Get scraper for a site."""
    scrapers = {
        "alljobs": AllJobsScraper,
        "jobmaster": JobmasterScraper,
    }
    
    scraper_class = scrapers.get(site)
    if not scraper_class:
        raise ValueError(f"Unknown site: {site}. Available: {list(scrapers.keys())}")
    
    return scraper_class(driver, config, lifecycle)

def list_available_scrapers():
    """Return list of all available scraper names."""
    return sorted(["alljobs", "jobmaster"])