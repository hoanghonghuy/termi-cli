from sqlalchemy import create_engine, inspect, text
from ..config import load_config

def get_db_schema() -> str:
    """
    Inspects the database and returns its schema (table names, columns, types).
    This provides context for the AI to write accurate queries.
    """
    print("--- TOOL: Đang lấy schema của database ---")
    try:
        config = load_config()
        db_uri = config.get("database", {}).get("connection_string")
        if not db_uri:
            return "Database connection string not configured."
        
        engine = create_engine(db_uri)
        inspector = inspect(engine)
        schema_info = []
        for table_name in inspector.get_table_names():
            columns = [f"{col['name']} ({col['type']})" for col in inspector.get_columns(table_name)]
            schema_info.append(f"Table '{table_name}': {', '.join(columns)}")
        
        # Trả về thông báo rõ ràng nếu không có bảng
        if not schema_info:
            return "No tables found in the database."
            
        return "\n".join(schema_info)
    except Exception as e:
        return f"Error getting database schema: {e}"

def run_sql_query(query: str) -> str:
    """
    Executes a read-only SQL query (SELECT) against the database and returns the result.
    IMPORTANT: For security, only SELECT statements are allowed.
    Args:
        query (str): The SQL SELECT statement to execute.
    """
    print(f"--- TOOL: Đang thực thi truy vấn SQL: {query} ---")
    
    if not query.strip().upper().startswith("SELECT"):
        return "Error: For security reasons, only SELECT queries are allowed."

    try:
        config = load_config()
        db_uri = config.get("database", {}).get("connection_string")
        if not db_uri:
            return "Database connection string not configured."
        
        engine = create_engine(db_uri)
        with engine.connect() as connection:
            result = connection.execute(text(query))
            rows = result.fetchall()
            if not rows:
                return "Query executed successfully, but returned no results."
            
            header = result.keys()
            result_str = " | ".join(map(str, header)) + "\n"
            result_str += "-" * (len(result_str) - 1) + "\n"
            for row in rows:
                result_str += " | ".join(map(str, row)) + "\n"
            return result_str
    except Exception as e:
        return f"Error executing SQL query: {e}"