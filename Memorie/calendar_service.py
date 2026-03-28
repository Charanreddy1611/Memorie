"""
Memoire — Google Calendar and Google Drive integration
=======================================================

This module connects Memoire to Google APIs: OAuth2 for Calendar and Drive (scoped via
``config.OAUTH_SCOPES``), uploads generated memory assets into a dedicated Drive folder
tree, and creates all-day Calendar events that summarize each memory (optionally linking
to uploaded files). It also exposes helpers to check whether OAuth is configured, run
the consent flow, and list upcoming memory-themed events for reminders or dashboards.

Use cases:
  * **First-time setup** — ``connect_calendar`` / ``_get_creds`` runs the desktop OAuth
    flow and persists ``token.json`` (path from config).
  * **Health check** — ``is_calendar_connected`` verifies a token exists and can be used
    or refreshed.
  * **Backup & sharing** — ``upload_memory_to_drive`` creates a per-memory subfolder,
    uploads video, music, cover, and comic panels, and returns web view links.
  * **Calendar journaling** — ``add_memory_event`` builds a rich description (people,
    location, emotion, key moments, Drive links) using ``CALENDAR_TIMEZONE`` and
    ``CALENDAR_EVENT_PREFIX`` from config.
  * **Upcoming memories** — ``get_upcoming_memory_events`` queries primary calendar for
    events whose summary matches the configured prefix.

Low-level helpers build API clients, resolve or create the app root folder in Drive,
and upload individual files with link-sharing enabled for readers.
"""

import json
import mimetypes
import os
from datetime import datetime

from config import (
    CALENDAR_EVENT_PREFIX,
    CALENDAR_TIMEZONE,
    CREDENTIALS_PATH,
    DRIVE_FOLDER_NAME,
    OAUTH_SCOPES,
    TOKEN_PATH,
)
from logger import get_logger

log = get_logger(__name__)


def _get_creds():
    """
    Return valid OAuth credentials, running the installed-app flow if needed.

    Loads ``TOKEN_PATH``; refreshes or opens the browser flow using
    ``CREDENTIALS_PATH`` and ``OAUTH_SCOPES``, then saves the token.

    Returns:
        google.oauth2.credentials.Credentials instance.

    Raises:
        FileNotFoundError: If client secrets are missing when a new flow is required.
    """
    log.info("_get_creds called")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, OAUTH_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Google credentials not found at {CREDENTIALS_PATH}. "
                    "Download from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, OAUTH_SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def _get_calendar_service():
    """
    Build and return the Google Calendar API v3 service object.

    Returns:
        googleapiclient discovery Resource for calendar v3.
    """
    log.info("_get_calendar_service called")
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=_get_creds())


def _get_drive_service():
    """
    Build and return the Google Drive API v3 service object.

    Returns:
        googleapiclient discovery Resource for drive v3.
    """
    log.info("_get_drive_service called")
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=_get_creds())


def _get_or_create_drive_folder(drive_service, folder_name: str = DRIVE_FOLDER_NAME) -> str:
    """
    Return the ID of the app folder in Drive, creating it if it does not exist.

    Args:
        drive_service: Authenticated Drive API service.
        folder_name: Folder display name (default from config).

    Returns:
        Google Drive folder id string.
    """
    log.info("_get_or_create_drive_folder called folder_name=%r", folder_name)
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
    """
    Upload a local file to Drive under the given parent folder with anyone-reader link.

    Args:
        drive_service: Authenticated Drive API service.
        file_path: Path to the file on disk.
        folder_id: Parent folder id in Drive.

    Returns:
        Dict with id, name, webViewLink, or None if path missing or file not found.
    """
    log.info("_upload_file called file_path=%r folder_id=%r", file_path, folder_id)
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
    """
    Upload all generated files for a memory into a new subfolder under the app root.

    Args:
        memory: Memory dict with optional video_path, music_path, cover_path, panel_paths.

    Returns:
        Dict with keys such as folder_link, video_link, music_link, cover_link,
        panel_links (list of webViewLink strings).
    """
    log.info("upload_memory_to_drive called memory=%r", memory)
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


def is_calendar_connected() -> bool:
    """
    Check whether a token file exists and credentials are valid or refreshable.

    Returns:
        True if OAuth state allows API calls without a new user flow.
    """
    log.info("is_calendar_connected called")
    if not os.path.exists(TOKEN_PATH):
        return False
    try:
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(TOKEN_PATH, OAUTH_SCOPES)
        return creds.valid or (creds.expired and creds.refresh_token is not None)
    except Exception:
        return False


def connect_calendar():
    """
    Run the OAuth flow (if needed) and persist the token.

    Returns:
        True on success.
    """
    log.info("connect_calendar called")
    _get_creds()
    return True


def add_memory_event(memory: dict, drive_links: dict | None = None) -> str | None:
    """
    Create a Google Calendar all-day event for a memory on its date.

    Args:
        memory: Memory dict (title, date, summary, people, key_moments, etc.).
        drive_links: Optional links from ``upload_memory_to_drive`` to embed in description.

    Returns:
        Created event id, or None on failure.
    """
    log.info("add_memory_event called memory=%r drive_links=%r", memory, drive_links)
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
            "summary": f"{CALENDAR_EVENT_PREFIX} {memory.get('title', 'Untitled')}",
            "description": description,
            "start": {
                "date": memory.get("date", datetime.now().strftime("%Y-%m-%d")),
                "timeZone": CALENDAR_TIMEZONE,
            },
            "end": {
                "date": memory.get("date", datetime.now().strftime("%Y-%m-%d")),
                "timeZone": CALENDAR_TIMEZONE,
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
        log.error("Calendar event creation failed: %s", e)
        return None


def get_upcoming_memory_events(max_results: int = 10) -> list[dict]:
    """
    List upcoming primary-calendar events whose text matches the memory event prefix.

    Args:
        max_results: Maximum number of events to return from the API.

    Returns:
        List of event resource dicts, or empty list on error.
    """
    log.info("get_upcoming_memory_events called max_results=%r", max_results)
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
                q=CALENDAR_EVENT_PREFIX,
            )
            .execute()
        )

        return result.get("items", [])
    except Exception as e:
        log.error("Failed to fetch calendar events: %s", e)
        return []
