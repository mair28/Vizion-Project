#!/usr/bin/env python3
"""
Universal Website Structure Analyzer
=====================================

A comprehensive tool to analyze any e-commerce website's structure and automatically
generate scraper configurations with optimal selectors and regex patterns.

Features:
- Automatic protection bypass (Cloudflare, Incapsula, bot detection)
- Product link detection and selector generation
- Field extraction regex pattern generation
- JSON-LD and structured data analysis
- Automatic scraper config generation
- Support for multiple browser engines
- Proxy rotation support

Usage:
    python universal_website_analyzer.py <website_url> [options]
    
Example:
    python universal_website_analyzer.py https://www.onlinecomponents.com/en/
    python universal_website_analyzer.py https://example.com --deep-analysis --generate-config
"""

import requests
import json
import re
import time
import random
import argparse
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup
from datetime import datetime
from html import unescape
from typing import Dict, List, Tuple, Optional, Any
import os
import sys
from dotenv import load_dotenv

# Try to import colorama for colored output
try:
    from colorama import Fore, Back, Style, init
    init(autoreset=True)  # Auto-reset colors after each print
    COLORAMA_AVAILABLE = True
except ImportError:
    # Fallback if colorama is not available
    class MockColor:
        def __getattr__(self, name):
            return ""
    Fore = Back = Style = MockColor()
    COLORAMA_AVAILABLE = False

# Try to import advanced libraries if available
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import undetected_chromedriver as uc
    UNDETECTED_CHROME_AVAILABLE = True
except ImportError:
    UNDETECTED_CHROME_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


def print_success(message):
    """Print success message in green"""
    print(f"{Fore.GREEN}{Style.BRIGHT}{message}{Style.RESET_ALL}")

def print_error(message):
    """Print error message in red"""
    print(f"{Fore.RED}{Style.BRIGHT}{message}{Style.RESET_ALL}")

def print_warning(message):
    """Print warning message in yellow"""
    print(f"{Fore.YELLOW}{Style.BRIGHT}{message}{Style.RESET_ALL}")

def print_info(message):
    """Print info message in cyan"""
    print(f"{Fore.CYAN}{message}{Style.RESET_ALL}")

def print_highlight(message):
    """Print highlighted message in magenta"""
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{message}{Style.RESET_ALL}")


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
            print_warning(f"WARNING: Could not load approach memory: {e}")
        return {}
    
    def save_memory(self):
        """Save approach memory to file"""
        try:
            with open(self.memory_file, 'w') as f:
                json.dump(self.memory, f, indent=2)
        except Exception as e:
            print_warning(f"WARNING: Could not save approach memory: {e}")
    
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

