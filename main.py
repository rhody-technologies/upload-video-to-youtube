#!/usr/bin/env python3
"""
YouTube Video Uploader using Google Data API v3
------------------------------------------------
Prerequisites:
    pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 tqdm

Setup:
    1. Go to https://console.cloud.google.com/
    2. Create a project and enable the "YouTube Data API v3"
    3. Create OAuth 2.0 credentials (Desktop App) and download as client_secrets.json
    4. Place client_secrets.json in the same directory as this script
    5. Run the script — a browser window will open to authorize on first use
"""
from __future__ import annotations

import io
import os
import re
import sys
import time
import argparse
import mimetypes
from datetime import date, datetime

from tqdm import tqdm
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ── Constants ────────────────────────────────────────────────────────────────

CLIENT_SECRETS_FILE = "client_secret.json"
SPREADSHEET_ID = "1ixRaM2U94qshptAZ7JATM8bihBGlLniS5gD2S43y_F0"
SHEET_NAME = "Segments"
POSTING_COLUMN = "Posted"
VIDEO_ID_COLUMN = "Video ID"
PLAYLIST_ID = "PLGjEeEf-wkkDgD6xRh0e-VnloDrbpY_bJ"

# YouTube and Sheets are authorized by different Google accounts, so each
# gets its own token file and its own OAuth consent (same client_secret.json).
TOKEN_FILE_YOUTUBE = "token_youtube.json"
TOKEN_FILE_SHEETS = "token_sheets.json"

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",  # needed for playlist management
]
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

VALID_PRIVACY = ("public", "private", "unlisted")
VALID_CATEGORIES = {
    "1":  "Film & Animation",
    "2":  "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "19": "Travel & Events",
    "20": "Gaming",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
    "29": "Nonprofits & Activism",
}

# Resumable upload chunk size (5 MB)
CHUNK_SIZE = 5 * 1024 * 1024

# Retry settings for transient HTTP errors
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
MAX_RETRIES = 5


# ── Auth ─────────────────────────────────────────────────────────────────────

def get_credentials(token_file: str, scopes: list[str]) -> Credentials:
    """Return valid OAuth credentials for the given token file/scopes, refreshing/creating as needed."""
    creds = None

    # if i use secrets manager i will need to read/load the file from secrets manager here before exiting


    # Grab the token file if it exists and return it as creds
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)

    # Check if creds  is empty or invalid (which states are invalid?)
    if not creds or not creds.valid:

        # this branch seems like the creds can be valid but expired
        # if creds exists and are expired and has a refresh token
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing access token…")
            # does this update the file when running locally?
            # for lambda the file will need to be in /tmp directory to be writable
            # if i use secrets manager i will need to write the file to secrets manager here before exiting
            creds.refresh(Request())
        else:
            # this branch should never run in the cloud because it's designed to generate a new token which will require a human user
            if not os.path.exists(CLIENT_SECRETS_FILE):
                sys.exit(
                    f"[ERROR] '{CLIENT_SECRETS_FILE}' not found.\n"
                    "Download it from https://console.cloud.google.com/ "
                    "(APIs & Services → Credentials → OAuth 2.0 Client IDs → Download JSON)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes)
            creds = flow.run_local_server(port=0)
        # so this is where the actual file right happens but only if the token changes
        with open(token_file, "w") as fh:
            fh.write(creds.to_json())
        print(f"Credentials saved to '{token_file}'.")

    # if the token is already available and valid, we just return creds
    return creds


def get_authenticated_service() -> object:
    """Return an authorised YouTube API client."""
    return build("youtube", "v3", credentials=get_credentials(TOKEN_FILE_YOUTUBE, YOUTUBE_SCOPES))


def get_sheets_service() -> object:
    """Return an authorised Google Sheets API client."""
    return build("sheets", "v4", credentials=get_credentials(TOKEN_FILE_SHEETS, SHEETS_SCOPES))


def get_drive_service() -> object:
    """Return an authorised Google Drive API client (same account as Sheets)."""
    return build("drive", "v3", credentials=get_credentials(TOKEN_FILE_SHEETS, SHEETS_SCOPES))


# ── Sheets ───────────────────────────────────────────────────────────────────

def get_pending_rows(spreadsheet_id: str = SPREADSHEET_ID, sheet_range: str = "Sheet1") -> list[dict]:
    """
    Fetch rows from the given Google Sheet where the 'Posting' column is FALSE.

    Returns a list of dicts mapping header names to cell values, one per pending row.
    Each dict also carries a '_row_number' key: its 1-indexed row number in the
    sheet (accounting for the header row), used later to write back upload results.
    """
    sheets = get_sheets_service()
    result = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=sheet_range,
    ).execute()

    rows = result.get("values", [])
    if not rows:
        return []

    header, *data_rows = rows
    try:
        posting_idx = header.index(POSTING_COLUMN)
    except ValueError:
        sys.exit(f"[ERROR] Could not find a '{POSTING_COLUMN}' column in the sheet header row.")

    pending_rows = []
    for i, row in enumerate(data_rows):
        posting_value = row[posting_idx] if posting_idx < len(row) else ""
        if str(posting_value).strip().upper() == "FALSE":
            row_dict = dict(zip(header, row))
            row_dict["_row_number"] = i + 2  # +1 for header row, +1 for 1-indexing
            pending_rows.append(row_dict)

    return pending_rows


