
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
import os
from pathlib import Path

# Service account file path
SERVICE_ACCOUNT_FILE = Path(__file__).parent / 'service-account.json'

# Scopes required for Google Calendar
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events'
]

# Business email that will receive the calendar events
CALENDAR_EMAIL = os.environ.get('CALENDAR_EMAIL', 'pejman@myhomeexperts.com.au')

# Sydney timezone
SYDNEY_TZ = pytz.timezone('Australia/Sydney')


def get_calendar_service():
    """Create and return Google Calendar service with domain-wide delegation."""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES
        )
        
        # Delegate to the business owner's email
        delegated_credentials = credentials.with_subject(CALENDAR_EMAIL)
        
        service = build('calendar', 'v3', credentials=delegated_credentials)
        return service
    except Exception as e:
        print(f"Error creating calendar service: {str(e)}")
        raise


def create_consultation_meeting(client_name, client_email, consultation_date_str, consultation_time_str="10:00", duration_minutes=30):
    """
    Create a Google Calendar event with Google Meet link.
    
    Args:
        client_name: Name of the client
        client_email: Email of the client
        consultation_date_str: Date string in ISO format (YYYY-MM-DD)
        consultation_time_str: Time string in HH:MM format (default "10:00")
        duration_minutes: Meeting duration in minutes (default 30)
    
    Returns:
        dict: Event details including meet link
    """
    try:
        service = get_calendar_service()
        
        # Parse the consultation date and time
        consultation_date = datetime.strptime(consultation_date_str, '%Y-%m-%d')
        
        # Parse time (HH:MM format)
        time_parts = consultation_time_str.split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1]) if len(time_parts) > 1 else 0
        
        # Combine date and time in Sydney timezone
        start_time = SYDNEY_TZ.localize(consultation_date.replace(hour=hour, minute=minute, second=0))
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Create event
        event = {
            'summary': f'Luxury Home Consultation - {client_name}',
            'description': f'Free consultation with {client_name} to discuss their custom luxury home project.\n\nClient Email: {client_email}',
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'Australia/Sydney',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'Australia/Sydney',
            },
            'attendees': [
                {'email': client_email, 'displayName': client_name},
                {'email': CALENDAR_EMAIL}
            ],
            'conferenceData': {
                'createRequest': {
                    'requestId': f'meet-{client_email}-{int(datetime.now().timestamp())}',
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                    {'method': 'popup', 'minutes': 30},  # 30 minutes before
                ],
            },
        }
        
        # Insert event with Google Meet (no sendUpdates since no attendees)
        created_event = service.events().insert(
            calendarId='primary',
            body=event,
            conferenceDataVersion=1
        ).execute()
        
        # Extract meet link
        meet_link = created_event.get('hangoutLink', 'No meet link generated')
        
        return {
            'success': True,
            'event_id': created_event['id'],
            'meet_link': meet_link,
            'start_time': start_time.strftime('%A, %B %d, %Y at %I:%M %p %Z'),
            'calendar_link': created_event.get('htmlLink')
        }
        
    except Exception as e:
        print(f"Error creating calendar event: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


def list_upcoming_consultations(max_results=10):
    """List upcoming consultation meetings."""
    try:
        service = get_calendar_service()
        
        now = datetime.now(SYDNEY_TZ).isoformat()
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        return {
            'success': True,
            'events': events
        }
        
    except Exception as e:
        print(f"Error listing events: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
