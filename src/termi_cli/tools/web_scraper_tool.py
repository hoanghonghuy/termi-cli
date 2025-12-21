"""Web scraper tool for Termi CLI.

This module provides functionality to:
- Fetch and parse web page content
- Extract specific elements using CSS selectors
- Convert HTML to readable text
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Check for available dependencies
_HTTPX_AVAILABLE = False
_BS4_AVAILABLE = False

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None
    logger.debug("httpx not available, web scraping disabled")

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    BeautifulSoup = None
    logger.debug("beautifulsoup4 not available, HTML parsing limited")


def _clean_text(text: str) -> str:
    """Clean extracted text by removing extra whitespace."""
    # Remove multiple newlines
    text = re.sub(r'\n\s*\n', '\n\n', text)
    # Remove multiple spaces
    text = re.sub(r' +', ' ', text)
    return text.strip()


def _html_to_text(html: str) -> str:
    """Convert HTML to readable text."""
    if _BS4_AVAILABLE:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script and style elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        
        # Get text
        text = soup.get_text(separator='\n')
        return _clean_text(text)
    else:
        # Fallback: simple regex-based HTML stripping
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&[a-z]+;', '', text)
        return _clean_text(text)


def scrape_url(
    url: str,
    selector: Optional[str] = None,
    max_length: int = 10000,
) -> str:
    """Fetch and extract content from a URL.
    
    Args:
        url: The URL to scrape
        selector: Optional CSS selector to extract specific elements
        max_length: Maximum length of returned text
        
    Returns:
        Extracted text content from the URL.
    """
    if not _HTTPX_AVAILABLE:
        return "Error: httpx not installed. Run: pip install httpx"
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; TermiCLI/1.0; +https://github.com/termi-cli)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
        
        if selector and _BS4_AVAILABLE:
            soup = BeautifulSoup(html, 'html.parser')
            elements = soup.select(selector)
            if elements:
                text = '\n\n'.join(el.get_text(separator='\n') for el in elements)
            else:
                text = f"No elements found matching selector: {selector}"
        else:
            text = _html_to_text(html)
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length] + f"\n\n... (truncated, showing first {max_length} chars)"
        
        return text
        
    except httpx.HTTPStatusError as e:
        return f"HTTP Error {e.response.status_code}: {e.response.reason_phrase}"
    except httpx.RequestError as e:
        return f"Request Error: {e}"
    except Exception as e:
        return f"Error scraping URL: {e}"


def get_page_links(url: str, filter_pattern: Optional[str] = None) -> str:
    """Extract all links from a web page.
    
    Args:
        url: The URL to scrape for links
        filter_pattern: Optional regex pattern to filter links
        
    Returns:
        List of links found on the page.
    """
    if not _HTTPX_AVAILABLE or not _BS4_AVAILABLE:
        return "Error: httpx and beautifulsoup4 required. Run: pip install httpx beautifulsoup4"
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; TermiCLI/1.0)",
        }
        
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
        
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)[:50]  # Limit text length
            
            if filter_pattern:
                if not re.search(filter_pattern, href):
                    continue
            
            links.append(f"- [{text or 'No text'}]({href})")
        
        if links:
            return f"Found {len(links)} links:\n" + "\n".join(links[:50])  # Limit to 50 links
        else:
            return "No links found on the page."
            
    except Exception as e:
        return f"Error extracting links: {e}"


def is_web_scraper_available() -> bool:
    """Check if web scraping is available."""
    return _HTTPX_AVAILABLE
