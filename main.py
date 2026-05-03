from fastapi import FastAPI, HTTPException
import httpx
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import base64
from email.message import EmailMessage
from googleapiclient.discovery import build
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

app = FastAPI()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"

# Scheduler for background tasks
scheduler = AsyncIOScheduler()


async def auto_reply_background_task():
    """Background task to automatically reply to emails from specific sender."""
    TARGET_EMAIL = "anaswarakanichadan@gmail.com"

    try:
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                return {"status": "error", "message": "Credentials not available"}

        service = build("gmail", "v1", credentials=creds)

        # Check for unread messages
        results = (
            service.users()
            .messages()
            .list(userId="me", q="is:unread from:" + TARGET_EMAIL, maxResults=10)
            .execute()
        )

        messages = results.get("messages", [])

        for msg in messages:
            msg_data = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="full")
                .execute()
            )

            headers = msg_data.get("payload", {}).get("headers", [])
            get_header = lambda name, default: next(
                (h["value"] for h in headers if h["name"] == name), default
            )

            sender_email = get_header("From", "")
            subject = get_header("Subject", "")

            # Extract email from format like "John Doe <john@example.com>"
            if "<" in sender_email and ">" in sender_email:
                sender_email = sender_email.split("<")[1].split(">")[0]

            # Extract message body/content
            message_body = ""
            payload = msg_data.get("payload", {})

            if "parts" in payload:
                # Multipart message
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        data = part.get("body", {}).get("data", "")
                        if data:
                            import base64 as b64

                            message_body = b64.urlsafe_b64decode(data).decode("utf-8")
                            break
            else:
                # Simple message
                data = payload.get("body", {}).get("data", "")
                if data:
                    import base64 as b64

                    message_body = b64.urlsafe_b64decode(data).decode("utf-8")

            # Display the read message
            print(f"\n📧 New Email Received:")
            print(f"   From: {sender_email}")
            print(f"   Subject: {subject}")
            print(
                f"   Content: {message_body[:200]}..."
                if len(message_body) > 200
                else f"   Content: {message_body}"
            )
            print(f"   Status: MARKED AS READ ✓")

            # Check if already replied to avoid duplicate replies
            thread_id = msg_data.get("threadId")
            thread_data = (
                service.users().threads().get(userId="me", id=thread_id).execute()
            )
            thread_messages = thread_data.get("messages", [])

            # Check if we already sent a reply in this thread
            already_replied = False
            for thread_msg in thread_messages:
                thread_headers = thread_msg.get("payload", {}).get("headers", [])
                thread_get_header = lambda name, default: next(
                    (h["value"] for h in thread_headers if h["name"] == name), default
                )
                if "anaswaraku17@gmail.com" in thread_get_header("From", ""):
                    already_replied = True
                    break

            if not already_replied:
                # Create reply message
                reply_subject = (
                    f"Re: {subject}" if not subject.startswith("Re:") else subject
                )

                reply_message = EmailMessage()
                reply_message.set_content(
                    "Thank you for contacting. We will get back to you soon!"
                )
                reply_message["To"] = sender_email
                reply_message["From"] = "anaswaraku17@gmail.com"
                reply_message["Subject"] = reply_subject
                reply_message["In-Reply-To"] = get_header("Message-ID", "")
                reply_message["References"] = get_header("Message-ID", "")

                # Encode and send
                encoded_message = base64.urlsafe_b64encode(
                    reply_message.as_bytes()
                ).decode()

                service.users().messages().send(
                    userId="me", body={"raw": encoded_message}
                ).execute()

                # Mark the original message as read to prevent duplicate replies
                service.users().messages().modify(
                    userId="me", id=msg["id"], body={"removeLabelIds": ["UNREAD"]}
                ).execute()

                print(f"   📨 Auto-reply sent ✓\n")

    except Exception as error:
        print(f"Background task error: {error}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler.add_job(
        auto_reply_background_task, "interval", minutes=2, id="auto_reply_job"
    )
    scheduler.start()
    print("🚀 Background auto-reply scheduler started (checks every 2 minutes)")
    yield
    # Shutdown
    scheduler.shutdown()
    print("⛔ Background scheduler stopped")


