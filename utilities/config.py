#!/usr/bin/env python3
from dataclasses import dataclass, field
from typing import Optional
import json
import sys
from pathlib import Path

@dataclass
class Selectors:
    popup_id: Optional[str] = None
    close_button_id: Optional[str] = None
    job_content_id: Optional[str] = None
    listings_id: Optional[str] = None
    title_id: Optional[str] = None
    company_id: Optional[str] = None
    location_elem_id: Optional[str] = None
    job_type_elem_id: Optional[str] = None
    job_body_upper_id: Optional[str] = None
    job_body_lower_elem_id: Optional[str] = None
    time_posted_id: Optional[str] = None
    link_id: Optional[str] = None
    pagenext_id: Optional[str] = None
    click_next_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Selectors":
        """Create Selectors from dictionary (from JSON)."""
        return cls(
            popup_id=data.get("popup_id"),
            close_button_id=data.get("close_button_id"),
            job_content_id=data.get("job_content_id"),
            listings_id=data.get("listings_id"),
            title_id=data.get("title_id"),
            company_id=data.get("company_id"),
            location_elem_id=data.get("location_elem_id"),
            job_type_elem_id=data.get("job_type_elem_id"),
            job_body_upper_id=data.get("job_body_upper_id"),
            job_body_lower_elem_id=data.get("job_body_lower_elem_id"),
            time_posted_id=data.get("time_posted_id"),
            link_id=data.get("link_id"),
            pagenext_id=data.get("pagenext_id"),
            click_next_id=data.get("click_next_id"),
        )

@dataclass
class ScraperConfig:
    base_url: Optional[str] = None
    selectors: Selectors = field(default_factory=Selectors)
    status_file: str = "scraper_status.json"
    jobs_file: str = "scraped_jobs.jsonl"
    stop_file: str = "scraper_stop.flag"
    excluded_words_file: str = "excludedwords.json"

    @classmethod
    def from_json(cls, site: str = "alljobs") -> "ScraperConfig":
        """Load config from JSON file based on site name."""
        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent
        
        config_file = base_path / "scrapers" / "configs" / f"{site}.json"
        
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return cls(
            base_url=data.get("base_url"),
            selectors=Selectors.from_dict(data.get("selectors", {})),
        )