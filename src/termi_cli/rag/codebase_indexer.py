"""Codebase indexer for RAG functionality.

This module provides functionality to:
- Walk a directory tree respecting .gitignore
- Chunk code files into semantic units
- Embed chunks using available embedding methods
- Store in ChromaDB for retrieval
"""

from __future__ import annotations

import os
import hashlib
import logging
from pathlib import Path
from typing import Generator

from termi_cli.config import APP_DIR

logger = logging.getLogger(__name__)

# Index storage path
INDEX_PATH = str(APP_DIR / "codebase_index")

# Supported file extensions for indexing
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".lua",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".html", ".css", ".scss", ".less", ".vue", ".svelte",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".md", ".rst", ".txt",
    ".sql", ".graphql", ".prisma",
    ".dockerfile", ".dockerignore", ".gitignore", ".env.example",
}

# Files to always skip
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.lock", "poetry.lock", "Pipfile.lock",
}

# Directories to always skip
SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".venv", "venv", "env",
    ".next", ".nuxt", "dist", "build", "out", "target",
    ".idea", ".vscode", ".vs",
    "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

# Default chunk size (characters)
DEFAULT_CHUNK_SIZE = 1500
DEFAULT_CHUNK_OVERLAP = 200


try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except Exception:
    chromadb = None  # type: ignore
    Settings = None  # type: ignore
    CHROMA_AVAILABLE = False


def _load_gitignore_patterns(root_path: Path) -> list[str]:
    """Load patterns from .gitignore file if it exists."""
    gitignore_path = root_path / ".gitignore"
    patterns = []
    if gitignore_path.exists():
        try:
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception:
            pass
    return patterns


def _should_skip_path(path: Path, root_path: Path, gitignore_patterns: list[str]) -> bool:
    """Check if a path should be skipped based on rules."""
    name = path.name
    
    # Skip hidden files/dirs (except specific ones)
    if name.startswith(".") and name not in {".env.example", ".dockerignore", ".gitignore"}:
        return True
    
    # Skip known directories
    if path.is_dir() and name in SKIP_DIRS:
        return True
    
    # Skip known files
    if path.is_file() and name in SKIP_FILES:
        return True
    
    # Check gitignore patterns (simple matching)
    rel_path = str(path.relative_to(root_path))
    for pattern in gitignore_patterns:
        # Simple pattern matching
        if pattern.endswith("/"):
            # Directory pattern
            if path.is_dir() and (name == pattern[:-1] or rel_path.startswith(pattern)):
                return True
        elif "*" in pattern:
            # Wildcard pattern (simplified)
            if pattern.startswith("*"):
                if name.endswith(pattern[1:]):
                    return True
            elif pattern.endswith("*"):
                if name.startswith(pattern[:-1]):
                    return True
        else:
            # Exact match
            if name == pattern or rel_path == pattern:
                return True
    
    return False


def _iter_code_files(root_path: Path) -> Generator[Path, None, None]:
    """Iterate over code files in a directory, respecting .gitignore."""
    gitignore_patterns = _load_gitignore_patterns(root_path)
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        current_dir = Path(dirpath)
        
        # Filter out directories to skip
        dirnames[:] = [
            d for d in dirnames
            if not _should_skip_path(current_dir / d, root_path, gitignore_patterns)
        ]
        
        for filename in filenames:
            file_path = current_dir / filename
            
            if _should_skip_path(file_path, root_path, gitignore_patterns):
                continue
            
            # Check extension
            if file_path.suffix.lower() in CODE_EXTENSIONS:
                yield file_path


def _chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # Try to break at a natural boundary (newline)
        if end < len(text):
            last_newline = chunk.rfind("\n")
            if last_newline > chunk_size // 2:
                chunk = chunk[:last_newline + 1]
                end = start + last_newline + 1
        
        if chunk.strip():
            chunks.append(chunk)
        
        start = end - overlap
        if start >= len(text):
            break
    
    return chunks


def _generate_chunk_id(file_path: str, chunk_index: int) -> str:
    """Generate a unique ID for a chunk."""
    content = f"{file_path}:{chunk_index}"
    return hashlib.md5(content.encode()).hexdigest()