class UniversalWebsiteAnalyzer:
    """Universal website analyzer for e-commerce scraping configuration"""
    
    def __init__(self, base_url: str, use_selenium: bool = True, use_proxies: bool = True, 
                 deep_analysis: bool = True, use_ai: bool = True):
        self.base_url = base_url.rstrip('/')
        self.domain = urlparse(base_url).netloc
        
        # AI configuration (will be set up after logger initialization)
        self.use_ai = use_ai and OPENAI_AVAILABLE
        self.openai_client = None
        
        # Prefer Playwright over Selenium for better protection bypass
        self.use_playwright = PLAYWRIGHT_AVAILABLE
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE and not self.use_playwright
        
        # Setup Webshare rotating proxy configuration
        self.webshare_proxy = {
            'server': 'http://p.webshare.io:80',
            'username': 'hiqjuwfu-rotate',
            'password': 'xmq4ru7a995q'
        }
        
        # Always use proxies (Webshare rotating proxy only)
        self.use_proxies = use_proxies
        
        # Initialize approach memory
        self.approach_memory = ApproachMemory()
        self.deep_analysis = deep_analysis
        
        # Initialize analysis results storage
        self.analysis_results = {
            'product_patterns': [],
            'field_patterns': {},
            'site_info': {},
            'sample_pages': {},
            'protection_detected': [],
            'errors': [],
            'recommended_config': {}
        }
        
        # Initialize OpenAI
        if self.use_ai:
            self._setup_openai()
    
    def _validate_gtin_upc(self, code: str) -> bool:
        """Validate if a code is a valid GTIN/UPC format"""
        if not code or not isinstance(code, str):
            return False
        
        # Remove any non-digit characters
        clean_code = ''.join(filter(str.isdigit, code))
        
        # Valid GTIN/UPC lengths: 8, 12, 13, 14 digits
        valid_lengths = [8, 12, 13, 14]
        if len(clean_code) not in valid_lengths:
            return False
        
        # Check if all zeros (invalid)
        if clean_code == '0' * len(clean_code):
            return False
        
        # Validate check digit using GTIN algorithm
        return self._validate_gtin_check_digit(clean_code)
    
    def _validate_gtin_check_digit(self, code: str) -> bool:
        """Validate GTIN check digit using the standard algorithm"""
        try:
            # Convert to list of integers
            digits = [int(d) for d in code]
            
            # Calculate check digit using GTIN algorithm
            check_sum = 0
            
            # For GTIN, we start from the rightmost digit (excluding check digit)
            # and alternate weights 3 and 1 from right to left
            for i in range(len(digits) - 1):
                position_from_right = len(digits) - 2 - i  # Position from right (0-based)
                weight = 3 if position_from_right % 2 == 0 else 1  # Odd positions get weight 3
                check_sum += digits[i] * weight
            
            # Calculate the check digit
            calculated_check = (10 - (check_sum % 10)) % 10
            
            # Compare with the actual check digit
            return calculated_check == digits[-1]
        except (ValueError, IndexError):
            return False
    
    def _create_gtin_upc_regex(self, base_pattern: str) -> str:
        """Create a regex pattern that only matches valid GTIN/UPC codes"""
        # Extract the capture group from the base pattern
        if '(' in base_pattern and ')' in base_pattern:
            # Replace the generic capture group with a GTIN-specific one
            # GTIN/UPC: 8, 12, 13, or 14 digits only
            gtin_pattern = r'(\d{8}|\d{12}|\d{13}|\d{14})'
            return base_pattern.replace(r'([A-Za-z0-9-_]+)', gtin_pattern).replace(r'([A-Za-z0-9-_\s\.]+)', gtin_pattern)
        return base_pattern
        
        # Load proxies - Webshare rotating proxy only
        self.proxies = []
        self.proxy_fallback_available = False
        if use_proxies:
            # Add Webshare rotating proxy as the only proxy
            self.proxies.append(self.webshare_proxy)
            print_info("Using Webshare rotating proxy")
            # Enable fallback to direct connection if proxy fails
            self.proxy_fallback_available = True
        
        # Browser headers rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
        
        # Analysis results storage
        self.analysis_results = {
            'site_info': {},
            'protection_detected': [],
            'product_patterns': [],
            'field_patterns': {},
            'recommended_config': {},
            'sample_pages': {},
            'errors': []
        }
    
    def _setup_openai(self):
        """Setup OpenAI client with API key"""
        try:
            load_dotenv()  # loads .env if present
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is not set")

            self.openai_client = openai.OpenAI(api_key=api_key)
            self.openai_model = "gpt-4o"  # keep your chosen model
            print_success("SUCCESS: OpenAI AI-POWERED analysis enabled (GPT-4o)")
        except Exception as e:
            print_warning(f"WARNING: OpenAI setup failed: {e}")
            self.use_ai = False

    def _extract_site_name(self, domain: str) -> str:
        """Extract clean site name from domain (remove www, .com, etc.)"""
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Remove common TLDs and get main name
        domain_parts = domain.split('.')
        if len(domain_parts) >= 2:
            # Take the main domain name (before the TLD)
            site_name = domain_parts[0]
        else:
            site_name = domain
        
        # Replace any remaining special characters with underscores
        site_name = site_name.replace('-', '_').replace('.', '_')
        
        return site_name
    
    def _optimize_html_for_ai(self, html: str, analysis_type: str = "product_links") -> str:
        """BeautifulSoup preprocessing + AI analysis optimization"""
        try:
            from bs4 import BeautifulSoup, Comment
            soup = BeautifulSoup(html, 'html.parser')
            
            # Phase 1: Remove noise elements
            for tag in soup(['script', 'style', 'noscript', 'iframe', 'embed', 'object', 'head']):
                tag.decompose()
            
            # Remove comments
            for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()
            
            # Phase 2: Clean up attributes for AI focus
            for element in soup.find_all(True):
                # Keep only essential attributes for pattern detection
                essential_attrs = {}
                if element.get('class'):
                    essential_attrs['class'] = element['class']
                if element.get('id'):
                    essential_attrs['id'] = element['id']
                if element.get('data-testid'):
                    essential_attrs['data-testid'] = element['data-testid']
                if element.get('href') and element.name == 'a':
                    essential_attrs['href'] = element['href']
                # Keep data-* attributes that might contain field data
                for attr_name, attr_value in element.attrs.items():
                    if attr_name and isinstance(attr_name, str) and attr_name.startswith('data-') and any(term in attr_name.lower() for term in ['price', 'product', 'brand', 'sku', 'model']):
                        essential_attrs[attr_name] = attr_value
                
                element.attrs = essential_attrs
            
            # Phase 3: Structure-aware content selection
            if analysis_type == "product_links":
                # BeautifulSoup-powered link analysis
                link_containers = []
                for container in soup.find_all(['div', 'section', 'ul', 'ol', 'main', 'article']):
                    links = container.find_all('a', href=True)
                    if len(links) >= 2:  # Container with multiple links
                        # Score container by link relevance
                        score = 0
                        for link in links:
                            href = link.get('href', '').lower()
                            text = link.get_text(strip=True).lower()
                            if any(term in href or term in text for term in ['product', 'item', '/p/', '/prod']):
                                score += 2
                            elif len(text.split()) >= 2:  # Multi-word link text
                                score += 1
                        if score >= 3:
                            link_containers.append((container, score))
                
                # Sort by score and keep best containers
                link_containers.sort(key=lambda x: x[1], reverse=True)
                relevant_content = [container for container, score in link_containers[:3]]
                
            else:  # product_fields
                # BeautifulSoup-powered field analysis
                field_elements = []
                
                # Find price-related elements (including nested structures)
                price_elements = soup.find_all(['div', 'span', 'p'], 
                                             class_=lambda x: x and any(term in str(x).lower() for term in ['price', 'cost', 'dollar']))
                field_elements.extend(price_elements[:3])
                
                # Find title elements
                title_elements = soup.find_all(['h1', 'h2', 'div', 'span'], 
                                             class_=lambda x: x and any(term in str(x).lower() for term in ['title', 'name', 'product']))
                field_elements.extend(title_elements[:3])
                
                # Find brand/manufacturer elements
                brand_elements = soup.find_all(['a', 'span', 'div'], 
                                             attrs={'data-testid': lambda x: x and isinstance(x, str) and ('brand' in x.lower() or 'manufacturer' in x.lower())}) or \
                                soup.find_all(['a', 'span', 'div'], 
                                             class_=lambda x: x and isinstance(x, (str, list)) and any(term in str(x).lower() for term in ['brand', 'manufacturer']))
                field_elements.extend(brand_elements[:2])
                
                # Find SKU/model elements
                sku_elements = soup.find_all(['span', 'div', 'p'], 
                                           string=lambda text: text and isinstance(text, str) and any(term in text.lower() for term in ['sku:', 'model:', 'mpn:', 'part #']))
                field_elements.extend(sku_elements[:2])
                
                relevant_content = field_elements
            
            # Phase 4: Create structured output for AI
            if relevant_content:
                new_soup = BeautifulSoup('<html><body></body></html>', 'html.parser')
                body = new_soup.body
                
                # Add analysis context comment
                context_comment = soup.new_string(f"<!-- BeautifulSoup Analysis Context: {analysis_type} -->", Comment)
                body.append(context_comment)
                
                # Add unique relevant elements
                added_elements = set()
                for element in relevant_content[:15]:  # Limit for AI processing
                    if element and element.parent:  # Still in DOM
                        element_id = id(element)
                        if element_id not in added_elements:
                            try:
                                # For nested price structures, preserve parent-child relationships
                                if analysis_type == "product_fields" and element.name in ['div', 'span'] and 'price' in str(element.get('class', [])).lower():
                                    # Include children to preserve nested structure
                                    cloned_element = element.__copy__()
                                    body.append(cloned_element)
                                else:
                                    body.append(element.__copy__())
                                added_elements.add(element_id)
                            except Exception as e:
                                print(f"Error adding element: {e}")
                                continue
                
                optimized_html = str(new_soup)
            else:
                # Fallback: use cleaned original
                optimized_html = str(soup)
            
            # Phase 5: Smart truncation with structure preservation
            max_chars = 20000  # Increased for GPT-4o
            if len(optimized_html) > max_chars:
                truncated = optimized_html[:max_chars]
                # Try to end at a complete tag
                last_tag_end = truncated.rfind('>')
                if last_tag_end > max_chars * 0.7:
                    truncated = truncated[:last_tag_end + 1]
                optimized_html = truncated + "\n<!-- HTML truncated for AI analysis -->"
            
            print(f"BeautifulSoup preprocessed: {len(html)} → {len(optimized_html)} chars ({analysis_type})")
            return optimized_html
            
        except Exception as e:
            print(f"BeautifulSoup preprocessing failed: {e}, using simple truncation")
            return html[:15000]
    
    def _extract_script_content_for_ai(self, html: str) -> str:
        """Extract relevant script content for AI analysis"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            script_tags = soup.find_all('script')
            
            relevant_scripts = []
            for script in script_tags:
                if script.string:
                    content = script.string.strip()
                    # Look for scripts that likely contain product data
                    if content and isinstance(content, str) and any(keyword in content.lower() for keyword in ['product', 'brand', 'price', 'sku', 'mpn', 'upc', 'name']):
                        # Limit script size for AI processing
                        if len(content) > 2000:
                            content = content[:2000] + "..."
                        relevant_scripts.append(content)
            
            return "\n\n".join(relevant_scripts[:5])  # Limit to 5 most relevant scripts
        except Exception as e:
            print(f"Script content extraction failed: {e}")
            return ""
    
    def _extract_json_ld_for_ai(self, html: str) -> Dict[str, Any]:
        """Extract JSON-LD and other structured data for AI analysis"""
        structured_data = {
            'json_ld': [],
            'other_json': [],
            'microdata': []
        }
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract JSON-LD data
            json_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    structured_data['json_ld'].append(data)
                except:
                    continue
            
            # Extract other JSON data (often in script tags or data attributes)
            all_scripts = soup.find_all('script')
            for script in all_scripts:
                if script.string and isinstance(script.string, str) and ('product' in script.string.lower() or 
                                    'price' in script.string.lower() or
                                    'sku' in script.string.lower()):
                    try:
                        # Try to find JSON objects in script content
                        script_content = script.string
                        # Look for JSON-like patterns
                        import re
                        json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', script_content)
                        for match in json_matches[:3]:  # Limit to 3 matches
                            try:
                                json_data = json.loads(match)
                                if isinstance(json_data, dict) and len(json_data) > 0:
                                    structured_data['other_json'].append(json_data)
                            except:
                                continue
                    except:
                        continue
            
            # Extract microdata
            microdata_elements = soup.find_all(attrs={'itemtype': True})
            for elem in microdata_elements[:5]:  # Limit to 5 elements
                microdata_item = {
                    'itemtype': elem.get('itemtype'),
                    'properties': {}
                }
                
                # Find all itemprop elements within this item
                prop_elements = elem.find_all(attrs={'itemprop': True})
                for prop_elem in prop_elements:
                    prop_name = prop_elem.get('itemprop')
                    prop_value = (prop_elem.get('content') or 
                                prop_elem.get('datetime') or 
                                prop_elem.get_text(strip=True))
                    if prop_value:
                        microdata_item['properties'][prop_name] = prop_value
                
                if microdata_item['properties']:
                    structured_data['microdata'].append(microdata_item)
                    
        except Exception as e:
            print(f"Error extracting structured data for AI: {e}")
        return structured_data
    
    def _get_random_headers(self) -> Dict[str, str]:
        """Generate random browser headers"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
            'DNT': '1'
        }
    
    def _fetch_simple_like_validate(self, url: str, timeout: int = 10) -> Optional[str]:
        """Fetch page using SIMPLE approach first, then PROXY as fallback"""
        
        # Use the exact headers that work in validate.py
        simple_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # Try SIMPLE approach first (no proxy)
        try:
            print(f"Trying SIMPLE approach (no proxy) for {url}")
            response = requests.get(url, headers=simple_headers, timeout=timeout)
            
            if response.status_code == 200:
                print(f"SIMPLE approach succeeded! ({len(response.text)} characters)")
                return response.text
            else:
                print(f"SIMPLE approach returned status {response.status_code}")
        except Exception as e:
            print(f"SIMPLE approach failed: {e}")
        # Fallback to PROXY approach (Webshare) if simple fails
        if self.proxies and any('server' in proxy and 'username' in proxy for proxy in self.proxies):
            try:
                # Use first Webshare proxy
                webshare_proxy = next(proxy for proxy in self.proxies if 'server' in proxy and 'username' in proxy)
                proxy_url = f"http://{webshare_proxy['username']}:{webshare_proxy['password']}@{webshare_proxy['server'].replace('http://', '')}"
                proxy_dict = {
                    'http': proxy_url,
                    'https': proxy_url
                }
                
                print(f"Trying PROXY approach (Webshare) for {url}")
                response = requests.get(url, headers=simple_headers, proxies=proxy_dict, timeout=timeout)
                
                if response.status_code == 200:
                    print(f"PROXY approach succeeded! ({len(response.text)} characters)")
                    return response.text
                else:
                    print(f"PROXY approach returned status {response.status_code}")
            except Exception as e:
                print(f"PROXY approach failed: {e}")
        return None
    
    def _fetch_cf_ray_bypass(self, url: str, timeout: int = 15) -> Optional[str]:
        """Specialized method to bypass cf-ray Cloudflare protection using cookie acquisition"""
        
        # Exact headers from your successful request
        cf_bypass_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Priority': 'u=0, i',
            'sec-ch-ua': '"Not;A=Brand";v="99", "Microsoft Edge";v="139", "Chromium";v="139"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'DNT': '1'
        }
        
        session = requests.Session()
        
        # Method 1: Replicate the EXACT successful flow from your request
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            print(f"Trying CF-RAY bypass (cookie acquisition method) for {url}")
            # Step 1: Visit homepage to get initial session
            print("  → Step 1: Visiting homepage to establish session...")
            homepage_headers = cf_bypass_headers.copy()
            homepage_headers['Sec-Fetch-Site'] = 'none'  # Direct navigation
            
            response = session.get(base_url, headers=homepage_headers, timeout=timeout, allow_redirects=True)
            print(f"  → Homepage: status {response.status_code}, cookies: {len(session.cookies)}")
            time.sleep(random.uniform(2, 4))
            
            # Step 2: Visit catalog page (like your referer)
            catalog_candidates = [
                f"{base_url}/pellet-guns/pellet-pistols",
                f"{base_url}/bb-guns/bb-pistols", 
                f"{base_url}/discounts-specials"
            ]
            
            catalog_url = None
            for candidate in catalog_candidates:
                print(f"  → Step 2: Trying catalog page: {candidate}")
                catalog_headers = cf_bypass_headers.copy()
                catalog_headers['Referer'] = base_url
                
                cat_response = session.get(candidate, headers=catalog_headers, timeout=timeout, allow_redirects=True)
                if cat_response.status_code == 200:
                    catalog_url = candidate
                    print(f"  → Catalog success: {catalog_url}, cookies: {len(session.cookies)}")
                    break
                time.sleep(random.uniform(1, 2))
            
            if not catalog_url:
                catalog_url = base_url  # Fallback
            
            time.sleep(random.uniform(2, 4))
            
            # Step 3: Access target page with proper referer (like your successful request)
            print(f"  → Step 3: Accessing target page with referer...")
            target_headers = cf_bypass_headers.copy()
            target_headers['Referer'] = catalog_url  # This is key!
            
            response = session.get(url, headers=target_headers, timeout=timeout, allow_redirects=True)
            
            # Check for success (allow cf-ray in headers but not as protection page)
            if response.status_code == 200:
                content = response.text
                if len(content) > 50000:  # Substantial content like your 530KB
                    print(f"CF-RAY bypass succeeded! ({len(content)} characters, cookies: {len(session.cookies)})")
                    return content
                else:
                    print(f"CF-RAY method: Got response but content too small ({len(content)} chars)")
            else:
                print(f"CF-RAY method: status {response.status_code}")
        except Exception as e:
            print(f"CF-RAY cookie method failed: {e}")
        # Method 3: With rotating User-Agents
        modern_user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0'
        ]
        
        for i, ua in enumerate(modern_user_agents[:2], 3):  # Try max 2 more attempts
            try:
                print(f"Trying CF-RAY bypass (method {i} - UA rotation) for {url}")
                rotation_headers = cf_bypass_headers.copy()
                rotation_headers['User-Agent'] = ua
                
                response = session.get(url, headers=rotation_headers, timeout=timeout, allow_redirects=True)
                
                if response.status_code == 200 and 'cf-ray' not in response.text.lower():
                    print(f"CF-RAY bypass method {i} succeeded! ({len(response.text)} characters)")
                    return response.text
                else:
                    print(f"CF-RAY method {i}: status {response.status_code}")
            except Exception as e:
                print(f"CF-RAY method {i} failed: {e}")
            time.sleep(random.uniform(1, 2))
        
        return None
    
    def _fetch_playwright_cf_ray_bypass(self, url: str) -> Optional[str]:
        """Advanced Playwright-based cf-ray bypass using proven techniques"""
        
        if not PLAYWRIGHT_AVAILABLE:
            return None
            
        try:
            from playwright.sync_api import sync_playwright
            from urllib.parse import urlparse
            
            print(f"Trying advanced Playwright CF-RAY bypass for {url}")
            with sync_playwright() as p:
                # Advanced browser arguments for stealth
                stealth_args = [
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--exclude-switches=enable-automation',
                    '--disable-web-security',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-default-apps',
                    '--disable-sync',
                    '--disable-translate',
                    '--hide-scrollbars',
                    '--mute-audio',
                    '--no-default-browser-check',
                    '--disable-ipc-flooding-protection',
                    '--password-store=basic',
                    '--use-mock-keychain',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
                
                browser = p.chromium.launch(
                    headless=False,  # Visible for debugging
                    args=stealth_args,
                    slow_mo=random.randint(100, 200)
                )
                
                # Create context with realistic properties
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    timezone_id="America/New_York",
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="121", "Google Chrome";v="121"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"'
                    }
                )
                
                # Advanced stealth script based on cloudflare_bypass.py
                stealth_script = """
                // Hide webdriver property thoroughly
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                delete Object.getPrototypeOf(navigator).webdriver;
                
                // Advanced Chrome runtime spoofing
                window.chrome = {
                    app: { isInstalled: false },
                    runtime: {
                        onConnect: undefined,
                        onMessage: undefined,
                        connect: () => ({
                            onMessage: { addListener: () => {}, removeListener: () => {} },
                            postMessage: () => {},
                            disconnect: () => {}
                        })
                    }
                };
                
                // Randomize fingerprints
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => Math.floor(Math.random() * 4) + 4
                });
                
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => [4, 8, 16][Math.floor(Math.random() * 3)]
                });
                
                // Canvas fingerprint spoofing
                const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(type) {
                    const shift = Math.floor(Math.random() * 10) - 5;
                    const canvas = this;
                    const ctx = canvas.getContext('2d');
                    if (ctx) {
                        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                        for (let i = 0; i < imageData.data.length; i += 4) {
                            imageData.data[i] = Math.min(255, Math.max(0, imageData.data[i] + shift));
                        }
                        ctx.putImageData(imageData, 0, 0);
                    }
                    return originalToDataURL.apply(this, arguments);
                };
                """
                
                context.add_init_script(stealth_script)
                page = context.new_page()
                
                # Session building approach
                parsed = urlparse(url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                
                # Step 1: Visit homepage first
                print("  → Building session via homepage...")
                try:
                    response = page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
                    if "cf-ray" in page.content().lower() or "checking your browser" in page.content().lower():
                        print("  → Cloudflare challenge detected, waiting...")
                        page.wait_for_function(
                            "!document.body.innerText.includes('Checking your browser')",
                            timeout=30000
                        )
                        print("  → Challenge resolved!")
                    time.sleep(random.uniform(3, 6))
                    
                    # Simulate human behavior
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                    time.sleep(random.uniform(1, 2))
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(random.uniform(1, 2))
                    
                except Exception as e:
                    print(f"  → Homepage visit failed: {e}")
                # Step 2: Try target URL
                print("  → Accessing target page...")
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    
                    # Check for challenge again
                    if "cf-ray" in page.content().lower() or "checking your browser" in page.content().lower():
                        print("  → Target page challenge detected, waiting...")
                        page.wait_for_function(
                            "!document.body.innerText.includes('Checking your browser')",
                            timeout=30000
                        )
                        print("  → Target challenge resolved!")
                    time.sleep(random.uniform(2, 4))
                    content = page.content()
                    
                    if response.status == 200 and content:
                        print(f"Advanced Playwright CF-RAY bypass succeeded! ({len(content)} characters)")
                        return content
                    else:
                        print(f"Advanced Playwright bypass: status {response.status}")
                except Exception as e:
                    print(f"Target page access failed: {e}")
                finally:
                    browser.close()
                    
        except Exception as e:
            print(f"Advanced Playwright CF-RAY bypass failed: {e}")
        return None
    
    def _ai_analyze_html_for_patterns(self, html: str, analysis_type: str = "product_links") -> Dict[str, Any]:
        """Use AI to analyze HTML and identify patterns"""
        if not self.use_ai or not self.openai_client:
            return {}
        
        try:
            # Extract JSON-LD and structured data first  
            json_ld_data = self._extract_json_ld_for_ai(html)
            
            # Extract and prepare script tags for AI analysis
            script_data = self._extract_script_content_for_ai(html)
            
            # Optimize HTML for AI analysis with multiple strategies
            html_sample = self._optimize_html_for_ai(html, analysis_type)
            
            if analysis_type == "product_links":
                structured_data_text = ""
                if json_ld_data['json_ld'] or json_ld_data['other_json'] or json_ld_data['microdata']:
                    structured_data_text = f"""
                    
Structured Data Found:
JSON-LD: {json.dumps(json_ld_data['json_ld'][:2], indent=2) if json_ld_data['json_ld'] else 'None'}
Other JSON: {json.dumps(json_ld_data['other_json'][:2], indent=2) if json_ld_data['other_json'] else 'None'}
Microdata: {json.dumps(json_ld_data['microdata'][:2], indent=2) if json_ld_data['microdata'] else 'None'}
"""
                
                prompt = f"""
Analyze this HTML from an e-commerce website and identify CSS selectors for product links.

Look for:
1. Links that lead to individual product pages
2. Common patterns in href attributes (like /product/, /item/, /p/, etc.)
3. CSS classes that indicate product links
4. Container elements that hold product listings
5. Use the structured data below to understand the product structure

HTML sample:
```html
{html_sample}
```
{structured_data_text}

IMPORTANT: Return ONLY valid JSON with this exact structure (no markdown, no explanations):
{{
    "product_link_patterns": [
        {{
            "selector": "a[href*='/product/']",
            "explanation": "Links containing /product/ in URL",
            "confidence": 0.9,
            "example_count": 5
        }}
    ],
    "container_selectors": [
        {{
            "selector": ".product-grid .product-item",
            "explanation": "Individual product containers",
            "confidence": 0.8
        }}
    ],
    "structured_data_insights": "Insights from JSON-LD or microdata if available"
}}
"""
            
            elif analysis_type == "product_fields":
                structured_data_text = ""
                if json_ld_data['json_ld'] or json_ld_data['other_json'] or json_ld_data['microdata']:
                    structured_data_text = f"""
                    
Structured Data Found:
JSON-LD: {json.dumps(json_ld_data['json_ld'][:2], indent=2) if json_ld_data['json_ld'] else 'None'}
Other JSON: {json.dumps(json_ld_data['other_json'][:2], indent=2) if json_ld_data['other_json'] else 'None'}
Microdata: {json.dumps(json_ld_data['microdata'][:2], indent=2) if json_ld_data['microdata'] else 'None'}
"""

                script_data_text = ""
                if script_data:
                    script_data_text = f"""

Script Tags with Product Data:
```javascript
{script_data}
```
"""
                
                prompt = f"""
Analyze this HTML from a product page and identify patterns for extracting product information.

Look for:
1. Product title/name
2. Price information  
3. Brand/manufacturer/make
4. SKU/model number/part number/MPN
5. Product codes (UPC, GTIN, barcode, EAN)
6. PRIORITY: Use structured data (JSON-LD, microdata) and script tags when available for accurate patterns

HTML sample:
```html
{html_sample}
```
{structured_data_text}{script_data_text}

IMPORTANT: Return ONLY valid JSON with this exact structure (no markdown, no explanations):
{{
    "field_patterns": {{
        "title": {{
            "selectors": ["h1.product-title", ".product-name"],
            "regex_patterns": ["<h1[^>]*>([^<]+)</h1>"],
            "json_paths": ["name", "title"] if found in structured data,
            "confidence": 0.9
        }},
        "price": {{
            "selectors": [".price", ".cost"],
            "regex_patterns": ["\\$([\\d,]+\\.\\d{{2}})"],
            "json_paths": ["offers.price", "price"] if found in structured data,
            "confidence": 0.8
        }},
        "brand": {{
            "selectors": [".brand", ".manufacturer"],
            "regex_patterns": ["brand[\"\\s:]*([A-Za-z0-9\\s&.-]+)"],
            "json_paths": ["brand.name", "brand", "manufacturer"] if found in structured data,
            "confidence": 0.7
        }},
        "sku": {{
            "selectors": [".sku", ".item-number"],
            "regex_patterns": ["sku[\"\\s:]*([A-Za-z0-9-_\\s\\.]+)"],
            "json_paths": ["sku", "productID"] if found in structured data,
            "confidence": 0.7
        }},
        "model": {{
            "selectors": [".model", ".part-number"],
            "regex_patterns": ["model[\"\\s:]*([A-Za-z0-9-_\\s\\.]+)"],
            "json_paths": ["mpn", "model", "partNumber"] if found in structured data,
            "confidence": 0.7
        }},
        "product_code": {{
            "selectors": [".upc", ".gtin"],
            "regex_patterns": ["upc[\"\\s:]*([A-Za-z0-9-_]+)"],
            "json_paths": ["gtin", "upc", "gtin13"] if found in structured data,
            "confidence": 0.6
        }}
    }},
    "structured_data_fields": {{
        "available": true/false,
        "source": "json-ld|microdata|other_json",
        "direct_extraction_possible": true/false
    }}
}}
"""
            
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": "You are an expert web scraper who analyzes HTML to identify patterns for data extraction. You MUST respond with valid JSON only. No markdown, no explanations, no text outside the JSON structure."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            # Parse the JSON response with better error handling
            response_content = response.choices[0].message.content.strip()
            
            # Log the raw response for debugging
            print(f"AI raw response: {response_content[:200]}...")
            # Clean and validate the response
            if not response_content:
                print(f"AI returned empty response for {analysis_type}")
                return {}
            
            # Try to extract JSON if it's wrapped in markdown or other text
            json_start = response_content.find('{')
            json_end = response_content.rfind('}')
            
            if json_start != -1 and json_end != -1 and json_end > json_start:
                json_content = response_content[json_start:json_end + 1]
            else:
                json_content = response_content
            
            try:
                ai_analysis = json.loads(json_content)
                print(f"AI analysis completed for {analysis_type}")
                return ai_analysis
            except json.JSONDecodeError as je:
                print(f"AI returned invalid JSON for {analysis_type}: {je}")
                print(f"Invalid JSON content: {json_content}")
                return {}
            
        except Exception as e:
            print(f"AI analysis failed for {analysis_type}: {e}")
            return {}
    
    def _ai_improve_regex_pattern(self, field_name: str, current_pattern: str, sample_html: str, expected_value: str = None) -> str:
        """Use AI to improve regex patterns"""
        if not self.use_ai or not self.openai_client:
            return current_pattern
        
        try:
            prompt = f"""
Improve this regex pattern for extracting {field_name} from HTML. Keep it SIMPLE and reliable.

Current pattern: {current_pattern}
Sample HTML: {sample_html[:5000]}
Expected value: {expected_value or "Not provided"}

Requirements:
1. Pattern must include named capture group: (?P<{field_name}>...)
2. Keep it as SIMPLE as possible - avoid complex alternations
3. For nested elements (like price with child divs), use .*? or [\\s\\S]*? to match across HTML tags
4. For simple elements, use [^<]+ for content capture
5. Must be valid Python regex
6. Prefer straightforward class matching over complex patterns

Example of GOOD simple pattern: <h1[^>]*class="[^"]*product-name[^"]*"[^>]*>(?P<Product_Title>[^<]+)</h1>
Example of GOOD nested pattern: <div[^>]*class="[^"]*price[^"]*"[^>]*>.*?(?P<Product_Price>[\\d,]+\\.?\\d*)
Example of BAD complex pattern: <h1[^>]*class="[^"]*(?:\\\\bproduct-name\\\\b|\\\\bd-none\\\\b)[^"]*"[^>]*>\\\\s*(?P<Product_Title>[^<]+?)\\\\s*</h1>

IMPORTANT: Do NOT use word boundaries (\\\\b) with CSS class names that contain hyphens - they don't work correctly!
Special note for {field_name}: {"If this is for nested price elements with child divs, use .*? to match across HTML tags" if field_name == "Product_Price" else ""}

Return only the improved regex pattern, nothing else.
"""
            
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": "You are a regex expert. Return only the improved regex pattern."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            improved_pattern = response.choices[0].message.content.strip()
            
            # Remove markdown formatting if present
            if improved_pattern.startswith('```'):
                lines = improved_pattern.split('\n')
                # Find the actual regex pattern (skip markdown lines)
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('```') and not line.startswith('regex'):
                        improved_pattern = line
                        break
            
            # Validate the improved pattern
            try:
                re.compile(improved_pattern)
                print(f"AI improved regex for {field_name}")
                return improved_pattern
            except re.error:
                print(f"AI regex improvement failed validation for {field_name}")
                return current_pattern
                
        except Exception as e:
            print(f"AI regex improvement failed for {field_name}: {e}")
            return current_pattern
    
    def _ai_generate_css_selector(self, html: str, description: str) -> str:
        """Use AI to generate CSS selectors"""
        if not self.use_ai or not self.openai_client:
            return ""
        
        try:
            prompt = f"""
Generate a CSS selector for: {description}

HTML sample:
```html
{html[:10000]}
```

Return only the CSS selector, nothing else. Make it as specific as needed but not overly complex.
"""
            
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": "You are a CSS selector expert. Return only the selector."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=100
            )
            
            selector = response.choices[0].message.content.strip()
            print(f"AI generated selector: {selector}")
            return selector
            
        except Exception as e:
            print(f"AI selector generation failed: {e}")
            return ""
    
    def _ai_generate_json_path_patterns(self, structured_data: Dict, field_name: str) -> List[str]:
        """Use AI to generate JSON path patterns for structured data extraction"""
        if not self.use_ai or not self.openai_client:
            return []
        
        try:
            prompt = f"""
Generate JSON path patterns to extract {field_name} from this structured data.

Structured Data:
{json.dumps(structured_data, indent=2)}

Field to extract: {field_name}

Return a JSON array of possible JSON paths (using dot notation) that could contain this field.
Examples: ["name", "brand.name", "offers.price", "sku", "mpn"]

Consider common e-commerce schema.org patterns and variations.
"""
            
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": "You are a JSON path expert. Return only a JSON array of possible paths."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            try:
                response_content = response.choices[0].message.content.strip()
                
                # Try to extract JSON array if it's wrapped in text
                if '[' in response_content and ']' in response_content:
                    json_start = response_content.find('[')
                    json_end = response_content.rfind(']')
                    json_content = response_content[json_start:json_end + 1]
                else:
                    json_content = response_content
                
                paths = json.loads(json_content)
                if isinstance(paths, list):
                    print(f"AI generated {len(paths)} JSON paths for {field_name}")
                    return paths
            except Exception as parse_error:
                print(f"JSON path parsing failed: {parse_error}")
                pass
                
        except Exception as e:
            print(f"AI JSON path generation failed for {field_name}: {e}")
        return []
    
    def _extract_from_json_path(self, data: Dict, path: str) -> Any:
        """Extract value from JSON using dot notation path"""
        try:
            keys = path.split('.')
            current = data
            
            for key in keys:
                if isinstance(current, dict):
                    current = current.get(key)
                elif isinstance(current, list) and current:
                    # If it's a list, try the first item
                    current = current[0].get(key) if isinstance(current[0], dict) else None
                else:
                    return None
                    
                if current is None:
                    return None
            
            return current
        except:
            return None
    
    def _generate_patterns_from_html(self, user_html: str) -> List[Dict]:
        """Generate product link patterns from user-provided HTML element"""
        patterns = []
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(user_html, 'html.parser')
            
            # Find the main container element
            root_element = soup.find()
            if not root_element:
                return patterns
            
            # Generate CSS selector for this element
            css_selector = self._generate_css_selector_from_element(root_element)
            
            # Look for links within the element
            links = root_element.find_all('a', href=True)
            
            if links:
                # Create pattern based on links found
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    if href and text:  # Only include links with both href and text
                        pattern = {
                            'pattern': f"{css_selector} a",
                            'selector': f"{css_selector} a",
                            'count': 1,  # Since this is from a single example
                            'examples': [{'href': href, 'text': text}],
                            'confidence': 0.8,  # High confidence since user-provided
                            'type': 'user_generated'
                        }
                        patterns.append(pattern)
                        break  # Use the first valid link pattern
            
            # If no links found, create a pattern for the container itself
            if not patterns:
                pattern = {
                    'pattern': css_selector,
                    'selector': css_selector,
                    'count': 1,
                    'examples': [{'href': '#', 'text': root_element.get_text(strip=True)[:50]}],
                    'confidence': 0.7,  # Lower confidence since no links
                    'type': 'user_generated_container'
                }
                patterns.append(pattern)
                
            # Use AI to improve the pattern if available
            if self.use_ai and self.openai_client and patterns:
                improved_patterns = self._ai_improve_user_patterns(user_html, patterns)
                if improved_patterns:
                    patterns = improved_patterns
                    
        except Exception as e:
            print(f"Error generating patterns from HTML: {e}")
            
        return patterns
    
    def _extract_field_patterns_from_html(self, user_html: str) -> Dict[str, List[Dict]]:
        """Extract field patterns from user-provided HTML element"""
        field_patterns = {}
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(user_html, 'html.parser')
            
            # Define field detection strategies
            field_strategies = {
                'Product_Title': [
                    {'tags': ['h1', 'h2', 'h3'], 'classes': ['title', 'name', 'product']},
                    {'classes': ['product-title', 'product-name', 'item-title', 'title']}
                ],
                'Price': [
                    {'classes': ['price', 'cost', 'amount']},
                    {'tags': ['span', 'div'], 'content_patterns': [r'\$\d+', r'€\d+', r'£\d+']}
                ],
                'Brand': [
                    {'classes': ['brand', 'manufacturer', 'make']},
                    {'tags': ['span', 'div'], 'classes': ['brand']}
                ]
            }
            
            for field_name, strategies in field_strategies.items():
                found_patterns = []
                
                for strategy in strategies:
                    elements = []
                    
                    # Find by tags and classes
                    if 'tags' in strategy:
                        for tag in strategy['tags']:
                            tag_elements = soup.find_all(tag)
                            if 'classes' in strategy:
                                tag_elements = [el for el in tag_elements 
                                              if any(cls in str(el.get('class', [])).lower() 
                                                   for cls in strategy['classes'])]
                            elements.extend(tag_elements)
                    
                    # Find by classes only
                    elif 'classes' in strategy:
                        for cls in strategy['classes']:
                            elements.extend(soup.find_all(attrs={'class': lambda x: x and cls in str(x).lower()}))
                    
                    # Process found elements
                    for element in elements:
                        css_selector = self._generate_css_selector_from_element(element)
                        text_content = element.get_text(strip=True)
                        
                        if text_content and css_selector:
                            pattern = {
                                'regex': f'<{element.name}[^>]*>\\s*({re.escape(text_content)})\\s*</{element.name}>',
                                'css_selector': css_selector,
                                'example_value': text_content,
                                'confidence': 0.8,
                                'type': 'user_generated'
                            }
                            found_patterns.append(pattern)
                
                if found_patterns:
                    field_patterns[field_name] = found_patterns
                    
            # Use AI to improve field patterns if available
            if self.use_ai and self.openai_client and field_patterns:
                improved_field_patterns = self._ai_improve_field_patterns(user_html, field_patterns)
                if improved_field_patterns:
                    field_patterns = improved_field_patterns
                    
        except Exception as e:
            print(f"Error extracting field patterns from HTML: {e}")
            
        return field_patterns
    
    def _generate_css_selector_from_element(self, element) -> str:
        """Generate a CSS selector for a given BeautifulSoup element"""
        try:
            selector_parts = []
            
            # Start with tag name
            tag_name = element.name
            
            # Add class information if available
            classes = element.get('class', [])
            if classes:
                # Use first class for specificity
                main_class = classes[0]
                selector_parts.append(f"{tag_name}.{main_class}")
            else:
                selector_parts.append(tag_name)
            
            # Add any unique attributes
            for attr in ['id', 'data-id', 'data-product']:
                if element.get(attr):
                    attr_value = element.get(attr)
                    selector_parts.append(f"[{attr}='{attr_value}']")
                    break
            
            return ''.join(selector_parts)
            
        except Exception:
            return element.name if element.name else 'div'
    
    def _ai_improve_user_patterns(self, user_html: str, patterns: List[Dict]) -> List[Dict]:
        """Use AI to improve user-generated patterns"""
        if not self.use_ai or not self.openai_client:
            return patterns
            
        try:
            prompt = f"""
Analyze this HTML element and improve the CSS selectors for product extraction:

HTML Element:
{user_html}

Current Patterns:
{json.dumps(patterns, indent=2)}

Please provide improved CSS selectors that would be more robust and specific for finding similar product elements on the same website. Consider:
1. Making selectors more specific but not overly rigid
2. Using class patterns that are likely to be consistent
3. Avoiding selectors that are too specific to this exact element

Return as JSON array in this format:
[
  {{
    "pattern": "improved css selector",
    "selector": "improved css selector", 
    "confidence": 0.9,
    "type": "ai_improved"
  }}
]
"""

            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": "You are an expert at CSS selectors and web scraping. Provide improved selectors in valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            if '[' in content and ']' in content:
                json_start = content.find('[')
                json_end = content.rfind(']')
                json_content = content[json_start:json_end + 1]
                improved = json.loads(json_content)
                
                if isinstance(improved, list) and improved:
                    print("[SUCCESS] AI improved the patterns")
                    return improved
                    
        except Exception as e:
            print(f"AI pattern improvement failed: {e}")
            
        return patterns
    
    def _ai_improve_field_patterns(self, user_html: str, field_patterns: Dict) -> Dict:
        """Use AI to improve field patterns extracted from user HTML"""
        if not self.use_ai or not self.openai_client:
            return field_patterns
            
        try:
            prompt = f"""
Analyze this HTML element and improve the field extraction patterns:

HTML Element:
{user_html}

Current Field Patterns:
{json.dumps(field_patterns, indent=2)}

Please provide improved regex patterns and CSS selectors for extracting product fields like title, price, brand, etc. Make the patterns more robust and flexible.

Return as JSON object in this format:
{{
  "Product_Title": [
    {{
      "regex": "improved regex pattern",
      "css_selector": "improved css selector",
      "confidence": 0.9,
      "type": "ai_improved"
    }}
  ],
  "Price": [...],
  "Brand": [...]
}}
"""

            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": "You are an expert at regex patterns and CSS selectors for web scraping. Provide improved patterns in valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content.strip()
            if '{' in content and '}' in content:
                json_start = content.find('{')
                json_end = content.rfind('}')
                json_content = content[json_start:json_end + 1]
                improved = json.loads(json_content)
                
                if isinstance(improved, dict) and improved:
                    print("[SUCCESS] AI improved the field patterns")
                    return improved
                    
        except Exception as e:
            print(f"AI field pattern improvement failed: {e}")
            
        return field_patterns
    
    def _fetch_with_requests(self, url: str, timeout: int = 20) -> Optional[str]:
        """Fetch page using requests with advanced protection bypass attempts"""
        # Create a session for better cookie/state management
        session = requests.Session()
        
        # Enhanced approaches with different header combinations
        approaches = [
            # Standard approach
            {
                'headers': self._get_random_headers(),
                'allow_redirects': True,
                'timeout': timeout
            },
            # With referer
            {
                'headers': {**self._get_random_headers(), 'Referer': self.base_url},
                'allow_redirects': True,
                'timeout': timeout
            },
            # With additional security headers
            {
                'headers': {
                    **self._get_random_headers(),
                    'Referer': self.base_url,
                    'Origin': self.base_url,
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'same-origin',
                    'Sec-Fetch-User': '?1'
                },
                'allow_redirects': True,
                'timeout': timeout
            },
            # Chrome-like headers
            {
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"'
                },
                'allow_redirects': True,
                'timeout': timeout
            }
        ]
        
        # Add proxy approach if available
        if self.proxies:
            proxy = self.proxies[0]  # Only one proxy (Webshare)
            
            # Format Webshare proxy for requests
            proxy_url = f"http://{proxy['username']}:{proxy['password']}@{proxy['server'].replace('http://', '')}"
            proxy_dict = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            approaches.append({
                'headers': self._get_random_headers(),
                'proxies': proxy_dict,
                'allow_redirects': True,
                'timeout': timeout
            })
        
        for i, approach in enumerate(approaches):
            try:
                print(f"Trying approach {i+1} for {url}")
                # Add random delay to seem more human
                time.sleep(random.uniform(0.5, 2.0))
                
                response = session.get(url, **approach)
                
                # Check for protection pages
                if self._is_protection_page(response.text):
                    print(f"Protection detected on approach {i+1}")
                    continue
                
                response.raise_for_status()
                
                # Additional validation
                if len(response.text) < 500:  # Too short might be error page
                    print(f"Response too short ({len(response.text)} chars) on approach {i+1}")
                    continue
                
                print_success(f"Successfully fetched with approach {i+1} ({len(response.text)} characters)")
                return response.text
                
            except Exception as e:
                print(f"Approach {i+1} failed: {e}")
                continue
        
        session.close()
        return None
    
    def _get_playwright_stealth_script(self) -> str:
        """Get advanced Playwright stealth script from the proven working implementation"""
        return """
        // Advanced Playwright stealth script for bypassing bot detection
        
        // Hide webdriver property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
        
        // Override navigator properties
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                {name: 'Native Client', filename: 'internal-nacl-plugin'}
            ],
        });
        
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        
        Object.defineProperty(navigator, 'permissions', {
            get: () => ({
                query: () => Promise.resolve({ state: 'granted' })
            }),
        });
        
        // Add chrome runtime
        window.chrome = {
            runtime: {
                onConnect: undefined,
                onMessage: undefined,
                connect: () => ({
                    onMessage: {
                        addListener: () => {},
                        removeListener: () => {}
                    },
                    postMessage: () => {},
                    disconnect: () => {}
                })
            },
            app: {
                isInstalled: false
            }
        };
        
        // Hardware properties
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => Math.floor(Math.random() * 4) + 4, // 4-8 cores
        });
        
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => Math.pow(2, Math.floor(Math.random() * 3) + 2), // 4, 8, or 16 GB
        });
        
        // Platform consistency
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
        });
        
        // Override automation-specific properties
        delete navigator.__proto__.webdriver;
        
        // Spoof canvas fingerprinting
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            const shift = Math.floor(Math.random() * 10) - 5;
            const canvas = this;
            const ctx = canvas.getContext('2d');
            const originalData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            
            // Add slight noise
            for (let i = 0; i < originalData.data.length; i += 4) {
                originalData.data[i] += shift;
                originalData.data[i + 1] += shift;
                originalData.data[i + 2] += shift;
            }
            
            ctx.putImageData(originalData, 0, 0);
            return originalToDataURL.apply(this, arguments);
        };
        
        // Mouse movement simulation
        let mouseEvents = [];
        document.addEventListener('mousemove', (e) => {
            mouseEvents.push({x: e.clientX, y: e.clientY, time: Date.now()});
            if (mouseEvents.length > 100) mouseEvents.shift();
        });
        
        // Random mouse movements
        function simulateMouseMovement() {
            const event = new MouseEvent('mousemove', {
                clientX: Math.random() * window.innerWidth,
                clientY: Math.random() * window.innerHeight,
                bubbles: true
            });
            document.dispatchEvent(event);
        }
        
        // Simulate human-like behavior
        setTimeout(() => {
            for (let i = 0; i < 5; i++) {
                setTimeout(simulateMouseMovement, Math.random() * 2000);
            }
        }, Math.random() * 1000);
        
        // Override toString methods
        navigator.webdriver = undefined;
        Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {
            set: undefined,
            enumerable: false,
            configurable: false
        });
        """
    
    def _get_random_user_agent(self) -> str:
        """Get a random realistic user agent from proven working list"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
        ]
        return random.choice(user_agents)
    
    def _fetch_with_playwright(self, url: str, fast_mode: bool = False) -> Optional[str]:
        """Fetch page using Playwright with headless/non-headless fallback and advanced anti-bot detection bypass"""
        if not self.use_playwright:
            return None
        
        # Check if we should skip direct Playwright due to known event loop issues
        domain = self.approach_memory.get_domain_from_url(url) if hasattr(self, 'approach_memory') else None
        remembered_approach = self.approach_memory.get_successful_approach(domain) if hasattr(self, 'approach_memory') and domain else None
        
        if remembered_approach == 'playwright_subprocess':
            print(f"Using remembered subprocess approach for {domain}")
            try:
                html = self._fetch_playwright_subprocess(url, headless=True)
                if html and not self._is_protection_page(html):
                    print(f"SUCCESS with remembered subprocess approach!")
                    return html
            except Exception as e:
                print(f"Remembered subprocess approach failed: {e}")
        # Try all 4 approaches: headless+no-proxy, headless+proxy, non-headless+no-proxy, non-headless+proxy
        approaches = [
            {'headless': True, 'use_proxy': False, 'label': 'headless + no proxy'},
            {'headless': True, 'use_proxy': True, 'label': 'headless + proxy'}, 
            {'headless': False, 'use_proxy': False, 'label': 'non-headless + no proxy'},
            {'headless': False, 'use_proxy': True, 'label': 'non-headless + proxy'}
        ]
        
        for approach in approaches:
            headless_mode = approach['headless']
            use_proxy = approach['use_proxy']
            try:
                print(f"Trying Playwright {approach['label']} mode for {url}")
                # Note: Skip event loop cleanup as it causes conflicts
                # The subprocess fallback handles event loop issues automatically
                
                with sync_playwright() as p:
                    if fast_mode:
                        # Fast mode: minimal arguments for speed
                        browser_args = [
                            '--no-sandbox',
                            '--disable-dev-shm-usage',
                            '--disable-extensions'
                        ]
                        selected_viewport = {"width": 1920, "height": 1080}
                        slow_mo_delay = 0  # No delay for fast mode
                    else:
                        # Stealth mode: full anti-detection (for full analysis)
                        browser_args = [
                            '--no-sandbox',
                            '--disable-blink-features=AutomationControlled',
                            '--exclude-switches=enable-automation',
                            '--disable-web-security',
                            '--disable-extensions',
                            '--disable-plugins',
                            '--disable-background-timer-throttling',
                            '--disable-renderer-backgrounding',
                            '--disable-backgrounding-occluded-windows',
                            '--disable-default-apps',
                            '--disable-sync',
                            '--disable-translate',
                            '--hide-scrollbars',
                            '--mute-audio',
                            '--no-default-browser-check',
                            '--disable-ipc-flooding-protection',
                            '--password-store=basic',
                            '--use-mock-keychain',
                            '--disable-dev-shm-usage',
                            '--disable-field-trial-config',
                            '--no-first-run',
                            '--disable-background-networking',
                            '--disable-client-side-phishing-detection',
                            '--disable-component-extensions-with-background-pages',
                            '--disable-domain-reliability',
                            '--disable-features=TranslateUI',
                            '--force-color-profile=srgb',
                            '--metrics-recording-only',
                            '--safebrowsing-disable-auto-update'
                        ]
                        # Random viewport dimensions
                        viewports = [
                            {"width": 1920, "height": 1080},
                            {"width": 1366, "height": 768},
                            {"width": 1536, "height": 864},
                            {"width": 1440, "height": 900},
                            {"width": 1600, "height": 900}
                        ]
                        selected_viewport = random.choice(viewports)
                        slow_mo_delay = random.randint(50, 150)
                    
                    # Launch browser
                    browser = p.chromium.launch(
                        headless=headless_mode,
                        args=browser_args,
                        slow_mo=slow_mo_delay,
                        devtools=False
                    )
                
                # Setup proxy if this approach uses proxy
                proxy_dict = None
                if use_proxy and self.proxies:
                    proxy = self.proxies[0]  # Only one proxy (Webshare)
                    
                    # Configure Webshare proxy for Playwright
                    proxy_dict = {
                        "server": proxy['server'],
                        "username": proxy['username'], 
                        "password": proxy['password']
                    }
                    print(f"Using Playwright Webshare proxy: {proxy['server']}")
                else:
                    print(f"Running without proxy")
                # Context arguments (fast vs stealth mode)
                if fast_mode:
                    # Fast mode: minimal context setup
                    context_args = {
                        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "viewport": selected_viewport
                    }
                else:
                    # Stealth mode: full anti-detection
                    timezones = [
                        "America/New_York",
                        "America/Chicago", 
                        "America/Denver",
                        "America/Los_Angeles",
                        "Europe/London",
                        "Europe/Berlin"
                    ]
                    
                    context_args = {
                        "user_agent": self._get_random_user_agent(),
                        "viewport": selected_viewport,
                        "locale": random.choice(["en-US", "en-GB", "en-CA"]),
                        "timezone_id": random.choice(timezones),
                        "permissions": ["geolocation", "notifications"],
                        "geolocation": {
                            "latitude": round(random.uniform(25, 48), 6),
                            "longitude": round(random.uniform(-125, -65), 6),
                            "accuracy": random.randint(100, 1000)
                        },
                        "color_scheme": random.choice(["light", "dark", "no-preference"]),
                        "reduced_motion": random.choice(["reduce", "no-preference"]),
                        "forced_colors": random.choice(["active", "none"]),
                        "extra_http_headers": {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                            "Accept-Language": "en-US,en;q=0.9",
                            "Accept-Encoding": "gzip, deflate, br",
                            "Connection": "keep-alive",
                            "Upgrade-Insecure-Requests": "1",
                            "Sec-Fetch-Dest": "document",
                            "Sec-Fetch-Mode": "navigate",
                            "Sec-Fetch-Site": "none",
                            "Sec-Fetch-User": "?1",
                            "Cache-Control": "max-age=0",
                            "DNT": "1",
                            "Sec-Ch-Ua": f'"Not_A Brand";v="8", "Chromium";v="{random.randint(110, 125)}", "Google Chrome";v="{random.randint(110, 125)}"',
                            "Sec-Ch-Ua-Mobile": "?0",
                            "Sec-Ch-Ua-Platform": f'"{random.choice(["Windows", "macOS", "Linux"])}"',
                            "Sec-Ch-Ua-Platform-Version": f'"{random.randint(10, 15)}.{random.randint(0, 9)}.{random.randint(0, 9)}"'
                        }
                    }
                
                if proxy_dict:
                    context_args["proxy"] = proxy_dict
                
                context = browser.new_context(**context_args)
                
                # Add stealth scripts only in stealth mode
                if not fast_mode:
                    context.add_init_script(self._get_playwright_stealth_script())
                
                # Additional fingerprint randomization
                random_height_offset = random.randint(30, 80)
                random_graphics_number = random.randint(5000, 6000)
                
                context.add_init_script(f"""
                    // Randomize screen properties
                    Object.defineProperty(screen, 'width', {{
                        get: () => {selected_viewport["width"]}
                    }});
                    Object.defineProperty(screen, 'height', {{
                        get: () => {selected_viewport["height"]}
                    }});
                    Object.defineProperty(screen, 'availWidth', {{
                        get: () => {selected_viewport["width"]}
                    }});
                    Object.defineProperty(screen, 'availHeight', {{
                        get: () => {selected_viewport["height"] - random_height_offset}
                    }});
                    
                    // Randomize WebGL properties
                    const getParameter = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                        if (parameter === 37445) {{
                            return 'Intel Inc.';
                        }}
                        if (parameter === 37446) {{
                            return 'Intel(R) Iris(TM) Graphics {random_graphics_number}';
                        }}
                        return getParameter.call(this, parameter);
                    }};
                """)
                
                page = context.new_page()
                
                # Multi-strategy navigation like in the working script
                success = self._playwright_navigate_with_retry(page, url)
                
                if success:
                    # Wait for complete page load after navigation
                    page.wait_for_load_state('domcontentloaded')
                    
                    # Wait for network activity to settle
                    try:
                        page.wait_for_load_state('networkidle', timeout=10000)
                    except:
                        # If networkidle fails, wait for dynamic content
                        page.wait_for_timeout(5000)
                    
                    # Additional wait to ensure all content is loaded
                    page.wait_for_timeout(3000)
                    
                    # Simulate human-like behavior
                    self._simulate_human_behavior(page)
                    
                    # Get page content
                    html = page.content()
                    
                    # Check if we got a valid page
                    if not self._is_protection_page(html):
                        print_success(f"Successfully fetched page with Playwright {approach['label']} mode ({len(html)} characters)")
                        browser.close()
                        return html
                    else:
                        print(f"Still seeing protection page after Playwright {approach['label']} bypass")
                        browser.close()
                        
            except Exception as e:
                if 'browser' in locals():
                    try:
                        browser.close()
                    except:
                        pass
                print(f"Playwright {approach['label']} mode failed: {e}")
                # If it's an event loop error, immediately use subprocess approach
                if "Event loop is closed" in str(e) or "event loop" in str(e).lower():
                    print(f"Event loop conflict detected, using subprocess approach for {approach['label']} mode")
                    try:
                        html = self._fetch_playwright_subprocess(url, headless_mode)
                        if html and not self._is_protection_page(html):
                            print(f"SUCCESS with Playwright subprocess {approach['label']} mode!")
                            # Record this success in approach memory
                            if hasattr(self, 'approach_memory'):
                                self.approach_memory.record_successful_approach(url, 'playwright_subprocess')
                            return html
                    except Exception as subprocess_error:
                        print(f"Subprocess approach failed: {subprocess_error}")
                continue
        
        # If all 4 approaches failed
        print_error("All 4 Playwright approaches failed (headless+no-proxy, headless+proxy, non-headless+no-proxy, non-headless+proxy)")
        return None
    
    def _fetch_playwright_subprocess(self, url: str, headless: bool = True) -> Optional[str]:
        """Fallback: Run Playwright in a subprocess to avoid event loop conflicts"""
        import subprocess
        import tempfile
        import json
        import os
        import sys
        
        try:
            # Create a temporary script to run Playwright
            script_content = f'''
import sys
from playwright.sync_api import sync_playwright
import json

def fetch_with_playwright():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless={headless},
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()
            page.goto("{url}", wait_until="load", timeout=60000)
            page.wait_for_load_state('domcontentloaded')
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except:
                page.wait_for_timeout(5000)
            page.wait_for_timeout(3000)
            
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"Error: {{e}}", file=sys.stderr)
        return None

result = fetch_with_playwright()
if result:
    # Ensure UTF-8 output to handle Unicode characters
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(result)
'''
            
            # Write script to temporary file with UTF-8 encoding
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                script_path = f.name
            
            # Set environment for UTF-8 handling
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            # Run the script in a subprocess with UTF-8 encoding
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',  # Replace problematic characters
                env=env,
                timeout=120  # 2 minutes timeout
            )
            
            # Clean up temporary file
            try:
                os.unlink(script_path)
            except:
                pass
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            else:
                print(f"Subprocess failed: {result.stderr}")
                return None
                
        except Exception as e:
            print(f"Subprocess execution failed: {e}")
            return None
    
    def _playwright_navigate_with_retry(self, page, url: str, max_retries: int = 3) -> bool:
        """Navigate with advanced retry strategies from the working script"""
        
        # Different referrer strategies
        referrers = [
            "https://www.google.com/",
            "https://www.bing.com/",
            "https://duckduckgo.com/",
            "https://www.yahoo.com/",
            None  # Direct access
        ]
        
        for attempt in range(max_retries):
            try:
                print(f"Playwright attempt {attempt + 1}/{max_retries} for URL: {url}")
                # Progressive delay between attempts
                if attempt > 0:
                    delay = random.uniform(3, 8) * (attempt + 1)
                    print(f"Waiting {delay:.1f} seconds before retry...")
                    time.sleep(delay)
                
                # Strategy 1: Direct navigation
                if attempt == 0:
                    print("Strategy: Direct navigation")
                    response = page.goto(url, timeout=60000, wait_until="load")
                
                # Strategy 2: Navigate via homepage first
                elif attempt == 1:
                    print("Strategy: Navigate via homepage and build session")
                    parsed = urlparse(url)
                    homepage = f"{parsed.scheme}://{parsed.netloc}"
                    
                    try:
                        # Go to homepage first
                        print("Loading homepage to establish session...")
                        home_response = page.goto(homepage, timeout=30000, wait_until="load")
                        if home_response.status == 200:
                            print("Homepage loaded successfully")
                            time.sleep(random.uniform(2, 4))
                            response = page.goto(url, timeout=60000, wait_until="load")
                        else:
                            response = page.goto(url, timeout=60000, wait_until="load")
                    except Exception as e:
                        print(f"Homepage strategy error: {e}")
                        response = page.goto(url, timeout=60000, wait_until="load")
                
                # Strategy 3: Simulate search engine click
                else:
                    print("Strategy: Simulate search engine referral")
                    try:
                        google_url = f"https://www.google.com/search?q=site:{urlparse(url).netloc}"
                        page.goto(google_url, timeout=30000, wait_until="load")
                        time.sleep(random.uniform(2, 4))
                        response = page.goto(url, timeout=60000, wait_until="load")
                    except:
                        response = page.goto(url, timeout=60000, wait_until="load")
                
                # Check response status
                if response and response.status == 200:
                    print(f"Successfully loaded page (HTTP {response.status})")
                    return True
                elif response and response.status == 403:
                    print(f"403 Forbidden on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        print("All bypass strategies failed with 403")
                        return False
                else:
                    status = response.status if response else "No response"
                    print(f"HTTP {status} - retrying with different strategy")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return False
                        
            except Exception as e:
                print(f"Error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    continue
                else:
                    return False
        
        return False
    
    def _simulate_human_behavior(self, page):
        """Simulate human-like behavior on the page"""
        try:
            # Random initial wait (like a human reading)
            initial_wait = random.uniform(1, 3)
            time.sleep(initial_wait)
            
            # Simulate mouse movements
            for i in range(random.randint(2, 4)):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                page.mouse.move(x, y)
                time.sleep(random.uniform(0.2, 0.5))
            
            # Random scrolling behavior
            scroll_count = random.randint(1, 3)
            for i in range(scroll_count):
                scroll_distance = random.randint(200, 600)
                page.evaluate(f"window.scrollBy(0, {scroll_distance})")
                time.sleep(random.uniform(0.5, 1.5))
                
                # Sometimes scroll back up
                if random.random() > 0.7:
                    page.evaluate(f"window.scrollBy(0, -{scroll_distance // 2})")
                    time.sleep(random.uniform(0.3, 0.8))
            
            # Scroll back to top
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(random.uniform(0.5, 1))
            
        except Exception as e:
            print(f"Human behavior simulation error (continuing): {e}")
    def _fetch_with_selenium(self, url: str) -> Optional[str]:
        """Fetch page using Selenium with advanced protection bypass"""
        if not self.use_selenium:
            return None
        
        driver = None
        try:
            # Enhanced Chrome options for better stealth
            if UNDETECTED_CHROME_AVAILABLE:
                print("Using undetected Chrome driver with advanced stealth")
                options = uc.ChromeOptions()
                
                # Advanced stealth arguments
                stealth_args = [
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-default-apps',
                    '--disable-sync',
                    '--disable-translate',
                    '--hide-scrollbars',
                    '--mute-audio',
                    '--no-default-browser-check',
                    '--disable-ipc-flooding-protection',
                    '--password-store=basic',
                    '--use-mock-keychain',
                    '--disable-background-networking',
                    '--disable-default-apps',
                    '--disable-dev-shm-usage',
                    '--disable-features=VizDisplayCompositor,TranslateUI',
                    '--disable-hang-monitor',
                    '--disable-prompt-on-repost',
                    '--disable-component-update',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-logging',
                    '--disable-background-timer-throttling',
                    '--disable-breakpad',
                    '--disable-client-side-phishing-detection',
                    '--disable-crash-reporter',
                    '--disable-extensions-file-access-check',
                    '--disable-extensions-http-throttling'
                ]
                
                for arg in stealth_args:
                    options.add_argument(arg)
                
                # Remove automation indicators
                options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
                options.add_experimental_option('useAutomationExtension', False)
                
                # Random user agent
                options.add_argument(f'--user-agent={random.choice(self.user_agents)}')
                
                # Add proxy if available
                if self.proxies:
                    proxy = random.choice(self.proxies)
                    
                    # Use Webshare proxy (only proxy type we support now)
                    if 'server' in proxy:
                        server = proxy['server'].replace('http://', '').replace('https://', '')
                        options.add_argument(f'--proxy-server={server}')
                        print(f"Using Webshare proxy {server}")
                driver = uc.Chrome(options=options)
                
                # Advanced stealth scripts
                stealth_script = self._get_advanced_stealth_script()
                driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': stealth_script})
            
            # Fallback to regular Chrome with enhanced stealth
            else:
                print("Using regular Chrome driver with enhanced stealth")
                options = ChromeOptions()
                # options.add_argument('--headless')  # Visible browser for debugging
                
                # Add the same stealth arguments
                stealth_args = [
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-extensions',
                    '--disable-plugins'
                ]
                
                for arg in stealth_args:
                    options.add_argument(arg)
                
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                options.add_argument(f'--user-agent={random.choice(self.user_agents)}')
                
                driver = webdriver.Chrome(options=options)
                
                # Basic stealth script
                basic_stealth = """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                delete Object.getPrototypeOf(navigator).webdriver;
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                """
                driver.execute_script(basic_stealth)
            
            # Navigate to page with random delay
            time.sleep(random.uniform(1, 3))
            driver.get(url)
            
            # Wait for page load and handle potential challenges
            time.sleep(random.uniform(3, 6))
            
            # Check for protection challenges and handle them
            challenge_handled = self._handle_protection_challenges(driver)
            if challenge_handled:
                time.sleep(random.uniform(5, 8))
            
            # Additional wait for dynamic content
            time.sleep(random.uniform(2, 4))
            
            # Get page source
            html = driver.page_source
            
            # Check if we got a valid page
            if self._is_protection_page(html):
                print("Still seeing protection page after advanced bypass")
                return None
            
            print_success(f"Successfully fetched page content ({len(html)} characters)")
            return html
            
        except Exception as e:
            print(f"Selenium fetch failed: {e}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def _get_advanced_stealth_script(self) -> str:
        """Get advanced stealth script for bypassing detection"""
        return """
        // Advanced stealth script for bypassing bot detection
        
        // Hide webdriver property more thoroughly
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
        
        // Delete webdriver property from prototype
        delete Object.getPrototypeOf(navigator).webdriver;
        
        // Override automation flags
        Object.defineProperty(navigator, 'permissions', {
            get: () => ({
                query: () => Promise.resolve({ state: 'granted' })
            }),
        });
        
        // Spoof Chrome runtime
        window.chrome = {
            app: {
                isInstalled: false,
                InstallState: {
                    DISABLED: 'disabled',
                    INSTALLED: 'installed',
                    NOT_INSTALLED: 'not_installed'
                },
                RunningState: {
                    CANNOT_RUN: 'cannot_run',
                    READY_TO_RUN: 'ready_to_run',
                    RUNNING: 'running'
                }
            },
            runtime: {
                onConnect: null,
                onMessage: null,
                onStartup: null,
                onInstalled: null,
                onSuspend: null,
                onSuspendCanceled: null,
                onUpdateAvailable: null,
                id: 'fake-extension-id'
            }
        };
        
        // Spoof plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        // Spoof languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        
        // Spoof platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
        });
        
        // Mock getParameter function for WebGL
        const getParameter = WebGLRenderingContext.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel(R) Iris(TM) Graphics 6100';
            }
            return getParameter(parameter);
        };
        
        // Mock getBattery
        navigator.getBattery = () => Promise.resolve({
            charging: true,
            chargingTime: 0,
            dischargingTime: Infinity,
            level: 1
        });
        
        // Override Date to be consistent
        Date.prototype.getTimezoneOffset = () => -new Date().getTimezoneOffset();
        
        // Spoof screen properties
        Object.defineProperty(screen, 'colorDepth', {get: () => 24});
        Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
        
        // Remove automation indicators
        ['__driver_evaluate', '__webdriver_evaluate', '__selenium_evaluate', '__fxdriver_evaluate', '__driver_unwrapped', '__webdriver_unwrapped', '__selenium_unwrapped', '__fxdriver_unwrapped', '_Selenium_IDE_Recorder', '_selenium', 'calledSelenium', '_WEBDRIVER_ELEM_CACHE', 'ChromeDriverw', 'driver-evaluate', 'webdriver-evaluate', 'selenium-evaluate', 'webdriverCommand', 'webdriver-evaluate-response'].forEach(prop => {
            delete window[prop];
        });
        
        // Mock notification permission
        Object.defineProperty(Notification, 'permission', {
            get: () => 'default'
        });
        
        console.log('Advanced stealth script loaded');
        """
    
    def _is_protection_page(self, html: str) -> bool:
        """Check if page is a protection/challenge page (NOT marketing popups)"""
        # More specific protection indicators to avoid false positives
        # Note: cf-ray appears in headers of successful requests, so we need to be more specific
        protection_indicators = [
            'incapsula incident id', 'imperva', 'cloudflare ray id',
            'checking your browser before', 'ddos protection by',
            'please wait while we', 'security check in progress', 
            'bot detection', 'access denied by', 'blocked by',
            'solve this challenge', 'complete the captcha',
            'human verification required', 'ray id:',
            'attention required! cloudflare', 'checking if the site connection is secure',
            'enable javascript and cookies to continue'
        ]
        
        html_lower = html.lower()
        detected_protection = []
        
        for indicator in protection_indicators:
            if indicator in html_lower:
                detected_protection.append(indicator)
        
        # Only return True if we have strong evidence of protection
        if detected_protection:
            self.analysis_results['protection_detected'].extend(detected_protection)
            print(f"Real protection detected: {', '.join(detected_protection)}")
            return True
            
        # Additional check: if page is very short and contains protection keywords
        if len(html) < 5000 and any(word in html_lower for word in ['access denied', 'blocked', 'forbidden']):
            self.analysis_results['protection_detected'].append('short_protection_page')
            print("Short protection page detected")
            return True
            
        return False
    
    def _handle_protection_challenges(self, driver) -> bool:
        """Handle various protection challenges"""
        try:
            # Wait for potential challenges to appear
            time.sleep(2)
            
            # Check for Cloudflare challenge
            if "checking your browser" in driver.page_source.lower():
                print("Detected Cloudflare challenge, waiting...")
                WebDriverWait(driver, 10).until(
                    lambda d: "checking your browser" not in d.page_source.lower()
                )
                return True
            
            # Check for other challenge patterns
            challenge_patterns = [
                "please wait", "loading", "redirecting"
            ]
            
            for pattern in challenge_patterns:
                if pattern in driver.page_source.lower():
                    print(f"Detected challenge pattern: {pattern}")
                    time.sleep(5)
                    return True
            
        except TimeoutException:
            print("Timeout waiting for challenge to complete")
        except Exception as e:
            print(f"Error handling challenges: {e}")
        return False
    
    def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page with multiple fallback methods using approach memory"""
        print(f"Fetching: {url}")
        domain = self.approach_memory.get_domain_from_url(url)
        successful_approach = self.approach_memory.get_successful_approach(domain)
        
        if successful_approach:
            print(f"Using remembered successful approach: {successful_approach} for {domain}")
            # Try the remembered approach first
            if successful_approach == 'requests':
                html = self._fetch_simple_like_validate(url)
                if html and not self._is_protection_page(html):
                    print_success(f"SUCCESS with remembered {successful_approach} approach!")
                    return html
            elif successful_approach == 'playwright' and self.use_playwright:
                html = self._fetch_with_playwright(url, fast_mode=True)
                if html and not self._is_protection_page(html):
                    print_success(f"SUCCESS with remembered {successful_approach} approach!")
                    return html
            elif successful_approach == 'selenium' and self.use_selenium:
                html = self._fetch_with_selenium(url)
                if html and not self._is_protection_page(html):
                    print_success(f"SUCCESS with remembered {successful_approach} approach!")
                    return html
        
        # Try SIMPLE approach first (if not already tried)
        if successful_approach != 'requests':
            html = self._fetch_simple_like_validate(url)
            if html and not self._is_protection_page(html):
                print("SUCCESS with simple validate.py-style approach!")
                self.approach_memory.record_successful_approach(domain, 'requests')
                return html
        
        # If simple approach got cf-ray protection, try specialized bypass
        if html and 'cf-ray' in html.lower():
            print("CF-RAY protection detected, trying specialized bypass...")
            # Try requests-based cf-ray bypass first
            cf_html = self._fetch_cf_ray_bypass(url)
            if cf_html and not self._is_protection_page(cf_html):
                print("SUCCESS with CF-RAY bypass approach!")
                return cf_html
            
            # If requests cf-ray bypass fails, try advanced Playwright bypass
            if self.use_playwright:
                print("Trying advanced Playwright CF-RAY bypass...")
                pw_cf_html = self._fetch_playwright_cf_ray_bypass(url)
                if pw_cf_html and not self._is_protection_page(pw_cf_html):
                    print("SUCCESS with advanced Playwright CF-RAY bypass!")
                    return pw_cf_html
        
        # Try Playwright second (if simple fails and not already tried)
        if self.use_playwright and successful_approach != 'playwright':
            html = self._fetch_with_playwright(url, fast_mode=True)
            if html and not self._is_protection_page(html):
                print("SUCCESS with Playwright approach!")
                self.approach_memory.record_successful_approach(domain, 'playwright')
                return html
        
        # Fallback to Selenium (if not already tried)
        if self.use_selenium and successful_approach != 'selenium':
            html = self._fetch_with_selenium(url)
            if html and not self._is_protection_page(html):
                print("SUCCESS with Selenium approach!")
                self.approach_memory.record_successful_approach(domain, 'selenium')
                return html
        
        # Final fallback to complex requests
        html = self._fetch_with_requests(url)
        if html and not self._is_protection_page(html):
            return html
        
        # If proxies failed, try without proxies as last resort
        if self.proxy_fallback_available and self.proxies:
            print("Proxy methods failed, trying without proxies as fallback")
            original_proxies = self.proxies
            self.proxies = []  # Temporarily disable proxies
            
            # Try Playwright without proxies
            if self.use_playwright:
                html = self._fetch_with_playwright(url, fast_mode=True)
                if html and not self._is_protection_page(html):
                    print("Success with Playwright (no proxy)")
                    self.proxies = original_proxies  # Restore proxies
                    return html
            
            # Try requests without proxies
            html = self._fetch_with_requests(url)
            self.proxies = original_proxies  # Restore proxies
            if html and not self._is_protection_page(html):
                print("Success with requests (no proxy)")
                return html
        
        print_error(f"Failed to fetch {url} with all methods")
        return None
    
    def analyze_homepage(self) -> Dict[str, Any]:
        """Analyze the homepage structure"""
        print_info("Analyzing homepage...")
        html = self.fetch_page(self.base_url)
        if not html:
            self.analysis_results['errors'].append("Failed to fetch homepage")
            return {}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Save homepage for inspection
        homepage_file = f"{self.domain}_homepage.html"
        with open(homepage_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Extract basic site info
        site_info = {
            'title': soup.find('title').get_text(strip=True) if soup.find('title') else '',
            'description': '',
            'platform_indicators': [],
            'navigation_links': [],
            'potential_catalog_links': []
        }
        
        # Get meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            site_info['description'] = meta_desc.get('content', '')
        
        # Detect e-commerce platform
        platform_indicators = self._detect_ecommerce_platform(html, soup)
        site_info['platform_indicators'] = platform_indicators
        
        # Find navigation and catalog links
        nav_links = self._find_navigation_links(soup)
        site_info['navigation_links'] = nav_links[:20]  # Limit to first 20
        
        catalog_links = self._find_catalog_links(soup)
        site_info['potential_catalog_links'] = catalog_links[:10]  # Limit to first 10
        
        self.analysis_results['site_info'] = site_info
        self.analysis_results['sample_pages']['homepage'] = homepage_file
        
        print(f"Homepage analysis complete. Found {len(catalog_links)} potential catalog links")
        return site_info
    
    def _detect_ecommerce_platform(self, html: str, soup: BeautifulSoup) -> List[str]:
        """Detect e-commerce platform"""
        indicators = []
        html_lower = html.lower()
        
        platform_patterns = {
            'shopify': ['shopify', 'myshopify.com', 'shopifycdn.com', '__st ='],
            'woocommerce': ['woocommerce', 'wp-content/plugins/woocommerce'],
            'magento': ['magento', 'mage/', 'var FORM_KEY'],
            'bigcommerce': ['bigcommerce', 'cdn.bcapp.dev'],
            'prestashop': ['prestashop', 'ps_'],
            'opencart': ['index.php?route=', 'catalog/view/theme/'],
            'squarespace': ['squarespace.com', 'static1.squarespace.com'],
            'wix': ['wix.com', 'static.wixstatic.com']
        }
        
        for platform, patterns in platform_patterns.items():
            for pattern in patterns:
                if pattern in html_lower:
                    indicators.append(platform)
                    break
        
        return indicators
    
    def _find_navigation_links(self, soup: BeautifulSoup) -> List[Dict]:
        """Find navigation links"""
        nav_links = []
        
        # Look for navigation elements
        nav_selectors = [
            'nav a', 'header a', '.navigation a', '.nav a',
            '.menu a', '.navbar a', '#navigation a', '#nav a'
        ]
        
        for selector in nav_selectors:
            try:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    if href and text:
                        nav_links.append({
                            'href': href,
                            'text': text,
                            'classes': link.get('class', [])
                        })
            except Exception:
                continue
        
        return nav_links
    
    def _find_catalog_links(self, soup: BeautifulSoup) -> List[Dict]:
        """Find potential catalog/category links"""
        catalog_links = []
        
        # Keywords that indicate product categories
        catalog_keywords = [
            'product', 'category', 'catalog', 'shop', 'store',
            'collection', 'browse', 'taxonomy', 'department'
        ]
        
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '').lower()
            text = link.get_text(strip=True).lower()
            
            # Check if link contains catalog keywords
            if any(keyword in href or keyword in text for keyword in catalog_keywords):
                catalog_links.append({
                    'href': link.get('href'),
                    'text': link.get_text(strip=True),
                    'classes': link.get('class', [])
                })
        
        return catalog_links
    
    def analyze_catalog_page(self, catalog_url: str = None) -> Dict[str, Any]:
        """Analyze a catalog/category page"""
        if not catalog_url:
            # Try to find a catalog URL from homepage analysis
            catalog_links = self.analysis_results.get('site_info', {}).get('potential_catalog_links', [])
            if not catalog_links:
                print("No catalog URL provided and none found in homepage")
                return {}
            catalog_url = urljoin(self.base_url, catalog_links[0]['href'])
        
        print_info(f"Analyzing catalog page: {catalog_url}")
        html = self.fetch_page(catalog_url)
        if not html:
            self.analysis_results['errors'].append(f"Failed to fetch catalog page: {catalog_url}")
            return {}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Save catalog page for inspection
        catalog_file = f"{self.domain}_catalog.html"
        with open(catalog_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Find product links
        product_patterns = self._find_product_link_patterns(soup, html)
        self.analysis_results['product_patterns'] = product_patterns
        self.analysis_results['sample_pages']['catalog'] = catalog_file
        
        # Find pagination patterns
        pagination_patterns = self._find_pagination_patterns(soup)
        
        print(f"Catalog analysis complete. Found {len(product_patterns)} product link patterns")
        return {
            'catalog_url': catalog_url,
            'product_patterns': product_patterns,
            'pagination_patterns': pagination_patterns
        }
    
    def _find_product_link_patterns(self, soup: BeautifulSoup, html: str) -> List[Dict]:
        """Find product link patterns with AI assistance"""
        patterns = []
        
        # AI analysis as PRIMARY method for pattern detection
        ai_patterns_found = False
        if self.use_ai:
            ai_patterns = self._ai_analyze_html_for_patterns(html, "product_links")
            if ai_patterns.get('product_link_patterns'):
                for ai_pattern in ai_patterns['product_link_patterns']:
                    # Test the AI-generated selector
                    original_selector = ai_pattern['selector']
                    actual_count = self._test_selector_on_page(original_selector, html)
                    # If original selector fails, try fallback patterns
                    if actual_count == 0:
                        # Try without leading/trailing slashes (common issue)
                        fallback_selectors = []
                        if '/product/' in original_selector:
                            fallback_selectors.append(original_selector.replace('/product/', 'product'))
                        if '/item/' in original_selector:
                            fallback_selectors.append(original_selector.replace('/item/', 'item'))
                        if '/p/' in original_selector:
                            fallback_selectors.append(original_selector.replace('/p/', 'p'))
                        
                        for fallback in fallback_selectors:
                            fallback_count = self._test_selector_on_page(fallback, html)
                            if fallback_count > actual_count:
                                actual_count = fallback_count
                                ai_pattern['selector'] = fallback  # Update the selector
                                break
                    
                    if actual_count > 0:
                        # Extract examples for the AI pattern
                        ai_examples = []
                        try:
                            soup_temp = BeautifulSoup(html, 'html.parser')
                            ai_links = soup_temp.select(ai_pattern['selector'])[:5]
                            for link in ai_links:
                                ai_examples.append({
                                    'href': link.get('href', ''),
                                    'text': link.get_text(strip=True),
                                    'classes': link.get('class', [])
                                })
                        except:
                            pass
                        
                        patterns.append({
                            'pattern': 'ai_generated',
                            'selector': ai_pattern['selector'],
                            'count': actual_count,
                            'examples': ai_examples,
                            'explanation': f"AI-detected: {ai_pattern['explanation']}",
                            'confidence': ai_pattern.get('confidence', 0.9)  # Higher confidence for AI
                        })
                        print(f"AI found pattern: {ai_pattern['selector']} ({actual_count} matches)")
                        ai_patterns_found = True
        
        # If AI found good patterns, prioritize them but still run traditional analysis as backup
        if ai_patterns_found:
            print("AI successfully identified product patterns - traditional analysis will supplement")
        all_links = soup.find_all('a', href=True)
        
        # Enhanced product URL patterns
        product_indicators = [
            # Common patterns
            '/product/', '/item/', '/p/', '/products/', '/productdetail/', '/detail/', '/pd/', '/prod/',
            # More specific patterns
            '/catalog/', '/shop/', '/buy/', '/goods/', '/merchandise/', '/sku/', '/model/',
            # ID-based patterns
            '/id/', '/item-id/', '/product-id/', '/pid/',
            # Category-based patterns that might lead to products
            '/category/', '/cat/', '/c/', '/taxonomy/', '/department/', '/section/'
        ]
        
        # Group links by patterns
        pattern_groups = {}
        href_analysis = {}
        
        for link in all_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Skip empty, too long, or obvious navigation links
            if (not href or not text or len(text) > 300 or 
                any(nav in text.lower() for nav in ['home', 'login', 'register', 'cart', 'checkout', 'search', 'contact', 'about'])):
                continue
            
            # Check for data attributes that indicate product links
            data_event_type = link.get('data-event-type', '')
            if data_event_type == 'product-click':
                best_indicator = 'data-product-click'
            else:
                # Analyze href structure for patterns
                href_lower = href.lower()
                
                # Check for product indicators
                best_indicator = None
                for indicator in product_indicators:
                    if indicator in href_lower:
                        best_indicator = indicator
                        break
            
            if best_indicator:
                if best_indicator not in pattern_groups:
                    pattern_groups[best_indicator] = []
                
                pattern_groups[best_indicator].append({
                    'href': href,
                    'text': text,
                    'classes': link.get('class', []),
                    'parent_tag': link.parent.name if link.parent else None,
                    'parent_classes': link.parent.get('class', []) if link.parent else [],
                    'full_link_html': str(link)
                })
            else:
                # Analyze for potential product links without obvious indicators
                self._analyze_link_for_product_potential(href, text, link, href_analysis)
        
        # Generate CSS selectors for each pattern group
        for pattern_key, links in pattern_groups.items():
            if len(links) >= 1:  # Consider even single matches for specific patterns
                selector = self._generate_css_selector(pattern_key, links)
                confidence = self._calculate_pattern_confidence(pattern_key, links)
                
                # Test the selector on the actual page to get real count
                actual_count = self._test_selector_on_page(selector, html)
                
                patterns.append({
                    'pattern': pattern_key,
                    'selector': selector,
                    'count': actual_count,  # Use actual count from page test
                    'examples': links[:5],  # First 5 examples
                    'explanation': f"Links containing '{pattern_key}' pattern",
                    'confidence': confidence
                })
        
        # Add patterns from href analysis
        patterns.extend(self._generate_patterns_from_href_analysis(href_analysis, html))
        
        # If no specific patterns found, try generic approaches
        if not patterns:
            patterns.extend(self._find_generic_product_patterns(soup))
        
        # Sort patterns by confidence and count
        patterns.sort(key=lambda x: (x.get('confidence', 0), x.get('count', 0)), reverse=True)
        
        return patterns
    
    def _analyze_link_for_product_potential(self, href: str, text: str, link, href_analysis: Dict):
        """Analyze a link for potential product indicators"""
        # Look for numeric patterns (often product IDs)
        if re.search(r'/\d+/?$', href) or re.search(r'id=\d+', href):
            href_analysis.setdefault('numeric_ids', []).append({
                'href': href, 'text': text, 'classes': link.get('class', [])
            })
        
        # Look for alphanumeric patterns (often SKUs/codes)
        if re.search(r'/[A-Za-z0-9\-_]{6,}/?$', href):
            href_analysis.setdefault('alphanumeric_codes', []).append({
                'href': href, 'text': text, 'classes': link.get('class', [])
            })
        
        # Look for potential product names in URLs
        if (len(href.split('/')) >= 3 and 
            not any(common in href.lower() for common in ['about', 'contact', 'blog', 'news', 'help', 'support'])):
            href_analysis.setdefault('potential_product_names', []).append({
                'href': href, 'text': text, 'classes': link.get('class', [])
            })
    
    def _calculate_pattern_confidence(self, pattern_key: str, links: List[Dict]) -> float:
        """Calculate confidence score for a pattern"""
        confidence = 0.5  # Base confidence
        
        # Very high confidence for data attribute patterns
        if pattern_key == 'data-product-click':
            confidence += 0.4  # Higher than URL patterns
        
        # Higher confidence for specific product patterns
        high_confidence_patterns = ['/product/', '/productdetail/', '/item/', '/p/']
        if pattern_key in high_confidence_patterns:
            confidence += 0.3
        
        # Boost confidence based on number of links
        if len(links) >= 10:
            confidence += 0.2
        elif len(links) >= 5:
            confidence += 0.1
        
        # Boost confidence if links have product-related classes
        product_classes = ['product', 'item', 'card', 'tile', 'listing']
        class_matches = 0
        for link in links[:10]:  # Check first 10 links
            link_classes = ' '.join(link.get('classes', [])).lower()
            if any(pc in link_classes for pc in product_classes):
                class_matches += 1
        
        if class_matches > len(links) * 0.5:  # More than 50% have product classes
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _generate_patterns_from_href_analysis(self, href_analysis: Dict, html: str = '') -> List[Dict]:
        """Generate patterns from href analysis"""
        patterns = []
        
        for pattern_type, links in href_analysis.items():
            if len(links) >= 3:  # Need at least 3 examples
                if pattern_type == 'numeric_ids':
                    # Simplified selector - check for common patterns in actual links
                    common_path = self._find_common_href_pattern([link['href'] for link in links])
                    selector = f"a[href*='{common_path}']" if common_path else "a[href*='/product']"
                    explanation = "Links with numeric IDs at the end"
                elif pattern_type == 'alphanumeric_codes':
                    # Simplified selector - check for common patterns in actual links
                    common_path = self._find_common_href_pattern([link['href'] for link in links])
                    selector = f"a[href*='{common_path}']" if common_path else "a[href*='/item']"
                    explanation = "Links with alphanumeric codes"
                else:
                    continue
                
                # Test the selector on the actual page to get real count
                actual_count = self._test_selector_on_page(selector, html)
                
                patterns.append({
                    'pattern': pattern_type,
                    'selector': selector,
                    'count': actual_count,  # Use actual count from page test
                    'examples': links[:3],
                    'explanation': explanation,
                    'confidence': 0.3  # Lower confidence for inferred patterns
                })
        
        return patterns
    
    def _find_common_href_pattern(self, hrefs: List[str]) -> str:
        """Find common pattern in href URLs"""
        if not hrefs:
            return ""
        
        # Look for common path segments
        common_segments = []
        for href in hrefs[:5]:  # Check first 5 examples
            segments = [seg for seg in href.split('/') if seg and not seg.startswith('?')]
            for i, segment in enumerate(segments):
                if len(segment) > 2 and segment.isalpha():  # Likely a path segment
                    if i == 0:
                        continue  # Skip domain parts
                    common_segments.append(f'/{segment}')
        
        # Find most common segment
        if common_segments:
            from collections import Counter
            most_common = Counter(common_segments).most_common(1)
            if most_common:
                return most_common[0][0]
        
        return ""
    
    def _test_regex_pattern(self, pattern: str, html: str, field_name: str) -> bool:
        """Test if a regex pattern actually matches and extracts valid data from HTML"""
        if not pattern or not html:
            return False
        
        try:
            import re
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if match:
                # Try to get the named group
                try:
                    value = match.group(field_name)
                    # Allow null or empty values for better pattern capture
                    if value is None:
                        # Pattern matched but captured null - this is valid for null-handling patterns
                        return True
                    elif value.strip():
                        # Decode HTML entities for human-readable text
                        decoded_value = unescape(value.strip())
                        # Additional validation based on field type
                        return self._is_valid_field_value(field_name, decoded_value)
                    else:
                        # Empty string is also valid for null-capable patterns
                        return True
                except (IndexError, KeyError):
                    # Named group doesn't exist - pattern structure issue
                    return False
            return False
        except Exception as e:
            print(f"Regex test error for {field_name}: {e}")
            return False
    
    def _test_selector_on_page(self, selector: str, html: str) -> int:
        """Test a CSS selector on the actual page HTML to get real count"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            elements = soup.select(selector)
            return len(elements)
        except Exception as e:
            print(f"Selector test failed for '{selector}': {e}")
            return 0
    
    def _convert_to_named_group(self, pattern: str, field_name: str) -> str:
        """Convert any capture group in pattern to named group for specific field"""
        import re
        
        # Find all capture groups and replace with named groups
        # This handles any parenthesized capture group
        def replace_group(match):
            group_content = match.group(1)
            return f'(?P<{field_name}>{group_content})'
        
        # Replace capture groups that aren't already named
        # This regex finds (content) but not (?P<name>content) or (?:content)
        pattern_with_named_group = re.sub(r'\((?!\?\w+)([^)]+)\)', replace_group, pattern)
        
        return pattern_with_named_group
    
    def _generate_detailed_explanation(self, pattern: Dict) -> str:
        """Generate detailed explanation like Belkin example"""
        pattern_key = pattern.get('pattern', '')
        selector = pattern.get('selector', '')
        count = pattern.get('count', 0)
        
        # Generate detailed explanation based on selector type
        if '/product/' in pattern_key:
            return f"Product links on this site have URLs containing '/product/'; this selector targets anchor tags that contain '/product/' in their href attributes, effectively selecting product page links. Found {count} matching links."
        elif '/p/' in pattern_key:
            return f"Product links on this site have URLs containing '/p/' and often end with '.html'; this selector targets all anchor tags with href attributes starting with '/p/' or containing '/p/' and ending with '.html', effectively selecting product page links without including other non-product links. Found {count} matching links."
        elif '/item/' in pattern_key:
            return f"Product links on this site use '/item/' in their URLs; this selector targets anchor tags containing '/item/' in their href attributes to identify product pages. Found {count} matching links."
        else:
            return f"Product links identified by pattern '{pattern_key}' using selector '{selector}'. Found {count} matching links."
    
    def _generate_css_selector(self, pattern_key: str, links: List[Dict]) -> str:
        """Generate CSS selector for product links like Belkin example"""
        # Handle data attribute patterns
        if pattern_key == 'data-product-click':
            return "a[data-event-type='product-click']"
        
        # Analyze the actual href patterns in the links
        if not links:
            return f"a[href*='{pattern_key}']"
        
        # Sample some hrefs to find patterns
        sample_hrefs = [link.get('href', '') for link in links[:10] if link.get('href')]
        
        # Generate sophisticated selectors based on actual patterns
        selectors = []
        
        # Check for common URL patterns
        if pattern_key in ['/product/', '/item/', '/p/', '/products/', '/productdetail/', '/detail/']:
            if pattern_key == '/p/':
                # For /p/ pattern, generate Belkin-style selector
                selectors.append(f"a[href^='{pattern_key}']")  # Starts with /p/
                if any('.html' in href for href in sample_hrefs):
                    selectors.append(f"a[href*='{pattern_key}'][href$='.html']")  # Contains /p/ and ends with .html
            else:
                selectors.append(f"a[href*='{pattern_key}']")
        else:
            # For other patterns, be more specific
            if pattern_key.startswith('/'):
                selectors.append(f"a[href*='{pattern_key}']")
            else:
                # Try to find common classes
                common_classes = self._find_common_classes(links)
                if common_classes:
                    selectors.append(f"a.{common_classes[0]}")
                else:
                    selectors.append(f"a[href*='{pattern_key}']")
        
        # Return combined selector or single best one
        if len(selectors) > 1:
            return ', '.join(selectors)
        elif selectors:
            return selectors[0]
        else:
            return f"a[href*='{pattern_key}']"
    
    def _find_common_classes(self, links: List[Dict]) -> List[str]:
        """Find most common CSS classes among links"""
        class_counts = {}
        
        for link in links:
            for cls in link.get('classes', []):
                class_counts[cls] = class_counts.get(cls, 0) + 1
        
        # Return classes sorted by frequency
        return sorted(class_counts.keys(), key=lambda x: class_counts[x], reverse=True)
    
    def _find_generic_product_patterns(self, soup: BeautifulSoup) -> List[Dict]:
        """Find generic product link patterns when specific patterns aren't found"""
        patterns = []
        
        # Look for links with product-related text patterns
        product_text_patterns = [
            r'\$[\d,]+\.?\d*',  # Price patterns
            r'buy\s+now', r'add\s+to\s+cart', r'quick\s+view',
            r'model\s*#?[\w\d-]+', r'sku\s*#?[\w\d-]+'
        ]
        
        all_links = soup.find_all('a', href=True)
        potential_product_links = []
        
        for link in all_links:
            text = link.get_text(strip=True).lower()
            href = link.get('href', '').lower()
            
            # Check for product-related patterns
            for pattern in product_text_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    potential_product_links.append({
                        'href': link.get('href'),
                        'text': link.get_text(strip=True),
                        'classes': link.get('class', []),
                        'pattern_matched': pattern
                    })
                    break
        
        if potential_product_links:
            patterns.append({
                'pattern': 'generic_product_links',
                'selector': self._generate_generic_selector(potential_product_links),
                'count': len(potential_product_links),
                'examples': potential_product_links[:3],
                'explanation': "Generic product links based on text patterns"
            })
        
        return patterns
    
    def _generate_generic_selector(self, links: List[Dict]) -> str:
        """Generate generic CSS selector"""
        common_classes = self._find_common_classes(links)
        
        selectors = []
        if common_classes:
            selectors.append(f"a.{common_classes[0]}")
        
        # Add href-based selectors for common patterns
        href_patterns = set()
        for link in links:
            href = link['href'].lower()
            if '/product' in href:
                href_patterns.add("a[href*='/product']")
            elif '/item' in href:
                href_patterns.add("a[href*='/item']")
            elif '/p/' in href:
                href_patterns.add("a[href*='/p/']")
        
        selectors.extend(list(href_patterns))
        
        return ', '.join(selectors) if selectors else "a[href*='product'], a[href*='item']"
    
    def _find_pagination_patterns(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Find pagination patterns"""
        pagination = {
            'type': 'none',
            'selectors': [],
            'parameter': None,
            'template': None
        }
        
        # Look for common pagination elements
        pagination_selectors = [
            '.pagination a', '.pager a', '.page-numbers a',
            'a[href*="page="]', 'a[href*="p="]', 'a[href*="offset="]'
        ]
        
        for selector in pagination_selectors:
            try:
                elements = soup.select(selector)
                if elements:
                    pagination['selectors'].append(selector)
                    pagination['type'] = 'link_based'
                    
                    # Try to extract pagination parameter
                    for elem in elements:
                        href = elem.get('href', '')
                        if 'page=' in href:
                            pagination['parameter'] = 'page'
                        elif 'p=' in href:
                            pagination['parameter'] = 'p'
                        elif 'offset=' in href:
                            pagination['parameter'] = 'offset'
            except Exception:
                continue
        
        return pagination
    
    def analyze_product_page(self, product_url: str = None) -> Dict[str, Any]:
        """Analyze a product page to extract field patterns"""
        if not product_url:
            # Try to find a product URL from catalog analysis
            product_patterns = self.analysis_results.get('product_patterns', [])
            if not product_patterns:
                print("No product URL provided and no patterns found")
                return {}
            
            # Use first example from first pattern
            first_pattern = product_patterns[0]
            if first_pattern.get('examples'):
                product_url = urljoin(self.base_url, first_pattern['examples'][0]['href'])
            else:
                print("No example product URLs found")
                return {}
        
        print_info(f"Analyzing product page: {product_url}")
        html = self.fetch_page(product_url)
        if not html:
            self.analysis_results['errors'].append(f"Failed to fetch product page: {product_url}")
            return {}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Save product page for inspection
        product_file = f"{self.domain}_product_sample.html"
        with open(product_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Extract field patterns
        field_patterns = self._extract_field_patterns(html, soup)
        self.analysis_results['field_patterns'] = field_patterns
        self.analysis_results['sample_pages']['product'] = product_file
        
        print(f"Product page analysis complete. Found patterns for {len(field_patterns)} fields")
        return {
            'product_url': product_url,
            'field_patterns': field_patterns
        }
    
    def _add_pattern_to_collection(self, all_patterns: Dict, field: str, pattern_data: Dict, html: str = None):
        """Helper to add a pattern to the collection if it's valid and unique"""
        if not pattern_data.get('regex') or not pattern_data.get('example_value'):
            return
        
        # Check if pattern already exists (avoid duplicates)
        for existing in all_patterns[field]:
            if existing['regex'] == pattern_data['regex']:
                return
        
        # Decode HTML entities in example_value for human-readable display
        if pattern_data.get('example_value'):
            pattern_data['example_value'] = unescape(str(pattern_data['example_value']))
        
        # Test the pattern if HTML is provided, otherwise trust the pattern
        if html:
            if self._test_regex_pattern(pattern_data['regex'], html, field):
                all_patterns[field].append(pattern_data)
                print(f"Added {field} pattern via {pattern_data.get('method', 'unknown')}: {pattern_data['example_value']}")
        else:
            # If no HTML provided, add the pattern (trust that it was already validated)
            all_patterns[field].append(pattern_data)
            print(f"Added {field} pattern via {pattern_data.get('method', 'unknown')}: {pattern_data['example_value']}")
    def _extract_field_patterns(self, html: str, soup: BeautifulSoup) -> Dict[str, Dict]:
        """Extract regex patterns for common product fields with AI assistance"""
        # Store multiple patterns per field for user selection
        all_patterns = {
            'Product_Title': [],
            'Product_Price': [],
            'Brand': [],
            'Manufacturer': [],
            'Sku': [],
            'Model_Number': [],
            'Product_Code': []
        }
        
        # First, try AI analysis if available (primary method)
        if self.use_ai:
            ai_field_patterns = self._ai_analyze_html_for_patterns(html, "product_fields")
            if ai_field_patterns.get('field_patterns'):
                field_mapping = {
                    'title': 'Product_Title',
                    'price': 'Product_Price', 
                    'brand': 'Brand',
                    'manufacturer': 'Manufacturer',
                    'sku': 'Sku',
                    'model': 'Model_Number',
                    'product_code': 'Product_Code'
                }
                
                # Extract structured data for JSON path analysis
                structured_data = self._extract_json_ld_for_ai(html)
                
                for ai_field, ai_data in ai_field_patterns['field_patterns'].items():
                    our_field = field_mapping.get(ai_field)
                    if not our_field:
                        continue
                    
                    # Priority 0: For Product_Title, try HTML structure first (most reliable)
                    if our_field == 'Product_Title':
                        soup = BeautifulSoup(html, 'html.parser')
                        # Look for H1 with product-related classes
                        h1_elements = soup.find_all('h1')
                        for h1 in h1_elements:
                            if h1.get('class'):
                                class_str = ' '.join(h1.get('class'))
                                if any(term in class_str.lower() for term in ['product', 'title', 'name']):
                                    title_text = h1.get_text(strip=True)
                                    if title_text and self._is_valid_field_value('Product_Title', title_text):
                                        # Create a specific regex for this H1 structure
                                        regex_pattern = f'<h1[^>]*class="[^"]*{re.escape(class_str.split()[0])}[^"]*"[^>]*>(?P<Product_Title>[^<]+)</h1>'
                                        pattern_data = {
                                            'regex': regex_pattern,
                                            'example_value': title_text,
                                            'method': 'html_h1_class',
                                            'confidence': 0.98
                                        }
                                        self._add_pattern_to_collection(all_patterns, our_field, pattern_data, html)
                    
                    # Priority 1: Try JSON paths if available, but make them context-specific
                    if ai_data.get('json_paths') and (structured_data['json_ld'] or structured_data['other_json']):
                        for json_path in ai_data['json_paths']:
                            # Try all structured data sources
                            for data_source in structured_data['json_ld'] + structured_data['other_json']:
                                extracted_value = self._extract_from_json_path(data_source, json_path)
                                if extracted_value:
                                    # Decode HTML entities for human-readable text
                                    extracted_value = unescape(str(extracted_value))
                                    # Generate a more specific JSON extraction pattern
                                    if json_path == 'name' and our_field == 'Product_Title':
                                        # For product name, be more specific and handle escaped quotes
                                        json_pattern = r'"@type"\s*:\s*"Product"[\s\S]*?"name"\s*:\s*"(?P<' + our_field + r'>(?:[^"\\]|\\.)*)"'
                                    elif json_path == 'brand.name':
                                        json_pattern = r'"brand"\s*:\s*\{\s*"@type"\s*:\s*"Brand"\s*,\s*"name"\s*:\s*"(?P<' + our_field + r'>[^"]+)"'
                                    else:
                                        # Generic pattern for other fields
                                        json_pattern = f'"' + json_path.replace('.', '"\\s*:\\s*[^"]*"[^"]*"') + '"\\s*:\\s*"(?P<' + our_field + '>[^"]+)"'
                                    
                                    pattern_data = {
                                        'regex': json_pattern,
                                        'example_value': str(extracted_value),
                                        'method': 'ai_json_path',
                                        'json_path': json_path,
                                        'confidence': 0.95
                                    }
                                    self._add_pattern_to_collection(all_patterns, our_field, pattern_data, html)
                    
                    # Priority 2: Try AI-generated regex patterns
                    if ai_data.get('regex_patterns'):
                        for regex_pattern in ai_data['regex_patterns']:
                            # Convert to named group
                            named_pattern = self._convert_to_named_group(regex_pattern, our_field)
                            match = re.search(named_pattern, html, re.DOTALL)
                            if match:
                                raw_value = match.group(our_field) if our_field in match.groupdict() else 'AI-detected'
                                # Decode HTML entities for human-readable text
                                example_value = unescape(str(raw_value)) if raw_value != 'AI-detected' else raw_value
                                pattern_data = {
                                    'regex': named_pattern,
                                    'example_value': example_value,
                                    'method': 'ai_regex',
                                    'confidence': ai_data.get('confidence', 0.8)
                                }
                                self._add_pattern_to_collection(all_patterns, our_field, pattern_data, html)
        
        # Then, try to extract from JSON-LD structured data
        json_ld_patterns = self._extract_from_json_ld(html)
        for field, pattern_data in json_ld_patterns.items():
            if field in all_patterns:
                pattern_data['method'] = 'json_ld'
                pattern_data['confidence'] = 0.90
                self._add_pattern_to_collection(all_patterns, field, pattern_data, html)
        
        # Define comprehensive field extraction strategies
        field_strategies = {
            'Product_Title': [
                # 1. Meta tags (highest priority)
                {'type': 'meta', 'attrs': {'property': 'og:title'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'twitter:title'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'itemprop': 'name'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'title'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'product-title'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'product-name'}, 'attr': 'content'},
                
                # 2. Data attributes (very reliable)
                {'type': 'data', 'attr': 'data-product-title'},
                {'type': 'data', 'attr': 'data-product-name'},
                {'type': 'data', 'attr': 'data-title'},
                {'type': 'data', 'attr': 'data-name'},
                
                # 3. CSS classes and IDs (HTML structure - high priority)
                {'type': 'class', 'classes': ['productTitle', 'productName', 'product-title', 'product-name', 'product-Name', 'item-title', 'title', 'product_title', 'prod-title', 'item-name', 'product_name', 'name', 'heading', 'main-title']},
                {'type': 'class_pattern', 'patterns': ['*productTitle*', '*product-title*', '*ProductTitle*', '*ProductName*', '*product-name*']},
                {'type': 'id', 'ids': ['product-title', 'product-name', 'item-title', 'title', 'name', 'product_title', 'productTitle', 'productName']},
                
                # 4. HTML tags (structure-based - prioritized!)
                {'type': 'tag', 'tag': 'h1'},
                {'type': 'tag', 'tag': 'h2'},
                {'type': 'tag', 'tag': 'title'},
                
                # 5. More specific Script/JSON patterns (structured data)
                {'type': 'regex', 'pattern': r'"@type"\s*:\s*"Product"[^}]*"name"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"product"\s*:[^}]*"name"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"product_name"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"product_title"\s*:\s*"([^"]+)"'},
                
                # 6. Regex patterns (lowest priority - fallback)
                {'type': 'regex', 'pattern': r'<h1[^>]*class="[^"]*product[^"]*"[^>]*>([^<]+)</h1>'},
                {'type': 'regex', 'pattern': r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</h1>'},
                {'type': 'regex', 'pattern': r'<h1[^>]*class="[^"]*name[^"]*"[^>]*>([^<]+)</h1>'},
                {'type': 'regex', 'pattern': r'<h2[^>]*class="[^"]*product[^"]*"[^>]*>([^<]+)</h2>'},
                {'type': 'regex', 'pattern': r'<h1[^>]*>([^<]+)</h1>'},
                {'type': 'regex', 'pattern': r'<h2[^>]*>([^<]+)</h2>'},
            ],
            'Product_Price': [
                # 1. Meta tags (highest priority)
                {'type': 'meta', 'attrs': {'property': 'product:price:amount'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'property': 'og:price:amount'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'itemprop': 'price'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'price'}, 'attr': 'content'},
                
                # 2. Data attributes (very reliable)
                {'type': 'data', 'attr': 'data-price'},
                {'type': 'data', 'attr': 'data-cost'},
                {'type': 'data', 'attr': 'data-amount'},
                {'type': 'data', 'attr': 'data-product-price'},
                
                # 3. CSS classes and IDs (HTML structure - high priority)
                {'type': 'class', 'classes': ['price', 'cost', 'amount', 'product-price', 'productPrice', 'productprice', 'item-price', 'current-price', 'sale-price', 'regular-price', 'pricing', 'value']},
                {'type': 'id', 'ids': ['price', 'product-price', 'productPrice', 'item-price', 'cost', 'amount']},
                
                # 4. Script/JSON patterns (structured data)
                {'type': 'regex', 'pattern': r'"price"\s*:\s*"?[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)"?'},
                {'type': 'regex', 'pattern': r'"cost"\s*:\s*"?[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)"?'},
                {'type': 'regex', 'pattern': r'"amount"\s*:\s*"?[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)"?'},
                
                # 5. Regex patterns with HTML structure (fallback)
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*price[^"]*"[^>]*>[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)</span>'},
                {'type': 'regex', 'pattern': r'<div[^>]*class="[^"]*price[^"]*"[^>]*>[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)</div>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*cost[^"]*"[^>]*>[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*amount[^"]*"[^>]*>[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)</span>'},
                
                # 6. Generic regex patterns (lowest priority)
                {'type': 'regex', 'pattern': r'[\$£€¥¢₹₽¤]([\d,]+\.?\d*)'},
                {'type': 'regex', 'pattern': r'price["\s:]*[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)'},
                {'type': 'regex', 'pattern': r'cost["\s:]*[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)'},
                {'type': 'regex', 'pattern': r'amount["\s:]*[\$£€¥¢₹₽¤]?([\d,]+\.?\d*)'},
                {'type': 'regex', 'pattern': r'\$([0-9,]+\.[0-9]{2})'},
                {'type': 'regex', 'pattern': r'£([0-9,]+\.[0-9]{2})'},
                {'type': 'regex', 'pattern': r'€([0-9,]+\.[0-9]{2})'},
                {'type': 'regex', 'pattern': r'([0-9,]+\.[0-9]{2})'},
                {'type': 'regex', 'pattern': r'([0-9,]+\.[0-9]{1,2})'},
                {'type': 'regex', 'pattern': r'([0-9,]+)'},
            ],
            'Brand': [
                # 1. Meta tags (highest priority)
                {'type': 'meta', 'attrs': {'property': 'product:brand'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'itemprop': 'brand'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'brand'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'manufacturer'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'make'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'organization'}, 'attr': 'content'},
                
                # 2. Data attributes (very reliable)
                {'type': 'data', 'attr': 'data-brand'},
                {'type': 'data', 'attr': 'data-manufacturer'},
                {'type': 'data', 'attr': 'data-make'},
                {'type': 'data', 'attr': 'data-brand-name'},
                {'type': 'data', 'attr': 'data-organization'},
                {'type': 'data_testid', 'attr': 'data-testid', 'value': 'manufacturer-link'},
                
                # 3. CSS classes and IDs (HTML structure - high priority)
                {'type': 'class', 'classes': ['brand', 'manufacturer', 'product-brand', 'item-brand', 'brand-name', 'make', 'mfg', 'mfr', 'company', 'vendor', 'brandLink', 'organization']},
                {'type': 'id', 'ids': ['brand', 'manufacturer', 'product-brand', 'make', 'mfg', 'organization']},
                
                # 4. Script/JSON patterns (structured data - more specific)
                {'type': 'regex', 'pattern': r'"brand"\s*:\s*\{\s*"@type"\s*:\s*"Brand"\s*,\s*"name"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"@type"\s*:\s*"Product"[^}]*"brand"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"manufacturer"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"make"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"organization"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"organization"\s*:\s*\{\s*"@type"\s*:\s*"Organization"\s*,\s*"name"\s*:\s*"([^"]+)"'},
                
                # 5. HTML structure-based regex patterns (fallback)
                {'type': 'regex', 'pattern': r'<a[^>]*data-testid="manufacturer-link"[^>]*>([^<]+)</a>'},
                {'type': 'regex', 'pattern': r'<a[^>]*class="[^"]*brandLink[^"]*"[^>]*>([^<]+)</a>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*brand[^"]*"[^>]*>([A-Za-z0-9\s&.-]+)</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*manufacturer[^"]*"[^>]*>([A-Za-z0-9\s&.-]+)</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*make[^"]*"[^>]*>([A-Za-z0-9\s&.-]+)</span>'},
                
                # 6. Generic regex patterns (lowest priority)
                {'type': 'regex', 'pattern': r'brand["\s:]*([A-Za-z0-9\s&.-]+)'},
                {'type': 'regex', 'pattern': r'manufacturer["\s:]*([A-Za-z0-9\s&.-]+)'},
                {'type': 'regex', 'pattern': r'make["\s:]*([A-Za-z0-9\s&.-]+)'},
                {'type': 'regex', 'pattern': r'mfg["\s:]*([A-Za-z0-9\s&.-]+)'},
            ],
            'Manufacturer': [
                # 1. Meta tags (highest priority)
                {'type': 'meta', 'attrs': {'itemprop': 'manufacturer'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'manufacturer'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'make'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'brand'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'organization'}, 'attr': 'content'},
                
                # 2. Data attributes (very reliable)
                {'type': 'data', 'attr': 'data-manufacturer'},
                {'type': 'data', 'attr': 'data-maker'},
                {'type': 'data', 'attr': 'data-brand'},
                {'type': 'data', 'attr': 'data-mfg'},
                {'type': 'data', 'attr': 'data-mfr'},
                {'type': 'data', 'attr': 'data-organization'},
                
                # 3. CSS classes and IDs (HTML structure - high priority)
                {'type': 'class', 'classes': ['manufacturer', 'brand', 'maker', 'mfg', 'mfr', 'product-manufacturer', 'item-manufacturer', 'company', 'vendor', 'organization']},
                {'type': 'id', 'ids': ['manufacturer', 'maker', 'mfg', 'mfr', 'brand', 'organization']},
                
                # 4. Script/JSON patterns (structured data)
                {'type': 'regex', 'pattern': r'"manufacturer"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"maker"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"mfg"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"organization"\s*:\s*"([^"]+)"'},
                {'type': 'regex', 'pattern': r'"organization"\s*:\s*\{\s*"@type"\s*:\s*"Organization"\s*,\s*"name"\s*:\s*"([^"]+)"'},
                
                # 5. HTML structure-based regex patterns (fallback)
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*manufacturer[^"]*"[^>]*>([A-Za-z0-9\s&.-]+)</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*maker[^"]*"[^>]*>([A-Za-z0-9\s&.-]+)</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*mfg[^"]*"[^>]*>([A-Za-z0-9\s&.-]+)</span>'},
                
                # 6. Generic regex patterns (lowest priority)
                {'type': 'regex', 'pattern': r'manufacturer["\s:]*([A-Za-z0-9\s&.-]+)'},
                {'type': 'regex', 'pattern': r'maker["\s:]*([A-Za-z0-9\s&.-]+)'},
                {'type': 'regex', 'pattern': r'mfg["\s:]*([A-Za-z0-9\s&.-]+)'},
                {'type': 'regex', 'pattern': r'mfr["\s:]*([A-Za-z0-9\s&.-]+)'},
            ],
            'Sku': [
                # Meta tags
                {'type': 'meta', 'attrs': {'itemprop': 'sku'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'sku'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'item-number'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'product-id'}, 'attr': 'content'},
                # Data attributes
                {'type': 'data', 'attr': 'data-sku'},
                {'type': 'data', 'attr': 'data-product-sku'},
                {'type': 'data', 'attr': 'data-item-sku'},
                {'type': 'data', 'attr': 'data-item-number'},
                {'type': 'data', 'attr': 'data-product-number'},
                {'type': 'data', 'attr': 'data-item-id'},
                # CSS classes
                {'type': 'class', 'classes': ['sku', 'product-sku', 'item-sku', 'product-code', 'item-code', 'item-number', 'product-number', 'item-id', 'product-id']},
                # ID selectors
                {'type': 'id', 'ids': ['sku', 'product-sku', 'item-sku', 'item-number', 'product-number']},
                # Regex patterns
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*sku[^"]*"[^>]*>([A-Za-z0-9-_\s\.]+)</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*item[_-]?number[^"]*"[^>]*>([A-Za-z0-9-_\s\.]+)</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*product[_-]?number[^"]*"[^>]*>([A-Za-z0-9-_\s\.]+)</span>'},
                {'type': 'regex', 'pattern': r'"sku"\s*:\s*"([A-Za-z0-9-_\s\.]+)"'},
                {'type': 'regex', 'pattern': r'"item_number"\s*:\s*"([A-Za-z0-9-_\s\.]+)"'},
                {'type': 'regex', 'pattern': r'"product_number"\s*:\s*"([A-Za-z0-9-_\s\.]+)"'},
                {'type': 'regex', 'pattern': r'sku["\s:]*([A-Za-z0-9-_\s\.]+)'},
                {'type': 'regex', 'pattern': r'item\s*#?\s*:?\s*([A-Za-z0-9-_\s\.]+)'},
                {'type': 'regex', 'pattern': r'item\s*number["\s:]*([A-Za-z0-9-_\s\.]+)'},
                {'type': 'regex', 'pattern': r'product\s*#?\s*:?\s*([A-Za-z0-9-_\s\.]+)'},
                {'type': 'regex', 'pattern': r'product\s*number["\s:]*([A-Za-z0-9-_\s\.]+)'},
            ],
            'Model_Number': [
                # Meta tags - Comprehensive coverage
                {'type': 'meta', 'attrs': {'itemprop': 'model'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'itemprop': 'mpn'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'model'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'mpn'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'part-number'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'partnumber'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'part_number'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'model-number'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'model_number'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'manufacturer-part-number'}, 'attr': 'content'},
                
                # Data attributes - Extended coverage
                {'type': 'data', 'attr': 'data-model'},
                {'type': 'data', 'attr': 'data-model-number'},
                {'type': 'data', 'attr': 'data-model-num'},
                {'type': 'data', 'attr': 'data-part-number'},
                {'type': 'data', 'attr': 'data-part-num'},
                {'type': 'data', 'attr': 'data-partnumber'},
                {'type': 'data', 'attr': 'data-mpn'},
                {'type': 'data', 'attr': 'data-part'},
                {'type': 'data', 'attr': 'data-product-model'},
                {'type': 'data', 'attr': 'data-item-model'},
                {'type': 'data', 'attr': 'data-manufacturer-part'},
                {'type': 'data', 'attr': 'data-mfg-part'},
                {'type': 'data', 'attr': 'data-oem-part'},
                {'type': 'data', 'attr': 'data-catalog-number'},
                
                # CSS classes - Extended coverage
                {'type': 'class', 'classes': [
                    'model', 'model-number', 'model-num', 'modelNumber', 'modelNum',
                    'part-number', 'part-num', 'partnumber', 'partNumber', 'partNum',
                    'product-model', 'product-part', 'item-model', 'item-part',
                    'mpn', 'mfg-part', 'mfg-number', 'manufacturer-part', 'manufacturer-number',
                    'oem-part', 'oem-number', 'catalog-number', 'catalog-num',
                    'part-code', 'model-code', 'product-number', 'item-number'
                ]},
                
                # ID selectors - Extended coverage
                {'type': 'id', 'ids': [
                    'model', 'model-number', 'model-num', 'modelNumber', 'modelNum',
                    'part-number', 'part-num', 'partnumber', 'partNumber', 'partNum',
                    'mpn', 'mfg-part', 'manufacturer-part', 'oem-part', 'catalog-number'
                ]},
                
                # HTML element patterns - More comprehensive
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*model[^"]*"[^>]*>([A-Za-z0-9-_\s\.\/]+)</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*mpn[^"]*"[^>]*>([A-Za-z0-9-_\s\.\/]+)</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*part[^"]*"[^>]*>([A-Za-z0-9-_\s\.\/]+)</span>'},
                {'type': 'regex', 'pattern': r'<div[^>]*class="[^"]*model[^"]*"[^>]*>([A-Za-z0-9-_\s\.\/]+)</div>'},
                {'type': 'regex', 'pattern': r'<div[^>]*class="[^"]*part[^"]*"[^>]*>([A-Za-z0-9-_\s\.\/]+)</div>'},
                {'type': 'regex', 'pattern': r'<td[^>]*class="[^"]*model[^"]*"[^>]*>([A-Za-z0-9-_\s\.\/]+)</td>'},
                {'type': 'regex', 'pattern': r'<td[^>]*class="[^"]*part[^"]*"[^>]*>([A-Za-z0-9-_\s\.\/]+)</td>'},
                
                # JSON patterns with null handling - Comprehensive coverage
                {'type': 'regex', 'pattern': r'"model"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"mpn"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"modelNumber"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"model_number"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"modelNum"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"partNumber"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"part_number"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"partNum"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"manufacturerPartNumber"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"manufacturer_part_number"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"mfgPartNumber"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"mfg_part_number"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"oemPartNumber"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"oem_part_number"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"catalogNumber"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"catalog_number"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"productModel"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"product_model"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"itemModel"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                {'type': 'regex', 'pattern': r'"item_model"\s*:\s*(?:null|"(?P<Model_Number>[^"]*)")'},
                
                # Text-based patterns - Enhanced with more variations
                {'type': 'regex', 'pattern': r'model["\s#:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'mpn["\s#:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'part\s*#?\s*:?\s*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'part\s*number["\s#:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'manufacturer\s*part["\s#:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'mfg\s*part["\s#:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'oem\s*part["\s#:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'catalog\s*#?\s*:?\s*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'item\s*model["\s#:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'product\s*model["\s#:]*([A-Za-z0-9-_\s\.\/]+)'},
                
                # Label-based patterns - Common e-commerce labels
                {'type': 'regex', 'pattern': r'Model\s*Number[:\s]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'Part\s*Number[:\s]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'MPN[:\s]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'Manufacturer\s*Part[:\s]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'OEM\s*Part[:\s]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'Catalog\s*Number[:\s]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'Item\s*Model[:\s]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'Product\s*Model[:\s]*([A-Za-z0-9-_\s\.\/]+)'},
                
                # Specific e-commerce platform patterns
                {'type': 'regex', 'pattern': r'PartNumber["\s:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'ModelNumber["\s:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'CatalogNumber["\s:]*([A-Za-z0-9-_\s\.\/]+)'},
                {'type': 'regex', 'pattern': r'ManufacturerPartNumber["\s:]*([A-Za-z0-9-_\s\.\/]+)'},
            ],
            'Product_Code': [
                # Meta tags - GTIN/UPC only
                {'type': 'meta', 'attrs': {'itemprop': 'gtin'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'itemprop': 'gtin8'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'itemprop': 'gtin12'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'itemprop': 'gtin13'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'itemprop': 'gtin14'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'upc'}, 'attr': 'content'},
                {'type': 'meta', 'attrs': {'name': 'gtin'}, 'attr': 'content'},
                # Data attributes - GTIN/UPC only
                {'type': 'data', 'attr': 'data-upc'},
                {'type': 'data', 'attr': 'data-gtin'},
                {'type': 'data', 'attr': 'data-ean'},
                # CSS classes - GTIN/UPC specific
                {'type': 'class', 'classes': ['upc', 'gtin', 'ean', 'product-upc', 'product-gtin', 'product-ean']},
                # ID selectors - GTIN/UPC specific
                {'type': 'id', 'ids': ['upc', 'gtin', 'ean', 'product-upc', 'product-gtin']},
                # Regex patterns - GTIN/UPC format only (8, 12, 13, or 14 digits)
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*upc[^"]*"[^>]*>(\d{8}|\d{12}|\d{13}|\d{14})</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*gtin[^"]*"[^>]*>(\d{8}|\d{12}|\d{13}|\d{14})</span>'},
                {'type': 'regex', 'pattern': r'<span[^>]*class="[^"]*ean[^"]*"[^>]*>(\d{8}|\d{12}|\d{13}|\d{14})</span>'},
                {'type': 'regex', 'pattern': r'"upc"\s*:\s*(?:null|"(\d{8}|\d{12}|\d{13}|\d{14})")'},
                {'type': 'regex', 'pattern': r'"gtin"\s*:\s*(?:null|"(\d{8}|\d{12}|\d{13}|\d{14})")'},
                {'type': 'regex', 'pattern': r'"ean"\s*:\s*(?:null|"(\d{8}|\d{12}|\d{13}|\d{14})")'},
                {'type': 'regex', 'pattern': r'upc["\s#:]*(\d{8}|\d{12}|\d{13}|\d{14})'},
                {'type': 'regex', 'pattern': r'gtin["\s#:]*(\d{8}|\d{12}|\d{13}|\d{14})'},
                {'type': 'regex', 'pattern': r'ean["\s#:]*(\d{8}|\d{12}|\d{13}|\d{14})'},
                # Barcode patterns that might contain GTIN/UPC
                {'type': 'regex', 'pattern': r'"barcode"\s*:\s*(?:null|"(\d{8}|\d{12}|\d{13}|\d{14})")'},
                {'type': 'regex', 'pattern': r'barcode["\s#:]*(\d{8}|\d{12}|\d{13}|\d{14})'},
                # Generic product code patterns that match GTIN/UPC format
                {'type': 'regex', 'pattern': r'"productCode"\s*:\s*(?:null|"(\d{8}|\d{12}|\d{13}|\d{14})")'},
                {'type': 'regex', 'pattern': r'"product_code"\s*:\s*(?:null|"(\d{8}|\d{12}|\d{13}|\d{14})")'},
            ]
        }
        
        # Enhanced script tag analysis for all fields
        script_patterns = self._extract_from_script_tags(html)
        for field, pattern_data in script_patterns.items():
            if field in all_patterns:
                pattern_data['method'] = 'script_tags'
                pattern_data['confidence'] = 0.85
                self._add_pattern_to_collection(all_patterns, field, pattern_data, html)
        
        # Extract patterns for each field using traditional methods
        for field_name, strategies in field_strategies.items():
            if field_name in all_patterns:
                best_pattern = self._find_best_pattern(field_name, strategies, html, soup)
                if best_pattern:
                    # Test the pattern to make sure it actually works
                    if self._test_regex_pattern(best_pattern['regex'], html, field_name):
                        best_pattern['confidence'] = best_pattern.get('confidence', 0.7)
                        self._add_pattern_to_collection(all_patterns, field_name, best_pattern, html)
        
        # Store all patterns for later selection - don't show selection menu yet
        return all_patterns
    
    def _show_pattern_selection_menu(self, all_patterns: Dict, html: str) -> Dict[str, Dict]:
        """Show interactive menu for pattern selection"""
        selected_patterns = {}
        
        print("\n" + "="*80)
        print_highlight("INTERACTIVE PATTERN SELECTION")
        print("="*80)
        print_info("Multiple patterns found for various fields. Please select your preferred pattern:")
        print()
        print_warning("IMPORTANT:")
        print_warning("   • Product_Code only accepts valid GTIN/UPC formats (8, 12, 13, or 14 digits)")
        print_warning("   • Model_Number accepts: part numbers, MPNs, model numbers, catalog numbers, OEM parts")
        print_warning("   • Model_Number supports: letters, numbers, hyphens, slashes, parentheses (including null)")
        print_warning("   • JSON-LD patterns capture fields even when current product has null values")
        print()
        
        for field_name in ['Product_Title', 'Product_Price', 'Brand', 'Manufacturer', 'Sku', 'Model_Number', 'Product_Code']:
            patterns = all_patterns.get(field_name, [])
            
            if not patterns:
                print(f"ERROR: {field_name}: No patterns found")
                selected_patterns[field_name] = {'regex': None, 'example_value': None, 'method': 'not_found'}
                continue
                
            if len(patterns) == 1:
                # Single pattern - show it with null option
                print(f"\n{field_name}:")
                pattern = patterns[0]
                method = pattern.get('method', 'unknown')
                confidence = pattern.get('confidence', 0.0)
                example = pattern['example_value']
                print(f"   1. [{method}] (confidence: {confidence:.2f}) - {example}")
                print(f"   2. [null] - Set field to null (skip this field)")
                
                while True:
                    try:
                        choice = input(f"Select pattern for {field_name} (1-2): ").strip()
                        if choice == '1':
                            selected_patterns[field_name] = patterns[0]
                            print(f"Selected pattern 1 for {field_name}")
                            break
                        elif choice == '2':
                            selected_patterns[field_name] = {'regex': None, 'example_value': None, 'method': 'user_null'}
                            print(f"Set {field_name} to null")
                            break
                        else:
                            print("WARNING: Please enter 1 or 2")
                    except ValueError:
                        print("WARNING: Please enter a valid number")
                continue
            
            # Multiple patterns - show selection menu
            print(f"\n{field_name}:")
            for i, pattern in enumerate(patterns, 1):
                method = pattern.get('method', 'unknown')
                confidence = pattern.get('confidence', 0.0)
                example = pattern['example_value']  # Show complete value
                print(f"   {i}. [{method}] (confidence: {confidence:.2f}) - {example}")
            
            # Add the null option at the end
            print(f"   {len(patterns) + 1}. [null] - Set field to null (skip this field)")
            
            while True:
                try:
                    choice = input(f"Select pattern for {field_name} (1-{len(patterns) + 1}): ").strip()
                    if choice == str(len(patterns) + 1):
                        # User chose null option
                        selected_patterns[field_name] = {'regex': None, 'example_value': None, 'method': 'user_null'}
                        print(f"Set {field_name} to null")
                        break
                    elif 1 <= int(choice) <= len(patterns):
                        selected_patterns[field_name] = patterns[int(choice) - 1]
                        print(f"Selected pattern {choice} for {field_name}")
                        break
                    else:
                        print(f"WARNING: Please enter a number between 1 and {len(patterns) + 1}")
                except ValueError:
                    print("WARNING: Please enter a valid number")
        
        print("\n" + "="*80)
        print("PATTERN SELECTION COMPLETE")
        print("="*80)
        
        # Show summary
        print("\nSelected Patterns Summary:")
        for field_name, pattern_data in selected_patterns.items():
            if pattern_data.get('regex'):
                example = pattern_data['example_value']  # Show complete value
                method = pattern_data.get('method', 'unknown')
                print(f"  SUCCESS {field_name:15} [{method}] - {example}")
            else:
                method = pattern_data.get('method', 'not_found')
                if method == 'user_null':
                    print(f"  NULL {field_name:15} [null] - Set to null by user")
                else:
                    print(f"  ERROR {field_name:15} [not_found] - No pattern available")
        
        return selected_patterns
    
    def _extract_from_script_tags(self, html: str) -> Dict[str, Any]:
        """Extract field patterns from script tags (not just JSON-LD)"""
        patterns = {}
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            script_tags = soup.find_all('script')
            
            field_mapping = {
                'Product_Title': ['name', 'title', 'productName', 'product_name', 'productTitle', 'product_title'],
                'Product_Price': ['price', 'cost', 'amount', 'productPrice', 'product_price'],
                'Brand': ['brand', 'brandName', 'brand_name', 'manufacturer'],
                'Manufacturer': ['manufacturer', 'maker', 'brand', 'mfg', 'mfr'],
                'Sku': ['sku', 'itemNumber', 'item_number', 'productNumber', 'product_number', 'productId', 'product_id'],
                'Model_Number': [
                    'modelNumber', 'model_number', 'modelNum', 'model',
                    'mpn', 'partNumber', 'part_number', 'partNum', 'part',
                    'manufacturerPartNumber', 'manufacturer_part_number', 'mfgPartNumber', 'mfg_part_number',
                    'oemPartNumber', 'oem_part_number', 'catalogNumber', 'catalog_number',
                    'productModel', 'product_model', 'itemModel', 'item_model'
                ],
                'Product_Code': ['upc', 'gtin', 'barcode', 'productCode', 'product_code', 'ean']
            }
            
            for script in script_tags:
                if script.string:
                    script_content = script.string.strip()
                    
                    # Skip empty scripts
                    if not script_content:
                        continue
                    
                    # Try to extract field values from various script patterns
                    for field_name, field_keys in field_mapping.items():
                        if field_name in patterns:
                            continue  # Already found
                        
                        for key in field_keys:
                            # Pattern 1: JSON-style "key": "value" OR "key": null
                            pattern1 = f'"{key}"\\s*:\\s*(?:null|"([^"]*)")'
                            match1 = re.search(pattern1, script_content, re.IGNORECASE)
                            
                            # Pattern 2: JavaScript variable assignment: key = "value" OR key = null  
                            pattern2 = f'{key}\\s*[=:]\\s*(?:null|["\']([^"\']*)["\'])'
                            match2 = re.search(pattern2, script_content, re.IGNORECASE)
                            
                            # Pattern 3: Object property: {key: "value"} OR {key: null}
                            pattern3 = f'{key}\\s*:\\s*(?:null|["\']([^"\']*)["\'])'
                            match3 = re.search(pattern3, script_content, re.IGNORECASE)
                            
                            if match1:
                                patterns[field_name] = {
                                    'type': 'script_json',
                                    'regex': self._convert_to_named_group(pattern1, field_name),
                                    'source': 'script_tag',
                                    'confidence': 0.8
                                }
                                break
                            elif match2:
                                patterns[field_name] = {
                                    'type': 'script_variable', 
                                    'regex': self._convert_to_named_group(pattern2, field_name),
                                    'source': 'script_tag',
                                    'confidence': 0.7
                                }
                                break
                            elif match3:
                                patterns[field_name] = {
                                    'type': 'script_object',
                                    'regex': self._convert_to_named_group(pattern3, field_name),
                                    'source': 'script_tag',
                                    'confidence': 0.7
                                }
                                break
            
            if patterns:
                print(f"Found {len(patterns)} field patterns in script tags")
        except Exception as e:
            print(f"Script tag extraction failed: {e}")
        return patterns
    
    def _extract_from_json_ld(self, html: str) -> Dict[str, Dict]:
        """Extract product information from JSON-LD structured data"""
        patterns = {}
        
        try:
            # Find all script tags with type="application/ld+json"
            soup = BeautifulSoup(html, 'html.parser')
            json_scripts = soup.find_all('script', type='application/ld+json')
            
            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    
                    # Handle different JSON-LD structures
                    if isinstance(data, list):
                        for item in data:
                            item_patterns = self._extract_from_json_ld_item(item, html)
                            for field, pattern_data in item_patterns.items():
                                if field not in patterns:  # Only add if not already found
                                    patterns[field] = pattern_data
                    elif isinstance(data, dict):
                        item_patterns = self._extract_from_json_ld_item(data, html)
                        for field, pattern_data in item_patterns.items():
                            if field not in patterns:  # Only add if not already found
                                patterns[field] = pattern_data
                        
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            print(f"JSON-LD extraction failed: {e}")
        return patterns
    
    def _extract_from_json_ld_item(self, data: Dict, html: str = '') -> Dict[str, Dict]:
        """Extract product fields from a single JSON-LD item"""
        patterns = {}
        
        # Check if this is a Product schema
        schema_type = data.get('@type', '').lower()
        if 'product' not in schema_type and 'offer' not in schema_type:
            return patterns
        
        # Map JSON-LD fields to our field names
        field_mapping = {
            'name': 'Product_Title',
            'brand': 'Brand',
            'manufacturer': 'Manufacturer',
            'make': 'Brand',
            'mfg': 'Manufacturer',
            'mfr': 'Manufacturer',
            'sku': 'Sku',
            'itemNumber': 'Sku',
            'item_number': 'Sku',
            'productNumber': 'Sku',
            'product_number': 'Sku',
            'model': 'Model_Number',
            'mpn': 'Model_Number',
            'partNumber': 'Model_Number',
            'part_number': 'Model_Number',
            'partNum': 'Model_Number',
            'manufacturerPartNumber': 'Model_Number',
            'manufacturer_part_number': 'Model_Number',
            'mfgPartNumber': 'Model_Number',
            'mfg_part_number': 'Model_Number',
            'oemPartNumber': 'Model_Number',
            'oem_part_number': 'Model_Number',
            'catalogNumber': 'Model_Number',
            'catalog_number': 'Model_Number',
            'modelNumber': 'Model_Number',
            'model_number': 'Model_Number',
            'modelNum': 'Model_Number',
            'productModel': 'Model_Number',
            'product_model': 'Model_Number',
            'itemModel': 'Model_Number',
            'item_model': 'Model_Number',
            'productID': 'Product_Code',
            'product_id': 'Product_Code',
            'identifier': 'Product_Code',
            'gtin': 'Product_Code',
            'gtin8': 'Product_Code',
            'gtin12': 'Product_Code',
            'gtin13': 'Product_Code',
            'gtin14': 'Product_Code',
            'upc': 'Product_Code',
            'ean': 'Product_Code',
            'barcode': 'Product_Code'
        }
        
        for json_field, our_field in field_mapping.items():
            value = data.get(json_field)
            
            # Always check if the field exists in JSON-LD, even if null
            if json_field in data:
                actual_value = value
                example_value = "null"
                
                # Process non-null values
                if value:
                    if isinstance(value, dict) and 'name' in value:
                        actual_value = value['name']  # Extract from nested objects
                        example_value = str(actual_value)
                    elif isinstance(value, str):
                        actual_value = value
                        example_value = str(actual_value)
                    else:
                        # For other types, convert to string
                        actual_value = str(value)
                        example_value = actual_value
                
                # Create patterns that handle both null and actual values
                test_patterns = []
                
                # Pattern 1: Handle both null and string values "field":null OR "field":"value"
                test_patterns.append(f'"{json_field}"\\s*:\\s*(?:null|"(?P<{our_field}>[^"]*)")') 
                
                # Pattern 2: Nested object with name "field":{"@type":"...","name":"value"}
                if json_field in ['brand', 'manufacturer']:
                    test_patterns.append(f'"{json_field}"\\s*:\\s*{{[^}}]*"name"\\s*:\\s*"(?P<{our_field}>[^"]+)"[^}}]*}}')
                
                test_html = html
                
                for test_pattern in test_patterns:
                    if self._test_regex_pattern(test_pattern, test_html, our_field):
                        patterns[our_field] = {
                            'regex': test_pattern,
                            'example_value': unescape(str(example_value)),
                            'method': 'json_ld_structured_data'
                        }
                        print_info(f"JSON-LD pattern captured for {our_field}: {json_field} (value: {example_value})")
                        break
                else:
                    print_warning(f"JSON-LD pattern for {our_field} ({json_field}) found but failed validation test")
        # Handle price from offers
        offers = data.get('offers', data.get('offer'))
        if offers:
            if isinstance(offers, list) and offers:
                offer = offers[0]
            elif isinstance(offers, dict):
                offer = offers
            else:
                offer = None
                
            if offer and 'price' in offer:
                price = offer['price']
                test_pattern = r'"price"\\s*:\\s*"?(?P<Product_Price>[\\d,]+\\.?\\d*)"?'
                test_html = html
                
                if self._test_regex_pattern(test_pattern, test_html, 'Product_Price'):
                    patterns['Product_Price'] = {
                        'regex': test_pattern,
                        'example_value': unescape(str(price)),
                        'method': 'json_ld_structured_data'
                    }
                else:
                    print("JSON-LD price pattern failed validation test")
        return patterns
    
    def _find_best_pattern(self, field_name: str, strategies: List[Dict], html: str, soup: BeautifulSoup) -> Optional[Dict]:
        """Find the best extraction pattern for a field"""
        for strategy in strategies:
            try:
                if strategy['type'] == 'meta':
                    element = soup.find('meta', attrs=strategy['attrs'])
                    if element and element.get(strategy['attr']):
                        value = element.get(strategy['attr'])
                        regex = self._generate_meta_regex(strategy['attrs'], strategy['attr'], field_name)
                        return {
                            'regex': regex,
                            'example_value': value,
                            'method': 'meta_tag'
                        }
                
                elif strategy['type'] == 'tag':
                    element = soup.find(strategy['tag'])
                    if element and element.get_text(strip=True):
                        value = element.get_text(strip=True)
                        regex = f"<{strategy['tag']}[^>]*>(?P<{field_name}>[^<]+)</{strategy['tag']}>"
                        return {
                            'regex': regex,
                            'example_value': value,
                            'method': 'html_tag'
                        }
                
                elif strategy['type'] == 'class':
                    for class_name in strategy['classes']:
                        elements = soup.find_all(class_=class_name)
                        for element in elements:
                            text = element.get_text(strip=True)
                            if text and self._is_valid_field_value(field_name, text):
                                regex = f'class="[^"]*{class_name}[^"]*"[^>]*>(?P<{field_name}>[^<]+)'
                                return {
                                    'regex': regex,
                                    'example_value': text,
                                    'method': 'css_class'
                                }
                
                elif strategy['type'] == 'class_pattern':
                    # Handle dynamic CSS classes with patterns like ProductPage_productTitle__bTLgA
                    for pattern in strategy['patterns']:
                        # Convert pattern like '*productTitle*' to regex
                        regex_pattern = pattern.replace('*', '.*')
                        all_elements = soup.find_all()
                        for element in all_elements:
                            if element.get('class'):
                                class_str = ' '.join(element.get('class'))
                                if re.search(regex_pattern, class_str, re.IGNORECASE):
                                    text = element.get_text(strip=True)
                                    if text and self._is_valid_field_value(field_name, text):
                                        # Create a regex that matches the dynamic class pattern
                                        regex = f'class="[^"]*{regex_pattern}[^"]*"[^>]*>(?P<{field_name}>[^<]+)'
                                        return {
                                            'regex': regex,
                                            'example_value': text,
                                            'method': 'css_class_pattern'
                                        }
                
                elif strategy['type'] == 'id':
                    for id_name in strategy['ids']:
                        element = soup.find(id=id_name)
                        if element:
                            text = element.get_text(strip=True)
                            if text and self._is_valid_field_value(field_name, text):
                                regex = f'id="{id_name}"[^>]*>(?P<{field_name}>[^<]+)'
                                return {
                                    'regex': regex,
                                    'example_value': text,
                                    'method': 'css_id'
                                }
                
                elif strategy['type'] == 'data':
                    elements = soup.find_all(attrs={strategy['attr']: True})
                    for element in elements:
                        value = element.get(strategy['attr'])
                        if value and self._is_valid_field_value(field_name, value):
                            regex = f'{strategy["attr"]}="(?P<{field_name}>[^"]+)"'
                            return {
                                'regex': regex,
                                'example_value': value,
                                'method': 'data_attribute'
                            }
                
                elif strategy['type'] == 'data_testid':
                    # Handle specific data-testid values like data-testid="manufacturer-link"
                    elements = soup.find_all(attrs={strategy['attr']: strategy['value']})
                    for element in elements:
                        text = element.get_text(strip=True)
                        if text and self._is_valid_field_value(field_name, text):
                            regex = f'{strategy["attr"]}="{strategy["value"]}"[^>]*>(?P<{field_name}>[^<]+)'
                            return {
                                'regex': regex,
                                'example_value': text,
                                'method': 'data_testid'
                            }
                
                elif strategy['type'] == 'regex':
                    matches = re.findall(strategy['pattern'], html, re.IGNORECASE)
                    if matches:
                        value = matches[0] if isinstance(matches[0], str) else matches[0][0]
                        if self._is_valid_field_value(field_name, value):
                            # Convert ANY capture group to named group for this field
                            pattern_with_named_group = self._convert_to_named_group(strategy['pattern'], field_name)
                            return {
                                'regex': pattern_with_named_group,
                                'example_value': value,
                                'method': 'regex_pattern'
                            }
            
            except Exception as e:
                print(f"Strategy failed for {field_name}: {e}")
                continue
        
        return None
    
    def _generate_meta_regex(self, attrs: Dict, attr: str, field_name: str = None) -> str:
        """Generate regex for meta tag extraction"""
        attr_patterns = []
        for key, value in attrs.items():
            attr_patterns.append(f'{key}="{value}"')
        
        attrs_pattern = '[^>]*'.join(attr_patterns)
        if field_name:
            return f'<meta[^>]*{attrs_pattern}[^>]*{attr}="(?P<{field_name}>[^"]+)"'
        else:
            return f'<meta[^>]*{attrs_pattern}[^>]*{attr}="([^"]+)"'
    
    def _is_valid_field_value(self, field_name: str, value: str) -> bool:
        """Validate if extracted value is reasonable for the field"""
        # Special handling for Model_Number - allow empty/null values
        if field_name == 'Model_Number' and not value:
            return True
        
        if not value:
            return False
            
        value = value.strip()
        
        if not value or len(value) > 1000:
            return False
        
        # Remove common HTML entities and tags
        value_clean = re.sub(r'&[a-zA-Z]+;', ' ', value)
        value_clean = re.sub(r'<[^>]+>', ' ', value_clean)
        value_clean = value_clean.strip()
        
        # Field-specific validation
        if field_name == 'Product_Price':
            # Must contain numbers and reasonable price format
            if not re.search(r'[\d,]+\.?\d*', value_clean):
                return False
            # Should not be too long or contain too much text
            if len(value_clean) > 50:
                return False
            # Should not contain obvious non-price text
            invalid_patterns = ['shipping', 'tax', 'description', 'warranty', 'return']
            if any(pattern in value_clean.lower() for pattern in invalid_patterns):
                return False
            return True
            
        elif field_name == 'Product_Title':
            # Product title should be meaningful
            if len(value_clean) < 3:
                return False
            # Reject single words that are likely person names or generic terms
            if len(value_clean.split()) == 1:
                # Single word titles are usually not good product names
                single_word_rejects = ['michael', 'john', 'david', 'james', 'review', 'reviews', 'home', 'shop', 'store', 'buy', 'sale']
                if value_clean.lower() in single_word_rejects:
                    return False
            # Should not contain obvious navigation or UI text
            invalid_patterns = ['click here', 'read more', 'buy now', 'add to cart', 'sign in', 'register', 'menu']
            if any(pattern in value_clean.lower() for pattern in invalid_patterns):
                return False
            return True
            
        elif field_name == 'Product_Code':
            # Product_Code must be a valid GTIN/UPC format
            return self._validate_gtin_upc(value_clean)
            
        elif field_name == 'Model_Number':
            # Model_Number is very permissive - can be null, part numbers, MPNs, etc.
            # Allow null or empty values
            if not value_clean or value_clean.lower() in ['null', 'none', 'n/a', 'not available', 'tbd', 'tba']:
                return True
            # Should be reasonable alphanumeric with common separators and special chars
            # Allow letters, numbers, hyphens, underscores, dots, slashes, parentheses, colons, spaces
            if not re.match(r'^[A-Za-z0-9\-_#\s\./\(\)\[\]&+*@:]+$', value_clean):
                return False
            # Should not be too long (part numbers can be quite long)
            if len(value_clean) > 150:
                return False
            # Should not be obviously invalid content
            invalid_keywords = [
                'description', 'title', 'buy', 'add', 'cart', 'click', 'more', 'select',
                'choose', 'option', 'view', 'details', 'information', 'shipping', 'delivery',
                'warranty', 'return', 'policy', 'terms', 'condition', 'brand new', 'used',
                'refurbished', 'genuine', 'original', 'replacement'
            ]
            # Should not start with http or contain obvious non-part-number text
            if (value_clean.lower().startswith('http') or 
                any(word in value_clean.lower() for word in invalid_keywords)):
                return False
            # Reject if it's just numbers (likely a price or quantity, not a model number)
            if re.match(r'^\d+\.?\d*$', value_clean.strip()):
                return False
            # Must contain at least one letter or be a reasonable part number format
            if not re.search(r'[A-Za-z]', value_clean) and len(value_clean) < 3:
                return False
            return True
            
        elif field_name == 'Sku':
            # Should be alphanumeric with common separators
            if not re.match(r'^[A-Za-z0-9\-_#\s\.]+$', value_clean):
                return False
            # Should not be too long
            if len(value_clean) > 100:
                return False
            # Should not start with http or contain obvious non-code text
            if (value_clean.lower().startswith('http') or 
                any(word in value_clean.lower() for word in ['description', 'title', 'name', 'buy', 'add', 'cart'])):
                return False
            return True
            
        elif field_name == 'Product_Title':
            # Should be reasonable length
            if len(value_clean) < 5 or len(value_clean) > 500:
                return False
            # Should not be navigation text
            nav_indicators = ['home', 'login', 'register', 'cart', 'checkout', 'search', 'menu']
            if any(indicator == value_clean.lower() for indicator in nav_indicators):
                return False
            return True
            
        elif field_name in ['Brand', 'Manufacturer']:
            # Should be reasonable length
            if len(value_clean) < 1 or len(value_clean) > 100:
                return False
            # Should not contain obvious non-brand text
            invalid_patterns = ['description', 'title', 'price', 'buy', 'add', 'cart', 'http']
            if any(pattern in value_clean.lower() for pattern in invalid_patterns):
                return False
            return True
        
        return True
    
    def _run_validation_and_fixing_loop(self, config: Dict[str, Any]):
        """Run validation and interactive field fixing loop"""
        config_file = f"scraper_config_{self._extract_site_name(self.domain)}.json"
        
        while True:
            print(f"\nRunning validation: python validate.py {config_file}")
            validation_results = self._run_validate_py(config_file)
            
            # Always show field fixing menu, even if validation had issues
            # This allows users to manually fix patterns
            if not self._show_field_fixing_menu(config, validation_results):
                break  # User chose to exit
    
    def _run_validate_py(self, config_file: str) -> Dict[str, any]:
        """Run validate.py and capture results"""
        try:
            import subprocess
            import sys
            import os
            
            # Make sure we're in the right directory
            current_dir = os.getcwd()
            validate_path = os.path.join(current_dir, 'validate.py')
            
            if not os.path.exists(validate_path):
                print(f"ERROR: validate.py not found at {validate_path}")
                return {}
            
            # Check approach memory for best validation method
            domain = self.approach_memory.get_domain_from_url(self.base_url)
            successful_approach = self.approach_memory.get_successful_approach(domain)
            
            # Build command with smart approach selection
            cmd = [sys.executable, validate_path, config_file]
            
            if successful_approach:
                print(f"Using remembered successful approach: {successful_approach} for {domain}")
                cmd.extend(['--method', successful_approach])
            else:
                print(f"No previous success recorded for {domain}, using smart validation")
                cmd.extend(['--method', 'both'])
            
            print(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=current_dir)
            
            # Show both stdout and stderr to user
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(f"Error output: {result.stderr}")
            
            if result.returncode == 0:
                # Parse the output to extract validation results
                output = result.stdout
                
                # Extract field results from output
                field_results = {}
                lines = output.split('\n')
                
                for line in lines:
                    if 'SUCCESS' in line and 'matched:' in line:
                        # Extract field name and value
                        parts = line.split()
                        if len(parts) >= 3:
                            field_name = parts[2]  # e.g., "Product_Title"
                            field_results[field_name] = {'status': 'success', 'line': line}
                    elif 'FAILED' in line and ('did not match' in line or 'group empty' in line):
                        # Extract field name
                        parts = line.split()
                        if len(parts) >= 3:
                            field_name = parts[2]  # e.g., "Product_Price"
                            field_results[field_name] = {'status': 'failed', 'line': line}
                    elif 'WARNING' in line and 'has no regex' in line:
                        # Extract field name from "Field 'Product_Code' has no regex"
                        if "'" in line:
                            field_name = line.split("'")[1]
                            field_results[field_name] = {'status': 'no_regex', 'line': line}
                
                # Return results even if field_results is empty, so menu shows
                return field_results if field_results else {'validation_ran': True}
            else:
                print(f"ERROR: Validation failed with return code: {result.returncode}")
                # Still return something so menu can show
                return {'validation_failed': True}
                
        except subprocess.TimeoutExpired:
            print("ERROR: Validation timeout (>90 seconds)")
            return {'validation_timeout': True}
        except Exception as e:
            print(f"ERROR running validation: {e}")
            import traceback
            traceback.print_exc()
            return {'validation_error': str(e)}
    
    def _show_field_fixing_menu(self, config: Dict[str, Any], validation_results: Dict) -> bool:
        """Show field fixing menu and handle user choice. Returns True to continue, False to exit"""
        print(f"\nFIELD PATTERN FIXER")
        print("=" * 50)
        
        # Prepare field list with status
        field_names = ['Product_Title', 'Product_Price', 'Brand', 'Manufacturer', 'Sku', 'Model_Number', 'Product_Code']
        field_display = {
            'Product_Title': 'Title',
            'Product_Price': 'Price', 
            'Brand': 'Brand',
            'Manufacturer': 'Manufacturer',
            'Sku': 'SKU',
            'Model_Number': 'Model Number',
            'Product_Code': 'Product Code'
        }
        
        print("What field needs to be fixed?\n")
        
        for i, field_name in enumerate(field_names, 1):
            display_name = field_display[field_name]
            status = validation_results.get(field_name, {}).get('status', 'unknown')
            
            if status == 'success':
                status_icon = "OK"
            elif status == 'failed':
                status_icon = "X"
            elif status == 'no_regex':
                status_icon = "O"
            else:
                status_icon = "?"
            
            print(f"{i}. {display_name} {status_icon}")
        
        print(f"\n{len(field_names) + 1}. Exit")
        
        try:
            choice = input(f"\nSelect option (1-{len(field_names) + 1}): ").strip()
            choice_num = int(choice)
            
            if choice_num == len(field_names) + 1:  # Exit option
                return False
            elif 1 <= choice_num <= len(field_names):
                field_name = field_names[choice_num - 1]
                self._fix_field_interactive(field_name, config)
                return True
            else:
                print("ERROR: Invalid choice")
                return True
                
        except ValueError:
            print("ERROR: Please enter a valid number")
            return True
    
    def _fix_field_interactive(self, field_name: str, config: Dict[str, Any]):
        """Fix a specific field interactively"""
        display_name = {
            'Product_Title': 'Title',
            'Product_Price': 'Price',
            'Brand': 'Brand', 
            'Manufacturer': 'Manufacturer',
            'Sku': 'SKU',
            'Model_Number': 'Model Number',
            'Product_Code': 'Product Code'
        }.get(field_name, field_name)
        
        print(f"\nFixing: {display_name}")
        print("=" * 40)
        print("Instructions:")
        print("1. Go to the product page in your browser")
        print("2. Right-click on the element containing the data you want")
        print("3. Select 'Inspect' or 'Inspect Element'")
        print("4. Copy the HTML element that contains the data")
        print("5. Paste it here")
        print("\nExample:")
        if field_name == 'Brand':
            print('<div class="ProductSpecification_row__57y0j"><div>Brand</div><div>Magnum Research</div></div>')
        elif field_name == 'Product_Price':
            print('<span class="price">$399.99</span>')
        elif field_name == 'Product_Title':
            print('<h1 class="product-title">Air Venturi MicroStrike PCP Air Pistol</h1>')
        
        element_html = input(f"\nPaste the HTML element for {display_name}: ").strip()
        
        if not element_html:
            print("ERROR: No element provided")
            return
        
        # Generate regex pattern from the provided element
        regex_pattern = self._generate_regex_from_element(element_html, field_name)
        
        # No AI - use the direct pattern generation which is more reliable
        
        if regex_pattern:
            # Update the configuration
            config['products'][0]['fields'][field_name]['regex'] = regex_pattern
            
            # Save the updated configuration
            config_file = f"scraper_config_{self._extract_site_name(self.domain)}.json"
            try:
                with open(config_file, 'w', encoding='utf-8') as f:
                    import json
                    json.dump(config, f, indent=2, ensure_ascii=False)
                print(f"Updated {display_name} pattern and saved configuration")
                print(f"New pattern: {regex_pattern}")
            except Exception as e:
                print(f"ERROR saving configuration: {e}")
        else:
            print("ERROR: Could not generate regex pattern from the provided element")
    
    def _generate_regex_from_element(self, element_html: str, field_name: str) -> str:
        """Generate regex pattern from provided HTML element"""
        try:
            # Check if this looks like a multi-element context (e.g., title + description)
            if '<div' in element_html and element_html.count('<div') > 1:
                return self._generate_context_aware_pattern(element_html, field_name)
            
            soup = BeautifulSoup(element_html, 'html.parser')
            
            # Find the element containing the actual data
            element = soup.find()
            if not element:
                return ""
            
            # Get element text content
            text_content = element.get_text(strip=True)
            if not text_content:
                return ""
            
            # Extract tag name, classes, and structure
            tag_name = element.name
            classes = element.get('class', [])
            element_id = element.get('id', '')
            
            # For nested elements, analyze the structure intelligently
            children = element.find_all(string=True, recursive=True)
            children_text = [t.strip() for t in children if t.strip()]
            
            # Special handling for nested price structures like:
            # <div class="price"><div class="dollar-price">$</div>4.55</div>
            if field_name == 'Product_Price' and len(children_text) >= 2:
                # Look for numeric values in nested content
                price_candidates = []
                for text in children_text:
                    if re.search(r'[\d,]+\.?\d*', text):
                        price_candidates.append(text)
                
                if price_candidates:
                    # Choose the text with the most complete price format
                    price_candidates.sort(key=lambda x: len(re.findall(r'[\d,]+\.?\d*', x)), reverse=True)
                    actual_value = text_content  # Use full combined text for price
                    print(f"🧹 Detected nested price structure: '{actual_value}'")
                else:
                    actual_value = text_content
            elif len(children_text) >= 2:
                # General nested element handling
                possible_values = []
                for text in children_text:
                    # Skip common labels and symbols
                    if (text.lower() not in ['brand', 'manufacturer', 'sku', 'model', 'price', 'title', 'name', 'code', '$', '€', '£'] and
                        len(text) > 1):  # Avoid single character strings
                        possible_values.append(text)
                
                if possible_values:
                    actual_value = possible_values[0]  # Use first meaningful text
                else:
                    actual_value = children_text[-1]  # Use last text as fallback
            else:
                actual_value = text_content
            
            # Generate flexible pattern options based on element structure
            patterns = []
            
            # Pattern 1: Simple tag-based with primary class (most reliable)
            if classes:
                primary_class = classes[0]  # Use the first class as the main identifier
                patterns.append(f'<{tag_name}[^>]*class="[^"]*{re.escape(primary_class)}[^"]*"[^>]*>(?P<{field_name}>[^<]+)</{tag_name}>')
            
            # Pattern 2: Tag-based with multiple classes (if more than one class)
            if len(classes) > 1:
                # Create pattern that matches any of the classes
                class_options = '|'.join(re.escape(cls) for cls in classes[:3])  # Use first 3 classes max
                patterns.append(f'<{tag_name}[^>]*class="[^"]*(?:{class_options})[^"]*"[^>]*>(?P<{field_name}>[^<]+)</{tag_name}>')
            
            # Pattern 3: Simple tag-based (fallback)
            patterns.append(f'<{tag_name}[^>]*>(?P<{field_name}>[^<]+)</{tag_name}>')
            
            # Pattern 4: ID-based (if available)
            if element_id:
                patterns.append(f'id="{re.escape(element_id)}"[^>]*>(?P<{field_name}>[^<]+)')
            
            # Pattern 5: Enhanced price field patterns for nested structures
            if field_name == 'Product_Price':
                # Extract price number and currency info
                price_match = re.search(r'[\d,]+\.?\d*', actual_value)
                currency_match = re.search(r'[\$£€¥¢₹₽¤]', actual_value)
                
                if price_match and classes:
                    primary_class = classes[0]
                    
                    # Clear existing patterns for price - we want specialized ones only
                    patterns = []
                    
                    # Pattern A: Nested structure with any content between tags (most flexible)
                    patterns.append(rf'<{tag_name}[^>]*class="[^"]*{re.escape(primary_class)}[^"]*"[^>]*>.*?(?P<{field_name}>[\d,]+\.?\d*)')
                    
                    # Pattern B: With optional currency symbol (handles $7.82, €7.82, 7.82)
                    patterns.append(rf'<{tag_name}[^>]*class="[^"]*{re.escape(primary_class)}[^"]*"[^>]*>.*?(?P<{field_name}>[\$£€¥¢₹₽¤]?[\d,]+\.?\d*)')
                    
                    # Pattern C: Complete combined text content (gets "$7.82" from "$" + "7.82")
                    if currency_match:
                        patterns.append(rf'<{tag_name}[^>]*class="[^"]*{re.escape(primary_class)}[^"]*"[^>]*>(?P<{field_name}>[\$£€¥¢₹₽¤][\s\S]*?[\d,]+\.?\d*)')
                    
                    # Pattern D: Flexible text extraction (handles whitespace and nested elements)
                    patterns.append(rf'<{tag_name}[^>]*class="[^"]*{re.escape(primary_class)}[^"]*"[^>]*>[\s\S]*?(?P<{field_name}>[\d,]+\.?\d*)[\s\S]*?</{tag_name}>')
                    
                    print(f"💰 Generated {len(patterns)} enhanced price patterns for nested structure")
                    # Return the most flexible pattern for nested structures
                    return patterns[0] if patterns else ""
            elif field_name in ['Sku', 'Model_Number', 'Product_Code']:
                # Allow for alphanumeric codes
                patterns.append(f'(?P<{field_name}>{re.escape(actual_value)})')
            
            # Return the most specific pattern (first one with class if available)
            return patterns[0] if patterns else ""
            
        except Exception as e:
            print(f"Error generating regex from element: {e}")
            return ""
    
    def _generate_context_aware_pattern(self, element_html: str, field_name: str) -> str:
        """Generate regex pattern for multi-element HTML contexts (e.g., spec-title + spec-description)"""
        try:
            soup = BeautifulSoup(element_html, 'html.parser')
            elements = soup.find_all()
            
            if len(elements) < 2:
                # Fallback to single element processing
                return self._generate_single_element_pattern(elements[0], field_name) if elements else ""
            
            # Look for common patterns like label + value
            label_element = None
            value_element = None
            
            # Strategy 1: Find elements with field-related classes or text
            field_keywords = {
                'Manufacturer': ['manufacturer', 'maker', 'brand'],
                'Brand': ['brand', 'manufacturer', 'maker'], 
                'Sku': ['sku', 'item', 'product', 'code'],
                'Model_Number': ['model', 'mpn', 'part'],
                'Product_Code': ['code', 'upc', 'barcode', 'item'],
                'Product_Price': ['price', 'cost', 'amount'],
                'Product_Title': ['title', 'name', 'product']
            }
            
            keywords = field_keywords.get(field_name, [field_name.lower().replace('_', '')])
            
            for element in elements:
                element_text = element.get_text(strip=True).lower()
                classes = ' '.join(element.get('class', [])).lower()
                
                # Check if this element contains field keywords (likely a label)
                if any(keyword in element_text or keyword in classes for keyword in keywords):
                    if len(element_text) < 50:  # Likely a label if short
                        label_element = element
                    else:
                        value_element = element  # Likely the value if longer
                elif not any(keyword in element_text for keyword in ['title', 'label', 'name']) and len(element_text) > 3:
                    # This could be the value element
                    if value_element is None or len(element.get_text(strip=True)) > len(value_element.get_text(strip=True)):
                        value_element = element
            
            # Strategy 2: Pattern matching based on class names
            if not (label_element and value_element):
                for element in elements:
                    classes = element.get('class', [])
                    if any('title' in cls or 'label' in cls for cls in classes):
                        label_element = element
                    elif any('description' in cls or 'value' in cls or 'content' in cls for cls in classes):
                        value_element = element
            
            # Generate pattern based on found elements
            if label_element and value_element:
                # Generate context-aware pattern: label_pattern + value_pattern
                label_pattern = self._generate_element_selector(label_element, field_name)
                value_pattern = self._generate_element_selector(value_element, field_name, capture_content=True)
                
                if label_pattern and value_pattern:
                    # Combine patterns with flexible spacing
                    combined_pattern = f"{label_pattern}[^<]*{value_pattern}"
                    print(f"Generated context-aware pattern using label + value elements")
                    return combined_pattern
            
            # Fallback: use the element with the most meaningful content
            if value_element:
                return self._generate_single_element_pattern(value_element, field_name)
            else:
                # Use the last element as fallback
                return self._generate_single_element_pattern(elements[-1], field_name)
                
        except Exception as e:
            print(f"Error generating context-aware pattern: {e}")
            return ""
    
    def _generate_element_selector(self, element, field_name: str, capture_content: bool = False) -> str:
        """Generate regex selector for a specific element"""
        try:
            tag_name = element.name
            classes = element.get('class', [])
            
            if classes:
                primary_class = classes[0]
                class_pattern = f'class="[^"]*{re.escape(primary_class)}[^"]*"'
            else:
                class_pattern = '[^>]*'
            
            if capture_content:
                # Clean the content for capture (remove quotes, extra whitespace)
                content = element.get_text(strip=True)
                # Handle quoted content like ' " BOISE WHITE PAPER, L.L.C. " '
                if content.startswith('"') and content.endswith('"'):
                    content_pattern = f'\\s*"\\s*(?P<{field_name}>[^"]+)\\s*"\\s*'
                else:
                    content_pattern = f'(?P<{field_name}>[^<]+)'
                
                return f'<{tag_name}[^>]*{class_pattern}[^>]*>{content_pattern}</{tag_name}>'
            else:
                # Just match the element structure without capturing
                element_text = element.get_text(strip=True)
                return f'<{tag_name}[^>]*{class_pattern}[^>]*>{re.escape(element_text)}</{tag_name}>'
                
        except Exception as e:
            print(f"Error generating element selector: {e}")
            return ""
    
    def _generate_single_element_pattern(self, element, field_name: str) -> str:
        """Generate pattern for a single element (fallback method)"""
        try:
            tag_name = element.name
            classes = element.get('class', [])
            content = element.get_text(strip=True)
            
            if classes:
                primary_class = classes[0]
                class_pattern = f'class="[^"]*{re.escape(primary_class)}[^"]*"'
            else:
                class_pattern = '[^>]*'
            
            # Handle quoted content
            if content.startswith('"') and content.endswith('"'):
                content_pattern = f'\\s*"\\s*(?P<{field_name}>[^"]+)\\s*"\\s*'
            else:
                content_pattern = f'(?P<{field_name}>[^<]+)'
            
            return f'<{tag_name}[^>]*{class_pattern}[^>]*>{content_pattern}</{tag_name}>'
            
        except Exception as e:
            print(f"Error generating single element pattern: {e}")
            return ""
    
    def _select_product_pattern(self, product_patterns: List[Dict]) -> Dict:
        """Allow user to select the best product pattern when multiple patterns are found"""
        if not product_patterns:
            return {}
        
        if len(product_patterns) == 1:
            return product_patterns[0]
        
        # Multiple patterns - let user choose
        print("\n" + "="*80)
        print_highlight("PRODUCT LINK PATTERN SELECTION")
        print("="*80)
        print_info("Multiple product link patterns found. Please select your preferred pattern:")
        print()
        
        for i, pattern in enumerate(product_patterns, 1):
            selector = pattern.get('selector', 'N/A')
            count = pattern.get('count', 0)
            explanation = pattern.get('explanation', 'No explanation')
            confidence = pattern.get('confidence', 0.0)
            examples = pattern.get('examples', [])
            
            print(f"   {i}. [{count} matches] (confidence: {confidence:.2f}) - {selector}")
            print(f"      {explanation}")
            
            # Show sample URLs found by this pattern
            if examples:
                print(f"      Sample URLs found:")
                for j, example in enumerate(examples[:3], 1):  # Show up to 3 examples
                    href = example.get('href', 'N/A')
                    title = example.get('title', '')
                    # Clean up the URL display
                    if href.startswith('/'):
                        display_url = f"{self.base_url.rstrip('/')}{href}"
                    elif href.startswith('http'):
                        display_url = href
                    else:
                        display_url = f"{self.base_url.rstrip('/')}/{href.lstrip('/')}"
                    
                    # Truncate long URLs for better display
                    if len(display_url) > 80:
                        display_url = display_url[:77] + "..."
                    
                    print(f"         {j}. {display_url}")
                    if title and len(title.strip()) > 0:
                        title_display = title.strip()[:60]
                        if len(title.strip()) > 60:
                            title_display += "..."
                        print(f"            \"{title_display}\"")
            else:
                print(f"      No sample URLs available")
            print()
        
        while True:
            try:
                choice = input(f"Select product pattern (1-{len(product_patterns)}): ").strip()
                choice_num = int(choice)
                if 1 <= choice_num <= len(product_patterns):
                    selected_pattern = product_patterns[choice_num - 1]
                    print(f"Selected pattern {choice}: {selected_pattern['selector']}")
                    print("="*80)
                    return selected_pattern
                else:
                    print(f"WARNING: Please enter a number between 1 and {len(product_patterns)}")
            except ValueError:
                print("WARNING: Please enter a valid number")

    def generate_config(self, catalog_url: str = None, product_url: str = None) -> Dict[str, Any]:
        """Generate scraper configuration based on analysis"""
        print("Generating scraper configuration...")
        if not self.analysis_results['product_patterns']:
            print("Cannot generate config: no product patterns found")
            
            # Try to generate patterns from user-provided HTML elements
            print("\n" + "="*60)
            print("FALLBACK: Manual Pattern Generation")
            print("="*60)
            print("Since no product patterns were automatically detected, we can help you create patterns manually.")
            print("Please paste an HTML element from a product listing page that represents a single product.")
            print("This could be a <div>, <article>, or other container that holds product information.")
            print("\nExample of what to paste:")
            print('<div class="product-card" data-id="12345">')
            print('  <h3 class="product-title">Sample Product</h3>')
            print('  <span class="price">$29.99</span>')
            print('</div>')
            print("\nInstructions:")
            print("1. Go to a product listing/catalog page on the website")
            print("2. Right-click on a product item and select 'Inspect Element'")
            print("3. Find the container element that wraps the entire product")
            print("4. Right-click on that element and select 'Copy' > 'Copy outerHTML'")
            print("5. Paste it below")
            print("\nPaste the HTML element here (press Enter twice when done):")
            
            # Get HTML input from user
            html_lines = []
            empty_lines = 0
            while empty_lines < 2:
                try:
                    line = input()
                    if line.strip() == "":
                        empty_lines += 1
                    else:
                        empty_lines = 0
                        html_lines.append(line)
                except (EOFError, KeyboardInterrupt):
                    print("\nInput cancelled.")
                    return {}
            
            user_html = '\n'.join(html_lines).strip()
            
            if not user_html:
                print("No HTML provided. Cannot generate configuration.")
                return {}
                
            # Generate patterns from the provided HTML
            print("\nGenerating patterns from your HTML element...")
            generated_patterns = self._generate_patterns_from_html(user_html)
            
            if generated_patterns:
                self.analysis_results['product_patterns'] = generated_patterns
                print(f"[SUCCESS] Generated {len(generated_patterns)} product pattern(s)")
                
                # Also try to extract field patterns from the same HTML
                field_patterns = self._extract_field_patterns_from_html(user_html)
                if field_patterns:
                    self.analysis_results['field_patterns'] = field_patterns
                    print(f"[SUCCESS] Generated field patterns for: {', '.join(field_patterns.keys())}")
            else:
                print("[ERROR] Could not generate patterns from the provided HTML.")
                return {}
        
        if not self.analysis_results['product_patterns']:
            return {}
        

        # Get the product pattern (already selected during analysis if multiple patterns existed)
        if len(self.analysis_results['product_patterns']) == 1:
            best_pattern = self.analysis_results['product_patterns'][0]
        else:
            # Fallback: select the best one by count (shouldn't happen with new flow)
            best_pattern = max(self.analysis_results['product_patterns'], key=lambda x: x.get('count', 0))
        
        # Get catalog URL - prioritize meaningful catalog pages
        if not catalog_url:
            catalog_url = self.base_url  # Fallback to homepage
            catalog_links = self.analysis_results.get('site_info', {}).get('potential_catalog_links', [])
            
            # Look for more specific catalog pages
            if catalog_links:
                # Prioritize category/product listing pages over homepage
                for link in catalog_links[:5]:  # Check top 5 catalog links
                    href = link.get('href', '')
                    text = link.get('text', '').lower()
                    if any(keyword in href.lower() or keyword in text for keyword in 
                          ['products', 'category', 'shop', 'catalog', 'collection', 'store']):
                        catalog_url = urljoin(self.base_url, href)
                        break
        
        # Get example product URL - ensure it's actually a product page
        example_url = product_url  # Use parameter if provided
        if not example_url and best_pattern.get('examples'):
            # Find the best example URL that looks like a real product page
            for example in best_pattern['examples'][:5]:
                href = example.get('href', '')
                if href and not any(avoid in href.lower() for avoid in 
                                  ['account', 'login', 'cart', 'checkout', 'search', 'contact', 'about']):
                    # Prefer URLs that look like product pages
                    if any(indicator in href.lower() for indicator in 
                          ['product', 'item', 'p/', '/pd/', 'detail', '.html']):
                        example_url = urljoin(self.base_url, href)
                        break
            
            # Fallback to first example if no clear product URL found
            if not example_url and best_pattern.get('examples'):
                example_url = urljoin(self.base_url, best_pattern['examples'][0]['href'])
        
        # Build configuration
        config = {
            "site": self._extract_site_name(self.domain),
            "catalog_pages": [catalog_url],
            "pagination": {
                "parameter": "page",
                "template": "?page={page}"
            },
            "products": [{
                "catalog_url": catalog_url,
                "selector": {
                    "pattern": best_pattern['selector'],
                    "explanation": self._generate_detailed_explanation(best_pattern)
                },
                "example_url": example_url or f"{self.base_url}/sample-product",
                "fields": {}
            }]
        }
        
        # Add field patterns in the requested order
        field_order = ['Product_Title', 'Product_Price', 'Brand', 'Manufacturer', 'Sku', 'Model_Number', 'Product_Code']
        field_patterns = self.analysis_results.get('field_patterns', {})
        
        for field_name in field_order:
            if field_name in field_patterns:
                field_pattern = field_patterns[field_name]
                
                # Handle both dict and list cases safely
                if isinstance(field_pattern, dict):
                    config['products'][0]['fields'][field_name] = {
                        "regex": field_pattern.get('regex')
                    }
                elif isinstance(field_pattern, list) and field_pattern:
                    # Take the first pattern if it's a list
                    first_pattern = field_pattern[0]
                    if isinstance(first_pattern, dict):
                        config['products'][0]['fields'][field_name] = {
                            "regex": first_pattern.get('regex')
                        }
                    else:
                        config['products'][0]['fields'][field_name] = {
                            "regex": None
                        }
                else:
                    config['products'][0]['fields'][field_name] = {
                        "regex": None
                    }
            else:
                # Add null regex for fields that weren't found
                config['products'][0]['fields'][field_name] = {
                    "regex": None
                }
        
        self.analysis_results['recommended_config'] = config
        
        # Save configuration to file only if valid
        if config:  # Only save if config is not empty
            config_file = f"scraper_config_{self._extract_site_name(self.domain)}.json"
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            print(f"Configuration saved to {config_file}")
        else:
            print("WARNING: No configuration to save - analysis incomplete")
        return config
    
    def run_full_analysis(self, catalog_url: str = None, product_url: str = None) -> Dict[str, Any]:
        """Run complete website analysis"""
        print(f"Starting full analysis of {self.domain}")
        try:
            # Step 1: Analyze homepage
            homepage_result = self.analyze_homepage()
            
            # Step 2: Analyze catalog page
            catalog_result = self.analyze_catalog_page(catalog_url)
            
            # Step 2.5: Select product link pattern (always show, even for single patterns)
            product_patterns = self.analysis_results.get('product_patterns', [])
            if len(product_patterns) > 1:
                selected_pattern = self._select_product_pattern(product_patterns)
                # Update the analysis results to only include the selected pattern
                self.analysis_results['product_patterns'] = [selected_pattern]
                print(f"Selected product pattern will be used: {selected_pattern.get('selector', 'N/A')}")
            elif len(product_patterns) == 1:
                # Show the single pattern that will be used
                pattern = product_patterns[0]
                print(f"\nUsing single product link pattern found:")
                print(f"   Selector: {pattern.get('selector', 'N/A')}")
                print(f"   Explanation: {pattern.get('explanation', 'No explanation')}")
                print(f"   Confidence: {pattern.get('confidence', 0.0):.2f}")
                print(f"   Found {pattern.get('count', 0)} matching links")
                print(f"Selected product pattern will be used: {pattern.get('selector', 'N/A')}")
            
            # Step 3: Analyze product page
            product_result = self.analyze_product_page(product_url)
            
            # Step 3.5: Select field patterns (if multiple patterns found for any field)
            raw_field_patterns = self.analysis_results.get('field_patterns', {})
            has_multiple_patterns = any(len(patterns) > 1 for patterns in raw_field_patterns.values() if isinstance(patterns, list))
            
            if raw_field_patterns and has_multiple_patterns:
                # Get the product page HTML for pattern selection
                product_html = ""
                product_file = self.analysis_results.get('sample_pages', {}).get('product', '')
                if product_file and os.path.exists(product_file):
                    with open(product_file, 'r', encoding='utf-8') as f:
                        product_html = f.read()
                
                selected_field_patterns = self._show_pattern_selection_menu(raw_field_patterns, product_html)
                self.analysis_results['field_patterns'] = selected_field_patterns
                print("Selected field patterns will be used for configuration generation.")
            
            # Step 4: Generate configuration
            config = self.generate_config(catalog_url, product_url)
            
            # Generate final report
            report = self._generate_analysis_report()
            
            # Ask user if they want to validate and fix patterns
            print(f"\nTest the generated configuration? (y/N): ", end="")
            test_choice = input().strip().lower()
            
            if test_choice in ['y', 'yes']:
                self._run_validation_and_fixing_loop(config)
            
            return {
                'success': True,
                'analysis_results': self.analysis_results,
                'recommended_config': config,
                'report': report
            }
            
        except Exception as e:
            print(f"Analysis failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'analysis_results': self.analysis_results
            }
    
    def _generate_analysis_report(self) -> str:
        """Generate human-readable analysis report"""
        report = [
            f"Website Analysis Report for {self.domain}",
            "=" * 60,
            ""
        ]
        
        # Site info
        site_info = self.analysis_results.get('site_info', {})
        if site_info:
            report.extend([
                "Site Information:",
                f"  Title: {site_info.get('title', 'N/A')}",
                f"  Platform: {', '.join(site_info.get('platform_indicators', ['Unknown']))}",
                f"  Catalog Links Found: {len(site_info.get('potential_catalog_links', []))}",
                ""
            ])
        
        # Protection detected
        if self.analysis_results.get('protection_detected'):
            report.extend([
                "Protection Detected:",
                f"  {', '.join(self.analysis_results['protection_detected'])}",
                ""
            ])
        
        # Product patterns
        product_patterns = self.analysis_results.get('product_patterns', [])
        if product_patterns:
            report.extend([
                "🔗 Product Link Patterns Found:",
            ])
            ai_patterns = [p for p in product_patterns if p.get('pattern') == 'ai_generated']
            traditional_patterns = [p for p in product_patterns if p.get('pattern') != 'ai_generated']
            
            if ai_patterns:
                report.append("  AI-Detected Patterns:")
                for pattern in ai_patterns:
                    report.append(f"    - {pattern.get('count', 0)} links ({pattern.get('confidence', 0.8):.1%} confidence)")
                    report.append(f"      Selector: {pattern.get('selector', 'N/A')}")
                    report.append(f"      {pattern.get('explanation', 'No explanation')}")
            
            if traditional_patterns:
                report.append("  Traditional Patterns:")
                for pattern in traditional_patterns:
                    report.append(f"    - {pattern.get('pattern', 'Unknown')}: {pattern.get('count', 0)} links")
                    report.append(f"      Selector: {pattern.get('selector', 'N/A')}")
            report.append("")
        
        # Field patterns
        field_patterns = self.analysis_results.get('field_patterns', {})
        if field_patterns:
            report.extend([
                "📝 Field Extraction Patterns:",
            ])
            
            # Group by method type
            ai_json_fields = {k: v for k, v in field_patterns.items() if v.get('method') == 'ai_json_path'}
            ai_regex_fields = {k: v for k, v in field_patterns.items() if v.get('method') == 'ai_regex'}
            json_ld_fields = {k: v for k, v in field_patterns.items() if v.get('method') == 'json_ld_structured_data'}
            traditional_fields = {k: v for k, v in field_patterns.items() if v.get('method') not in ['ai_json_path', 'ai_regex', 'json_ld_structured_data']}
            
            if ai_json_fields:
                report.append("  AI JSON Path Extraction:")
                for field, info in ai_json_fields.items():
                    example_value = info.get('example_value') or 'N/A'
                    json_path = info.get('json_path', 'N/A')
                    report.append(f"    - {field}: {json_path} → {example_value}")
            
            if ai_regex_fields:
                report.append("  AI Regex Patterns:")
                for field, info in ai_regex_fields.items():
                    confidence = info.get('confidence', 0.8)
                    report.append(f"    - {field}: AI-generated ({confidence:.1%} confidence)")
            
            if json_ld_fields:
                report.append("  JSON-LD Structured Data:")
                for field, info in json_ld_fields.items():
                    example_value = info.get('example_value') or 'N/A'
                    if isinstance(example_value, str) and len(example_value) > 30:
                        example_display = example_value[:30] + "..."
                    else:
                        example_display = str(example_value)
                    report.append(f"    - {field}: {example_display}")
            
            if traditional_fields:
                report.append("  Traditional Methods:")
                for field, info in traditional_fields.items():
                    example_value = info.get('example_value') or 'N/A'
                    if isinstance(example_value, str) and len(example_value) > 30:
                        example_display = example_value[:30] + "..."
                    else:
                        example_display = str(example_value)
                    report.append(f"    - {field}: {info.get('method', 'unknown')} ({example_display})")
            
            report.append("")
        
        # Errors
        if self.analysis_results.get('errors'):
            report.extend([
                "ERRORS Encountered:",
            ])
            for error in self.analysis_results['errors']:
                report.append(f"  - {error}")
            report.append("")
        
        # Sample files
        sample_pages = self.analysis_results.get('sample_pages', {})
        if sample_pages:
            report.extend([
                "📁 Sample Files Generated:",
            ])
            for page_type, filename in sample_pages.items():
                report.append(f"  - {page_type.title()}: {filename}")
            report.append("")
        
        return "\n".join(report)

def main():
    """Main function with interactive input"""
    print("🌟 UNIVERSAL WEBSITE ANALYZER")
    print("=" * 60)
    print("Automatically analyzes any e-commerce website and generates")
    print("scraper configurations with pattern detection and field extraction!")
    print()
    
    # Get website URL from user
    while True:
        url = input("🔗 Enter website URL to analyze: ").strip()
        if url:
            # Add http:// if no protocol specified
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            break
        print_error("ERROR: Please enter a valid URL")
    
    # Unified AI-POWERED mode
    print_info("\nInitializing AI-POWERED analysis...")
    print_success("   ✓ OpenAI integration enabled")
    print_success("   ✓ Anti-bot protection bypass enabled") 
    print_success("   ✓ Proxy rotation enabled")
    print_success("   ✓ Deep analysis enabled")
    
    simple_mode = False
    use_ai = True
    
    # Optional specific URLs
    catalog_url = input("\nSpecific catalog URL (optional, press Enter to skip): ").strip() or None
    product_url = input("Specific product URL (optional, press Enter to skip): ").strip() or None
    
    print("\n" + "=" * 60)
    
    # Initialize AI-POWERED analyzer with all features
    analyzer = UniversalWebsiteAnalyzer(
        base_url=url,
        use_ai=True
        # All other defaults are already optimal (selenium=True, proxies=True, deep_analysis=True)
    )
    
    # Run analysis
    print(f"\nAnalyzing: {url}")
    print("=" * 60)
    
    try:
        results = analyzer.run_full_analysis(
            catalog_url=catalog_url,
            product_url=product_url
        )
        
        if results['success']:
            print(results['report'])
            
            # Check if we actually have a valid configuration
            config = results.get('recommended_config', {})
            if config and 'products' in config and config['products']:
                print_success(f"✓ Analysis completed successfully!")
                config_file = f"scraper_config_{analyzer._extract_site_name(analyzer.domain)}.json"
                print_success(f"✓ Configuration saved to: {config_file}")
                
                # Show quick summary
                fields = config['products'][0].get('fields', {})
                print_info(f"Detected {len(fields)} field patterns: {', '.join(fields.keys())}")
            else:
                print_warning(f"WARNING: Analysis completed but no configuration generated")
                print_info(f"TIP: The website may have protection that prevented proper analysis")
            
            # Ask if user wants to test the configuration (only if config exists)
            if config and 'products' in config and config['products']:
                test_config = input(f"\nTest the generated configuration? (y/N): ").strip().lower()
                if test_config == 'y':
                    print_info(f"\nTIP: You can test the configuration with:")
                    print_highlight(f"   python validate.py {config_file}")
        else:
            print_error(f"ERROR: Analysis failed: {results['error']}")
            print_info(f"TIP: The website may have strong protection or be temporarily unavailable")
            return 1
            
    except KeyboardInterrupt:
        print_warning("\n\nWARNING: Analysis interrupted by user")
        return 1
    except Exception as e:
        print_error(f"\nERROR: Unexpected error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
