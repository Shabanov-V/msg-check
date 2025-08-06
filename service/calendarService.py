from googleapiclient.discovery import build
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_SUMMARY = "Event Calendar"

class CalendarService:
    def __init__(self, calendar_id, credentials_path="service_account_creds.json"):
        self.credentials_path = credentials_path
        self.calendar_id = calendar_id
        self.creds = self.authenticate()
        self.service = build("calendar", "v3", credentials=self.creds)

    def authenticate(self):
        creds = service_account.Credentials.from_service_account_file(self.credentials_path, scopes=SCOPES)
        return creds
    
    def create_event(self, name, description, start_datetime, end_datetime):
        event = {
            "summary": name,
            "description": description,
            "start": {
                "dateTime": start_datetime.isoformat()
            },
            "end": {
                "dateTime": end_datetime.isoformat()
            },
        }
        return self.service.events().insert(calendarId=self.calendar_id, body=event).execute()

    def get_subscription_link(self):
        return f"https://calendar.google.com/calendar/u/0/r?cid={self.calendar_id}"

    # Only manual execution
    def clear_all_events(self):
        """Deletes all events from the calendar."""
        events_result = self.service.events().list(calendarId=self.calendar_id).execute()
        events = events_result.get('items', [])
        for event in events:
            self.service.events().delete(calendarId=self.calendar_id, eventId=event['id']).execute()
            print(f"Deleted event: {event.get('summary', event['id'])}")