class CodebaseIndexer:
    """Indexes a codebase for RAG retrieval."""
    
    def __init__(self, index_name: str = "default"):
        """Initialize the indexer.
        
        Args:
            index_name: Name of the index (for multiple projects)
        """
        self.index_name = index_name
        self.collection = None
        self.client = None
        
        if not CHROMA_AVAILABLE:
            logger.warning("ChromaDB not available. Codebase indexing disabled.")
            return
        
        try:
            os.makedirs(INDEX_PATH, exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=INDEX_PATH,
                settings=Settings(anonymized_telemetry=False),
            )
            self.collection = self.client.get_or_create_collection(
                name=f"codebase_{index_name}",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.error("Failed to initialize codebase index: %s", e)
    
    def index_directory(
        self,
        directory: str | Path,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        force_reindex: bool = False,
    ) -> dict:
        """Index a directory of code files.
        
        Args:
            directory: Path to the directory to index
            chunk_size: Size of each chunk in characters
            chunk_overlap: Overlap between chunks
            force_reindex: If True, reindex even if already indexed
            
        Returns:
            Statistics about the indexing operation
        """
        if self.collection is None:
            return {"error": "Indexer not available", "files": 0, "chunks": 0}
        
        directory = Path(directory).resolve()
        if not directory.exists():
            return {"error": f"Directory not found: {directory}", "files": 0, "chunks": 0}
        
        stats = {
            "directory": str(directory),
            "files": 0,
            "chunks": 0,
            "skipped": 0,
            "errors": [],
        }
        
        # Get existing document IDs if not force reindexing
        existing_ids = set()
        if not force_reindex:
            try:
                result = self.collection.get()
                existing_ids = set(result.get("ids", []))
            except Exception:
                pass
        
        documents = []
        metadatas = []
        ids = []
        
        for file_path in _iter_code_files(directory):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                if not content.strip():
                    continue
                
                rel_path = str(file_path.relative_to(directory))
                chunks = _chunk_text(content, chunk_size, chunk_overlap)
                
                for i, chunk in enumerate(chunks):
                    chunk_id = _generate_chunk_id(rel_path, i)
                    
                    if chunk_id in existing_ids and not force_reindex:
                        stats["skipped"] += 1
                        continue
                    
                    # Create document with file context
                    doc = f"File: {rel_path}\n\n{chunk}"
                    
                    documents.append(doc)
                    metadatas.append({
                        "file_path": rel_path,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "language": file_path.suffix.lstrip("."),
                    })
                    ids.append(chunk_id)
                    stats["chunks"] += 1
                
                stats["files"] += 1
                
            except Exception as e:
                stats["errors"].append(f"{file_path}: {e}")
        
        # Batch upsert to ChromaDB
        if documents:
            try:
                # ChromaDB has a batch limit, process in batches
                batch_size = 100
                for i in range(0, len(documents), batch_size):
                    batch_docs = documents[i:i + batch_size]
                    batch_metas = metadatas[i:i + batch_size]
                    batch_ids = ids[i:i + batch_size]
                    
                    self.collection.upsert(
                        documents=batch_docs,
                        metadatas=batch_metas,
                        ids=batch_ids,
                    )
            except Exception as e:
                stats["errors"].append(f"Failed to save to index: {e}")
        
        return stats
    
    def get_stats(self) -> dict:
        """Get statistics about the current index."""
        if self.collection is None:
            return {"available": False, "count": 0}
        
        try:
            count = self.collection.count()
            return {"available": True, "count": count, "name": self.index_name}
        except Exception as e:
            return {"available": False, "error": str(e)}
    
    def clear(self) -> bool:
        """Clear the index."""
        if self.collection is None:
            return False
        
        try:
            self.client.delete_collection(f"codebase_{self.index_name}")
            self.collection = self.client.get_or_create_collection(
                name=f"codebase_{self.index_name}",
                metadata={"hnsw:space": "cosine"}
            )
            return True
        except Exception as e:
            logger.error("Failed to clear index: %s", e)
            return False


def index_codebase(directory: str, index_name: str = "default", force: bool = False) -> dict:
    """Convenience function to index a codebase.
    
    Args:
        directory: Path to the directory to index
        index_name: Name of the index
        force: If True, force reindex
        
    Returns:
        Indexing statistics
    """
    indexer = CodebaseIndexer(index_name)
    return indexer.index_directory(directory, force_reindex=force)


def get_index_stats(index_name: str = "default") -> dict:
    """Get statistics about an index."""
    indexer = CodebaseIndexer(index_name)
    return indexer.get_stats()


def clear_index(index_name: str = "default") -> bool:
    """Clear an index."""
    indexer = CodebaseIndexer(index_name)
    return indexer.clear()
