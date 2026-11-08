"""Replicate audio models: song structure and audio description.

These are the only two capabilities that leave this machine. They call the same
pinned community models as the upstream fork, require REPLICATE_API_TOKEN, and
fail loudly without it. No new dependency: the file upload and prediction
polling use urllib. Model slugs are overridable via environment variables because
community model versions can disappear.
"""

import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

from .numbers import finite

DEFAULT_STRUCTURE_MODEL = (
    "jhurliman/allinone-targetbpm:f8657cff598c47c2c2dc2f5cdabfc26e25d099d62e9458119c16c716b0cfe259"
)
DEFAULT_DESCRIBE_MODEL = (
    "jhurliman/music-flamingo:0fa8fa07084102b5ebeeee377ea6311f32fc856f8f95fadbede43f69329acb47"
)
API = "https://api.replicate.com/v1"
MAX_BYTES = 512 * 1024 * 1024
SUPPORTED_SUFFIXES = (".wav", ".wave", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".aiff", ".aif")
POLL_SECONDS = 2.0


def api_token():
    value = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not value:
        raise ValueError(
            "Set REPLICATE_API_TOKEN to use the Replicate audio models; no other tool needs it"
        )
    return value


def _local_file(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Existing absolute local audio file required")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Unsupported audio suffix: " + path.suffix)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Audio file exceeds 512 MiB")
    return path


def _model(slug, env_name, default):
    chosen = os.environ.get(env_name, "").strip() or default
    if ":" not in chosen:
        raise ValueError("Model must be owner/name:version, got " + chosen)
    owner, version = chosen.rsplit(":", 1)
    return owner, version


def _request(url, token, payload=None, headers=None, method=None, timeout=120):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    merged = {"Authorization": "Bearer " + token}
    if payload is not None:
        merged["Content-Type"] = "application/json"
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, data=body, headers=merged, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:400]
        raise RuntimeError("Replicate HTTP %d: %s" % (error.code, detail)) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Replicate is unreachable: " + str(error.reason)) from error


def upload(path, token):
    """Upload the audio through Replicate's file API and return its URL."""
    path = _local_file(path)
    boundary = uuid.uuid4().hex
    head = (
        '--%s\r\nContent-Disposition: form-data; name="content"; filename="%s"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n" % (boundary, path.name)
    ).encode("utf-8")
    body = head + path.read_bytes() + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    request = urllib.request.Request(
        API + "/files",
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            "Replicate upload failed with HTTP %d: %s"
            % (error.code, error.read().decode("utf-8", "replace")[:400])
        ) from error
    urls = payload.get("urls") or {}
    url = urls.get("get") or payload.get("url")
    if not url:
        raise RuntimeError("Replicate upload returned no file URL")
    return url


def run_model(path, slug, payload, token, timeout_seconds=600):
    """Create one prediction, poll it and return the raw output."""
    owner, version = slug
    audio_url = upload(path, token)
    created = _request(
        API + "/predictions", token, {"version": version, "input": dict(payload, audio=audio_url)}
    )
    poll_url = (created.get("urls") or {}).get("get")
    if not poll_url:
        raise RuntimeError("Replicate returned no prediction URL")
    deadline = time.monotonic() + timeout_seconds
    status = created.get("status")
    while status not in ("succeeded", "failed", "canceled"):
        if time.monotonic() > deadline:
            raise RuntimeError("Replicate prediction timed out; check the job before retrying")
        time.sleep(POLL_SECONDS)
        created = _request(poll_url, token)
        status = created.get("status")
    if status != "succeeded":
        raise RuntimeError(
            "Replicate prediction %s: %s" % (status, created.get("error") or "no detail")
        )
    if not created.get("output"):
        raise RuntimeError("Replicate returned no output")
    result = {"output": created["output"], "model": owner, "version": version}
    result["metrics"] = created.get("metrics")
    return result


def _structure_payload(result):
    raw = result["output"]
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.endswith(".json"):
                with urllib.request.urlopen(item, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
        raise RuntimeError("Replicate returned URLs but no JSON result")
    if isinstance(raw, dict):
        return raw
    raise RuntimeError("Unexpected Replicate output type: " + type(raw).__name__)


def analyze_song_structure(path, target_bpm=None, include_beats=True, include_key=True):
    """BPM, key and labelled segments from the third-party all-in-one model."""
    slug = _model(None, "REPLICATE_STRUCTURE_MODEL", DEFAULT_STRUCTURE_MODEL)
    payload = {}
    if target_bpm is not None:
        bpm = finite(target_bpm, "target_bpm")
        if not 20 <= bpm <= 999:
            raise ValueError("target_bpm must be within 20..999")
        payload["target_bpm"] = bpm
    result = run_model(path, slug, payload, api_token())
    data = _structure_payload(result)
    if not isinstance(data, dict) or "bpm" not in data:
        raise RuntimeError("Model output did not contain bpm and segments")
    report = {
        "bpm": data.get("bpm"),
        "segments": data.get("segments", []),
        "provider": "replicate",
        "model": slug[0],
        "version": slug[1][:12],
        "note": "Third-party model output; verify every boundary and tempo before editing",
    }
    if include_beats:
        report["beats"] = data.get("beats", [])
        report["downbeats"] = data.get("downbeats", [])
    if include_key:
        report["key"] = data.get("key") or data.get("key_prediction")
    return report


def describe_audio(path, prompt, max_new_tokens=512):
    """Ask the third-party Music Flamingo model a question about an audio file."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt required")
    if isinstance(max_new_tokens, bool) or not isinstance(max_new_tokens, int):
        raise ValueError("max_new_tokens must be an integer")
    if not 1 <= max_new_tokens <= 4096:
        raise ValueError("max_new_tokens must be within 1..4096")
    slug = _model(None, "REPLICATE_DESCRIBE_MODEL", DEFAULT_DESCRIBE_MODEL)
    payload = {"prompt": prompt.strip(), "max_new_tokens": max_new_tokens, "temperature": 0.7}
    result = run_model(path, slug, payload, api_token())
    raw = result["output"]
    if isinstance(raw, list):
        text = "".join(str(part) for part in raw)
    else:
        text = str(raw)
    return {
        "description": text,
        "prompt": payload["prompt"],
        "provider": "replicate",
        "model": slug[0],
        "metrics": result.get("metrics"),
        "note": "Language-model description, not measurement: treat claims about key, tempo or structure as unverified",
    }
