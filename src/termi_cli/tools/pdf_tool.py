"""PDF reader tool for Termi CLI.

Extracts text and metadata from PDF files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PYPDF_AVAILABLE = False
try:
    import pypdf
    _PYPDF_AVAILABLE = True
except ImportError:
    pypdf = None
    logger.debug("pypdf not available, PDF reading disabled")


def read_pdf(
    file_path: str,
    pages: Optional[str] = None,
    max_chars: int = 10000,
) -> str:
    """Extract text from a PDF file.
    
    Args:
        file_path: Path to the PDF file
        pages: Optional page range like "1-5" or "1,3,5"
        max_chars: Maximum characters to return
        
    Returns:
        Extracted text from the PDF
    """
    if not _PYPDF_AVAILABLE:
        return "Error: pypdf not installed. Run: pip install pypdf"
    
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"
    
    if not path.suffix.lower() == ".pdf":
        return f"Error: Not a PDF file: {file_path}"
    
    try:
        reader = pypdf.PdfReader(str(path))
        total_pages = len(reader.pages)
        
        # Parse page range
        if pages:
            page_nums = _parse_page_range(pages, total_pages)
        else:
            page_nums = range(total_pages)
        
        text_parts = []
        for i in page_nums:
            if i < total_pages:
                page_text = reader.pages[i].extract_text()
                text_parts.append(f"--- Page {i + 1} ---\n{page_text}")
        
        text = "\n\n".join(text_parts)
        
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n... (truncated, showing first {max_chars} chars)"
        
        return text
        
    except Exception as e:
        return f"Error reading PDF: {e}"


def get_pdf_info(file_path: str) -> str:
    """Get metadata and info about a PDF file.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        PDF metadata and page count
    """
    if not _PYPDF_AVAILABLE:
        return "Error: pypdf not installed"
    
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"
    
    try:
        reader = pypdf.PdfReader(str(path))
        metadata = reader.metadata
        
        info = [
            f"File: {path.name}",
            f"Pages: {len(reader.pages)}",
        ]
        
        if metadata:
            if metadata.title:
                info.append(f"Title: {metadata.title}")
            if metadata.author:
                info.append(f"Author: {metadata.author}")
            if metadata.subject:
                info.append(f"Subject: {metadata.subject}")
        
        return "\n".join(info)
        
    except Exception as e:
        return f"Error: {e}"


def _parse_page_range(pages: str, total: int) -> list[int]:
    """Parse a page range string like '1-5' or '1,3,5'."""
    result = []
    for part in pages.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            result.extend(range(int(start) - 1, min(int(end), total)))
        else:
            result.append(int(part) - 1)
    return result


def is_pdf_available() -> bool:
    """Check if PDF reading is available."""
    return _PYPDF_AVAILABLE