# ── Sheet updates ────────────────────────────────────────────────────────────

def _col_letter(index: int) -> str:
    """Convert a 0-indexed column number to its A1 letter(s) (0 -> 'A', 25 -> 'Z', 26 -> 'AA')."""
    index += 1
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _get_header(sheets, spreadsheet_id: str, sheet_range: str) -> list[str]:
    """Fetch just the header row of the given sheet."""
    result = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_range}!1:1",
    ).execute()
    values = result.get("values", [])
    return values[0] if values else []


def _ensure_column(sheets, spreadsheet_id: str, sheet_range: str, header: list[str], column_name: str) -> tuple[list[str], int]:
    """
    Ensure `column_name` exists in the sheet header, appending it as a new
    column if it doesn't. Returns the (possibly updated) header and the
    column's 0-indexed position.
    """
    if column_name in header:
        return header, header.index(column_name)

    col_index = len(header)
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_range}!{_col_letter(col_index)}1",
        valueInputOption="RAW",
        body={"values": [[column_name]]},
    ).execute()
    return header + [column_name], col_index


def mark_video_posted(
        sheets,
        spreadsheet_id: str,
        sheet_range: str,
        row_number: int,
        posted_col_idx: int,
        video_id_col_idx: int,
        video_url: str,
) -> None:
    """Set the Posted column to TRUE and record the video's watch URL for the given sheet row."""
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": f"{sheet_range}!{_col_letter(posted_col_idx)}{row_number}", "values": [["TRUE"]]},
                {"range": f"{sheet_range}!{_col_letter(video_id_col_idx)}{row_number}", "values": [[video_url]]},
            ],
        },
    ).execute()


# ── Drive ────────────────────────────────────────────────────────────────────

DOWNLOAD_DIR = "/tmp/yt-uploader"

DRIVE_URL_ID_PATTERNS = [
    re.compile(r"/d/([a-zA-Z0-9_-]+)"),      # .../file/d/<ID>/view, .../document/d/<ID>/edit
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),  # .../open?id=<ID>, .../uc?id=<ID>&export=download
]


def _extract_drive_file_id(url: str) -> str:
    """Extract the Google Drive file ID from a share/view/download URL."""
    for pattern in DRIVE_URL_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    sys.exit(f"[ERROR] Could not extract a Google Drive file ID from URL: {url}")


