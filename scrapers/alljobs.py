#!/usr/bin/env python3
import time
import random
import logging
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from .base import BaseScraper
from parsers import parse_time, get_job_hours, job_is_excluded
import driver as driver_module

logger = logging.getLogger("job_helper.scraper")

class AllJobsScraper(BaseScraper):
    """AllJobs.co.il scraper."""

    def handle_popup_if_present(self):
        """Handle AllJobs-specific popup."""
        if driver_module.is_element_present(self.driver, By.ID, self.config.selectors.popup_id):
            popup = self.driver.find_element(By.ID, self.config.selectors.popup_id)
            style = popup.get_attribute("style")
            if "display: none" not in style:
                logger.info("Popup detected.")
                try:
                    close_button = self.driver.find_element(By.ID, self.config.selectors.close_button_id)
                    self.driver.execute_script("arguments[0].click();", close_button)
                    logger.info("Popup closed.")
                    time.sleep(random.uniform(1, 2))
                except NoSuchElementException:
                    logger.warning("Popup found, but no close button. Skipping...")

    def find_listings(self):
        """Find AllJobs job listings."""
        return self.driver.find_elements(By.CLASS_NAME, self.config.selectors.listings_id)

    def extract_job(self, job_element):
        """Extract job data from AllJobs listing element."""
        try:
            title = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.title_id}'] a.N").text.strip()
            company = job_element.find_element(By.CLASS_NAME, self.config.selectors.company_id).text.strip()
            location_elem = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.location_elem_id}']")
            location = self.driver.execute_script(
                "return arguments[0].childNodes[1].textContent.trim();",
                location_elem
            )
            job_type_elem = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.job_type_elem_id}']")
            job_type = self.driver.execute_script(
                "return arguments[0].childNodes[1].textContent.trim();",
                job_type_elem
            )
            job_body_upper = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.job_body_upper_id}']").text.strip()
            job_body_lower_elem = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.job_body_lower_elem_id}']")
            job_body_lower = self.driver.execute_script(
                "return arguments[0].textContent;",
                job_body_lower_elem
            )
            time_posted = job_element.find_element(By.CLASS_NAME, self.config.selectors.time_posted_id).text.strip()
            link = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.link_id}'] a.N").get_attribute("href")

            # Time logic
            job_hour = get_job_hours(time_posted)
            if hasattr(self, 'selected_hours') and job_hour > self.selected_hours:
                logger.info(f"Reached postings from {time_posted} ({job_hour}h ago, limit: {self.selected_hours}h). Stopping.")
                self.current_hour = job_hour 
                return self.current_hour

            # Exclude jobs
            if job_is_excluded(title, company):
                logger.info(f"Excluded: {title}, Posted: {time_posted}")
                return None

            # Parse time
            time_parsed = parse_time(time_posted)

            # Validate critical fields
            if not title or not company:
                logger.warning("Skipping job due to missing critical data")
                return None

            job_data = {
                "Title": title,
                "Company": company,
                "Time": time_parsed,
                "Link": link or "",
                "Location": location or "Unknown Location",
                "Type": job_type or "Unknown Type",
                "Description": (job_body_upper + "\n" + job_body_lower).strip()
            }

            return job_data

        except NoSuchElementException as e:
            logger.error(f"Skipped job due to missing element: {e}")
            return None
        except Exception as e:
            logger.error(f"Error extracting job: {e}")
            return None

    def go_to_next_page(self):
        """Handle AllJobs pagination."""
        try:
            pagenext = self.driver.find_element(By.CLASS_NAME, self.config.selectors.pagenext_id)
            time.sleep(random.uniform(3, 6))
            click_next = pagenext.find_element(By.CLASS_NAME, self.config.selectors.click_next_id)
            time.sleep(random.uniform(0.2, 0.5))
            self.driver.execute_script("arguments[0].scrollIntoView(true);", click_next)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", click_next)
            return True
        except NoSuchElementException:
            logger.info("No next page button found")
            return False