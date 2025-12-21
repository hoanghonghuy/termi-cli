"""Advanced Git tools for Termi CLI.

This module provides AI-powered Git automation:
- resolve_merge_conflict: AI-assisted conflict resolution
- generate_changelog: Smart changelog from commits
- review_pr: Analyze PR diff and provide review
"""

from __future__ import annotations

import subprocess
import os
import re
import logging
from typing import Optional

from termi_cli.config import load_config

logger = logging.getLogger(__name__)


def _run_git_command(args: list[str], cwd: str = ".") -> tuple[int, str, str]:
    """Run a git command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Git command timed out"
    except Exception as e:
        return -1, "", str(e)


def get_merge_conflicts() -> str:
    """Get list of files with merge conflicts.
    
    Returns:
        String listing conflicted files, or message if no conflicts.
    """
    exit_code, stdout, stderr = _run_git_command(["diff", "--name-only", "--diff-filter=U"])
    
    if exit_code != 0:
        return f"Error checking conflicts: {stderr}"
    
    if not stdout.strip():
        return "No merge conflicts found in the repository."
    
    conflicted_files = stdout.strip().split("\n")
    result = f"Found {len(conflicted_files)} file(s) with merge conflicts:\n"
    for f in conflicted_files:
        result += f"  - {f}\n"
    
    return result


def get_conflict_content(file_path: str) -> str:
    """Get the content of a conflicted file showing conflict markers.
    
    Args:
        file_path: Path to the conflicted file
        
    Returns:
        File content with conflict markers, or error message.
    """
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' does not exist."
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        # Check if file has conflict markers
        if "<<<<<<<" not in content:
            return f"File '{file_path}' does not contain merge conflict markers."
        
        return f"Content of '{file_path}' with conflict markers:\n\n```\n{content}\n```"
    except Exception as e:
        return f"Error reading file: {e}"


def resolve_conflict_in_file(file_path: str, resolved_content: str) -> str:
    """Write resolved content to a conflicted file.
    
    Args:
        file_path: Path to the file to resolve
        resolved_content: The resolved content to write
        
    Returns:
        Success or error message.
    """
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' does not exist."
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(resolved_content)
        
        # Stage the resolved file
        exit_code, _, stderr = _run_git_command(["add", file_path])
        if exit_code != 0:
            return f"File written but could not stage: {stderr}"
        
        return f"Successfully resolved and staged '{file_path}'."
    except Exception as e:
        return f"Error writing file: {e}"


def generate_changelog(
    from_ref: str = "HEAD~10",
    to_ref: str = "HEAD",
    format_style: str = "conventional",
) -> str:
    """Generate a changelog from git commits.
    
    Args:
        from_ref: Starting reference (default: HEAD~10)
        to_ref: Ending reference (default: HEAD)
        format_style: 'conventional' or 'simple'
        
    Returns:
        Formatted changelog string.
    """
    # Get commit log with useful info
    log_format = "--pretty=format:%h|%s|%an|%ad"
    exit_code, stdout, stderr = _run_git_command([
        "log",
        log_format,
        "--date=short",
        f"{from_ref}..{to_ref}",
    ])
    
    if exit_code != 0:
        # Try with just recent commits if range fails
        exit_code, stdout, stderr = _run_git_command([
            "log",
            log_format,
            "--date=short",
            "-n", "20",
        ])
        if exit_code != 0:
            return f"Error getting git log: {stderr}"
    
    if not stdout.strip():
        return "No commits found in the specified range."
    
    commits = []
    for line in stdout.strip().split("\n"):
        parts = line.split("|")
        if len(parts) >= 4:
            commits.append({
                "hash": parts[0],
                "subject": parts[1],
                "author": parts[2],
                "date": parts[3],
            })
    
    if format_style == "conventional":
        # Group by conventional commit type
        groups = {
            "feat": [],
            "fix": [],
            "docs": [],
            "style": [],
            "refactor": [],
            "perf": [],
            "test": [],
            "chore": [],
            "other": [],
        }
        
        for commit in commits:
            subject = commit["subject"]
            matched = False
            for group_key in groups:
                if subject.lower().startswith(f"{group_key}:") or subject.lower().startswith(f"{group_key}("):
                    groups[group_key].append(commit)
                    matched = True
                    break
            if not matched:
                groups["other"].append(commit)
        
        # Build changelog
        changelog = "# Changelog\n\n"
        type_labels = {
            "feat": "✨ Features",
            "fix": "🐛 Bug Fixes",
            "docs": "📚 Documentation",
            "style": "💄 Styling",
            "refactor": "♻️ Refactoring",
            "perf": "⚡ Performance",
            "test": "✅ Tests",
            "chore": "🔧 Chores",
            "other": "📦 Other Changes",
        }
        
        for type_key, label in type_labels.items():
            if groups[type_key]:
                changelog += f"## {label}\n\n"
                for c in groups[type_key]:
                    changelog += f"- {c['subject']} ({c['hash']})\n"
                changelog += "\n"
        
        return changelog
    else:
        # Simple format
        changelog = "# Changelog\n\n"
        current_date = None
        for commit in commits:
            if commit["date"] != current_date:
                current_date = commit["date"]
                changelog += f"\n## {current_date}\n\n"
            changelog += f"- {commit['subject']} ({commit['hash']}) - {commit['author']}\n"
        
        return changelog


def get_pr_diff(base_branch: str = "main", head_branch: str = "HEAD") -> str:
    """Get the diff for a PR (or between two branches).
    
    Args:
        base_branch: The base branch (default: main)
        head_branch: The head/feature branch (default: HEAD)
        
    Returns:
        The diff output.
    """
    # First try to find merge base
    exit_code, merge_base, stderr = _run_git_command([
        "merge-base",
        base_branch,
        head_branch,
    ])
    
    if exit_code != 0:
        # Fallback to direct diff
        exit_code, diff, stderr = _run_git_command([
            "diff",
            base_branch,
            "--stat",
        ])
        if exit_code != 0:
            return f"Error getting diff: {stderr}"
        return f"Diff against {base_branch}:\n\n{diff}"
    
    merge_base = merge_base.strip()
    
    # Get stat diff
    exit_code, stat_diff, _ = _run_git_command([
        "diff",
        "--stat",
        merge_base,
        head_branch,
    ])
    
    # Get full diff (limited to reasonable size)
    exit_code, full_diff, _ = _run_git_command([
        "diff",
        merge_base,
        head_branch,
    ])
    
    # Truncate if too long
    max_diff_chars = 15000
    if len(full_diff) > max_diff_chars:
        full_diff = full_diff[:max_diff_chars] + "\n\n... (diff truncated, showing first 15000 chars)"
    
    result = f"## PR Diff Summary\n\n{stat_diff}\n\n## Full Diff\n\n```diff\n{full_diff}\n```"
    return result


def get_branch_info() -> str:
    """Get information about current and related branches.
    
    Returns:
        Branch information summary.
    """
    # Current branch
    exit_code, current, _ = _run_git_command(["branch", "--show-current"])
    current = current.strip() if exit_code == 0 else "unknown"
    
    # All local branches
    exit_code, branches, _ = _run_git_command(["branch", "-v", "--no-color"])
    
    # Remote tracking
    exit_code, remote, _ = _run_git_command([
        "for-each-ref",
        "--format=%(refname:short) -> %(upstream:short)",
        "refs/heads/",
    ])
    
    result = f"**Current branch:** {current}\n\n"
    result += "**Local branches:**\n```\n{branches}\n```\n\n"
    result += f"**Remote tracking:**\n{remote if remote.strip() else '(no remote tracking configured)'}"
    
    return result
