import os
import time

import httpx

_API = "https://api.assemblyai.com/v2"


def transcribe_audio(data: bytes, *, timeout_s: float = 90.0) -> str:
    key = os.environ.get("ASSEMBLYAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not set")
    headers = {"authorization": key}
    with httpx.Client(timeout=30.0) as client:
        up = client.post(f"{_API}/upload", headers=headers, content=data)
        up.raise_for_status()
        upload_url = up.json()["upload_url"]

        tr = client.post(
            f"{_API}/transcript",
            headers={**headers, "content-type": "application/json"},
            json={"audio_url": upload_url},
        )
        tr.raise_for_status()
        tid = tr.json()["id"]

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            poll = client.get(f"{_API}/transcript/{tid}", headers=headers)
            poll.raise_for_status()
            body = poll.json()
            status = body.get("status")
            if status == "completed":
                return (body.get("text") or "").strip()
            if status == "error":
                raise RuntimeError(body.get("error") or "AssemblyAI transcription failed")
            time.sleep(1.5)
    raise RuntimeError("AssemblyAI transcription timed out")
