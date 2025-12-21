"""Screenshot tool for Termi CLI.

Captures screenshots and optionally analyzes them with AI.
"""

from __future__ import annotations

import logging
import base64
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PIL_AVAILABLE = False
try:
    from PIL import ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    ImageGrab = None
    logger.debug("PIL not available, screenshot disabled")


def take_screenshot(
    save_path: Optional[str] = None,
    region: Optional[tuple] = None,
) -> str:
    """Capture a screenshot of the screen.
    
    Args:
        save_path: Optional path to save the screenshot
        region: Optional tuple (left, top, right, bottom) for partial capture
        
    Returns:
        Path to saved screenshot or base64 encoded image data
    """
    if not _PIL_AVAILABLE:
        return "Error: PIL not installed. Run: pip install Pillow"
    
    try:
        if region:
            screenshot = ImageGrab.grab(bbox=region)
        else:
            screenshot = ImageGrab.grab()
        
        if save_path:
            path = Path(save_path)
            screenshot.save(path)
            return f"Screenshot saved to: {path.absolute()}"
        else:
            # Save to temp and return path
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                screenshot.save(f.name)
                return f"Screenshot saved to: {f.name}"
                
    except Exception as e:
        return f"Error taking screenshot: {e}"


def get_screen_size() -> str:
    """Get the screen resolution."""
    if not _PIL_AVAILABLE:
        return "Error: PIL not installed"
    
    try:
        screenshot = ImageGrab.grab()
        width, height = screenshot.size
        return f"Screen size: {width}x{height}"
    except Exception as e:
        return f"Error: {e}"


def is_screenshot_available() -> bool:
    """Check if screenshot is available."""
    return _PIL_AVAILABLE
