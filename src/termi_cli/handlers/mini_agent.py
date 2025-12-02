"""Mini-agent pattern-based cho single-turn HTTP providers.

Đọc cấu hình từ config["mini_agent"] và quyết định có nên gọi một tool nội bộ
thay vì gửi prompt sang LLM HTTP (DeepSeek/Groq/OpenRouter/Ollama).
"""

from __future__ import annotations

from typing import Optional
import logging

from termi_cli import api


logger = logging.getLogger(__name__)


def validate_mini_agent_rules(config: dict) -> list[str]:
    """Trả về danh sách cảnh báo (nếu có) cho cấu hình mini-agent."""

    issues: list[str] = []
    if not isinstance(config, dict):
        issues.append("mini_agent config phải là dict")
        return issues

    mini_cfg = config.get("mini_agent") or {}
    if not isinstance(mini_cfg, dict):
        issues.append("mini_agent phải là object chứa enabled/rules")
        return issues

    rules = mini_cfg.get("rules")
    if rules is None:
        return issues

    if not isinstance(rules, list):
        issues.append("mini_agent.rules phải là list")
        return issues

    for idx, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            issues.append(f"Rule #{idx} không phải dict")
            continue

        tool_name = rule.get("tool_name")
        patterns = rule.get("patterns")

        if not tool_name or not isinstance(tool_name, str):
            issues.append(f"Rule #{idx} thiếu tool_name hợp lệ")
        elif tool_name not in api.AVAILABLE_TOOLS:
            issues.append(f"Rule #{idx} trỏ tới tool '{tool_name}' không tồn tại")

        if not isinstance(patterns, list) or not all(isinstance(p, str) and p.strip() for p in patterns):
            issues.append(f"Rule #{idx} có patterns không hợp lệ")

    return issues


def run_http_mini_agent(prompt_text: str, user_intent: str, config: dict) -> Optional[str]:
    """Thử áp dụng mini-agent cho một prompt single-turn HTTP.

    - Nếu khớp một rule trong config["mini_agent"]["rules"]:
      * Gọi tool tương ứng và trả về kết quả (string).
    - Nếu không khớp rule nào hoặc cấu hình bị tắt: trả về None để caller fallback.
    """
    if not isinstance(config, dict):
        return None

    mini_agent_cfg = config.get("mini_agent") or {}
    if not isinstance(mini_agent_cfg, dict):
        return None

    if not mini_agent_cfg.get("enabled", True):
        return None

    normalized_prompt = (prompt_text or "").lower()

    for rule in mini_agent_cfg.get("rules", []):
        # Mỗi rule: {"tool_name": str, "patterns": [str], "pass_prompt": bool}
        if not isinstance(rule, dict):
            continue

        tool_name = rule.get("tool_name")
        patterns = rule.get("patterns") or []
        pass_prompt = bool(rule.get("pass_prompt", False))

        if not tool_name or not isinstance(patterns, list):
            continue

        has_match = any(
            isinstance(p, str) and p.lower() in normalized_prompt
            for p in patterns
        )
        if not has_match:
            continue

        tool_func = api.AVAILABLE_TOOLS.get(tool_name)
        if not callable(tool_func):
            continue

        logger.info("Mini-agent khớp rule #%s (tool=%s, pass_prompt=%s)", rule.get("name", "?"), tool_name, pass_prompt)

        if pass_prompt:
            query = user_intent or prompt_text or ""
            return str(tool_func(query))

        return str(tool_func())

    return None
