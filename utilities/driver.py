#!/usr/bin/env python3
import os
import sys
import tempfile
import logging
import time
import psutil
import undetected_chromedriver as uc
import random
from selenium.common.exceptions import NoSuchElementException

logger = logging.getLogger("job_helper.scraper")

_driver = None

def get_stealth_headless_options():
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
    """Create and return an undetected-chromedriver instance and keep a module-level ref for cleanup."""
    global _driver
    options = get_stealth_headless_options()
    temp_dir = tempfile.mkdtemp(prefix=f"scraper_{os.getpid()}_")
    options.add_argument(f"--user-data-dir={temp_dir}")

    _driver = uc.Chrome(options=options)

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
    try {
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    } catch (e) {}
    """

    try:
        _driver.execute_script(stealth_js)
        logger.info("Stealth JavaScript executed successfully")
    except Exception as e:
        logger.error(f"Warning: Could not execute stealth JS: {e}")

    return _driver

def cleanup_driver():
    """Force cleanup of Chrome driver and associated processes."""
    global _driver
    if _driver:
        try:
            logger.warning("Force closing Chrome driver...")
            try:
                _driver.quit()
            except Exception:
                pass
            _driver = None
            logger.info("Chrome driver closed successfully")
        except Exception as e:
            logger.error(f"Error during driver cleanup: {e}")
        finally:
            _driver = None

    # Kill any remaining Chrome processes that look like automation
    try:
        logger.info("Cleaning up remaining Chrome processes...")
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info.get('name') or ""
                if 'chrome' in name.lower() or 'chromedriver' in name.lower():
                    cmdline = proc.info.get('cmdline') or []
                    if any('automation' in str(arg).lower() or 'test-type' in str(arg).lower() for arg in cmdline):
                        logger.info(f"Killing lingering Chrome process: {proc.info['pid']}")
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        logger.error(f"Error during process cleanup: {e}")

def human_scroll(driver):
    """Perform human-like scrolling to avoid bot detection."""
    scroll_script = "window.scrollBy(0, arguments[0]);"
    for _ in range(random.randint(2, 5)):
        driver.execute_script(scroll_script, random.randint(100, 400))
        time.sleep(random.uniform(0.5, 1.5))

def is_element_present(driver, by, value):
    """Check if element exists without raising exception."""
    try:
        driver.find_element(by, value)
        return True
    except NoSuchElementException:
        return False