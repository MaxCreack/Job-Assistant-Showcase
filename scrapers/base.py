#!/usr/bin/env python3
import time
import random
import logging
from abc import ABC, abstractmethod
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger("job_helper.scraper")

class BaseScraper(ABC):
    """
    Generic scraper orchestrator. Subclasses implement site-specific extraction.
    """

    def __init__(self, driver, config, lifecycle_module):
        """
        Args:
            driver: Selenium WebDriver instance
            config: ScraperConfig object with selectors and URLs
            lifecycle_module: Module with update_status, should_stop, write_job_data, etc.
        """
        self.driver = driver
        self.config = config
        self.lifecycle = lifecycle_module
        self.jobs_scraped = 0
        self.current_hour = 0
        self.time_limit_reached = False

    @abstractmethod
    def extract_job(self, job_element):
        """
        Extract job data from a job listing element.
        Subclasses must implement this.
        Returns dict or None to skip job.
        """
        pass

    @abstractmethod
    def find_listings(self):
        """Find job listing elements. Default uses listings_id selector."""
        return self.driver.find_elements(By.CLASS_NAME, self.config.selectors.listings_id)

    @abstractmethod
    def handle_popup_if_present(self):
        """Handle site-specific popup. Override in subclass if needed."""
        pass

    @abstractmethod
    def go_to_next_page(self):
        """Handle pagination. Return True if next page exists, False otherwise."""
        pass

    def run(self, selected_hours):
        """Main scraping loop."""
        self.current_page = 1 
        self.jobs_scraped = 0
        self.current_hour = 0

        while not self.lifecycle.should_stop():
            url = self.config.base_url.format(page=self.current_page) 
            self.lifecycle.update_status("running", f"Scraping page {self.current_page}...", self.jobs_scraped, self.current_page)  
            logger.info(f"Scraping page {self.current_page}...") 
            try:
                self.driver.get(url)
                logger.info("Loading URL")
            except Exception as e:
                self.lifecycle.update_status("error", f"Error loading page: {e}")
                logger.error(f"Error loading page: {e}")
                break

            if self.lifecycle.should_stop():
                self.driver.quit()
                break

            # Wait for job listings
            try:
                timeout = 15 if self.current_page >= 10 else 10 
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, self.config.selectors.job_content_id))
                )
                logger.info("Waiting for job listings")
                time.sleep(random.uniform(1, 3))
            except TimeoutException:
                self.driver.save_screenshot("debug_screenshot2.png")
                self.lifecycle.update_status("error", "Timed out waiting for job listings")
                logger.error("Timed out waiting for job listings.")
                break

            # Anti-bot measures
            time.sleep(random.uniform(2, 4))

            if self.lifecycle.should_stop():
                self.driver.quit()
                break

            # Human-like scrolling
            from driver import human_scroll
            human_scroll(self.driver)
            time.sleep(random.uniform(2, 4))

            # Get listings
            listings = self.find_listings()
            if not listings:
                #self.driver.save_screenshot("debug_screenshot3.png")
                self.lifecycle.update_status("completed", "No more job listings found")
                logger.warning("No job listings found.")
                break

            # Handle popup
            try:
                self.handle_popup_if_present()
            except Exception as e:
                logger.error(f"Error handling popup: {e}")

            # Process listings
            for i, job in enumerate(listings):
                if self.lifecycle.should_stop():
                    self.driver.quit()
                    self.lifecycle.update_status("stopped", "Stop flag detected")
                    break

                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(self.driver)
                    actions.move_to_element(job).pause(random.uniform(0.3, 0.7)).perform()

                    job_data = self.extract_job(job)
                    if not job_data:
                        continue
                    elif self.current_hour > 0:
                        self.driver.quit()
                        logger.info("Time limit reached based on job posting time. Ending scrape.")
                        break

                    self.lifecycle.write_job_data(job_data)
                    self.jobs_scraped += 1
                    logger.info(f"SCRAPED: {job_data.get('Title', 'Unknown')} at {job_data.get('Company', 'Unknown')}")

                    if self.lifecycle.should_stop():
                        self.driver.quit()
                        break

                except NoSuchElementException as e:
                    logger.error(f"Skipped job due to missing element: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error processing job: {e}")
                    continue

            if self.lifecycle.should_stop():
                self.driver.quit()
                break

            if self.current_hour > 0: 
                logger.info("Exiting main loop due to time limit")
                break


            # Pagination
            try:
                if not self.go_to_next_page():
                    self.lifecycle.update_status("completed", f"No next page. Scraped {self.jobs_scraped} jobs.")
                    logger.info("No next page found. Ending scrape.")
                    break
                self.current_page += 1 
                time.sleep(random.uniform(1.5, 3.5))
            except Exception as e:
                self.lifecycle.update_status("error", f"Error with pagination: {e}")
                logger.error(f"Error with pagination: {e}")
                break

        if not self.lifecycle.should_stop():
            self.lifecycle.update_status("completed", f"Scraping completed. Total jobs scraped: {self.jobs_scraped}")
        else:
            self.lifecycle.update_status("stopped", f"Scraping stopped by user. Jobs scraped: {self.jobs_scraped}")