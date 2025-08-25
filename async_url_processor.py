#!/usr/bin/env python3heo
"""
Parallel Async URL Processor for Product-Details Pattern
High-speed processing using aiohttp and asyncio for maximum concurrency
With smart approach memory system for optimal performance per domain
"""
import aiohttp
import asyncio
import re
import time
import random
import json
import os
import subprocess
from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, Optional, List

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  Playwright not available - only simple/proxy approaches will work")

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
            print(f"⚠️  Could not load approach memory: {e}")
        return {}
    
    def save_memory(self):
        """Save approach memory to file"""
        try:
            with open(self.memory_file, 'w') as f:
                json.dump(self.memory, f, indent=2)
        except Exception as e:
            print(f"⚠️  Could not save approach memory: {e}")
    
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

class AsyncURLProcessor:
    """
    High-speed async URL processor with dedicated content retrieval memory.
    
    Focuses on efficient content retrieval for pattern matching, independent 
    from structural analysis. Uses separate approach memory optimized for
    bulk HTML content fetching rather than complex DOM manipulation.
    
    Supports 'simple' (direct requests) and 'proxy' approaches.
    """
    def __init__(self, pattern=None, min_count=25, max_concurrent=20):
        self.min_count = min_count
        self.max_concurrent = max_concurrent  # Reduced from 50 to 20
        self.pattern = pattern or r'<div class="product-details abt-pricing"'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        }
        
        # Rotating user agents and headers for better stealth
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        self.session_count = 0  # Track session rotations
        

        
        # Initialize approach memory (separate from analyzer/validate)
        self.approach_memory = ApproachMemory('async_processor_memory.json')
        
        # Webshare proxy configuration (same as Universal Website Analyzer)
        self.webshare_proxy = {
            'server': 'http://p.webshare.io:80',
            'username': 'hiqjuwfu-rotate',
            'password': 'xmq4ru7a995q'
        }
        
        # Counters
        self.processed_count = 0
        self.valid_count = 0
        self.error_count = 0
        self.valid_urls = []
        self.start_time = None
        self._counter_lock = asyncio.Lock()
        
        # Two-phase processing: retry queue for timeout/network errors
        self.retry_queue = []  # URLs that need retry due to network/timeout errors
        self.retry_processed = 0
        self.retry_success = 0
        
        # Adaptive throttling and domain-based rate limiting
        self.domain_semaphores = {}  # Per-domain concurrency limits
        self.domain_delays = {}      # Per-domain adaptive delays
        self.domain_error_counts = {} # Track errors per domain
        self.max_domain_concurrent = 3  # Max concurrent requests per domain
        self.base_delay = 0.5       # Base delay between requests (increased from 0.1-0.3)
        self.adaptive_delay = 0.5   # Current adaptive delay
        
        # Approach statistics (expand based on Playwright availability)
        self.approach_stats = {
            'simple': {'attempts': 0, 'successes': 0},
            'proxy': {'attempts': 0, 'successes': 0}
        }
        
        if PLAYWRIGHT_AVAILABLE:
            self.approach_stats.update({
                'playwright_headless_no_proxy': {'attempts': 0, 'successes': 0},
                'playwright_headless_proxy': {'attempts': 0, 'successes': 0},
                'playwright_visible_no_proxy': {'attempts': 0, 'successes': 0},
                'playwright_visible_proxy': {'attempts': 0, 'successes': 0}
            })
    
    def get_domain_semaphore(self, domain):
        """Get or create a semaphore for domain-specific rate limiting"""
        if domain not in self.domain_semaphores:
            self.domain_semaphores[domain] = asyncio.Semaphore(self.max_domain_concurrent)
            self.domain_delays[domain] = self.base_delay
            self.domain_error_counts[domain] = 0
        return self.domain_semaphores[domain]
    
    async def adaptive_delay_for_domain(self, domain, had_error=False):
        """Apply adaptive delay based on domain performance"""
        if had_error:
            # Increase delay for this domain when errors occur
            self.domain_error_counts[domain] = self.domain_error_counts.get(domain, 0) + 1
            error_count = self.domain_error_counts[domain]
            
            # Exponential backoff per domain: 0.5s -> 1s -> 2s -> 4s -> max 10s
            new_delay = min(self.base_delay * (2 ** min(error_count - 1, 4)), 10.0)
            self.domain_delays[domain] = new_delay
            
            if error_count % 5 == 1:  # Log every 5th error
                print(f"⚠️  Domain {domain} having issues, increased delay to {new_delay:.1f}s")
        else:
            # Gradually reduce delay on success (but don't go below base)
            current_delay = self.domain_delays.get(domain, self.base_delay)
            if current_delay > self.base_delay:
                new_delay = max(current_delay * 0.8, self.base_delay)
                self.domain_delays[domain] = new_delay
        
        # Apply the domain-specific delay
        domain_delay = self.domain_delays.get(domain, self.base_delay)
        await asyncio.sleep(domain_delay + random.uniform(0, 0.2))
    
    def _get_domain(self, url):
        """Extract domain from URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return ""
    
    def _get_rotating_headers(self, domain=""):
        """Get rotating headers with different user agents for stealth"""
        import random
        
        # Select user agent based on session count (every 5 URLs)
        agent_index = (self.session_count // 5) % len(self.user_agents)
        user_agent = self.user_agents[agent_index]
        
        # Base headers with rotating user agent
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': random.choice(['en-US,en;q=0.9', 'en-US,en;q=0.8,es;q=0.7', 'en-GB,en;q=0.9']),
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Add browser-specific headers
        if 'Chrome' in user_agent:
            chrome_version = '120' if '120.0.0.0' in user_agent else '119'
            headers.update({
                'sec-ch-ua': f'"Not_A Brand";v="8", "Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': random.choice(['"Windows"', '"macOS"', '"Linux"']),
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1'
            })
        elif 'Firefox' in user_agent:
            headers['DNT'] = '1'
        elif 'Safari' in user_agent and 'Chrome' not in user_agent:
            headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        
        # Academy.com specific enhancements
        if 'academy.com' in domain.lower():
            headers.update({
                'Cache-Control': random.choice(['no-cache', 'max-age=0']),
                'Pragma': 'no-cache' if random.random() > 0.5 else None
            })
            # Remove None values
            headers = {k: v for k, v in headers.items() if v is not None}
        
        return headers
    
    def deduplicate_parent_child_urls(self, urls: List[str]) -> List[str]:
        """
        Remove child URLs when parent URLs exist to avoid duplicate processing.
        Only applies to meaningful category hierarchies, not homepage elimination.
        """
        if not urls:
            return urls
        
        # Normalize URLs - remove trailing slashes and fragments for comparison
        normalized_urls = []
        for url in urls:
            # Remove trailing slashes and fragments (#)
            clean_url = url.rstrip('/').split('#')[0].split('?')[0]
            normalized_urls.append((clean_url, url))  # (normalized, original)
        
        # Sort by URL length (shortest first) so parents come before children
        normalized_urls.sort(key=lambda x: len(x[0]))
        
        # Keep track of URLs to keep
        urls_to_keep = []
        excluded_urls = set()
        
        for normalized_url, original_url in normalized_urls:
            # Skip if this URL was already marked as a child of a parent
            if normalized_url in excluded_urls:
                continue
                
            # Add this URL to keep list
            urls_to_keep.append(original_url)
            
            # Only exclude children if the parent has meaningful depth (not just homepage)
            # Count path segments to determine if this is a meaningful parent
            path_segments = len([seg for seg in normalized_url.split('/')[3:] if seg])  # Skip protocol and domain
            
            # Only apply parent-child logic if parent has at least 1 path segment
            # This prevents homepage from eliminating category pages
            if path_segments >= 1:
                # Mark all URLs that start with this URL as children (exclude them)
                for other_normalized, other_original in normalized_urls:
                    if (other_normalized != normalized_url and 
                        other_normalized.startswith(normalized_url + '/') and
                        other_normalized not in excluded_urls):
                        excluded_urls.add(other_normalized)
        
        return urls_to_keep
    

    
    async def validate_single_url(self, session, semaphore, url):
        """Validate a single URL with smart approach selection"""
        async with semaphore:  # Global concurrency limit
            try:
                # Extract domain for per-domain rate limiting
                domain = self.approach_memory.get_domain_from_url(url)
                domain_semaphore = self.get_domain_semaphore(domain)
                
                # Per-domain concurrency limit
                async with domain_semaphore:
                    # Adaptive delay based on domain performance
                    await self.adaptive_delay_for_domain(domain, had_error=False)
                    
                    successful_approach = self.approach_memory.get_successful_approach(domain)
                    
                    # Define approaches to try (prioritize remembered approach)
                    approaches = []
                    all_approaches = ['simple', 'proxy']
                    
                    # Add Playwright approaches if available
                    if PLAYWRIGHT_AVAILABLE:
                        all_approaches.extend([
                            'playwright_headless_no_proxy',
                            'playwright_headless_proxy', 
                            'playwright_visible_no_proxy',
                            'playwright_visible_proxy'
                        ])
                    
                    # Use processor-specific approach memory (simple priority logic)
                    if successful_approach and successful_approach in all_approaches:
                        # Use ONLY the remembered approach (since we tested it sequentially)
                        approaches = [successful_approach]
                        # Debug for first few URLs
                        if self.processed_count <= 10:
                            print(f"🧠 Using learned {successful_approach} approach for {domain}")
                    else:
                        # Fallback - try both approaches (shouldn't happen after sequential testing)
                        approaches = ['simple', 'proxy']
                        if self.processed_count <= 10:
                            print(f"⚠️ No learned approach for {domain}, trying both")
                    
                    # Phase 1: Try each approach once (no retries during main processing)
                    had_error = False
                    for approach in approaches:
                        # Only track stats for supported approaches
                        if approach in self.approach_stats:
                            self.approach_stats[approach]['attempts'] += 1
                        
                        success, count, processed_url = await self._try_approach(session, url, approach)
                        
                        if success is True:
                            # Record successful approach for content retrieval (processor-specific)
                            if not successful_approach or successful_approach != approach:
                                self.approach_memory.record_successful_approach(domain, approach)
                                # ALWAYS log when we learn a new domain approach (not just every 50th)
                                print(f"🧠✅ LEARNED: {approach} works for content retrieval from {domain}")
                            
                            # Track stats for supported approaches
                            if approach in self.approach_stats:
                                self.approach_stats[approach]['successes'] += 1
                            
                            return True, count, processed_url
                        elif success == "invalid":
                            # Valid HTTP response but insufficient pattern matches - don't retry
                            return False, count, processed_url
                        else:
                            # This approach failed - mark as error for adaptive delay
                            had_error = True
                        # Continue to next approach if this one failed
                    
                    # All approaches failed - apply adaptive delay and add to retry queue
                    if had_error:
                        await self.adaptive_delay_for_domain(domain, had_error=True)
                    
                    async with self._counter_lock:
                        self.processed_count += 1
                        self.error_count += 1
                        current_count = self.processed_count
                        
                        # Add to retry queue with the best approach to try
                        retry_approach = successful_approach if successful_approach else approaches[0]
                        self.retry_queue.append({
                            'url': url.strip(),
                            'approach': retry_approach,
                            'domain': domain
                        })
                        
                    if current_count % 50 == 0:  # Log occasionally
                        print(f"⏳ [{current_count}] QUEUED FOR RETRY ({retry_approach}): {url.strip()}")
                    return False, 0, url.strip()
                
            except Exception as e:
                # Apply adaptive delay for this domain due to error
                try:
                    domain = self.approach_memory.get_domain_from_url(url)
                    await self.adaptive_delay_for_domain(domain, had_error=True)
                except:
                    pass  # Don't let delay errors break the flow
                
                # Thread-safe counter updates
                async with self._counter_lock:
                    self.processed_count += 1
                    self.error_count += 1
                    current_count = self.processed_count
                    
                print(f"❌ [{current_count}] ERROR: {url.strip()} - {str(e)[:50]}")
                return False, 0, url.strip()
    
    async def retry_single_url(self, session, semaphore, retry_item):
        """Retry a single URL from the retry queue (Phase 2)"""
        async with semaphore:  # Global concurrency limit
            try:
                url = retry_item['url']
                approach = retry_item['approach']
                domain = retry_item['domain']
                
                # Use domain-specific rate limiting for retries too
                domain_semaphore = self.get_domain_semaphore(domain)
                async with domain_semaphore:
                    # Apply adaptive delay (retries get longer delays)
                    await self.adaptive_delay_for_domain(domain, had_error=False)
                    
                    # Track retry stats
                    if approach in self.approach_stats:
                        self.approach_stats[approach]['attempts'] += 1
                    
                    success, count, processed_url = await self._try_approach(session, url, approach)
                    
                    # Thread-safe counter updates
                    async with self._counter_lock:
                        self.retry_processed += 1
                        current_retry = self.retry_processed
                        
                        if success is True:
                            self.retry_success += 1
                            self.valid_count += 1  # Add to total valid count
                            self.valid_urls.append({
                                'url': url.strip(),
                                'count': count,
                                'approach': approach
                            })
                            
                            # Track stats for successful retries
                            if approach in self.approach_stats:
                                self.approach_stats[approach]['successes'] += 1
                            
                            print(f"🔄✅ [{current_retry}] RETRY SUCCESS ({approach}): {url.strip()} ({count} instances)")
                            return True, count, processed_url
                        elif success == "invalid":
                            # Valid response but insufficient matches - don't count as error
                            print(f"🔄❌ [{current_retry}] RETRY INVALID ({approach}): {url.strip()} ({count} instances)")
                            return False, count, processed_url
                        else:
                            # Still failed after retry - apply adaptive delay
                            await self.adaptive_delay_for_domain(domain, had_error=True)
                            print(f"🔄❌ [{current_retry}] RETRY FAILED ({approach}): {url.strip()}")
                            return False, 0, processed_url
                        
            except Exception as e:
                async with self._counter_lock:
                    self.retry_processed += 1
                    current_retry = self.retry_processed
                    
                print(f"🔄❌ [{current_retry}] RETRY ERROR: {retry_item['url']} - {str(e)[:50]}")
                return False, 0, retry_item['url']
    
    async def _try_approach(self, session, url, approach):
        """Try a specific approach (simple or proxy)"""
        try:
            # Longer timeout for Academy.com due to dynamic content loading
            domain = self._get_domain(url)
            if 'academy.com' in domain.lower():
                timeout = aiohttp.ClientTimeout(total=60, connect=20)  # Extra time for Academy.com
            else:
                timeout = aiohttp.ClientTimeout(total=45, connect=15)  # Standard timeout
            
            if approach == 'simple':
                # Simple approach: direct request with rotating headers
                headers = self._get_rotating_headers(domain)
                # Increment session count for rotation tracking
                self.session_count += 1
                rotation_interval = random.randint(4, 6)  # Randomize rotation between 4-6 URLs
                if self.session_count % rotation_interval == 1:  # Log rotation
                    agent_short = headers['User-Agent'].split('/')[-1].split()[0]  # Get browser name
                    print(f"🔄 Identity rotation #{(self.session_count-1)//5 + 1}: Using {agent_short}")
                
                async with session.get(url.strip(), headers=headers, timeout=timeout) as response:
                    return await self._process_response(response, url, approach)
                    
            elif approach == 'proxy':
                # Proxy approach: use Webshare proxy with rotating headers
                headers = self._get_rotating_headers(domain)
                # Increment session count for rotation tracking
                self.session_count += 1
                rotation_interval = random.randint(4, 6)  # Randomize rotation between 4-6 URLs
                if self.session_count % rotation_interval == 1:  # Log rotation
                    agent_short = headers['User-Agent'].split('/')[-1].split()[0]  # Get browser name
                    print(f"🔄 Identity rotation #{(self.session_count-1)//5 + 1}: Using {agent_short} (proxy)")
                
                proxy_url = f"http://{self.webshare_proxy['username']}:{self.webshare_proxy['password']}@{self.webshare_proxy['server'].replace('http://', '')}"
                async with session.get(url.strip(), headers=headers, timeout=timeout, proxy=proxy_url) as response:
                    return await self._process_response(response, url, approach)
                    
            elif approach.startswith('playwright_') and PLAYWRIGHT_AVAILABLE:
                # Playwright approaches: headless/visible + no_proxy/proxy
                return await self._try_playwright_approach(url, approach)
                
            else:
                # Unsupported approach - skip
                if self.processed_count % 100 == 0:  # Log occasionally
                    print(f"⚠️  Skipping unsupported approach '{approach}' for {url.strip()}")
                return False, 0, url.strip()
            
            return False, 0, url.strip()
            
        except asyncio.TimeoutError:
            # Return False to trigger retry logic in validate_single_url
            return False, 0, url.strip()
            
        except aiohttp.ClientError as e:
            # Return False to trigger retry logic in validate_single_url
            return False, 0, url.strip()
            
        except Exception as e:
            # Return False to trigger retry logic in validate_single_url
            return False, 0, url.strip()
    
    async def _try_playwright_approach(self, url, approach):
        """Try Playwright approach with different configurations"""
        try:
            # Parse approach configuration
            is_headless = 'headless' in approach
            use_proxy = 'proxy' in approach
            
            # Set up proxy if needed
            proxy_config = None
            if use_proxy:
                proxy_config = {
                    'server': self.webshare_proxy['server'],
                    'username': self.webshare_proxy['username'],
                    'password': self.webshare_proxy['password']
                }
            
            async with async_playwright() as p:
                # Launch browser
                browser = await p.chromium.launch(
                    headless=is_headless,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-software-rasterizer'
                    ]
                )
                
                # Create context with proxy if needed
                context_options = {
                    'viewport': {'width': 1920, 'height': 1080},
                    'user_agent': self.headers['User-Agent']
                }
                if proxy_config:
                    context_options['proxy'] = proxy_config
                
                context = await browser.new_context(**context_options)
                page = await context.new_page()
                
                try:
                    # Navigate to page
                    # Longer timeout for Academy.com due to dynamic content
                    domain = self._get_domain(url)
                    if 'academy.com' in domain.lower():
                        await page.goto(url.strip(), wait_until='networkidle', timeout=45000)
                        # Additional wait for JavaScript content to load
                        await page.wait_for_timeout(3000)  # Wait 3 seconds for dynamic content
                    else:
                        await page.goto(url.strip(), wait_until='networkidle', timeout=30000)
                    
                    # Get page content
                    html_content = await page.content()
                    
                    # Search for pattern
                    matches = re.findall(self.pattern, html_content, re.IGNORECASE)
                    count = len(matches)
                    
                    # Thread-safe counter updates
                    async with self._counter_lock:
                        self.processed_count += 1
                        current_count = self.processed_count
                        
                        if count >= self.min_count:
                            self.valid_count += 1
                            self.valid_urls.append({
                                'url': url.strip(),
                                'count': count,
                                'approach': approach
                            })
                    
                    if count >= self.min_count:
                        print(f"✅ [{current_count}] VALID ({approach}): {url.strip()} ({count} instances)")
                        return True, count, url.strip()
                    else:
                        # Show all URLs for real-time monitoring
                        print(f"❌ [{current_count}] INVALID ({approach}): {url.strip()} ({count} instances)")
                        return "invalid", count, url.strip()
                        
                finally:
                    await context.close()
                    await browser.close()
                    
        except Exception as e:
            # Thread-safe counter updates
            async with self._counter_lock:
                self.processed_count += 1
                self.error_count += 1
                current_count = self.processed_count
                
            if current_count % 50 == 0:  # Log occasionally
                print(f"❌ [{current_count}] PLAYWRIGHT ERROR ({approach}): {url.strip()} - {str(e)[:50]}")
            return False, 0, url.strip()
                        
    async def _process_response(self, response, url, approach):
        """Process HTTP response and check for pattern"""
        if response.status == 200:
            try:
                html_content = await response.text()
                
                # Check content and add delays for dynamic loading
                domain = self._get_domain(url)
                if 'academy.com' in domain.lower():
                    # Academy.com loads content via JavaScript after initial response
                    # aiohttp cannot execute JavaScript, so we're limited to initial HTML
                    if 'Loading' in html_content or 'loading' in html_content or len(html_content) < 10000:
                        print(f"⚠️  Academy.com page appears to be loading content dynamically: {url.strip()}")
                        print(f"    Content length: {len(html_content)} chars - may need JavaScript execution")
                
                # Use the original pattern for all sites (no fallbacks)
                matches = re.findall(self.pattern, html_content, re.IGNORECASE)
                count = len(matches)
            except Exception as e:
                # Failed to read response content
                print(f"⚠️  Failed to read response content for {url}: {str(e)[:50]}")
                return "invalid", 0, url.strip()
            
            # Thread-safe counter updates
            async with self._counter_lock:
                self.processed_count += 1
                current_count = self.processed_count
                
                if count >= self.min_count:
                    self.valid_count += 1
                    self.valid_urls.append({
                        'url': url.strip(),
                        'count': count,
                        'approach': approach
                    })
            
            if count >= self.min_count:
                print(f"✅ [{current_count}] VALID ({approach}) [HTTP {response.status}]: {url.strip()} ({count} instances)")
                return True, count, url.strip()
            else:
                # Show all URLs for real-time monitoring
                print(f"❌ [{current_count}] INVALID ({approach}) [HTTP {response.status}]: {url.strip()} ({count} instances)")
                # Return "invalid" status (not retry-able) - use special return value
                return "invalid", count, url.strip()
        else:
            # HTTP error status (not 200)
            if response.status in [429, 503, 502, 504]:  # Rate limit or server errors - retry
                async with self._counter_lock:
                    self.processed_count += 1
                    current_count = self.processed_count
                print(f"🔄 [{current_count}] RETRY NEEDED ({approach}) [HTTP {response.status}]: {url.strip()}")
                return False, 0, url.strip()
            else:
                # Other HTTP errors (404, 403, etc.) - don't retry
                async with self._counter_lock:
                    self.processed_count += 1
                    self.error_count += 1
                    current_count = self.processed_count
                    
                if response.status not in [404, 403] and current_count % 50 == 0:  # Don't spam common errors
                    print(f"⚠️  [{current_count}] HTTP {response.status} ({approach}): {url.strip()}")
                return "invalid", 0, url.strip()
    
    def save_progress(self):
        """Save current progress to file"""
        filename = 'valid_urls.txt'
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Async Product Details Pattern Validation Results with Smart Approach Memory\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Pattern: {self.pattern}\n")
            f.write(f"# Minimum Count: {self.min_count}\n")
            f.write(f"# Max Concurrent: {self.max_concurrent}\n")
            f.write(f"# Total Processed: {self.processed_count}\n")
            f.write(f"# Valid URLs Found: {self.valid_count}\n")
            f.write(f"# Error Count: {self.error_count}\n")
            f.write(f"# Success Rate: {(self.valid_count/self.processed_count*100):.2f}%\n")
            f.write(f"#\n")
            f.write(f"# Approach Statistics:\n")
            for approach, stats in self.approach_stats.items():
                attempts = stats['attempts']
                successes = stats['successes']
                success_rate = (successes / attempts * 100) if attempts > 0 else 0
                f.write(f"# {approach.upper()}: {successes:,}/{attempts:,} success ({success_rate:.1f}%)\n")
            f.write(f"# Domains learned: {len(self.approach_memory.memory):,}\n")
            f.write(f"#\n")
            
            for item in sorted(self.valid_urls, key=lambda x: x['count'], reverse=True):
                approach_info = f" (approach: {item.get('approach', 'unknown')})" if 'approach' in item else ""
                f.write(f"{item['url']} (count: {item['count']}){approach_info}\n")
        
        print(f"💾 Results saved to: {filename}")
        return filename
    
    async def monitor_progress(self, total_urls):
        """Monitor and display progress while URLs are being processed concurrently"""
        last_processed = 0
        
        while True:
            await asyncio.sleep(10)  # Update every 10 seconds
            
            # Check if we've made progress
            if self.processed_count > last_processed:
                elapsed = time.time() - self.start_time
                rate = self.processed_count / elapsed if elapsed > 0 else 0
                eta = (total_urls - self.processed_count) / rate if rate > 0 else 0
                
                print(f"\n📊 CONCURRENT PROGRESS UPDATE:")
                print(f"   Processed: {self.processed_count:,}/{total_urls:,} ({(self.processed_count/total_urls*100):.1f}%)")
                print(f"   Valid URLs: {self.valid_count:,}")
                print(f"   Success Rate: {(self.valid_count/self.processed_count*100):.1f}%")
                print(f"   Rate: {rate:.1f} URLs/sec")
                print(f"   ETA: {eta/60:.1f} minutes")
                print(f"   Retry Queue: {len(self.retry_queue)} URLs queued for Phase 2")
                print("=" * 60)
                
                last_processed = self.processed_count
                
                # Save progress periodically
                if self.processed_count % 1000 == 0:
                    self.save_progress()
            
            # Check if we're done (all URLs processed)
            if self.processed_count >= total_urls:
                break
    
    async def test_approaches_sequentially(self, session, test_urls):
        """Test approaches on user-provided sample URL to learn domain patterns"""
        print(f"🧪 Testing approaches on sample catalog URL to learn domain patterns...")
        
        # Ask user for a valid catalog URL to test
        print("\n" + "="*80)
        print("🎯 APPROACH TESTING SETUP")
        print("To optimize processing, we need to test which approach works best.")
        print("Please provide a VALID product catalog/listing page URL that contains")
        print("multiple instances of your target pattern.")
        print("\nExamples of good test URLs:")
        print("  • Product category pages (e.g., /category/tools/)")
        print("  • Search results pages (e.g., /search?q=products)")
        print("  • Product listing pages (e.g., /products/)")
        print("="*80)
        
        # Get test URL from user
        while True:
            test_url = input("\nEnter a valid catalog URL to test approaches: ").strip()
            if test_url:
                # Validate URL format
                if test_url.startswith(('http://', 'https://')):
                    break
                else:
                    print("⚠️  Please enter a complete URL starting with http:// or https://")
            else:
                print("⚠️  URL cannot be empty")
        
        domain = self.approach_memory.get_domain_from_url(test_url)
        
        # Check if we already know this domain
        successful_approach = self.approach_memory.get_successful_approach(domain)
        if successful_approach:
            print(f"🧠 Already know {domain} works with {successful_approach}")
            print(f"🧪 Approach testing complete. Using remembered approach.")
            return
        
        # Test approaches for this domain
        print(f"🧪 Testing all approaches for {domain}...")
        print(f"🎯 Test URL: {test_url}")
        print("="*80)
        
        # Get all available approaches (including Playwright if available)
        all_approaches = ['simple', 'proxy']
        if PLAYWRIGHT_AVAILABLE:
            all_approaches.extend([
                'playwright_headless_no_proxy',
                'playwright_headless_proxy', 
                'playwright_visible_no_proxy',
                'playwright_visible_proxy'
            ])
        
        # Test all approaches on the user-provided URL
        for approach in all_approaches:
            print(f"  🔍 Testing {approach} approach...")
            
            try:
                if approach.startswith('playwright_') and PLAYWRIGHT_AVAILABLE:
                    # Test Playwright approach
                    success, count, _ = await self._try_playwright_approach(test_url, approach)
                    
                    if success and count >= self.min_count:
                        self.approach_memory.record_successful_approach(domain, approach)
                        print(f"  ✅ SUCCESS: {approach} works for {domain} (found {count} matches)")
                        break
                    else:
                        print(f"  ❌ FAILED: {approach} found only {count} matches (need {self.min_count})")
                
                elif approach == 'simple':
                    # Test simple HTTP approach
                    success, count = await self._test_http_approach(session, test_url, approach, domain)
                    if success:
                        break
                        
                elif approach == 'proxy':
                    # Test proxy HTTP approach  
                    success, count = await self._test_http_approach(session, test_url, approach, domain)
                    if success:
                        break
                
            except Exception as e:
                print(f"    ❌ ERROR with {approach}: {str(e)[:100]}")
        else:
            print(f"  ⚠️  No approach worked for {domain}")
        
        print(f"🧪 Approach testing complete. Learned {len(self.approach_memory.memory)} domain patterns")
        print("=" * 80)
    
    async def _test_http_approach(self, session, test_url, approach, domain):
        """Test HTTP approach (simple or proxy) with detailed analysis"""
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        try:
            if approach == 'simple':
                async with session.get(test_url.strip(), headers=self.headers, timeout=timeout) as response:
                    return await self._analyze_response(response, test_url, approach, domain)
            elif approach == 'proxy':
                proxy_url = f"http://{self.webshare_proxy['username']}:{self.webshare_proxy['password']}@{self.webshare_proxy['server'].replace('http://', '')}"
                async with session.get(test_url.strip(), headers=self.headers, timeout=timeout, proxy=proxy_url) as response:
                    return await self._analyze_response(response, test_url, approach, domain)
        except Exception as e:
            print(f"    ❌ CONNECTION ERROR: {str(e)[:50]}")
            return False, 0
    
    async def _analyze_response(self, response, test_url, approach, domain):
        """Analyze HTTP response and provide detailed feedback"""
        if response.status == 200:
            try:
                html_content = await response.text()
                matches = re.findall(self.pattern, html_content, re.IGNORECASE)
                count = len(matches)
            except Exception as e:
                print(f"⚠️  Failed to read response content during analysis for {domain}: {str(e)[:50]}")
                return False, 0
            
            print(f"    📄 Got HTML content: {len(html_content)} characters")
            print(f"    🔍 Pattern: {self.pattern}")
            print(f"    📊 Found: {count} matches")
            
            # Save HTML sample and analyze patterns if no matches found
            if count == 0:
                suffix = "_proxy" if approach == "proxy" else ""
                sample_filename = f"html_sample_{domain.replace('.', '_')}{suffix}.html"
                try:
                    with open(sample_filename, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    print(f"    💾 Saved HTML sample to {sample_filename} for inspection")
                except Exception as e:
                    print(f"    ⚠️  Could not save HTML sample: {str(e)[:50]}")
                
                # Show a snippet of the HTML
                print("    🔍 HTML snippet (first 500 chars):")
                print("    " + html_content[:500].replace('\n', ' ').replace('\r', ''))
                
                # Look for common e-commerce patterns
                print("    🔍 Looking for common product patterns...")
                common_patterns = [
                    r'<div[^>]*class="[^"]*product[^"]*"',
                    r'<div[^>]*class="[^"]*item[^"]*"',
                    r'<article[^>]*class="[^"]*product[^"]*"',
                    r'<div[^>]*data-product[^>]*',
                    r'<div[^>]*class="[^"]*card[^"]*"',
                    r'<div[^>]*class="[^"]*col[^"]*"[^>]*data-',
                    r'<div[^>]*data-item[^>]*'
                ]
                
                for i, pattern in enumerate(common_patterns, 1):
                    pattern_matches = re.findall(pattern, html_content, re.IGNORECASE)
                    if pattern_matches:
                        print(f"      {i}. Found {len(pattern_matches)} matches for: {pattern}")
                        if len(pattern_matches) >= self.min_count:
                            print(f"         ✅ This pattern has enough matches ({len(pattern_matches)} >= {self.min_count})!")
                        # Show first match as example
                        if pattern_matches:
                            print(f"         Example: {pattern_matches[0][:100]}...")
            
            if count >= self.min_count:
                self.approach_memory.record_successful_approach(domain, approach)
                print(f"  ✅ SUCCESS: {approach} works for {domain} (found {count} matches)")
                return True, count
            else:
                print(f"  ❌ FAILED: {approach} found only {count} matches (need {self.min_count})")
                return False, count
        else:
            print(f"    ⚠️ HTTP {response.status}: {test_url}")
            return False, 0
    
    async def process_all_urls_async(self, urls):
        """Process all URLs with high-speed async processing"""
        self.start_time = time.time()
        total_urls = len(urls)
        
        print(f"🚀 Starting HIGH-SPEED async URL validation with CONTENT RETRIEVAL MEMORY")
        print(f"📊 Total URLs to process: {total_urls:,}")
        print(f"🎯 Pattern: {self.pattern}")
        print(f"📈 Minimum count: {self.min_count}")
        print(f"⚡ Max concurrent: {self.max_concurrent}")
        print(f"🧠 Content retrieval memory: {len(self.approach_memory.memory)} domains learned")
        print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # Configure aiohttp session with optimizations
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 2,
            limit_per_host=20,
            ttl_dns_cache=300,
            use_dns_cache=True,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': self.headers['User-Agent']}
        ) as session:
            
            # First: Test approaches sequentially to learn domain patterns
            await self.test_approaches_sequentially(session, urls)
            
            print(f"🚀 Starting PHASE 1: CONCURRENT processing of ALL {total_urls:,} URLs")
            print("📊 Network/timeout errors will be queued for Phase 2 retry")
            print("=" * 80)
            
            # Start all URL processing tasks concurrently (no batching)
            tasks = [
                self.validate_single_url(session, semaphore, url)
                for url in urls
            ]
            
            # Start background task to monitor progress
            progress_task = asyncio.create_task(self.monitor_progress(total_urls))
            
            # Process all URLs concurrently
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                # Cancel progress monitoring
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            
            # Count final results
            final_valid = sum(1 for r in results if isinstance(r, tuple) and r[0])
            final_processed = len([r for r in results if not isinstance(r, Exception)])
            
            print(f"\n✅ PHASE 1 COMPLETE!")
            print(f"📊 Phase 1 results: {final_valid} valid, {final_processed} processed")
            
            # Phase 2: Retry failed URLs (1 retry each)
            if self.retry_queue:
                print(f"\n🔄 Starting PHASE 2: Retry {len(self.retry_queue)} timeout/network error URLs")
                print("📊 Each URL gets 1 retry attempt")
                print("=" * 80)
                
                retry_tasks = [
                    self.retry_single_url(session, semaphore, retry_item)
                    for retry_item in self.retry_queue
                ]
                
                # Process all retry URLs concurrently
                retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
                
                # Count retry results
                retry_valid = sum(1 for r in retry_results if isinstance(r, tuple) and r[0])
                retry_processed = len([r for r in retry_results if not isinstance(r, Exception)])
                
                print(f"\n✅ PHASE 2 COMPLETE!")
                print(f"📊 Retry results: {retry_valid} recovered, {retry_processed} attempted")
                print(f"🎯 Total valid URLs: {self.valid_count + retry_valid}")
        
        # Final results
        elapsed = time.time() - self.start_time
        print(f"\n🎉 ASYNC VALIDATION COMPLETE!")
        print(f"📊 Final Results:")
        print(f"   Phase 1 URLs processed: {self.processed_count:,}")
        print(f"   Phase 2 URLs retried: {self.retry_processed:,}")
        print(f"   Total URLs processed: {self.processed_count + self.retry_processed:,}")
        print(f"   Valid URLs found: {self.valid_count:,}")
        print(f"   Retry recoveries: {self.retry_success:,}")
        print(f"   Errors encountered: {self.error_count:,}")
        total_processed = self.processed_count + self.retry_processed
        print(f"   Success rate: {(self.valid_count/total_processed*100):.2f}%")
        print(f"   Total time: {elapsed/60:.1f} minutes")
        print(f"   Average rate: {self.processed_count/elapsed:.1f} URLs/sec")
        print(f"   Speed improvement: ~{(self.processed_count/elapsed)/2:.0f}x faster than sync!")
        
        # Approach statistics
        print(f"\n🧠 Approach Statistics:")
        for approach, stats in self.approach_stats.items():
            attempts = stats['attempts']
            successes = stats['successes']
            success_rate = (successes / attempts * 100) if attempts > 0 else 0
            print(f"   {approach.upper()}: {successes:,}/{attempts:,} success ({success_rate:.1f}%)")
        
        # Memory statistics
        memory_count = len(self.approach_memory.memory)
        print(f"   Domains learned: {memory_count:,}")
        
        if memory_count > 0:
            approach_distribution = {}
            for domain, approach in self.approach_memory.memory.items():
                approach_distribution[approach] = approach_distribution.get(approach, 0) + 1
            
            print(f"   Memory distribution:")
            for approach, count in approach_distribution.items():
                percentage = (count / memory_count * 100)
                print(f"     {approach}: {count} domains ({percentage:.1f}%)")
        
        # Adaptive throttling statistics
        if self.domain_delays:
            print(f"\n🔧 Adaptive Throttling Results:")
            print(f"   Domains monitored: {len(self.domain_delays):,}")
            
            # Show domains with increased delays (indicating server stress)
            stressed_domains = {d: delay for d, delay in self.domain_delays.items() if delay > self.base_delay}
            if stressed_domains:
                print(f"   Domains with adaptive delays: {len(stressed_domains)}")
                for domain, delay in sorted(stressed_domains.items(), key=lambda x: x[1], reverse=True)[:5]:
                    error_count = self.domain_error_counts.get(domain, 0)
                    print(f"     {domain}: {delay:.1f}s delay ({error_count} errors)")
            else:
                print(f"   All domains running at base delay ({self.base_delay}s)")
                
            # Show total error distribution
            total_domain_errors = sum(self.domain_error_counts.values())
            if total_domain_errors > 0:
                print(f"   Total domain-specific errors: {total_domain_errors:,}")
                most_errors = sorted(self.domain_error_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                for domain, errors in most_errors:
                    if errors > 0:
                        print(f"     {domain}: {errors} errors")
        
        # Apply deduplication to VALID URLs only (after validation)
        if self.valid_urls:
            print(f"\n🔧 Applying parent/child deduplication to {len(self.valid_urls)} valid URLs...")
            valid_url_list = [url_data['url'] for url_data in self.valid_urls]
            deduplicated_valid_urls = self.deduplicate_parent_child_urls(valid_url_list)
            
            # Filter valid_urls to keep only deduplicated ones
            deduplicated_data = []
            for url in deduplicated_valid_urls:
                for url_data in self.valid_urls:
                    if url_data['url'] == url:
                        deduplicated_data.append(url_data)
                        break
            
            removed_count = len(self.valid_urls) - len(deduplicated_data)
            if removed_count > 0:
                print(f"🔧 Removed {removed_count} child URLs from valid results to avoid duplicates")
                print(f"📊 Final valid URLs after deduplication: {len(deduplicated_data)}")
                
                # Update results with deduplicated valid URLs
                self.valid_urls = deduplicated_data
                self.valid_count = len(deduplicated_data)
            else:
                print("📊 No duplicate parent/child URLs found in valid results")

        # Save final results
        final_file = self.save_progress()
        print(f"✅ Final results saved to: {final_file}")
        
        # Show top results
        if self.valid_urls:
            print(f"\n🏆 TOP 10 RESULTS (by count):")
            top_results = sorted(self.valid_urls, key=lambda x: x['count'], reverse=True)[:10]
            for i, item in enumerate(top_results, 1):
                print(f"   {i:2d}. {item['url']} ({item['count']} instances)")
        
        return self.valid_urls

async def main():
    """Main async processing function"""
    import argparse
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(
        description="High-Speed Async URL Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python async_url_processor.py                                    # Default pattern
  python async_url_processor.py --pattern "div.card" --count 10    # Custom pattern
  python async_url_processor.py --count 50                         # Different count
  python async_url_processor.py --pattern "button.buy-now" --count 5 --concurrent 30
        """
    )
    
    parser.add_argument('--pattern', '-p', 
                       default=None,
                       help='Target pattern to search for')
    parser.add_argument('--count', '-c', type=int, default=None,
                       help='Minimum count required')
    parser.add_argument('--concurrent', type=int, default=50,
                       help='Max concurrent requests (default: 50)')
    parser.add_argument('--file', '-f', default='url.txt',
                       help='Input file containing URLs (default: url.txt)')
    
    args = parser.parse_args()
    
    print("⚡ High-Speed Async URL Processor")
    print("=" * 60)
    
    # Interactive input if not provided via command line
    if args.pattern is None:
        print("🎯 Pattern Configuration:")
        print("Examples:")
        print('  1. <div class="product-details abt-pricing">')
        print('  2. <div class="card h-100">')
        print('  3. <button class="btn btn-brand btn-block addtocart">')
        args.pattern = input("\nEnter HTML pattern to search for: ").strip()
        if not args.pattern:
            args.pattern = '<div class="product-details abt-pricing"'
            print(f"Using default: {args.pattern}")
    
    if args.count is None:
        count_input = input(f"\nEnter minimum count of pattern occurrences (default: 25): ").strip()
        if count_input and count_input.isdigit():
            count_value = int(count_input)
            if count_value > 0:
                args.count = count_value
            else:
                print("⚠️  Count must be positive, using default: 25")
                args.count = 25
        else:
            args.count = 25
            print(f"Using default: {args.count}")
    
    print("=" * 60)
    print(f"🎯 Target Pattern: {args.pattern}")
    print(f"📊 Minimum Count: {args.count}")
    print(f"⚡ Max Concurrent: {args.concurrent}")
    print(f"📁 Input File: {args.file}")
    print("=" * 60)
    
    try:
        # Read URL file
        print(f"📁 Reading {args.file} file...")
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            print(f"❌ Error: File '{args.file}' not found!")
            return
        except Exception as e:
            print(f"❌ Error reading file '{args.file}': {str(e)}")
            return
        
        # Extract URLs using regex (handles malformed XML)
        print("🔍 Extracting URLs from content...")
        url_pattern = r'<loc\s*>(.*?)</loc\s*>'
        urls = re.findall(url_pattern, content, re.IGNORECASE)
        
        if not urls:
            print(f"❌ No URLs found in {args.file}")
            return
        
        print(f"✅ Extracted {len(urls):,} URLs from {args.file}")
        
        # Configuration options
        print(f"\n⚙️  Speed Options:")
        print(f"1. FAST: 50 concurrent (recommended)")
        print(f"2. MODERATE: 30 concurrent")  
        print(f"3. CONSERVATIVE: 15 concurrent")
        print(f"4. CUSTOM: Enter your own concurrent value")
        
        choice = input(f"\nSelect speed (1-4) or press Enter for option 1: ").strip()
        
        if choice == '1' or choice == '':
            max_concurrent = 50
            speed_name = "FAST"
        elif choice == '2':
            max_concurrent = 30
            speed_name = "MODERATE"
        elif choice == '3':
            max_concurrent = 15
            speed_name = "CONSERVATIVE"
        elif choice == '4':
            # Ask user for custom concurrent value
            while True:
                custom_input = input(f"Enter custom concurrent value (5-1000, recommended: 20-200): ").strip()
                if custom_input.isdigit():
                    custom_concurrent = int(custom_input)
                    if 5 <= custom_concurrent <= 1000:
                        max_concurrent = custom_concurrent
                        speed_name = "CUSTOM"
                        break
                    else:
                        print("⚠️  Please enter a value between 5 and 1000")
                else:
                    print("⚠️  Please enter a valid number")
        else:
            # Default to FAST for invalid choice
            max_concurrent = 50
            speed_name = "FAST"
            print("⚠️  Invalid choice, using FAST mode")
        
        print(f"🚀 Selected: {speed_name} mode ({max_concurrent} concurrent)")
        
        # Confirm processing
        estimated_time = len(urls) / (max_concurrent * 2)  # Rough estimate
        response = input(f"\n⚡ This will process {len(urls):,} URLs in ~{estimated_time:.0f} minutes. Continue? (y/n): ").strip().lower()
        
        if response != 'y':
            print("❌ Processing cancelled by user")
            return
        
        # Start async processing
        processor = AsyncURLProcessor(pattern=args.pattern, min_count=args.count, max_concurrent=max_concurrent)
        valid_urls = await processor.process_all_urls_async(urls)
        
        print(f"\n🎊 HIGH-SPEED PROCESSING COMPLETED!")
        print(f"📈 Found {len(valid_urls):,} valid URLs with {args.count}+ matching elements")
        
    except FileNotFoundError:
        print("❌ url.txt file not found")
    except KeyboardInterrupt:
        print("\n⚠️  Processing interrupted by user")
        if 'processor' in locals():
            processor.save_progress()
            print("💾 Progress saved before exit")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
