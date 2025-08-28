#!/usr/bin/env python3
"""
Standalone scraper process that runs completely isolated from the main GUI.
Communicates via file-based system.
"""

import json
import os
import sys
import time
import tempfile
import atexit
import signal
import subprocess
import psutil
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import random
from datetime import datetime, timedelta
from excludedwords import KEYWORDS_TO_EXCLUDE

# Constants
BASE_URL = "INSERT_GENERIC_LINK"
STATUS_FILE = "scraper_status.json"
JOBS_FILE = "scraped_jobs.jsonl" 
STOP_FILE = "scraper_stop.flag"

# Global driver reference for cleanup
_driver = None

def cleanup_driver():
    """Force cleanup of Chrome driver and associated processes"""
    global _driver
    if _driver:
        try:
            print("Force closing Chrome driver...")
            _driver.quit()
            _driver = None
            print("Chrome driver closed successfully")
        except Exception as e:
            print(f"Error during driver cleanup: {e}")
        finally:
            _driver = None
    
    # Kill any remaining Chrome processes
    try:
        print("Cleaning up remaining Chrome processes...")
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and ('chrome' in proc.info['name'].lower() or 'chromedriver' in proc.info['name'].lower()):
                    cmdline = proc.info['cmdline'] or []
                    if any('automation' in str(arg).lower() or 'test-type' in str(arg).lower() for arg in cmdline):
                        print(f"Killing lingering Chrome process: {proc.info['pid']}")
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        print(f"Error during process cleanup: {e}")
    
    # Force DWM memory cleanup
    try:
        if os.name == 'nt':
            print("Attempting DWM memory cleanup...")
            subprocess.run(['taskkill', '/f', '/im', 'dwm.exe'], 
                         capture_output=True, check=False)
            time.sleep(0.5) 
    except Exception as e:
        print(f"Error during DWM cleanup: {e}")

def signal_handler(signum, frame):
    """Handle termination signals"""
    print(f"Received signal {signum}, cleaning up...")
    update_status("stopped", "Process terminated by signal")
    cleanup_driver()
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
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error updating status file: {e}")

def should_stop():
    """Check if stop flag file exists"""
    return os.path.exists(STOP_FILE)

def write_job_data(job_data):
    """Append job data to JSONL file"""
    try:
        with open(JOBS_FILE, 'a', encoding='utf-8') as f:
            json.dump(job_data, f, ensure_ascii=False)
            f.write('\n')
    except Exception as e:
        print(f"Error writing job data: {e}")

def handle_popup_if_present(driver):
    try:
        if is_element_present(driver, By.ID, "GENERIC_DOM_ELELEMT_POPUP"):
            popup = driver.find_element(By.ID, "GENERIC_DOM_ELELEMT_POPUP")
            style = popup.get_attribute("style")
            if "display: none" not in style:
                print("Popup detected.")
                try:
                    close_button = driver.find_element(By.ID, "GENERIC_DOM_ELELEMT_POPUP")
                    driver.execute_script("arguments[0].click();", close_button)
                    print("Popup closed.")
                    time.sleep(random.uniform(1, 2))
                except NoSuchElementException:
                    print("Popup found, but no close button. Skipping...")
    except Exception as e:
        print(f"Unexpected error during popup handling: {e}")

def is_element_present(driver, by, value):
    try:
        driver.find_element(by, value)
        return True
    except NoSuchElementException:
        return False

def parse_time(time_str):
    hours = 0
    if "שעה" in time_str or "שעות" in time_str:
        try:
            hours = int(time_str.split()[1])
        except:
            hours = 0
    
    timestamp = datetime.now() - timedelta(hours=hours)
    return timestamp.strftime('%Y-%m-%d %H:%M')

def get_job_hours(time_str):
    if "שעה" in time_str or "שעות" in time_str:
        try:
            num = int(time_str.split()[1])
            return num
        except:
            return 0
    return 0

