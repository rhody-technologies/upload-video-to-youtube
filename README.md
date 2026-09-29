# upload-video-to-youtube

Internal tool that automates uploading videos to YouTube. It reads pending
rows from a Google Sheet (where the `Posted` column is `FALSE` and the
`Scheduled Posting Date` is today or earlier), downloads the video and
thumbnail from the linked Google Drive files, uploads the video to YouTube
via the Data API v3, sets the thumbnail, and marks the sheet row as posted
with the resulting video URL.

## Prerequisites

- Python 3.10+
- A Google Cloud project with the **YouTube Data API v3**, **Google Sheets
  API**, and **Google Drive API** enabled
- OAuth 2.0 credentials (Desktop app) for that project, downloaded as
  `client_secret.json` and placed in the project root

## Setup

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Place `client_secret.json` (downloaded from Google Cloud Console →
   APIs & Services → Credentials → OAuth 2.0 Client IDs) in the project
   root.

## Running

```bash
python main.py
```

On first run, a browser window will open twice to authorize the app — once
for YouTube (upload/manage access) and once for Sheets/Drive (read access) —
since each is authorized by a different Google account. Access/refresh
tokens are then cached in `token_youtube.json` and `token_sheets.json` so
future runs don't require re-authorizing.

The script will:
1. Fetch pending rows from the configured Google Sheet
2. Download each due video and thumbnail from Google Drive
3. Upload the video to YouTube and set its thumbnail
4. Mark the sheet row as posted with the video's watch URL

To deactivate the virtual environment when done:

```bash
deactivate
```
