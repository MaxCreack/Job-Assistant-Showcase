#!/usr/bin/env python3

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
from dotenv import load_dotenv
load_dotenv()

# Constants
BASE_URL = os.getenv("base_url")
popup_id = os.getenv("popup")
close_button_id = os.getenv("close_button")
driver_executable_path_id = os.getenv("driver_executable_path")
job_content_id = os.getenv("job_content")
listings_id = os.getenv("listings")
title_id = os.getenv("title")
company_id = os.getenv("company")
location_elem_id = os.getenv("location_elem")
job_type_elem_id = os.getenv("job_type_elem")
job_body_upper_id = os.getenv("job_body_upper")
job_body_lower_elem_id = os.getenv("job_body_lower_elem")
time_posted_id = os.getenv("time_posted")
link_id = os.getenv("link")
pagenext_id = os.getenv("pagenext")
click_next_id = os.getenv("click_next")

# File paths
STATUS_FILE = "scraper_status.json"
JOBS_FILE = "scraped_jobs.jsonl" 
STOP_FILE = "scraper_stop.flag"
EXCLUDED_WORDS_FILE ="excludedwords.json"


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

def load_excluded_words():
    """Load excluded titles and companies from the JSON file."""
    if not os.path.exists(EXCLUDED_WORDS_FILE):
        print("Scraper: Excluded words file not found, using defaults.")
        return [], []

    with open(EXCLUDED_WORDS_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            titles = data.get("RAW_KEYWORDS_TO_EXCLUDE_TITLES", [])
            companies = data.get("RAW_KEYWORDS_TO_EXCLUDE_COMPANIES", [])
        except json.JSONDecodeError:
            print("Scraper: Error decoding excluded words file.")
            return [], []

    titles = [t.lower() for t in titles]
    companies = [c.lower() for c in companies]         

    return titles, companies

def handle_popup_if_present(driver):
    try:
        if is_element_present(driver, By.ID, popup_id):
            popup = driver.find_element(By.ID, popup_id)
            style = popup.get_attribute("style")
            if "display: none" not in style:
                print("Popup detected.")
                try:
                    close_button = driver.find_element(By.ID, close_button_id)
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
    return timestamp.strftime('%Y-%m-%d %H:%M:%S')

def get_job_hours(time_str):
    if "שעה" in time_str or "שעות" in time_str:
        try:
            num = int(time_str.split()[1])
            return num
        except:
            return 0
    return 0

def job_is_excluded(titles, companies):
    title_lower = titles.lower()
    company_lower = companies.lower()

    if title_lower == "אנגלית":
        return False

    for keyword in EXCLUDE_TITLES:
        if keyword in title_lower:
            print(f"Excluded due to title keyword: {keyword}")
            return True

    for keyword in EXCLUDE_COMPANIES:
        if keyword in company_lower:
            print(f"Excluded due to company keyword: {keyword}")
            return True

    return False

def human_scroll(driver):
    scroll_script = "window.scrollBy(0, arguments[0]);"
    for _ in range(random.randint(2, 5)):
        driver.execute_script(scroll_script, random.randint(100, 400))
        time.sleep(random.uniform(0.5, 1.5))

def get_stealth_headless_options():
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
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images") 
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return options

def setup_stealth_headless_driver():
    options = get_stealth_headless_options()
    
    temp_dir = tempfile.mkdtemp(prefix=f"scraper_{os.getpid()}_")
    options.add_argument(f"--user-data-dir={temp_dir}")
    
    driver = uc.Chrome(
        options=options,
        driver_executable_path=driver_executable_path_id
    )
    
    stealth_js = """
    // Hide webdriver property
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
    });
    
    // Mock plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
    
    // Mock languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });
    
    // Override permissions
    const originalQuery = window.navigator.permissions.query;
    return window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
    
    // Hide automation indicators
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    """
    
    try:
        driver.execute_script(stealth_js)
        print("Stealth JavaScript executed successfully")
    except Exception as e:
        print(f"Warning: Could not execute stealth JS: {e}")
    
    return driver

def load_selected_hours():
    """Load user-selected hours from config file."""
    try:
        with open("scraper_config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            return int(config.get("hours"))
    except FileNotFoundError:
        print("scraper_config.json not found, using default hours")
    except Exception as e:
        print(f"Error loading selected_hours: {e}")

    return None

def main():
    global _driver, EXCLUDE_TITLES, EXCLUDE_COMPANIES
    
    # Register signal handlers and cleanup
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(cleanup_driver)
    atexit.register(lambda: update_status("stopped", "Process exited"))
    EXCLUDE_TITLES, EXCLUDE_COMPANIES = load_excluded_words()
    
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
        
        _driver = setup_stealth_headless_driver()
        driver = _driver
        update_status("running", "Chrome driver started, beginning scrape...")
        print("Chrome driver started successfully")
        
        # Initialize scraping variables
        actions = ActionChains(driver)
        page = 1
        jobs_scraped = 0
        current_hour = 0
        selected_hours = load_selected_hours()
        
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
                driver.quit()
                break
                
            try:
                timeout = 15 if page >= 10 else 10
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, job_content_id))
                )
                print("Waiting for job listings")
                time.sleep(random.uniform(1, 3))
            except TimeoutException:
                driver.save_screenshot("debug_screenshot2.png")
                update_status("error", "Timed out waiting for job listings")
                print("Timed out waiting for job listings.")
                break
                
            # Anti-bot measures
            time.sleep(random.uniform(2, 4))
            
            if should_stop():
                driver.quit()
                break
                
            human_scroll(driver)
            time.sleep(random.uniform(2, 4))
            
            listings = driver.find_elements(By.CLASS_NAME, listings_id)
            if not listings:
                driver.save_screenshot("debug_screenshot3.png")
                update_status("completed", "No more job listings found")
                print("No job listings found.")
                break
                
            handle_popup_if_present(driver)
            
            # Process job listings
            for i, job in enumerate(listings):
                if should_stop():
                    driver.quit()
                    update_status("stopped", "Stop flag detected")
                    break
                  
                try:
                    actions.move_to_element(job).pause(random.uniform(0.3, 0.7)).perform()
                    
                    # Extract job details
                    title = job.find_element(By.CSS_SELECTOR, f"[class*='{title_id}'] a.N").text.strip()
                    company = job.find_element(By.CLASS_NAME, company_id).text.strip()
                    location_elem = job.find_element(By.CSS_SELECTOR, f"[class*='{location_elem_id}']")
                    location = driver.execute_script(
                        "return arguments[0].childNodes[1].textContent.trim();",
                        location_elem
                    )
                    job_type_elem = job.find_element(By.CSS_SELECTOR, f"[class*='{job_type_elem_id}']")
                    job_type = driver.execute_script(
                        "return arguments[0].childNodes[1].textContent.trim();",
                        job_type_elem
                    )
                    job_body_upper = job.find_element(By.CSS_SELECTOR, f"[class*='{job_body_upper_id}']").text.strip()
                    job_body_lower_elem = job.find_element(By.CSS_SELECTOR, f"[class*='{job_body_lower_elem_id}']")
                    job_body_lower = driver.execute_script(
                        "return arguments[0].textContent;",
                        job_body_lower_elem
                    )
                    time_posted = job.find_element(By.CLASS_NAME, time_posted_id).text.strip()
                    link = job.find_element(By.CSS_SELECTOR, f"[class*='{link_id}'] a.N").get_attribute("href")

                    # Time logic
                    job_hour = get_job_hours(time_posted)
                    if job_hour > selected_hours:  
                        update_status("completed", f"Reached postings from {time_posted}. Stopping.")
                        print(f"Reached postings from {time_posted}. Stopping.")
                        return
                        
                    if job_hour > current_hour:
                        current_hour = job_hour
                        print(f"Now processing jobs from {current_hour} hours ago")
                    
                    # Exclude jobs based on keywords
                    if job_is_excluded(title, company):
                        print(f"Excluded: {title}, Posted: {time_posted}.  Job: {i}/15")
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
                    
                    print(f"SCRAPED: {title} at {company} - Posted: {time_posted}, Job: {i}/15")
                    
                    if should_stop():
                        driver.quit()
                        break
                        
                except NoSuchElementException as e:
                    print(f"Skipped job due to missing element: {e}")
                    continue
                except Exception as e:
                    print(f"Unexpected error processing job: {e}")
                    continue
            
            if should_stop():
                driver.quit()
                break
                
            # Pagination
            try:
                pagenext = driver.find_element(By.CLASS_NAME, pagenext_id)
                time.sleep(random.uniform(3, 6))
                
                if should_stop():
                    driver.quit()
                    break
                    
                click_next = pagenext.find_element(By.CLASS_NAME, click_next_id)
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
            driver.quit()
            
    except Exception as e:
        update_status("error", f"Scraper error: {e}")
        print(f"Scraper error: {e}")
    finally:
        print("Scraper cleanup starting...")
        cleanup_driver()
        print("Standalone scraper process exiting")

if __name__ == "__main__":
    main()
