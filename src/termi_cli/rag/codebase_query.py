"""Codebase query module for RAG retrieval.

This module provides functionality to:
- Search the indexed codebase for relevant code snippets
- Format results for LLM context injection
"""

from __future__ import annotations

import logging
from typing import Optional

from termi_cli.rag.codebase_indexer import INDEX_PATH, CHROMA_AVAILABLE

logger = logging.getLogger(__name__)

if CHROMA_AVAILABLE:
    import chromadb
    from chromadb.config import Settings


class CodebaseQuery:
    """Query the indexed codebase for relevant code."""
    
    def __init__(self, index_name: str = "default"):
        """Initialize the query engine.
        
        Args:
            index_name: Name of the index to query
        """
        self.index_name = index_name
        self.collection = None
        
        if not CHROMA_AVAILABLE:
            logger.warning("ChromaDB not available. Codebase query disabled.")
            return
        
        try:
            client = chromadb.PersistentClient(
                path=INDEX_PATH,
                settings=Settings(anonymized_telemetry=False),
            )
            # Try to get existing collection
            try:
                self.collection = client.get_collection(f"codebase_{index_name}")
            except Exception:
                # Collection doesn't exist
                self.collection = None
        except Exception as e:
            logger.error("Failed to connect to codebase index: %s", e)
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_language: Optional[str] = None,
    ) -> list[dict]:
        """Search the codebase for relevant code.
        
        Args:
            query: Natural language query
            n_results: Number of results to return
            filter_language: Optional language filter (e.g., "py", "js")
            
        Returns:
            List of result dictionaries with keys:
            - file_path: Relative path to the file
            - content: The code chunk
            - chunk_index: Index of this chunk in the file
            - language: File language/extension
            - distance: Similarity distance (lower is better)
        """
        if self.collection is None:
            return []
        
        try:
            where_filter = None
            if filter_language:
                where_filter = {"language": filter_language}
            
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
            )
            
            output = []
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            
            for doc, meta, dist in zip(documents, metadatas, distances):
                output.append({
                    "file_path": meta.get("file_path", "unknown"),
                    "content": doc,
                    "chunk_index": meta.get("chunk_index", 0),
                    "total_chunks": meta.get("total_chunks", 1),
                    "language": meta.get("language", ""),
                    "distance": dist,
                })
            
            return output
            
        except Exception as e:
            logger.error("Failed to search codebase: %s", e)
            return []
    
    def format_context(
        self,
        query: str,
        n_results: int = 5,
        filter_language: Optional[str] = None,
    ) -> str:
        """Search and format results as context for LLM.
        
        Args:
            query: Natural language query
            n_results: Number of results to include
            filter_language: Optional language filter
            
        Returns:
            Formatted context string ready for LLM injection
        """
        results = self.search(query, n_results, filter_language)
        
        if not results:
            return ""
        
        context_parts = ["### Relevant Code from Codebase:\n"]
        
        for i, result in enumerate(results, 1):
            file_path = result["file_path"]
            content = result["content"]
            language = result["language"]
            chunk_info = f"(part {result['chunk_index'] + 1}/{result['total_chunks']})"
            
            context_parts.append(f"#### [{i}] `{file_path}` {chunk_info}")
            context_parts.append(f"```{language}")
            # Extract just the code content (remove the "File: ..." header we added)
            if content.startswith("File: "):
                lines = content.split("\n", 2)
                if len(lines) > 2:
                    content = lines[2]
            context_parts.append(content.strip())
            context_parts.append("```\n")
        
        return "\n".join(context_parts)


def search_codebase(
    query: str,
    index_name: str = "default",
    n_results: int = 5,
    filter_language: Optional[str] = None,
) -> list[dict]:
    """Convenience function to search the codebase.
    
    Args:
        query: Natural language query
        index_name: Name of the index to search
        n_results: Number of results
        filter_language: Optional language filter
        
    Returns:
        List of search results
    """
    engine = CodebaseQuery(index_name)
    return engine.search(query, n_results, filter_language)


def get_codebase_context(
    query: str,
    index_name: str = "default",
    n_results: int = 5,
    filter_language: Optional[str] = None,
) -> str:
    """Get formatted codebase context for LLM injection.
    
    Args:
        query: Natural language query
        index_name: Name of the index to search
        n_results: Number of results
        filter_language: Optional language filter
        
    Returns:
        Formatted context string
    """
    engine = CodebaseQuery(index_name)
    return engine.format_context(query, n_results, filter_language)


def is_index_available(index_name: str = "default") -> bool:
    """Check if an index is available and has data."""
    engine = CodebaseQuery(index_name)
    if engine.collection is None:
        return False
    try:
        return engine.collection.count() > 0
    except Exception:
        return False


def get_project_index_name(directory: str | None = None) -> str:
    """Get an index name based on the project directory.
    
    Uses the directory name (sanitized) as the index name.
    Falls back to 'default' if unable to determine.
    
    Args:
        directory: Directory path (uses cwd if None)
        
    Returns:
        Sanitized index name
    """
    import os
    import re
    from pathlib import Path
    
    if directory is None:
        directory = os.getcwd()
    
    path = Path(directory).resolve()
    name = path.name
    
    # Sanitize: only alphanumeric, dash, underscore
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    name = name.strip("_").lower()
    
    if not name or name in (".", ".."):
        return "default"
    
    return name