def job_is_excluded(title, company):
    title_lower = title.lower()
    company_lower = company.lower()
    if title_lower == "אנגלית":
        return False

    for keyword in KEYWORDS_TO_EXCLUDE:
        if keyword in title_lower or keyword in company_lower:
            print(f"Excluded due to keyword: {keyword}")
            return True
    return False

def human_scroll(driver):
    scroll_script = "window.scrollBy(0, arguments[0]);"
    for _ in range(random.randint(2, 5)):
        driver.execute_script(scroll_script, random.randint(100, 400))
        time.sleep(random.uniform(0.5, 1.5))

def main():
    global _driver
    
    # Register signal handlers and cleanup
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(cleanup_driver)
    atexit.register(lambda: update_status("stopped", "Process exited"))
    
    # Clean up any existing files
    for file in [STATUS_FILE, JOBS_FILE]:
        if os.path.exists(file):
            try:
                os.remove(file)
            except:
                pass
    
    update_status("starting", "Initializing Chrome driver...")
    
    try:
        print("Starting standalone scraper process...")
        print(f"PID: {os.getpid()}")
        
        # Initialize Chrome driver with isolation
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-gpu-sandbox")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--memory-pressure-off")
        options.add_argument("--max_old_space_size=4096")
        #options.add_argument("--headless=new")
        
        # Use completely isolated temp directory
        temp_dir = tempfile.mkdtemp(prefix=f"scraper_{os.getpid()}_")
        options.add_argument(f"--user-data-dir={temp_dir}")
        
        _driver = uc.Chrome(
            options=options,
            driver_executable_path=r"INSERT_EXECUTABLE_PATH"  # Adjust path as needed
        )
        driver = _driver
        
        update_status("running", "Chrome driver started, beginning scrape...")
        print("Chrome driver started successfully")
        
        # Initialize scraping variables
        actions = ActionChains(driver)
        page = 1
        jobs_scraped = 0
        current_hour = 0
        
        # Main scraping loop
        while not should_stop():
            url = BASE_URL.format(page=page)
            update_status("running", f"Scraping page {page}...", jobs_scraped, page)
            print(f"Scraping page {page}...")
            
            try:
                driver.get(url)
                print("Loading URL")
            except Exception as e:
                update_status("error", f"Error loading page: {e}")
                print(f"Error loading page: {e}")
                break
                
            if should_stop():
                break
                
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, "GENERIC_DOM_LINK_JOB_PAGE"))
                )
                print("Waiting for job content top")
                driver.save_screenshot("debug_screenshot1.png") # Debug screenshot
                time.sleep(random.uniform(3, 5))
                human_scroll(driver) # Initial scroll    
            except TimeoutException:
                driver.save_screenshot("debug_screenshot2.png") # Debug screenshot
                update_status("error", "Timed out waiting for job listings")
                print("Timed out waiting for job listings.")
                break
                
            # Anti-bot measures
            time.sleep(random.uniform(2, 4))
            
            if should_stop():
                break
                
            human_scroll(driver) # Additional scroll    
            time.sleep(random.uniform(1, 2))
            
            listings = driver.find_elements(By.CLASS_NAME, "GENERIC_DOM_ELEMENT_JOB_POSTING")
            if not listings:
                driver.save_screenshot("debug_screenshot3.png") # Debug screenshot
                update_status("completed", "No more job listings found")
                print("No job listings found.")
                break
                
            handle_popup_if_present(driver) # Handle any popups
            
            # Process job listings
            for i, job in enumerate(listings):
                if should_stop():
                    update_status("stopped", "Stop flag detected") 
                    break
                    
                try:
                    actions.move_to_element(job).pause(random.uniform(0.3, 0.7)).perform()       
                    
                    # Extract job details
                    title = job.find_element(By.CSS_SELECTOR, "[class*='GENERIC_DOM_ELEMENT'] a.N").text.strip()
                    company = job.find_element(By.CLASS_NAME, "GENERIC_DOM_ELEMENT").text.strip()
                    location_elem = job.find_element(By.CSS_SELECTOR, "[class*='GENERIC_DOM_ELEMENT']")
                    location = driver.execute_script(
                        "return arguments[0].childNodes[1].textContent.trim();",
                        location_elem
                    )
                    job_type_elem = job.find_element(By.CSS_SELECTOR, "[class*='GENERIC_DOM_ELEMENT']")
                    job_type = driver.execute_script(
                        "return arguments[0].childNodes[1].textContent.trim();",
                        job_type_elem
                    )
                    job_body_upper = job.find_element(By.CSS_SELECTOR, "[class*='GENERIC_DOM_ELEMENT']").text.strip()
                    job_body_lower_elem = job.find_element(By.CSS_SELECTOR, "[class*='GENERIC_DOM_ELEMENT']")
                    job_body_lower = driver.execute_script(
                        "return arguments[0].textContent;",
                        job_body_lower_elem
                    )
                    time_posted = job.find_element(By.CLASS_NAME, "GENERIC_DOM_ELEMENT").text.strip()
                    link = job.find_element(By.CSS_SELECTOR, "[class*='GENERIC_DOM_ELEMENT'] a.N").get_attribute("href")
                    
                    # Time logic
                    job_hour = get_job_hours(time_posted)
                    if job_hour >= 10:
                        update_status("completed", f"Reached postings from {time_posted}. Stopping.")
                        print(f"Reached postings from {time_posted}. Stopping.")
                        return
                        
                    if job_hour > current_hour:
                        current_hour = job_hour
                        print(f"Now processing jobs from {current_hour} hours ago")
                    
                    # Exclude jobs based on keywords
                    if job_is_excluded(title, company):
                        print(f"Excluded: {title}, Posted: {time_posted}.")
                        continue
                        
                    # Prepare job data
                    time_parsed = parse_time(time_posted)
                    job_data = {
                        "Title": title.strip() if title else "Unknown Title",
                        "Company": company.strip() if company else "Unknown Company", 
                        "Time": time_parsed,
                        "Link": link.strip() if link else "",
                        "Location": location.strip() if location else "Unknown Location",
                        "Type": job_type.strip() if job_type else "Unknown Type",
                        "Description Upper": job_body_upper.strip() if job_body_upper else "",
                        "Description Lower": job_body_lower.strip() if job_body_lower else ""
                    }
                    
                    # Validate critical fields
                    if not job_data["Title"] or not job_data["Company"]:
                        print(f"Skipping job due to missing critical data")
                        continue
                        
                    # Write job data to file
                    write_job_data(job_data)
                    jobs_scraped += 1
                    
                    print(f"SCRAPED: {title} at {company} - Posted: {time_posted}")
                    
                    if should_stop():
                        break
                        
                except NoSuchElementException as e:
                    print(f"Skipped job due to missing element: {e}")
                    continue
                except Exception as e:
                    print(f"Unexpected error processing job: {e}")
                    continue
            
            if should_stop():
                break
                
            # Pagination
            try:
                pagenext = driver.find_element(By.CLASS_NAME, "GENERIC_DOM_ELEMENT")
                time.sleep(random.uniform(3, 6))
                
                if should_stop():
                    break
                    
                click_next = pagenext.find_element(By.CLASS_NAME, "GENERIC_DOM_ELEMENT")
                time.sleep(random.uniform(0.2, 0.5))
                driver.execute_script("arguments[0].scrollIntoView(true);", click_next)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", click_next)
                page += 1
                
            except NoSuchElementException:
                update_status("completed", f"No next page button found. Scraped {jobs_scraped} jobs.")
                print("No next page button found. Ending pagination.")
                break
            except Exception as e:
                update_status("error", f"Error with pagination: {e}")
                print(f"Error with pagination: {e}")
                break
        
        if not should_stop():
            update_status("completed", f"Scraping completed. Total jobs scraped: {jobs_scraped}")
        else:
            update_status("stopped", f"Scraping stopped by user. Jobs scraped: {jobs_scraped}")
            
    except Exception as e:
        update_status("error", f"Scraper error: {e}")
        print(f"Scraper error: {e}")
    finally:
        print("Scraper cleanup starting...")
        cleanup_driver()
        print("Standalone scraper process exiting")

if __name__ == "__main__":
    main()
