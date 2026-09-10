# api.py
"""
FasalVachak — LiveKit token HTTP endpoint.

Provides:
    POST /connect  →  generates a LiveKit room, mints a short-lived JWT,
                      and returns connection details.
    GET  /health   →  simple liveness check.

Agent dispatch note:
    server.py registers its worker via WorkerOptions(entrypoint_fnc=entrypoint)
    with no explicit agent_name, which means it uses LiveKit's AUTOMATIC
    DISPATCH — the worker is spawned into every new room on its own. This
    endpoint therefore does NOT issue an explicit agent-dispatch request;
    doing so alongside automatic dispatch would spawn two agent jobs into
    the same room (one via auto-dispatch, one via the explicit call),
    causing duplicate STT streams and the "agent can't hear me" symptom.

    If you later switch server.py to explicit dispatch (by setting
    agent_name="fasalvachak" in WorkerOptions), reintroduce a matching
    explicit dispatch call here with the same agent_name — but never both
    automatic and explicit dispatch for the same worker.

Environment variables (same names used by server.py):
    LIVEKIT_URL        wss://your-project.livekit.cloud
    LIVEKIT_API_KEY    LiveKit API key
    LIVEKIT_API_SECRET LiveKit API secret
    PORT               TCP port to listen on (set automatically by Railway)
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load .env when running locally; Railway supplies real env vars at runtime.
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from livekit.api import (
    AccessToken,
    VideoGrants,
)

# ── Configuration (validated at startup) ────────────────────────────────────

LIVEKIT_URL: str = os.environ.get("LIVEKIT_URL", "")
LIVEKIT_API_KEY: str = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET: str = os.environ.get("LIVEKIT_API_SECRET", "")

# Token TTL: 10 minutes — short-lived so a stale URL can't be reused.
_TOKEN_TTL: timedelta = timedelta(seconds=600)


def _check_env() -> None:
    """Fail fast if required secrets are missing."""
    missing = [
        name
        for name, val in [
            ("LIVEKIT_URL", LIVEKIT_URL),
            ("LIVEKIT_API_KEY", LIVEKIT_API_KEY),
            ("LIVEKIT_API_SECRET", LIVEKIT_API_SECRET),
        ]
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )


# ── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    _check_env()
    yield


app = FastAPI(
    title="FasalVachak API",
    description="Token endpoint for the FasalVachak LiveKit voice agent.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Static files ─────────────────────────────────────────────────────────────
# Serve anything under static/ at /static/<filename>.
# The root route GET / is handled separately by the explicit route below.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ── CORS ─────────────────────────────────────────────────────────────────────
# Allow all origins during development. In production, replace "*" with
# the actual Railway frontend domain (e.g. "https://your-frontend.up.railway.app").
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _generate_room_name() -> str:
    """Return a short, unique room name for each call."""
    return f"fasalvachak-{uuid.uuid4().hex[:8]}"


def _mint_token(room_name: str, participant_identity: str) -> str:
    """
    Create a short-lived LiveKit JWT for a farmer/browser participant.

    Grants:
        roomJoin       — allowed to join the room
        canPublish     — can publish tracks (audio only via canPublishSources)
        canSubscribe   — can receive agent audio
        canPublishData — can send data messages (harmless, kept True by default)

    canPublishSources is set to ["microphone"] so the browser participant is
    effectively limited to audio; no video track grants are issued.
    """
    token = (
        AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
        .with_identity(participant_identity)
        .with_name(participant_identity)
        .with_ttl(_TOKEN_TTL)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                # Restrict published media to microphone (audio) only.
                can_publish_sources=["microphone"],
            )
        )
    )
    return token.to_jwt()


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", summary="Serve the FasalVachak frontend", include_in_schema=False)
async def index() -> FileResponse:
    """
    Return the static HTML/JS client.
    The browser calls POST /connect from this page, so they share the same
    origin and no CORS configuration is needed.
    """
    html_path = _STATIC_DIR / "index.html"
    if not html_path.exists():
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=404, detail="Frontend not found. Run from the project root.")
    return FileResponse(str(html_path), media_type="text/html")


@app.get("/health", summary="Liveness check")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/connect", summary="Obtain a LiveKit token and join a new room")
async def connect() -> dict:
    """
    Generate a unique room and mint a farmer JWT, returning the connection
    details needed by the browser client.

    The voice-agent worker (server.py) uses LiveKit's automatic dispatch,
    so it joins the room on its own once the farmer connects — no explicit
    dispatch call is made here (see module docstring for why).

    Returns:
        {
            "token": "<LiveKit JWT>",
            "url":   "<LiveKit WebSocket URL>",
            "room":  "<unique room name>"
        }
    """
    room_name = _generate_room_name()
    # Use a short stable identity for the browser participant.
    participant_identity = f"farmer-{uuid.uuid4().hex[:6]}"

    try:
        token = _mint_token(room_name, participant_identity)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Token generation failed: {exc}")

    return {
        "token": token,
        "url": LIVEKIT_URL,
        "room": room_name,
    }


# ── Entry point (local dev + Railway) ────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)