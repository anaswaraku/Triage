from fastapi import FastAPI, HTTPException
import httpx
import os.path
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import base64
from email.message import EmailMessage
from googleapiclient.discovery import build

app = FastAPI()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"


async def get_credentials():
    """Get valid user credentials (handles refresh automatically)."""
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds


def get_access_token():
    """Retrieves or refreshes the access token."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds.token


@app.get("/get_email")
async def fetch_latest_email():
    headers = {"Authorization": f"Bearer {get_access_token()}"}

    async with httpx.AsyncClient() as client:
        # Get message ID
        list_resp = await client.get(
            f"{GMAIL_BASE_URL}/messages?maxResults=1", headers=headers
        )
        if list_resp.status_code != 200:
            raise HTTPException(list_resp.status_code, "Failed to list emails")

        messages = list_resp.json().get("messages", [])
        if not messages:
            return {"message": "No emails found."}

        # Get message details
        msg_id = messages[0]["id"]
        msg_resp = await client.get(
            f"{GMAIL_BASE_URL}/messages/{msg_id}?format=full", headers=headers
        )
        if msg_resp.status_code != 200:
            raise HTTPException(msg_resp.status_code, "Failed to fetch email details")

        # Extract headers
        headers_list = msg_resp.json().get("payload", {}).get("headers", [])
        get_header = lambda name, default: next(
            (h["value"] for h in headers_list if h["name"] == name), default
        )

        return {
            "status": "success",
            "msg_id": msg_id,
            "from": get_header("From", "Unknown Sender"),
            "subject": get_header("Subject", "No Subject"),
            "raw_rest_url": f"{GMAIL_BASE_URL}/messages/{msg_id}?format=full",
            "message_snippet": msg_resp.json().get("snippet", ""),
        }


GMAIL_API_ROOT = "https://gmail.googleapis.com/gmail/v1/users"


@app.get("/user_info")
async def get_user_info(user_id: str = "me"):
    # Fix 2: Ensure the token logic is handled (ideally cached)
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        # Fix 3: Correct URL structure (https://gmail.googleapis.com/gmail/v1/users/me/profile)
        url = f"{GMAIL_API_ROOT}/{user_id}/profile"
        resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            # It's helpful to include the error detail from Google
            error_detail = (
                resp.json().get("error", {}).get("message", "Failed to fetch user info")
            )
            raise HTTPException(status_code=resp.status_code, detail=error_detail)

        return resp.json()
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{GMAIL_BASE_URL}/{user_id}", headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, "Failed to fetch user info")
        return resp.json()


@app.post("/create_draft")
async def create_draft():
    creds = await get_credentials()
    try:
        service = build("gmail", "v1", credentials=creds)
        message = EmailMessage()
        message.set_content("This is new mail from triage")
        message["To"] = "anaswarakanichadan@gmail.com"
        message["From"] = "anaswaraku17@gmail.com"
        message["Subject"] = "Automated Draft"

        # encoded message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {"message": {"raw": encoded_message}}

        draft = (
            service.users().drafts().create(userId="me", body=create_message).execute()
        )
    except HTTPException as error:
        print(f"An error occurred: {error}")
        draft = None
    return draft


@app.post("/send_message")
async def send_message():
    creds = await get_credentials()
    try:
        service = build("gmail", "v1", credentials=creds)
        message = EmailMessage()
        message.set_content("This is new mail from triage")
        message["To"] = "anaswarakanichadan@gmail.com"
        message["From"] = "anaswaraku17@gmail.com"
        message["Subject"] = "Automated Draft"

        # encoded message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        send_message = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": encoded_message})
            .execute()
        )
        print(f'Message Id: {send_message["id"]}')
    except HTTPException as error:
        print(f"An error occurred: {error}")
        send_message = None
    return send_message
