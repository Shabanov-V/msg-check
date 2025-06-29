import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_SUMMARY = "Event Calendar"

class CalendarService:
    def __init__(self, credentials_path="credentials.json", token_path="token.json"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.creds = self.authenticate()
        self.service = build("calendar", "v3", credentials=self.creds)
        self.calendar_id = self.get_or_create_calendar()

    def authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0, access_type='offline')
            with open(self.token_path, "w") as token:
                token.write(creds.to_json())
        return creds

    def get_or_create_calendar(self):
        calendars = self.service.calendarList().list().execute().get("items", [])
        for cal in calendars:
            if cal.get("summary") == CALENDAR_SUMMARY:
                return cal["id"]
        calendar = {
            "summary": CALENDAR_SUMMARY,
            "timeZone": "UTC",
        }
        created_calendar = self.service.calendars().insert(body=calendar).execute()
        rule = {
            "scope": {"type": "default"},
            "role": "reader"
        }
        self.service.acl().insert(calendarId=created_calendar["id"], body=rule).execute()
        return created_calendar["id"]

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