app = FastAPI(lifespan=lifespan)


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


@app.get("/check_new_messages")
async def check_new_messages():
    """Check for new unread messages and return alert."""
    creds = await get_credentials()
    try:
        service = build("gmail", "v1", credentials=creds)

        # Get unread messages
        results = (
            service.users()
            .messages()
            .list(userId="me", q="is:unread", maxResults=10)
            .execute()
        )

        messages = results.get("messages", [])

        if not messages:
            return {"alert": "No new messages", "status": "ok", "unread_count": 0}

        # Fetch details for each unread message
        message_details = []
        for msg in messages:
            msg_data = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="full")
                .execute()
            )

            headers = msg_data.get("payload", {}).get("headers", [])
            get_header = lambda name, default: next(
                (h["value"] for h in headers if h["name"] == name), default
            )

            message_details.append(
                {
                    "id": msg["id"],
                    "from": get_header("From", "Unknown"),
                    "subject": get_header("Subject", "No Subject"),
                    "date": get_header("Date", "Unknown"),
                    "snippet": msg_data.get("snippet", ""),
                }
            )

        return {
            "alert": f"🔔 You have {len(messages)} new unread message(s)!",
            "status": "new_messages",
            "unread_count": len(messages),
            "messages": message_details,
        }

    except Exception as error:
        print(f"An error occurred: {error}")
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/auto_reply")
async def auto_reply(message_id: str = None):
    """Send automatic reply if message is from specific email address."""
    TARGET_EMAIL = "anaswarakanichadan@gmail.com"

    creds = await get_credentials()
    try:
        service = build("gmail", "v1", credentials=creds)

        # If no message_id provided, check all unread messages
        if not message_id:
            results = (
                service.users()
                .messages()
                .list(userId="me", q="is:unread", maxResults=10)
                .execute()
            )
            messages = results.get("messages", [])
        else:
            messages = [{"id": message_id}]

        replied_count = 0
        replied_messages = []

        for msg in messages:
            msg_data = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="full")
                .execute()
            )

            headers = msg_data.get("payload", {}).get("headers", [])
            get_header = lambda name, default: next(
                (h["value"] for h in headers if h["name"] == name), default
            )

            sender_email = get_header("From", "")
            # Extract email from format like "John Doe <john@example.com>"
            if "<" in sender_email and ">" in sender_email:
                sender_email = sender_email.split("<")[1].split(">")[0]

            subject = get_header("Subject", "")
            original_from = get_header("From", "Unknown")

            # Check if sender matches target email
            if TARGET_EMAIL in sender_email:
                # Create reply message
                reply_subject = (
                    f"Re: {subject}" if not subject.startswith("Re:") else subject
                )

                reply_message = EmailMessage()
                reply_message.set_content(
                    "Thank you for contacting. We will get back to you soon!"
                )
                reply_message["To"] = sender_email
                reply_message["From"] = "anaswaraku17@gmail.com"
                reply_message["Subject"] = reply_subject
                reply_message["In-Reply-To"] = get_header("Message-ID", "")
                reply_message["References"] = get_header("Message-ID", "")

                # Encode and send
                encoded_message = base64.urlsafe_b64encode(
                    reply_message.as_bytes()
                ).decode()

                send_result = (
                    service.users()
                    .messages()
                    .send(userId="me", body={"raw": encoded_message})
                    .execute()
                )

                replied_count += 1
                replied_messages.append(
                    {
                        "original_from": original_from,
                        "subject": subject,
                        "reply_sent": True,
                        "reply_id": send_result.get("id"),
                    }
                )

        return {
            "status": "success",
            "message": f"Checked {len(messages)} message(s), sent {replied_count} auto-reply(ies)",
            "replied_count": replied_count,
            "replied_messages": replied_messages,
        }

    except Exception as error:
        print(f"An error occurred: {error}")
        raise HTTPException(status_code=500, detail=str(error))
