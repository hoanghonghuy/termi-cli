"""Memory Manager for Termi CLI.

Manages user memories (facts, notes) stored in a local JSON file.
Future upgrade: Use Vector Database for semantic search.
"""
import json
import time
from pathlib import Path
from termi_cli.config import APP_DIR

MEMORY_FILE = APP_DIR / "memories.json"

def _load_memories() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_memories(memories: list[dict]):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)

def add_memory(content: str) -> int:
    """Add a new memory string. Returns the new ID."""
    memories = _load_memories()
    
    # Simple auto-increment ID
    max_id = 0
    if memories:
        max_id = max(m.get("id", 0) for m in memories)
    new_id = max_id + 1
    
    memory = {
        "id": new_id,
        "content": content,
        "timestamp": time.time(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    memories.append(memory)
    _save_memories(memories)
    return new_id

def delete_memory(memory_id: int) -> bool:
    """Delete memory by ID. Returns True if found."""
    memories = _load_memories()
    initial_len = len(memories)
    memories = [m for m in memories if m["id"] != memory_id]
    
    if len(memories) < initial_len:
        _save_memories(memories)
        return True
    return False

def list_memories(limit: int = 10) -> list[dict]:
    """Get latest memories."""
    memories = _load_memories()
    # Sort by timestamp desc
    memories.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return memories[:limit]

def search_memories(query: str) -> list[dict]:
    """Search memories by text matching (case-insensitive)."""
    if not query:
        return []
    memories = _load_memories()
    q = query.lower()
    results = [m for m in memories if q in m["content"].lower()]
    return results

def clear_all_memories():
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
