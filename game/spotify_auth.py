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
PKCE_ALLOWED_CHARS = string.ascii_letters + string.digits + "-._~"


class SpotifyOAuthError(Exception):
    pass


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
        raise SpotifyOAuthError("Spotify token exchange failed.") from exc

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
        raise SpotifyOAuthError("Spotify profile lookup failed.") from exc

    payload = response.json()
    return {
        "id": payload.get("id"),
        "display_name": payload.get("display_name") or payload.get("email") or payload.get("id"),
        "email": payload.get("email"),
    }