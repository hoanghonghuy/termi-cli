"""API tester tool for Termi CLI.

Perform HTTP requests and test APIs.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_HTTPX_AVAILABLE = False
try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None
    logger.debug("httpx not available, API testing disabled")


def http_request(
    method: str,
    url: str,
    headers: Optional[dict] = None,
    body: Optional[str] = None,
    timeout: int = 30,
) -> str:
    """Make an HTTP request.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        url: Target URL
        headers: Optional request headers as dict
        body: Optional request body (JSON string)
        timeout: Request timeout in seconds
        
    Returns:
        Response status, headers summary, and body
    """
    if not _HTTPX_AVAILABLE:
        return "Error: httpx not installed. Run: pip install httpx"
    
    method = method.upper()
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
        return f"Error: Invalid HTTP method: {method}"
    
    try:
        req_headers = headers or {}
        req_body = None
        
        if body:
            try:
                req_body = json.loads(body)
                if "Content-Type" not in req_headers:
                    req_headers["Content-Type"] = "application/json"
            except json.JSONDecodeError:
                req_body = body  # Use as raw string
        
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.request(
                method=method,
                url=url,
                headers=req_headers,
                json=req_body if isinstance(req_body, dict) else None,
                content=req_body if isinstance(req_body, str) else None,
            )
        
        # Build response summary
        result = [
            f"Status: {response.status_code} {response.reason_phrase}",
            f"Time: {response.elapsed.total_seconds():.2f}s",
            "",
            "Response Headers:",
        ]
        
        for key, value in list(response.headers.items())[:10]:
            result.append(f"  {key}: {value[:100]}")
        
        result.append("")
        result.append("Response Body:")
        
        try:
            body_json = response.json()
            body_str = json.dumps(body_json, indent=2, ensure_ascii=False)
        except Exception:
            body_str = response.text
        
        # Truncate if too long
        if len(body_str) > 5000:
            body_str = body_str[:5000] + "\n... (truncated)"
        
        result.append(body_str)
        
        return "\n".join(result)
        
    except httpx.HTTPStatusError as e:
        return f"HTTP Error: {e.response.status_code} {e.response.reason_phrase}"
    except httpx.RequestError as e:
        return f"Request Error: {e}"
    except Exception as e:
        return f"Error: {e}"


def http_get(url: str, headers: Optional[dict] = None) -> str:
    """Shortcut for HTTP GET request."""
    return http_request("GET", url, headers=headers)


def http_post(url: str, body: str, headers: Optional[dict] = None) -> str:
    """Shortcut for HTTP POST request."""
    return http_request("POST", url, headers=headers, body=body)


def is_api_tester_available() -> bool:
    """Check if API tester is available."""
    return _HTTPX_AVAILABLE
