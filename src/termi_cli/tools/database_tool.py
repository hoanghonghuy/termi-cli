"""Database query tool for Termi CLI.

Execute SQL queries on SQLite databases.
"""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def query_sqlite(
    database_path: str,
    query: str,
    params: Optional[list] = None,
    max_rows: int = 100,
) -> str:
    """Execute a SQL query on a SQLite database.
    
    Args:
        database_path: Path to the SQLite database file
        query: SQL query to execute
        params: Optional list of query parameters
        max_rows: Maximum rows to return
        
    Returns:
        Query results as formatted text
    """
    path = Path(database_path)
    if not path.exists():
        return f"Error: Database not found: {database_path}"
    
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Check if it's a SELECT query
        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchmany(max_rows)
            
            if not rows:
                return "Query returned no results."
            
            # Get column names
            columns = rows[0].keys()
            
            # Format as table
            result = ["| " + " | ".join(columns) + " |"]
            result.append("| " + " | ".join(["---"] * len(columns)) + " |")
            
            for row in rows:
                values = [str(row[col])[:50] for col in columns]  # Truncate long values
                result.append("| " + " | ".join(values) + " |")
            
            if len(rows) == max_rows:
                result.append(f"\n... (showing first {max_rows} rows)")
            
            return "\n".join(result)
        else:
            # DML query
            conn.commit()
            return f"Query executed successfully. Rows affected: {cursor.rowcount}"
            
    except sqlite3.Error as e:
        return f"SQLite Error: {e}"
    except Exception as e:
        return f"Error: {e}"
    finally:
        if 'conn' in locals():
            conn.close()


def list_tables(database_path: str) -> str:
    """List all tables in a SQLite database.
    
    Args:
        database_path: Path to the SQLite database file
        
    Returns:
        List of table names
    """
    return query_sqlite(
        database_path,
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )


def describe_table(database_path: str, table_name: str) -> str:
    """Get the schema of a table.
    
    Args:
        database_path: Path to the SQLite database
        table_name: Name of the table
        
    Returns:
        Table schema information
    """
    return query_sqlite(
        database_path,
        f"PRAGMA table_info({table_name})"
    )


def is_database_available() -> bool:
    """Check if database tool is available (SQLite is built-in)."""
    return True
