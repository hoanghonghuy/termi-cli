from googleapiclient.discovery import build
from ..auth import get_credentials

def search_emails(query: str, max_results: int = 5) -> str:
    """
    Searches the user's Gmail for emails matching a query.

    Args:
        query (str): The search query (e.g., 'from:boss subject:report').
        max_results (int): The maximum number of emails to return.
    """
    print(f"--- TOOL: Đang tìm kiếm Gmail với từ khóa: '{query}' ---")
    try:
        creds = get_credentials()
        service = build("gmail", "v1", credentials=creds)

        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = results.get("messages", [])

        if not messages:
            return "No emails found matching the query."

        result_str = "Found emails:\n"
        for msg in messages:
            msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
            headers = msg_data["payload"]["headers"]
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "[No Subject]")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "[No Sender]")
            snippet = msg_data["snippet"]
            result_str += f"- From: {sender}\n  Subject: {subject}\n  Snippet: {snippet}\n\n"
        return result_str
    except Exception as e:
        return f"An error occurred with Gmail: {e}"