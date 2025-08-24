#!/usr/bin/env python3
"""
validate.py

Validates a scraper configuration by testing its selector and regexes
against the example URLs provided in the config JSON.

Usage:
    python validate.py path/to/scraper_config_<site>.json [--method requests|playwright|both]
"""
import sys
import json
import re

import argparse
import requests
import asyncio
import os
from html import unescape
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, Optional

# Try to import colorama for colored output
try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False

def print_success(message):
    """Print success message in green"""
    if COLORAMA_AVAILABLE:
        print(f"{Fore.GREEN}[SUCCESS] {message}{Style.RESET_ALL}")
    else:
        print(f"[SUCCESS] {message}")

def print_error(message):
    """Print error message in red"""
    if COLORAMA_AVAILABLE:
        print(f"{Fore.RED}[ERROR] {message}{Style.RESET_ALL}")
    else:
        print(f"[ERROR] {message}")

def print_warning(message):
    """Print warning message in yellow"""
    if COLORAMA_AVAILABLE:
        print(f"{Fore.YELLOW}[WARNING] {message}{Style.RESET_ALL}")
    else:
        print(f"[WARNING] {message}")

def print_info(message):
    """Print info message in cyan"""
    if COLORAMA_AVAILABLE:
        print(f"{Fore.CYAN}[INFO] {message}{Style.RESET_ALL}")
    else:
        print(f"[INFO] {message}")

def print_highlight(message):
    """Print highlighted message in magenta"""
    if COLORAMA_AVAILABLE:
        print(f"{Fore.MAGENTA}[HIGHLIGHT] {message}{Style.RESET_ALL}")
    else:
        print(f"[HIGHLIGHT] {message}")

def clean_extracted_value(value):
    """Clean extracted values by removing extra whitespace and HTML entities"""
    if not value:
        return value
    
    # Decode HTML entities
    cleaned_value = unescape(value)
    
    # Remove extra whitespace (newlines, tabs, multiple spaces)
    cleaned_value = re.sub(r'\s+', ' ', cleaned_value).strip()
    
    return cleaned_value

# Try to import Playwright (optional)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("WARNING: Playwright not available. Install with: pip install playwright && playwright install")

