"""Update checker for Termi CLI.

Checks for new versions on GitHub/PyPI.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Current version
CURRENT_VERSION = "1.0.0"
GITHUB_REPO = "termi-cli/termi-cli"
PYPI_PACKAGE = "termi-cli"


def _parse_version(version: str) -> tuple:
    """Parse version string to tuple for comparison."""
    parts = version.lstrip("v").split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def check_github_release() -> Optional[dict]:
    """Check for new release on GitHub.
    
    Returns:
        Dict with version info or None if error
    """
    try:
        import httpx
        
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            if response.status_code == 200:
                data = response.json()
                return {
                    "version": data.get("tag_name", "").lstrip("v"),
                    "url": data.get("html_url", ""),
                    "name": data.get("name", ""),
                    "published": data.get("published_at", ""),
                }
    except Exception as e:
        logger.debug("Failed to check GitHub: %s", e)
    
    return None


def check_pypi_version() -> Optional[str]:
    """Check for new version on PyPI.
    
    Returns:
        Latest version string or None if error
    """
    try:
        import httpx
        
        url = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            if response.status_code == 200:
                data = response.json()
                return data.get("info", {}).get("version")
    except Exception as e:
        logger.debug("Failed to check PyPI: %s", e)
    
    return None


def check_for_updates() -> dict:
    """Check for updates from all sources.
    
    Returns:
        Dict with update information
    """
    result = {
        "current_version": CURRENT_VERSION,
        "has_update": False,
        "latest_version": None,
        "source": None,
        "url": None,
    }
    
    # Try GitHub first
    github = check_github_release()
    if github:
        latest = github["version"]
        if _parse_version(latest) > _parse_version(CURRENT_VERSION):
            result["has_update"] = True
            result["latest_version"] = latest
            result["source"] = "GitHub"
            result["url"] = github["url"]
            return result
    
    # Try PyPI
    pypi_version = check_pypi_version()
    if pypi_version:
        if _parse_version(pypi_version) > _parse_version(CURRENT_VERSION):
            result["has_update"] = True
            result["latest_version"] = pypi_version
            result["source"] = "PyPI"
            result["url"] = f"https://pypi.org/project/{PYPI_PACKAGE}/"
            return result
    
    return result


def get_update_message(language: str = "en") -> str:
    """Get user-friendly update message.
    
    Args:
        language: Language code (en/vi)
        
    Returns:
        Formatted update message
    """
    info = check_for_updates()
    
    if info["has_update"]:
        if language == "vi":
            return (
                f"[bold yellow]🆕 Có phiên bản mới: {info['latest_version']}[/bold yellow]\n"
                f"   Phiên bản hiện tại: {info['current_version']}\n"
                f"   Nguồn: {info['source']}\n"
                f"   Link: {info['url']}\n"
                f"   Cập nhật: pip install --upgrade {PYPI_PACKAGE}"
            )
        else:
            return (
                f"[bold yellow]🆕 New version available: {info['latest_version']}[/bold yellow]\n"
                f"   Current version: {info['current_version']}\n"
                f"   Source: {info['source']}\n"
                f"   Link: {info['url']}\n"
                f"   Update: pip install --upgrade {PYPI_PACKAGE}"
            )
    else:
        if language == "vi":
            return f"[green]✓ Bạn đang dùng phiên bản mới nhất ({info['current_version']})[/green]"
        else:
            return f"[green]✓ You're using the latest version ({info['current_version']})[/green]"
