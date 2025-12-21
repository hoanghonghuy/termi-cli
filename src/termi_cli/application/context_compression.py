"""Context compression utilities for Termi CLI.

Compresses long conversations to save tokens while preserving important context.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def summarize_messages(
    messages: list[dict],
    max_messages: int = 20,
    keep_recent: int = 5,
) -> list[dict]:
    """Compress old messages into a summary while keeping recent ones.
    
    Args:
        messages: List of message dicts with role and content
        max_messages: Threshold to trigger compression
        keep_recent: Number of recent messages to keep verbatim
        
    Returns:
        Compressed list of messages
    """
    if len(messages) <= max_messages:
        return messages
    
    # Keep system message if present
    has_system = messages and messages[0].get("role") == "system"
    system_msg = [messages[0]] if has_system else []
    
    # Split into old and recent
    content_msgs = messages[1:] if has_system else messages
    old_msgs = content_msgs[:-keep_recent]
    recent_msgs = content_msgs[-keep_recent:]
    
    # Summarize old messages
    summary = _create_summary(old_msgs)
    summary_msg = {
        "role": "system",
        "content": f"[Previous conversation summary: {summary}]"
    }
    
    return system_msg + [summary_msg] + recent_msgs


def _create_summary(messages: list[dict]) -> str:
    """Create a brief summary of messages."""
    if not messages:
        return "No previous context."
    
    topics = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 10:
            # Extract first meaningful part
            first_line = content.split("\n")[0][:100]
            if msg.get("role") == "user":
                topics.append(f"User asked: {first_line}")
            else:
                topics.append(f"AI discussed: {first_line}")
    
    # Limit to key topics
    key_topics = topics[-5:]  # Last 5 topics
    return "; ".join(key_topics)


def estimate_tokens(text: str) -> int:
    """Rough estimate of token count (4 chars ≈ 1 token)."""
    return len(text) // 4


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total tokens in messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    total += estimate_tokens(item.get("text", ""))
                elif item.get("type") == "image_url":
                    total += 500  # Rough estimate for images
    return total


def should_compress(messages: list[dict], token_limit: int = 8000) -> bool:
    """Check if messages should be compressed."""
    return estimate_messages_tokens(messages) > token_limit
