#!/usr/bin/env python3
import time
import random
import logging
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .base import BaseScraper
from parsers import parse_time, get_job_hours, job_is_excluded

logger = logging.getLogger("job_helper.scraper")

class JobmasterScraper(BaseScraper):
    """Jobmaster Jobs scraper."""

    def handle_popup_if_present(self):
        """Handle Jobmaster-specific popup (if any)."""
        pass

    def find_listings(self):
        """Find Jobmaster job listings."""
        return self.driver.find_elements(By.CLASS_NAME, self.config.selectors.listings_id)

    def extract_job(self, job_element):
        """Extract job data from Jobmaster listing element."""

        if 'mekudam' in job_element.get_attribute('outerHTML').lower():
            logger.info("Found 'mekudam' in job HTML - skipping promoted job")
            return None
        elif self.current_page > 1:
            pass
   
        logger.debug("No mekudam found - processing as regular job")

        title = None
        try:
            title = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.title_id}']").text.strip()
            logger.debug(f"Extracted title: {title}")
        except NoSuchElementException as e:
            logger.error(f"Failed to extract title: {e}")
            return None
        
        company = None
        try:
            company = job_element.find_element(By.CLASS_NAME, self.config.selectors.company_id).text.strip()
            logger.debug(f"Extracted company: {company}")
        except NoSuchElementException as e:
            logger.error(f"Failed to extract company: {e}")
            return None
        
        location = "Unknown Location"
        try:
            if self.config.selectors.location_elem_id:
                location = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.location_elem_id}']").text.strip()
                logger.debug(f"Extracted location: {location}")
        except NoSuchElementException as e:
            logger.warning(f"Failed to extract location: {e}")
        
        job_type_elem = "Unknown Type"
        try:
            if self.config.selectors.job_type_elem_id:
                job_type_elem = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.job_type_elem_id}']").text.strip()
                logger.debug(f"Extracted job type: {job_type_elem}")
        except NoSuchElementException as e:
            logger.warning(f"Failed to extract job type: {e}")

        link = ""
        link_element = None
        try:
            if self.config.selectors.link_id:
                link_element = job_element.find_element(By.CSS_SELECTOR, f"[class*='{self.config.selectors.link_id}'] a")
                link = link_element.get_attribute("href")
                logger.debug(f"Extracted link: {link}")
        except NoSuchElementException as e:
            logger.warning(f"Failed to extract link: {e}")
        
        job_body_upper = ""
        try:
            if link_element:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_element)
                time.sleep(random.uniform(0.3, 0.5))
                
                try:
                    link_element.click()
                    logger.debug("Clicked job link with regular click")
                except:
                    self.driver.execute_script("arguments[0].click();", link_element)
                    logger.debug("Clicked job link with JavaScript click")
                
                try:
                    panel_container = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.ID, "enterJob"))
                    )
                    logger.debug("Found enterJob panel container")
                    
                    time.sleep(random.uniform(0.5, 1.0))
                    
                    job_desc_element = panel_container.find_element(By.CLASS_NAME, "jobDescription")
                    job_body_upper = job_desc_element.text.strip()
                    
                    if job_body_upper:
                        logger.debug(f"✓ Extracted full description from side panel (length): {len(job_body_upper)}")
                    else:
                        logger.warning("Side panel loaded but description was empty")
                        raise NoSuchElementException("Empty description")
                    
                except Exception as panel_error:
                    logger.warning(f"Side panel didn't load properly: {panel_error}")
                    if self.config.selectors.job_body_upper_id:
                        try:
                            job_body_upper = job_element.find_element(By.CLASS_NAME, self.config.selectors.job_body_upper_id).text.strip()
                            logger.debug(f"Using short description fallback (length): {len(job_body_upper)}")
                        except:
                            logger.warning("Could not extract short description either")
            else:
                if self.config.selectors.job_body_upper_id:
                    logger.debug("No link element found, using short description from listing")
                    try:
                        job_body_upper = job_element.find_element(By.CLASS_NAME, self.config.selectors.job_body_upper_id).text.strip()
                    except:
                        logger.warning("Could not find short description")
                
        except Exception as e:
            logger.error(f"Error extracting description: {e}")
        
        time_posted = ""
        try:
            if self.config.selectors.time_posted_id:
                time_posted = job_element.find_element(By.CLASS_NAME, self.config.selectors.time_posted_id).text.strip()
                logger.debug(f"Extracted time posted: {time_posted}")
        except NoSuchElementException as e:
            logger.warning(f"Failed to extract time posted: {e}")

        # Time logic
        try:
            if time_posted:
                job_hour = get_job_hours(time_posted)
                if hasattr(self, 'selected_hours') and job_hour > self.selected_hours:
                    logger.info(f"Reached postings from {time_posted}. Stopping.")
                    self.current_hour = job_hour
                    return self.current_hour
        except Exception as e:
            logger.warning(f"Error checking job hours: {e}")

        # Exclude jobs
        try:
            if job_is_excluded(title, company):
                logger.info(f"Excluded: {title}, Posted: {time_posted}")
                return None
        except Exception as e:
            logger.warning(f"Error checking exclusions: {e}")

        # Parse time
        time_parsed = ""
        try:
            if time_posted:
                time_parsed = parse_time(time_posted)
        except Exception as e:
            logger.warning(f"Error parsing time: {e}")

        # Validate critical fields
        if not title or not company:
            logger.warning(f"Skipping job due to missing critical data: title={title}, company={company}")
            return None

        job_data = {
            "Title": title,
            "Company": company,
            "Time": time_parsed,
            "Link": link or "",
            "Location": location or "Unknown Location",
            "Type": job_type_elem or "Unknown Type",
            "Description": job_body_upper or ""
        }
        
        logger.info(f"Successfully extracted job: {title} at {company}")
        return job_data

    def go_to_next_page(self):
        """Handle Jobmaster pagination."""
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