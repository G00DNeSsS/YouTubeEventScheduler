import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

CLIENT_SECRETS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "client_secrets.json"
)


def credentials_to_dict(creds: Credentials) -> dict:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }


def credentials_from_dict(data: dict) -> Credentials:
    return Credentials(
        token=data["token"],
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data.get("scopes", SCOPES),
    )


def authorize_youtube() -> tuple[Credentials, str, str]:
    """
    Runs OAuth flow in browser. Returns (credentials, channel_name, channel_id).
    Raises FileNotFoundError if client_secrets.json is missing.
    """
    if not os.path.exists(CLIENT_SECRETS_PATH):
        raise FileNotFoundError(
            f"Файл client_secrets.json не найден в {CLIENT_SECRETS_PATH}\n"
            "Скачайте его из Google Cloud Console (OAuth 2.0 → Desktop App)."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    youtube = build("youtube", "v3", credentials=creds)
    channel_resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = channel_resp.get("items", [])
    if items:
        channel_name = items[0]["snippet"]["title"]
        channel_id = items[0]["id"]
    else:
        channel_name = "Unknown"
        channel_id = ""

    return creds, channel_name, channel_id


def get_youtube_service(credentials_json: str):
    """Build authenticated YouTube service from stored credentials JSON."""
    data = json.loads(credentials_json)
    creds = credentials_from_dict(data)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("youtube", "v3", credentials=creds), credentials_to_dict(creds)
