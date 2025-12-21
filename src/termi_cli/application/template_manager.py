"""Template system for Termi CLI.

Allows users to save and reuse prompt templates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from termi_cli.config import APP_DIR

logger = logging.getLogger(__name__)

TEMPLATE_FILE = APP_DIR / "templates.json"


def load_templates() -> dict[str, dict]:
    """Load templates from file."""
    if TEMPLATE_FILE.exists():
        try:
            with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load templates: %s", e)
    return {}


def save_templates(templates: dict[str, dict]) -> bool:
    """Save templates to file."""
    try:
        with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save templates: %s", e)
        return False


def add_template(name: str, content: str, description: str = "") -> bool:
    """Add or update a template.
    
    Args:
        name: Template name
        content: Template content (can include {placeholders})
        description: Optional description
        
    Returns:
        True if successful
    """
    templates = load_templates()
    templates[name] = {
        "content": content,
        "description": description,
    }
    return save_templates(templates)


def remove_template(name: str) -> bool:
    """Remove a template.
    
    Args:
        name: Template name to remove
        
    Returns:
        True if removed
    """
    templates = load_templates()
    if name in templates:
        del templates[name]
        return save_templates(templates)
    return False


def get_template(name: str) -> Optional[dict]:
    """Get a template by name.
    
    Args:
        name: Template name
        
    Returns:
        Template dict or None
    """
    templates = load_templates()
    return templates.get(name)


def list_templates() -> dict[str, dict]:
    """List all templates."""
    return load_templates()


def apply_template(name: str, **kwargs) -> Optional[str]:
    """Apply a template with variable substitution.
    
    Args:
        name: Template name
        **kwargs: Variables to substitute
        
    Returns:
        Rendered template or None
    """
    template = get_template(name)
    if not template:
        return None
    
    content = template["content"]
    
    # Simple placeholder substitution
    for key, value in kwargs.items():
        content = content.replace(f"{{{key}}}", str(value))
    
    return content


# Built-in templates
DEFAULT_TEMPLATES = {
    "explain": {
        "content": "Giải thích chi tiết: {topic}",
        "description": "Giải thích một chủ đề"
    },
    "review": {
        "content": "Review code sau và đề xuất cải tiến:\n```\n{code}\n```",
        "description": "Review code"
    },
    "translate": {
        "content": "Dịch văn bản sau sang {lang}:\n{text}",
        "description": "Dịch văn bản"
    },
    "summarize": {
        "content": "Tóm tắt nội dung sau:\n{content}",
        "description": "Tóm tắt nội dung"
    },
}


def init_default_templates():
    """Initialize default templates if none exist."""
    templates = load_templates()
    if not templates:
        save_templates(DEFAULT_TEMPLATES)