def _download_drive_file(drive, file_id: str, dest_path_stem: str) -> str:
    """
    Download a Drive file by ID to `{dest_path_stem}.<ext>`, with the extension
    inferred from the file's name/MIME type. Returns the path written to.
    """
    metadata = drive.files().get(fileId=file_id, fields="name, mimeType").execute()
    ext = os.path.splitext(metadata.get("name", ""))[1] or mimetypes.guess_extension(metadata.get("mimeType", "")) or ""
    dest_path = f"{dest_path_stem}{ext}"

    request = drive.files().get_media(fileId=file_id)
    with io.FileIO(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    return dest_path


def get_assets(video_link: str, thumbnail_link: str) -> tuple[str, str]:
    """
    Resolve Google Drive share links for a video and thumbnail, and download
    both into DOWNLOAD_DIR as 'video.<ext>' and 'thumbnail.<ext>'.

    Returns (video_path, thumbnail_path).
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    drive = get_drive_service()

    video_path = _download_drive_file(
        drive, _extract_drive_file_id(video_link), os.path.join(DOWNLOAD_DIR, "video")
    )
    thumbnail_path = _download_drive_file(
        drive, _extract_drive_file_id(thumbnail_link), os.path.join(DOWNLOAD_DIR, "thumbnail")
    )

    return video_path, thumbnail_path


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_video(
        youtube,
        file_path: str,
        title: str,
        description: str,
        tags: list[str],
        category_id: str,
        privacy: str,
) -> str | None:
    """
    Upload a video file using a resumable upload session.

    Returns the YouTube video ID on success, or None on failure.
    """
    if not os.path.exists(file_path):
        sys.exit(fr"[ERROR] File not found: {file_path}")

    file_size = os.path.getsize(file_path)
    print(fr"Uploading: {file_path}  ({file_size / 1_048_576:.1f} MB)")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(fr"{file_path}", chunksize=CHUNK_SIZE, resumable=True)
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    video_id = None
    retry = 0

    with tqdm(total=file_size, unit="B", unit_scale=True, desc="Progress") as pbar:
        response = None
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    uploaded = int(status.resumable_progress)
                    pbar.update(uploaded - pbar.n)
            except HttpError as e:
                if e.resp.status in RETRIABLE_STATUS_CODES:
                    retry += 1
                    if retry > MAX_RETRIES:
                        print(f"\n[ERROR] Too many retries ({MAX_RETRIES}). Aborting.")
                        return None
                    wait = 2 ** retry
                    print(f"\n[WARN] HTTP {e.resp.status} — retrying in {wait}s… (attempt {retry}/{MAX_RETRIES})")
                    time.sleep(wait)
                else:
                    raise
            else:
                if response:
                    pbar.update(file_size - pbar.n)

    if response:
        video_id = response.get("id")

    return video_id


def _parse_scheduled_date(value: str) -> date | None:
    """Parse a 'Scheduled Date' cell value into a date, or None if blank/unparseable."""
    value = str(value).strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def upload_pending_videos(
        videos_to_upload: list[dict],
        spreadsheet_id: str = SPREADSHEET_ID,
        sheet_range: str = SHEET_NAME,
) -> None:
    """
    Upload every row in `videos_to_upload` whose 'Scheduled Date' is today or in the past.

    For each due row: download its video/thumbnail via get_assets() into the
    default download paths, upload the video from those paths, then delete
    the downloaded files. On success, the sheet row is updated: the 'Posted'
    column is set to TRUE and the video's watch URL is written to a 'Video ID'
    column (added to the sheet automatically if it doesn't already exist).
    """
    youtube = get_authenticated_service()
    sheets = get_sheets_service()
    today = date.today()

    header = _get_header(sheets, spreadsheet_id, sheet_range)
    posted_col_idx = header.index(POSTING_COLUMN)
    header, video_id_col_idx = _ensure_column(sheets, spreadsheet_id, sheet_range, header, VIDEO_ID_COLUMN)

    for video_row in videos_to_upload:
        scheduled_date = _parse_scheduled_date(video_row.get("Scheduled Posting Date", ""))
        if scheduled_date is None or scheduled_date > today:
            continue

        video_path, thumbnail_path = get_assets(video_row["Video Link"], video_row["Thumbnail Link"])

        try:
            video_id = upload_video(
                youtube=youtube,
                file_path=video_path,
                title=video_row.get("Title", ""),
                description=video_row.get("Description", ""),
                tags=[tag.strip() for tag in video_row.get("Tags", "").split(",") if tag.strip()],
                category_id=video_row.get("Category", "22"),
                privacy=video_row.get("Privacy", "public"),
            )

            if video_id:
                print(f"\n✅ Upload complete!")
                print(f"   Video ID : {video_id}")
                print(f"   Watch URL: https://www.youtube.com/watch?v={video_id}")
                print(f"   Studio   : https://studio.youtube.com/video/{video_id}/edit")


                request = youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path)
                )
                request.execute()

                # print(f"\nAdding to playlist '{video_row.get('Playlist', {PLAYLIST_ID})}'…")
                # # success = add_to_playlist(youtube, video_id, video_row.get('Playlist', PLAYLIST_ID))
                # if success:
                #     print(f"✅ Added to playlist: https://www.youtube.com/playlist?list={video_row.get('Playlist', {PLAYLIST_ID})}")
                # else:
                #     print("[WARN] Video was uploaded but could not be added to the playlist.")
                #     print("       You can add it manually in YouTube Studio.")

                mark_video_posted(
                    sheets=sheets,
                    spreadsheet_id=spreadsheet_id,
                    sheet_range=sheet_range,
                    row_number=video_row["_row_number"],
                    posted_col_idx=posted_col_idx,
                    video_id_col_idx=video_id_col_idx,
                    video_url=f"https://www.youtube.com/watch?v={video_id}",
                )
                print(f"✅ Sheet updated: row {video_row['_row_number']} marked as posted.")
            else:
                print("\n[ERROR] Upload failed — no video ID returned.")



        finally:
            for path in (video_path, thumbnail_path):
                if os.path.exists(path):
                    os.remove(path)


# ── Playlist ─────────────────────────────────────────────────────────────────

def add_to_playlist(youtube, video_id: str, playlist_id: str) -> bool:
    """
    Add an uploaded video to an existing playlist.

    Returns True on success, False on failure.
    The playlist_id is the part after 'list=' in a YouTube playlist URL.
    e.g. https://www.youtube.com/playlist?list=PLxxxxxxx  →  PLxxxxxxx
    """
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                }
            },
        ).execute()
        return True
    except HttpError as e:
        print(f"\n[ERROR] Could not add video to playlist: HTTP {e.resp.status}")
        print(f"        {e.content.decode()}")
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Upload a video to YouTube via the Data API v3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            [f"  {k}: {v}" for k, v in VALID_CATEGORIES.items()]
        ),
    )
    p.add_argument("file", help="Path to the video file to upload")
    p.add_argument("--title",       default="My Video",    help="Video title (default: 'My Video')")
    p.add_argument("--description", default="",            help="Video description")
    p.add_argument("--tags",        default="",            help="Comma-separated list of tags")
    p.add_argument("--category",    default="22",          help="Category ID (default: 22 — People & Blogs)")
    p.add_argument(
        "--privacy",
        default="private",
        choices=VALID_PRIVACY,
        help="Privacy setting (default: private)",
    )
    p.add_argument(
        "--playlist",
        default=None,
        metavar="PLAYLIST_ID",
        help=(
            "Playlist ID to add the video to after upload. "
            "Find it in the playlist URL: youtube.com/playlist?list=<PLAYLIST_ID>"
        ),
    )
    return p


def main():
    print("Starting")
    videos_to_upload = get_pending_rows(SPREADSHEET_ID, SHEET_NAME)
    print("Authenticating with YouTube…")
    upload_pending_videos(videos_to_upload)



def handler(event, context):
    """AWS Lambda entry point (placeholder)."""
    return {"statusCode": 200, "body": "yt-uploader placeholder"}


if __name__ == "__main__":
    # main()
    main()