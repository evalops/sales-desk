import os
import base64
import pickle
from typing import List, Dict, Optional, Type, Any
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

SCOPES = ['https://www.googleapis.com/auth/gmail.send', 
          'https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.compose']

class GmailToolInput(BaseModel):
    """Input schema for Gmail Tool"""
    action: str = Field(description="Action to perform: send, search, or read")
    to: Optional[str] = Field(default=None, description="Email recipient")
    subject: Optional[str] = Field(default=None, description="Email subject")
    body: Optional[str] = Field(default=None, description="Email body")
    query: Optional[str] = Field(default=None, description="Search query")
    message_id: Optional[str] = Field(default=None, description="Message ID to read")

class GmailTool(BaseTool):
    name: str = "Gmail Tool"
    description: str = "Tool for sending, reading, and managing Gmail emails. Use action='send' to send emails, action='search' to search emails, action='read' to read a specific email."
    args_schema: Type[BaseModel] = GmailToolInput
    service: Any = None
    
    def __init__(self):
        super().__init__()
        self.service = self._authenticate()
    
    def _authenticate(self):
        creds = None
        token_file = 'token.pickle'
        
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_config(
                    {
                        "installed": {
                            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                            "redirect_uris": ["http://localhost"]
                        }
                    },
                    SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        return build('gmail', 'v1', credentials=creds)
    
    def _run(self, **kwargs) -> str:
        action = kwargs.get('action', 'send')
        
        if action == 'send':
            return self.send_email(
                to=kwargs.get('to'),
                subject=kwargs.get('subject'),
                body=kwargs.get('body')
            )
        elif action == 'search':
            return self.search_emails(query=kwargs.get('query', ''))
        elif action == 'read':
            return self.read_email(message_id=kwargs.get('message_id'))
        else:
            return f"Unknown action: {action}"
    
    def send_email(self, to: str, subject: str, body: str, *, in_reply_to: Optional[str] = None, thread_id: Optional[str] = None) -> str:
        try:
            message = self._create_message(to, subject, body, in_reply_to=in_reply_to)
            payload: Dict[str, Any] = {'raw': message['raw']}
            if thread_id:
                payload['threadId'] = thread_id
            sent_message = self.service.users().messages().send(userId='me', body=payload).execute()
            return f"Email sent successfully! Message ID: {sent_message['id']}"
        except HttpError as error:
            return f"An error occurred: {error}"
    
    def _create_message(self, to: str, subject: str, body: str, in_reply_to: Optional[str] = None) -> Dict:
        msg = EmailMessage()
        msg['To'] = to
        msg['Subject'] = subject
        # From is set automatically by Gmail API for the authenticated user
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
            msg['References'] = in_reply_to
        msg.set_content(body)
        encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return {'raw': encoded_message}
    
    def search_emails(self, query: str, max_results: int = 10) -> str:
        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            if not messages:
                return "No messages found."
            
            email_summaries = []
            for msg in messages:
                msg_data = self.service.users().messages().get(
                    userId='me', 
                    id=msg['id']
                ).execute()
                
                headers = msg_data['payload'].get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
                
                email_summaries.append(f"From: {sender} | Subject: {subject} | ID: {msg['id']}")
            
            return "\n".join(email_summaries)
        except HttpError as error:
            return f"An error occurred: {error}"
    
    def read_email(self, message_id: str) -> str:
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id
            ).execute()
            
            payload = message['payload']
            headers = payload.get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown Date')
            
            body = self._get_message_body(payload)
            
            return f"From: {sender}\nDate: {date}\nSubject: {subject}\n\nBody:\n{body}"
        except HttpError as error:
            return f"An error occurred: {error}"
    
    def _get_message_body(self, payload: Dict) -> str:
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body']['data']
                    body += base64.urlsafe_b64decode(data).decode('utf-8')
        elif payload['body'].get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return body or "No body content found"

    def read_email_details(self, message_id: str) -> Dict[str, Any]:
        """Return structured details including threadId for threading replies."""
        try:
            message = self.service.users().messages().get(userId='me', id=message_id).execute()
            payload = message.get('payload', {})
            headers = payload.get('headers', [])
            get_h = lambda n: next((h['value'] for h in headers if h.get('name') == n), None)
            details = {
                'from': get_h('From') or 'Unknown Sender',
                'subject': get_h('Subject') or 'No Subject',
                'date': get_h('Date') or 'Unknown Date',
                'body': self._get_message_body(payload),
                'thread_id': message.get('threadId'),
            }
            return details
        except HttpError as error:
            return {'error': str(error)}

    def list_history_new_message_ids(self, start_history_id: str, max_pages: int = 1) -> List[str]:
        """List message IDs added since the given history ID.

        Returns a list of message IDs for messagesAdded events. Paginates up to max_pages.
        """
        try:
            user_id = 'me'
            page_token = None
            collected: List[str] = []
            pages = 0
            while True:
                req = self.service.users().history().list(
                    userId=user_id,
                    startHistoryId=start_history_id,
                    pageToken=page_token
                )
                resp = req.execute()
                for h in resp.get('history', []):
                    for m in h.get('messagesAdded', []) or []:
                        mid = m.get('message', {}).get('id')
                        if mid:
                            collected.append(mid)
                page_token = resp.get('nextPageToken')
                pages += 1
                if not page_token or pages >= max_pages:
                    break
            return collected
        except HttpError as error:
            return []
