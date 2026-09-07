# -*- coding: utf-8 -*-
"""HTTP service: Japanese text or audio -> viseme track JSON.

    pip install fastapi uvicorn python-multipart
    uvicorn server.app:app --reload --port 8000

    POST /lipsync        {"text": "こんにちは", "total": 1.4, "blink": true}
    POST /lipsync/audio  multipart file=<wav|mp3|...>
    GET  /health
"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pipeline"))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from jp_lipsync import build, blink_track

app = FastAPI(title="tanuki-lipsync")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOW_ORIGINS", "*").split(","),
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

class TextReq(BaseModel):
    text: str
    mora: float = 0.135
    total: Optional[float] = None   # fit the phrase to a known audio duration
    intensity: float = 1.0
    fps: int = 30
    blink: bool = True
    blink_seed: int = 0

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/lipsync")
def lipsync(req: TextReq):
    """Text path. Pass `total` set to the TTS clip's duration so the mouth
    finishes exactly when the audio does - mora timing is only an estimate."""
    if not req.text.strip():
        raise HTTPException(400, "text is empty")
    return build(req.text, mora_dur=req.mora, total=req.total,
                 intensity=req.intensity, fps=req.fps,
                 blink=req.blink, blink_seed=req.blink_seed)

@app.post("/lipsync/audio")
async def lipsync_audio(file: UploadFile = File(...), blink: bool = True):
    """Audio path, for when the script is not known. Vowels only: it cannot
    close the lips for /m/ /b/ /p/ the way the text path does."""
    from audio_lipsync import analyse, to_tracks
    suffix = os.path.splitext(file.filename or "")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(await file.read())
        tmp = f.name
    try:
        data = to_tracks(analyse(tmp))
    finally:
        os.unlink(tmp)
    if blink:
        data["tracks"]["Blink"] = blink_track(data["duration"])
        data["extras"] = ["Blink"]
    return data
