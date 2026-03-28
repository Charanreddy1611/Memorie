import os
import json
import mimetypes
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]
CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH = "token.json"

DRIVE_FOLDER_NAME = "Memoire"


def _get_creds():
    """Return valid OAuth credentials, running the flow if needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Google credentials not found at {CREDENTIALS_PATH}. "
                    "Download from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def _get_calendar_service():
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=_get_creds())


def _get_drive_service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_get_creds())


# ─── Drive helpers ───────────────────────────────────────────


def _get_or_create_drive_folder(drive_service, folder_name: str = DRIVE_FOLDER_NAME) -> str:
    """Return the ID of the app folder in Drive, creating it if needed."""
    query = (
        f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )
    results = drive_service.files().list(q=query, spaces="drive", fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = drive_service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def _upload_file(drive_service, file_path: str, folder_id: str) -> dict | None:
    """Upload a local file to Drive and return {name, webViewLink, id}."""
    from googleapiclient.http import MediaFileUpload

    if not file_path or not os.path.exists(file_path):
        return None

    mime, _ = mimetypes.guess_type(file_path)
    if not mime:
        mime = "application/octet-stream"

    file_name = os.path.basename(file_path)
    metadata = {"name": file_name, "parents": [folder_id]}

    media = MediaFileUpload(file_path, mimetype=mime, resumable=True)
    uploaded = (
        drive_service.files()
        .create(body=metadata, media_body=media, fields="id,name,webViewLink")
        .execute()
    )

    drive_service.permissions().create(
        fileId=uploaded["id"],
        body={"role": "reader", "type": "anyone"},
    ).execute()

    return uploaded


def upload_memory_to_drive(memory: dict) -> dict:
    """Upload all generated files for a memory to Drive.

    Returns a dict with keys like 'video_link', 'music_link',
    'cover_link', 'panel_links' (list), 'folder_link'.
    """
    drive = _get_drive_service()
    root_folder_id = _get_or_create_drive_folder(drive)

    title = memory.get("title", "Untitled").replace("/", "-")[:60]
    mem_folder_meta = {
        "name": title,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [root_folder_id],
    }
    mem_folder = drive.files().create(body=mem_folder_meta, fields="id,webViewLink").execute()
    mem_folder_id = mem_folder["id"]

    drive.permissions().create(
        fileId=mem_folder_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()

    links: dict = {"folder_link": mem_folder.get("webViewLink", "")}

    if memory.get("video_path"):
        res = _upload_file(drive, memory["video_path"], mem_folder_id)
        if res:
            links["video_link"] = res.get("webViewLink", "")

    if memory.get("music_path"):
        res = _upload_file(drive, memory["music_path"], mem_folder_id)
        if res:
            links["music_link"] = res.get("webViewLink", "")

    if memory.get("cover_path"):
        res = _upload_file(drive, memory["cover_path"], mem_folder_id)
        if res:
            links["cover_link"] = res.get("webViewLink", "")

    panel_paths_raw = memory.get("panel_paths")
    if panel_paths_raw:
        panel_list = panel_paths_raw if isinstance(panel_paths_raw, list) else []
        if isinstance(panel_paths_raw, str):
            try:
                panel_list = json.loads(panel_paths_raw)
            except (json.JSONDecodeError, TypeError):
                panel_list = []
        panel_links = []
        for p in panel_list:
            res = _upload_file(drive, p, mem_folder_id)
            if res:
                panel_links.append(res.get("webViewLink", ""))
        if panel_links:
            links["panel_links"] = panel_links

    return links


# ─── Calendar ────────────────────────────────────────────────


def is_calendar_connected() -> bool:
    """Check if Google Calendar OAuth token exists and is valid."""
    if not os.path.exists(TOKEN_PATH):
        return False
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        return creds.valid or (creds.expired and creds.refresh_token is not None)
    except Exception:
        return False


def connect_calendar():
    """Run the OAuth flow and save the token."""
    _get_creds()
    return True


def add_memory_event(memory: dict, drive_links: dict | None = None) -> str | None:
    """Create a Google Calendar event for a memory.

    If drive_links is provided, the event description and attachments
    will include links to the uploaded files in Google Drive.
    Returns the event ID or None on failure.
    """
    try:
        service = _get_calendar_service()

        people_str = ", ".join(memory.get("people", [])) if memory.get("people") else "—"
        moments_str = "\n".join(f"  • {m}" for m in memory.get("key_moments", []))
        emotion = memory.get("emotion", "").capitalize()

        description_parts = [
            f"Emotion: {emotion}" if emotion else "",
            f"People: {people_str}",
            f"Location: {memory.get('location', '—')}",
            "",
            memory.get("summary", ""),
            "",
            f"Key Moments:\n{moments_str}" if moments_str else "",
        ]

        if drive_links:
            description_parts.append("\n─── Your Memory Files ───")
            if drive_links.get("folder_link"):
                description_parts.append(f"📁 All Files: {drive_links['folder_link']}")
            if drive_links.get("video_link"):
                description_parts.append(f"🎬 Video: {drive_links['video_link']}")
            if drive_links.get("music_link"):
                description_parts.append(f"🎵 Soundtrack: {drive_links['music_link']}")
            if drive_links.get("cover_link"):
                description_parts.append(f"🖼️ Cover Art: {drive_links['cover_link']}")
            if drive_links.get("panel_links"):
                description_parts.append(f"📖 Comic Panels ({len(drive_links['panel_links'])} images):")
                for i, link in enumerate(drive_links["panel_links"], 1):
                    description_parts.append(f"   Panel {i}: {link}")

        description = "\n".join(p for p in description_parts if p)

        event = {
            "summary": f"📹 Memory: {memory.get('title', 'Untitled')}",
            "description": description,
            "start": {
                "date": memory.get("date", datetime.now().strftime("%Y-%m-%d")),
                "timeZone": "America/Los_Angeles",
            },
            "end": {
                "date": memory.get("date", datetime.now().strftime("%Y-%m-%d")),
                "timeZone": "America/Los_Angeles",
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 0},
                ],
            },
            "colorId": "7",
        }

        created = service.events().insert(calendarId="primary", body=event).execute()
        return created.get("id")
    except Exception as e:
        print(f"Calendar event creation failed: {e}")
        return None


def get_upcoming_memory_events(max_results: int = 10) -> list[dict]:
    """Retrieve upcoming memory events from Google Calendar."""
    try:
        service = _get_calendar_service()
        now = datetime.utcnow().isoformat() + "Z"

        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
                q="📹 Memory:",
            )
            .execute()
        )

        return result.get("items", [])
    except Exception as e:
        print(f"Failed to fetch calendar events: {e}")
        return []
