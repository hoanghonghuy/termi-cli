import datetime
from googleapiclient.discovery import build
from ..auth import get_credentials

def list_events(max_results: int = 10) -> str:
    """
    Lists the next upcoming events from the user's primary Google Calendar.

    Args:
        max_results (int): The maximum number of events to return.
    """
    print("--- TOOL: Đang lấy sự kiện từ Lịch Google ---")
    try:
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)

        now = datetime.datetime.utcnow().isoformat() + "Z"
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            return "No upcoming events found."

        result_str = "Upcoming events:\n"
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            result_str += f"- {start}: {event['summary']}\n"
        return result_str
    except Exception as e:
        return f"An error occurred with Google Calendar: {e}"