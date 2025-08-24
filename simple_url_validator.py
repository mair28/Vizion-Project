#!/usr/bin/env python3
"""
Simple URL Validator for Product-Details Pattern
Validates URLs by checking for <div class="text-center product__preview-buttons"> pattern
"""
import requests
import re
import time
import random
from datetime import datetime
from urllib.parse import urlparse

class SimpleURLValidator:
    def __init__(self, pattern=None, min_count=12):
        self.min_count = min_count
        self.pattern = pattern or r'<div class="text-center product__preview-buttons">'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        }
    
    def validate_url(self, url):
        """Validate a single URL"""
        try:
            print(f"🔍 Checking: {url}")
            
            # Add delay to be polite
            time.sleep(random.uniform(1.0, 2.0))
            
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                matches = re.findall(self.pattern, html_content, re.IGNORECASE)
                count = len(matches)
                
                print(f"   Status: {response.status_code}")
                print(f"   Pattern count: {count}")
                
                if count >= self.min_count:
                    print(f"   ✅ VALID: Found {count} instances (need {self.min_count}+)")
                    return True, count
                else:
                    print(f"   ❌ INVALID: Found {count} instances (need {self.min_count}+)")
                    return False, count
            else:
                print(f"   ❌ HTTP Error: {response.status_code}")
                return False, 0
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False, 0
    
    def validate_url_list(self, urls):
        """Validate a list of URLs"""
        print(f"🚀 Starting validation of {len(urls)} URLs")
        print(f"Pattern: {self.pattern}")
        print(f"Minimum count: {self.min_count}")
        print("=" * 60)
        
        valid_urls = []
        total_processed = 0
        
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Processing URL:")
            is_valid, count = self.validate_url(url.strip())
            
            if is_valid:
                valid_urls.append({
                    'url': url.strip(),
                    'count': count
                })
            
            total_processed += 1
            
            # Show progress every 10 URLs
            if i % 10 == 0:
                print(f"\n📊 Progress: {i}/{len(urls)} processed, {len(valid_urls)} valid found")
        
        print("\n" + "=" * 60)
        print(f"🎉 Validation Complete!")
        print(f"Total URLs processed: {total_processed}")
        print(f"Valid URLs found: {len(valid_urls)}")
        print(f"Success rate: {(len(valid_urls)/total_processed*100):.1f}%")
        
        # Save results
        if valid_urls:
            with open('valid_urls.txt', 'w', encoding='utf-8') as f:
                f.write(f"# Simple URL Validator Results\n")
                f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Pattern: {self.pattern}\n")
                f.write(f"# Minimum Count: {self.min_count}\n")
                f.write(f"# Total Processed: {total_processed}\n")
                f.write(f"# Valid URLs Found: {len(valid_urls)}\n")
                f.write(f"# Success Rate: {(len(valid_urls)/total_processed*100):.1f}%\n")
                f.write(f"#\n")
                for item in sorted(valid_urls, key=lambda x: x['count'], reverse=True):
                    f.write(f"{item['url']} (count: {item['count']})\n")
            print(f"✅ Results saved to: valid_urls.txt")
        else:
            # Create empty file even if no results
            with open('valid_urls.txt', 'w', encoding='utf-8') as f:
                f.write(f"# Simple URL Validator Results\n")
                f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Pattern: {self.pattern}\n")
                f.write(f"# Minimum Count: {self.min_count}\n")
                f.write(f"# Total Processed: {total_processed}\n")
                f.write(f"# Valid URLs Found: 0\n")
                f.write(f"# Success Rate: 0.0%\n")
                f.write(f"#\n")
                f.write(f"# No valid URLs found matching the criteria\n")
            print(f"✅ Empty results file saved to: valid_urls.txt")
        
        return valid_urls

def main():
    """Main function"""
    import argparse
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(
        description="Simple URL Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simple_url_validator.py                                    # Process all URLs with default pattern
  python simple_url_validator.py --pattern "div.card" --count 10    # Custom pattern and count
  python simple_url_validator.py --count 50                         # Different minimum count
  python simple_url_validator.py --url "https://example.com"        # Test single URL
        """
    )
    
    parser.add_argument('--pattern', '-p', 
                       default='<div class="text-center product__preview-buttons">',
                       help='Target pattern to search for (default: <div class="text-center product__preview-buttons">)')
    parser.add_argument('--count', '-c', type=int, default=25,
                       help='Minimum count required (default: 25)')
    parser.add_argument('--file', '-f', default='url.txt',
                       help='Input file containing URLs (default: url.txt)')
    parser.add_argument('--url', '-u', 
                       help='Test a single URL instead of processing file')

    
    args = parser.parse_args()
    
    print("🔍 Simple URL Validator")
    print("=" * 50)
    print(f"🎯 Target Pattern: {args.pattern}")
    print(f"📊 Minimum Count: {args.count}")
    if args.url:
        print(f"🔗 Test URL: {args.url}")
    else:
        print(f"📁 Input File: {args.file}")
    print("=" * 50)
    
    # Create validator with custom settings
    validator = SimpleURLValidator(pattern=args.pattern, min_count=args.count)
    
    # Test single URL if provided
    if args.url:
        print(f"\n🧪 Testing single URL: {args.url}")
        validator.validate_url(args.url)
        return
    
    # Ask if user wants to process file
    process_file = input(f"\nProcess {args.file} file? (y/n): ").strip().lower()
    
    if process_file == 'y':
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract URLs using regex (handles malformed XML)
            url_pattern = r'<loc\s*>(.*?)</loc\s*>'
            urls = re.findall(url_pattern, content, re.IGNORECASE)
            
            if urls:
                print(f"\n📁 Found {len(urls)} URLs in {args.file}")
                print(f"🔢 Processing all {len(urls)} URLs")
                validator.validate_url_list(urls)
            else:
                print(f"❌ No URLs found in {args.file}")
                
        except FileNotFoundError:
            print(f"❌ {args.file} file not found")
        except Exception as e:
            print(f"❌ Error reading {args.file}: {e}")

if __name__ == "__main__":
    main()
