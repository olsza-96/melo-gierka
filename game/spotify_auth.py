import base64
import hashlib
import secrets
import string
import time
from urllib.parse import urlencode

import httpx
from django.conf import settings


SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_PROFILE_URL = "https://api.spotify.com/v1/me"
SPOTIFY_TRACK_URL = "https://api.spotify.com/v1/tracks/{track_id}"
SPOTIFY_AVAILABLE_DEVICES_URL = "https://api.spotify.com/v1/me/player/devices"
SPOTIFY_TRANSFER_PLAYBACK_URL = "https://api.spotify.com/v1/me/player"
SPOTIFY_START_PLAYBACK_URL = "https://api.spotify.com/v1/me/player/play"
PKCE_ALLOWED_CHARS = string.ascii_letters + string.digits + "-._~"


class SpotifyOAuthError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def _build_spotify_error(message: str, exc: httpx.HTTPError) -> SpotifyOAuthError:
    response = getattr(exc, "response", None)
    if response is None:
        return SpotifyOAuthError(message)

    try:
        response_body = response.json()
    except ValueError:
        response_body = response.text.strip()

    return SpotifyOAuthError(
        message,
        status_code=response.status_code,
        response_body=response_body,
    )


def generate_code_verifier(length: int = 64) -> str:
    if not 43 <= length <= 128:
        raise ValueError("PKCE code verifier length must be between 43 and 128")
    return "".join(secrets.choice(PKCE_ALLOWED_CHARS) for _ in range(length))


def generate_oauth_state(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorize_url(*, state: str, code_verifier: str, redirect_uri: str) -> str:
    params = {
        "client_id": settings.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": settings.SPOTIFY_SCOPE,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": build_code_challenge(code_verifier),
    }
    return f"{SPOTIFY_AUTHORIZE_URL}?{urlencode(params)}"


def normalize_token_payload(token_payload: dict) -> dict:
    if "access_token" not in token_payload or "expires_in" not in token_payload:
        raise SpotifyOAuthError("Spotify token response is missing required fields.")

    expires_in = int(token_payload["expires_in"])
    return {
        "access_token": token_payload["access_token"],
        "token_type": token_payload.get("token_type", "Bearer"),
        "scope": token_payload.get("scope", settings.SPOTIFY_SCOPE),
        "refresh_token": token_payload.get("refresh_token"),
        "expires_in": expires_in,
        "expires_at": int(time.time()) + expires_in,
    }


def exchange_code_for_token(*, code: str, code_verifier: str, redirect_uri: str) -> dict:
    try:
        response = httpx.post(
            SPOTIFY_TOKEN_URL,
            data={
                "client_id": settings.SPOTIFY_CLIENT_ID,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _build_spotify_error("Spotify token exchange failed.", exc) from exc

    return normalize_token_payload(response.json())


def refresh_access_token(*, refresh_token: str) -> dict:
    try:
        response = httpx.post(
            SPOTIFY_TOKEN_URL,
            data={
                "client_id": settings.SPOTIFY_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _build_spotify_error("Spotify token refresh failed.", exc) from exc

    return normalize_token_payload(response.json())


def fetch_user_profile(access_token: str) -> dict:
    try:
        response = httpx.get(
            SPOTIFY_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _build_spotify_error("Spotify profile lookup failed.", exc) from exc

    payload = response.json()
    return {
        "id": payload.get("id"),
        "display_name": payload.get("display_name") or payload.get("email") or payload.get("id"),
        "email": payload.get("email"),
        "product": payload.get("product"),
    }


def fetch_track_details(*, access_token: str, spotify_track_id: str) -> dict:
    try:
        response = httpx.get(
            SPOTIFY_TRACK_URL.format(track_id=spotify_track_id),
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _build_spotify_error("Spotify track lookup failed.", exc) from exc

    payload = response.json()
    return {
        "spotify_track_id": payload.get("id") or spotify_track_id,
        "is_playable": payload.get("is_playable"),
        "restriction_reason": (payload.get("restrictions") or {}).get("reason"),
    }


def fetch_available_devices(*, access_token: str) -> list[dict]:
    try:
        response = httpx.get(
            SPOTIFY_AVAILABLE_DEVICES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _build_spotify_error("Spotify available devices lookup failed.", exc) from exc

    payload = response.json()
    return payload.get("devices", [])


def start_playback(
    *,
    access_token: str,
    device_id: str,
    spotify_track_id: str,
    position_ms: int,
) -> None:
    try:
        response = httpx.put(
            SPOTIFY_START_PLAYBACK_URL,
            params={"device_id": device_id},
            json={
                "uris": [f"spotify:track:{spotify_track_id}"],
                "position_ms": position_ms,
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _build_spotify_error("Spotify playback start failed.", exc) from exc


def transfer_playback(*, access_token: str, device_id: str, play: bool = False) -> None:
    try:
        response = httpx.put(
            SPOTIFY_TRANSFER_PLAYBACK_URL,
            json={
                "device_ids": [device_id],
                "play": play,
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _build_spotify_error("Spotify playback transfer failed.", exc) from exc