class ApproachMemory:
    """Manages successful approach memory across different validation methods"""
    
    def __init__(self, memory_file='approach_memory.json'):
        self.memory_file = memory_file
        self.memory = self._load_memory()
    
    def _load_memory(self) -> Dict[str, str]:
        """Load approach memory from file"""
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"WARNING: Could not load approach memory: {e}")
        return {}
    
    def save_memory(self):
        """Save approach memory to file"""
        try:
            with open(self.memory_file, 'w') as f:
                json.dump(self.memory, f, indent=2)
        except Exception as e:
            print(f"WARNING: Could not save approach memory: {e}")
    
    def get_successful_approach(self, domain: str) -> Optional[str]:
        """Get the successful approach for a domain"""
        return self.memory.get(domain)
    
    def record_successful_approach(self, domain: str, approach: str):
        """Record a successful approach for a domain"""
        self.memory[domain] = approach
        self.save_memory()
    
    def get_domain_from_url(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return url

async def try_playwright_with_fallback(p, task_func, *args, **kwargs):
    """Try Playwright task with 4 approaches: headless+no-proxy, headless+proxy, non-headless+no-proxy, non-headless+proxy"""
    last_error = None
    
    # Define all 4 approaches to try
    approaches = [
        {'headless': True, 'use_proxy': False, 'label': 'headless + no proxy'},
        {'headless': True, 'use_proxy': True, 'label': 'headless + proxy'}, 
        {'headless': False, 'use_proxy': False, 'label': 'non-headless + no proxy'},
        {'headless': False, 'use_proxy': True, 'label': 'non-headless + proxy'}
    ]
    
    for approach in approaches:
        try:
            print(f"Trying {approach['label']} mode")
            
            # Browser launch options
            browser_args = {
                'headless': approach['headless'],
                'args': ['--no-sandbox', '--disable-setuid-sandbox']
            }
            
            # Add proxy configuration if this approach uses proxy
            if approach['use_proxy'] and WEBSHARE_PROXY:
                proxy_config = {
                    'server': WEBSHARE_PROXY['server'],
                    'username': WEBSHARE_PROXY['username'],
                    'password': WEBSHARE_PROXY['password']
                }
                browser_args['proxy'] = proxy_config
                print(f"Using proxy: {WEBSHARE_PROXY['server']}")
            else:
                print("Running without proxy")
            browser = await p.chromium.launch(**browser_args)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # Execute the task function
            result = await task_func(browser, context, *args, **kwargs)
            await browser.close()
            print_success(f"SUCCESS with {approach['label']} approach!")
            return result
            
        except Exception as e:
            if 'browser' in locals():
                try:
                    await browser.close()
                except:
                    pass
            last_error = e
            print(f"{approach['label']} mode failed: {e}")
            continue
    
    # If all 4 approaches failed, raise the last error
    raise last_error

# Webshare proxy configuration (same as Universal Website Analyzer)
WEBSHARE_PROXY = {
    'server': 'http://p.webshare.io:80',
    'username': 'hiqjuwfu-rotate',
    'password': 'xmq4ru7a995q'
}

def make_request_with_proxy_fallback(url, headers, timeout=10):
    """Make HTTP request using SIMPLE first, then PROXY as fallback (matches Universal Website Analyzer)"""
    
    # Try SIMPLE approach first (no proxy) - matches analyzer logic
    try:
        print(f"Trying SIMPLE approach (no proxy) for {url}")
        resp = requests.get(url, timeout=timeout, headers=headers)
        
        if resp.status_code == 200:
            print(f"SIMPLE approach succeeded! ({len(resp.text)} characters)")
            return resp
        else:
            print(f"SIMPLE approach returned status {resp.status_code}")
    except Exception as e:
        print(f"SIMPLE approach failed: {e}")
    # Fallback to PROXY approach (Webshare) if simple fails - matches analyzer logic
    if WEBSHARE_PROXY:
        try:
            proxy_url = f"http://{WEBSHARE_PROXY['username']}:{WEBSHARE_PROXY['password']}@{WEBSHARE_PROXY['server'].replace('http://', '')}"
            proxy_dict = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            print(f"Trying PROXY approach (Webshare) for {url}")
            resp = requests.get(url, timeout=timeout, headers=headers, proxies=proxy_dict)
            
            if resp.status_code == 200:
                print(f"PROXY approach succeeded! ({len(resp.text)} characters)")
                return resp
            else:
                print(f"PROXY approach returned status {resp.status_code}")
        except Exception as e:
            print(f"PROXY approach failed: {e}")
    # If both failed, raise error
    raise Exception("Both SIMPLE and PROXY approaches failed")

async def test_selector_playwright(config):
    """
    Use Playwright to fetch the catalog page and test the CSS selector for product links.
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not available. Cannot run Playwright validation.")
        return []
    
    catalog_url = config["catalog_pages"][0]
    selector = config["products"][0]["selector"]["pattern"]

    print(f"Testing CSS selector with Playwright on catalog page: {catalog_url}")
    async def selector_task(browser, context, catalog_url, selector):
        """Task function for selector testing"""
        page = await context.new_page()
        
        # Navigate to catalog page and wait for complete load
        await page.goto(catalog_url, wait_until='load', timeout=60000)
        
        # Wait for DOM content to be fully loaded
        await page.wait_for_load_state('domcontentloaded')
        
        # Wait for network activity to settle
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except:
            # If networkidle fails, just wait a bit more for dynamic content
            await page.wait_for_timeout(5000)
        
        # Additional wait to ensure all dynamic content is loaded
        await page.wait_for_timeout(3000)
        
        # Test the selector
        elements = await page.query_selector_all(selector)
        print(f"Found {len(elements)} elements with selector {selector} using Playwright")
        if len(elements) == 0:
            print("Selector did not match any elements on the catalog page with Playwright.")
        else:
            # Get some sample hrefs for verification
            sample_links = []
            for i, element in enumerate(elements[:5]):  # First 5 elements
                href = await element.get_attribute('href')
                if href:
                    sample_links.append(href)
            
            if sample_links:
                print("Sample product links found:")
                for i, link in enumerate(sample_links, 1):
                    print(f"   {i}. {link}")
        return elements
    
    try:
        async with async_playwright() as p:
            return await try_playwright_with_fallback(p, selector_task, catalog_url, selector)
    except Exception as e:
        print(f"Playwright selector test failed: {e}")
        return []

async def test_regexes_playwright(config):
    """
    Use Playwright to fetch the example product page and test each field regex against its HTML.
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not available. Cannot run Playwright validation.")
        return {}
    
    example_url = config["products"][0]["example_url"]
    fields = config["products"][0]["fields"]

    print(f"Testing field regexes with Playwright on product page: {example_url}")
    async def regex_task(browser, context, example_url, fields):
        """Task function for regex testing"""
        page = await context.new_page()
        
        # Navigate to product page and wait for complete load
        await page.goto(example_url, wait_until='load', timeout=60000)
        
        # Wait for DOM content to be fully loaded
        await page.wait_for_load_state('domcontentloaded')
        
        # Wait for network activity to settle
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except:
            # If networkidle fails, just wait a bit more for dynamic content
            await page.wait_for_timeout(5000)
        
        # Additional wait to ensure all dynamic content is loaded
        await page.wait_for_timeout(3000)
        
        # Get page HTML content
        html = await page.content()
        
        # Test regexes against the HTML
        results = {}
        for field, info in fields.items():
            pattern = info.get("regex")
            if not pattern:
                print(f"Field {field} has no regex; skipping")
                results[field] = False
                continue

            try:
                m = re.search(pattern, html, re.MULTILINE | re.DOTALL)
            except re.error as e:
                print(f"Invalid regex for field {field}: {e}")
                results[field] = False
                continue

            if m and m.group(field):
                # Clean extracted value (remove whitespace and decode HTML entities)
                raw_value = m.group(field)
                cleaned_value = clean_extracted_value(raw_value)
                print_success(f"{field:<15} matched: {cleaned_value}")
                results[field] = True
            else:
                print_error(f"{field:<15} did not match or group empty")
                results[field] = False

        return results
    
    try:
        async with async_playwright() as p:
            return await try_playwright_with_fallback(p, regex_task, example_url, fields)
    except Exception as e:
        print(f"Playwright regex test failed: {e}")
        return {}

def test_selector(config):
    """
    Fetch the catalog page and test the CSS selector for product links.
    """
    catalog_url = config["catalog_pages"][0]
    selector = config["products"][0]["selector"]["pattern"]

    print(f"Testing CSS selector on catalog page: {catalog_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    resp = make_request_with_proxy_fallback(catalog_url, headers)
    soup = BeautifulSoup(resp.text, "html.parser")
    elements = soup.select(selector)
    print(f"Found {len(elements)} elements with selector {selector!r}")
    if len(elements) == 0:
        print("Selector did not match any elements on the catalog page.")
    return elements

def test_regexes(config):
    """
    Fetch the example product page and test each field regex against its HTML.
    """
    example_url = config["products"][0]["example_url"]
    fields = config["products"][0]["fields"]

    print(f"Testing field regexes on product page: {example_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    resp = make_request_with_proxy_fallback(example_url, headers)
    html = resp.text

    results = {}
    for field, info in fields.items():
        pattern = info.get("regex")
        if not pattern:
            print(f"Field {field!r} has no regex; skipping")
            results[field] = False
            continue

        try:
            m = re.search(pattern, html, re.MULTILINE | re.DOTALL)
        except re.error as e:
            print(f"Invalid regex for field {field!r}: {e}")
            results[field] = False
            continue

        if m and m.group(field):
            # Clean extracted value (remove whitespace and decode HTML entities)
            raw_value = m.group(field)
            cleaned_value = clean_extracted_value(raw_value)
            print_success(f"{field:<15} matched: {cleaned_value}")
            results[field] = True
        else:
            print_error(f"{field:<15} did not match or group empty")
            results[field] = False

    return results

async def run_validation_smart(config, method, approach_memory):
    """Run validation using smart approach selection with memory"""
    catalog_url = config["catalog_pages"][0]
    example_url = config["products"][0]["example_url"]
    
    domain = approach_memory.get_domain_from_url(catalog_url)
    successful_approach = approach_memory.get_successful_approach(domain)
    
    if successful_approach:
        print(f"Using remembered successful approach: {successful_approach} for {domain}")
    # Define approaches to try (prioritize remembered approach)
    approaches = []
    if successful_approach and method in ['both', successful_approach]:
        approaches.append(successful_approach)
    
    # Add remaining approaches based on method
    if method == 'both':
        all_approaches = ['requests', 'playwright']
        for approach in all_approaches:
            if approach != successful_approach and (approach == 'requests' or (approach == 'playwright' and PLAYWRIGHT_AVAILABLE)):
                approaches.append(approach)
    elif method == 'requests' and 'requests' not in approaches:
        approaches.append('requests')
    elif method == 'playwright' and PLAYWRIGHT_AVAILABLE and 'playwright' not in approaches:
        approaches.append('playwright')
    
    # Try each approach
    for approach in approaches:
        print(f"Trying {approach} validation approach for {domain}")
        try:
            if approach == 'requests':
                success = await run_requests_validation(config)
            elif approach == 'playwright':
                success = await run_playwright_validation(config)
            else:
                continue
            
            if success:
                # Success! Remember this approach
                if not successful_approach or successful_approach != approach:
                    print(f"Recording successful approach: {approach} for {domain}")
                    approach_memory.record_successful_approach(domain, approach)
                
                print_success(f"Validation successful with {approach} method")
                return True
            else:
                print(f"ERROR: {approach} approach failed for {domain}")
        except Exception as e:
            print(f"ERROR with {approach} approach: {e}")
            continue
    
    # All approaches failed
    print(f"WARNING: All validation approaches failed for {domain}")
    return False

async def run_requests_validation(config):
    """Run requests-based validation"""
    try:
        # 1) Test the CSS selector on the catalog page
        test_selector(config)
        
        # 2) Test each field regex on the example product page
        test_regexes(config)
        return True
    except Exception as e:
        print(f"Requests validation failed: {e}")
        return False

async def run_playwright_validation(config):
    """Run Playwright-based validation"""
    try:
        # 1) Test the CSS selector on the catalog page
        await test_selector_playwright(config)
        
        # 2) Test each field regex on the example product page
        await test_regexes_playwright(config)
        return True
    except Exception as e:
        print(f"Playwright validation failed: {e}")
        return False

async def run_validation_async(config, method):
    """Run validation using the specified method"""
    approach_memory = ApproachMemory()
    
    if method == 'both':
        print("Running smart validation with approach memory")
        return await run_validation_smart(config, method, approach_memory)
    
    requests_success = False
    playwright_success = False
    
    if method in ['requests', 'both']:
        print("=== REQUESTS-BASED VALIDATION ===")
        try:
            # 1) Test the CSS selector on the catalog page
            test_selector(config)
            
            # 2) Test each field regex on the example product page
            test_regexes(config)
            requests_success = True
            print_success("Requests-based validation completed successfully")
        except Exception as e:
            print(f"ERROR: Requests-based validation failed: {e}")
            if method == 'requests':
                print("TIP: Try using --method playwright for sites with bot protection")
            requests_success = False
    
    if method in ['playwright', 'both']:
        if not PLAYWRIGHT_AVAILABLE:
            print("ERROR: Playwright validation requested but Playwright not available.")
            print("TIP: Install with: pip install playwright && playwright install")
            return
        
        print("=== PLAYWRIGHT-BASED VALIDATION ===")
        try:
            # 1) Test the CSS selector on the catalog page
            await test_selector_playwright(config)
            
            # 2) Test each field regex on the example product page
            await test_regexes_playwright(config)
            playwright_success = True
            print_success("Playwright-based validation completed successfully")
        except Exception as e:
            print(f"ERROR: Playwright-based validation failed: {e}")
            playwright_success = False
    
    # Summary
    if method == 'both':
        if requests_success and playwright_success:
            print_success("Both validation methods succeeded!")
        elif requests_success or playwright_success:
            success_method = "Requests" if requests_success else "Playwright"
            print_success(f"Validation successful with {success_method} method")
        else:
            print("WARNING: Both validation methods failed - site may have strong protection")
def main():
    parser = argparse.ArgumentParser(
        description="Validate a scraper_config JSON by testing its selector and regexes"
    )
    parser.add_argument(
        "config_file",
        help="Path to the scraper_config_<site>.json file"
    )
    parser.add_argument(
        "--method",
        choices=['requests', 'playwright', 'both'],
        default='both',
        help="Validation method to use (default: both)"
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Disable proxy usage for Playwright (requests will still use proxy fallback)"
    )
    args = parser.parse_args()

    # Load config
    with open(args.config_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Disable proxy if requested
    if args.no_proxy:
        print("🚫 Proxy usage disabled for Playwright")
        global WEBSHARE_PROXY
        WEBSHARE_PROXY = None

    # Show validation method
    if args.method == 'both':
        print("Running validation with both methods: Requests + Playwright")
    else:
        print(f"Running validation with: {args.method.title()}")
    # Run validation
    asyncio.run(run_validation_async(config, args.method))

if __name__ == "__main__":
    main()

