#!/usr/bin/env python
"""Sarvam connectivity smoke test - three tiny calls, no app changes.

Run with `make sarvam-smoke` (or `npm run sarvam-smoke`). It proves the key and
the three endpoints Spasht depends on actually work from this machine, before
phases 6-7 build on them:

  1. TTS  POST /text-to-speech       bulbul:v4-flash  -> mp3 on disk
  2. STT  POST /speech-to-text       saaras:v4        -> transcript of that mp3
  3. LLM  POST /v1/chat/completions  sarvam-105b-conversations

Field names were checked against docs.sarvam.ai (build plan section 10 requires
this, because the API evolves).

The API key is read from `app.config.settings` and is NEVER printed. Error
bodies are scrubbed before display in case the API echoes the key back.
"""

from __future__ import annotations

import asyncio
import base64
import sys
import time
from dataclasses import dataclass

import httpx

from app.config import BACKEND_DIR, settings

# --- what we send -------------------------------------------------------------

OUT_DIR = BACKEND_DIR / ".cache" / "smoke"
OUT_FILE = OUT_DIR / "hello_mr.mp3"

TTS_TEXT = "नमस्कार! मी स्पष्ट."
TTS_SPEAKER = "ishita_mr_conversational"
TTS_LANGUAGE = "mr-IN"
TTS_SAMPLE_RATE = 24000

# One short Marathi sentence, so the reply stays cheap and easy to eyeball.
CHAT_SYSTEM = "तुम्ही स्पष्ट आहात, एक मदतनीस. फक्त मराठीत, एकाच छोट्या वाक्यात उत्तर द्या."
CHAT_USER = "कर्जाचा EMI म्हणजे काय, एका वाक्यात सांगा."

TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)


@dataclass
class Step:
    """Outcome of one call, for the summary table."""

    name: str
    ok: bool
    status: int | None
    ms: float
    detail: str


def scrub(text: str) -> str:
    """Remove the API key from any text before it is printed."""
    key = settings.sarvam_api_key
    return text.replace(key, "[REDACTED]") if key else text


def short(text: str, limit: int = 300) -> str:
    """Trim a long body so the console stays readable."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def fail_detail(response: httpx.Response) -> str:
    """HTTP status plus the server's message, with the key scrubbed out."""
    try:
        body = response.json()
        message = body.get("error", {}).get("message") if isinstance(body, dict) else None
        text = str(message) if message else response.text
    except ValueError:
        text = response.text
    return f"HTTP {response.status_code}: {scrub(short(text))}"


async def post_with_retry(
    client: httpx.AsyncClient, url: str, *, label: str, **kwargs: object
) -> tuple[httpx.Response | None, float, str | None]:
    """POST once, retrying a single time on 429/5xx or a transport error.

    @returns (response, elapsed_ms, error). `response` is None only when both
             attempts raised at the transport layer.
    """
    last_error: str | None = None

    for attempt in (1, 2):
        started = time.perf_counter()
        try:
            response = await client.post(url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            elapsed = (time.perf_counter() - started) * 1000
            last_error = f"{type(exc).__name__}: {scrub(str(exc))}"
            if attempt == 1:
                print(f"   ! {label} transport error, retrying once — {last_error}")
                await asyncio.sleep(1.0)
                continue
            return None, elapsed, last_error

        elapsed = (time.perf_counter() - started) * 1000

        retryable = response.status_code == 429 or response.status_code >= 500
        if retryable and attempt == 1:
            print(f"   ! {label} {fail_detail(response)} — retrying once")
            await asyncio.sleep(1.0)
            continue

        return response, elapsed, None

    return None, 0.0, last_error


# --- the three calls ----------------------------------------------------------


async def run_tts(client: httpx.AsyncClient) -> Step:
    """Synthesise one Marathi line and write it to disk as mp3."""
    print("1/3  TTS  POST /text-to-speech")

    response, ms, error = await post_with_retry(
        client,
        "/text-to-speech",
        label="TTS",
        json={
            "text": TTS_TEXT,
            "language_code": TTS_LANGUAGE,
            "speaker": TTS_SPEAKER,
            "model": settings.sarvam_tts_model,
            "pace": 1.0,
            "speech_sample_rate": TTS_SAMPLE_RATE,
            "output_audio_codec": "mp3",
        },
    )

    if response is None:
        return Step("TTS", False, None, ms, error or "transport error")
    if response.status_code != 200:
        return Step("TTS", False, response.status_code, ms, fail_detail(response))

    audios = response.json().get("audios") or []
    if not audios:
        return Step("TTS", False, response.status_code, ms, "response carried no audio")

    audio = base64.b64decode(audios[0])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_bytes(audio)

    # ID3 tag or an MPEG frame header both mean "this really is mp3".
    looks_mp3 = audio[:3] == b"ID3" or audio[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    kind = "mp3" if looks_mp3 else f"unexpected header {audio[:4]!r}"

    print(f"     status 200 · {len(audio):,} bytes · {kind}")
    print(f"     saved to {OUT_FILE}")
    return Step("TTS", True, 200, ms, f"{len(audio):,} bytes {kind}")


async def run_stt(client: httpx.AsyncClient) -> Step:
    """Transcribe the file TTS just produced, with language auto-detection."""
    print("2/3  STT  POST /speech-to-text")

    if not OUT_FILE.is_file():
        return Step("STT", False, None, 0.0, "skipped: TTS produced no file")

    response, ms, error = await post_with_retry(
        client,
        "/speech-to-text",
        label="STT",
        files={"file": (OUT_FILE.name, OUT_FILE.read_bytes(), "audio/mpeg")},
        # "unknown" asks Saaras to auto-detect, which is what a real voice turn
        # does when the journey language is not yet established.
        data={"model": settings.sarvam_stt_model, "language_code": "unknown"},
    )

    if response is None:
        return Step("STT", False, None, ms, error or "transport error")
    if response.status_code != 200:
        return Step("STT", False, response.status_code, ms, fail_detail(response))

    body = response.json()
    transcript = body.get("transcript", "")
    language = body.get("language_code")
    probability = body.get("language_probability")

    print(f"     status 200 · transcript: {transcript!r}")
    print(f"     language_code: {language} · language_probability: {probability}")
    return Step("STT", True, 200, ms, f"{transcript!r} [{language} {probability}]")


async def run_chat(client: httpx.AsyncClient) -> Step:
    """Ask for one short Marathi sentence with reasoning switched off."""
    print("3/3  LLM  POST /v1/chat/completions")

    response, ms, error = await post_with_retry(
        client,
        "/v1/chat/completions",
        label="LLM",
        json={
            "model": settings.sarvam_llm_live_model,
            "messages": [
                {"role": "system", "content": CHAT_SYSTEM},
                {"role": "user", "content": CHAT_USER},
            ],
            "temperature": 0.2,
            "max_tokens": 300,
            # Explicit null disables reasoning. Live turns need latency, not
            # depth (build plan 10.3 / 10.4).
            "reasoning_effort": None,
        },
    )

    if response is None:
        return Step("LLM", False, None, ms, error or "transport error")
    if response.status_code != 200:
        return Step("LLM", False, response.status_code, ms, fail_detail(response))

    body = response.json()
    choices = body.get("choices") or []
    reply = (choices[0].get("message", {}).get("content") or "").strip() if choices else ""
    usage = body.get("usage") or {}

    print(f"     status 200 · reply: {reply!r}")
    print(
        "     tokens — prompt: {p} · completion: {c} · total: {t} · reasoning: {r}".format(
            p=usage.get("prompt_tokens"),
            c=usage.get("completion_tokens"),
            t=usage.get("total_tokens"),
            r=usage.get("reasoning_tokens", 0),
        )
    )
    return Step("LLM", True, 200, ms, f"{short(reply, 60)!r} ({usage.get('total_tokens')} tok)")


# --- driver -------------------------------------------------------------------


async def main() -> int:
    if not settings.sarvam_api_key:
        print("SARVAM_API_KEY is empty in backend/.env — nothing to smoke test.")
        return 2

    print(f"Sarvam smoke test · {settings.sarvam_base_url}")
    print(f"  key    : set ({len(settings.sarvam_api_key)} chars, never printed)")
    print(
        f"  models : {settings.sarvam_tts_model} · {settings.sarvam_stt_model} · "
        f"{settings.sarvam_llm_live_model}"
    )
    print()

    headers = {
        # TTS and STT accept only this header; chat accepts it too, so one set
        # of headers works for all three calls.
        "api-subscription-key": settings.sarvam_api_key,
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(
        base_url=settings.sarvam_base_url, headers=headers, timeout=TIMEOUT
    ) as client:
        steps = [await run_tts(client), await run_stt(client), await run_chat(client)]

    print()
    print("  step  status  latency     result")
    print("  " + "-" * 62)
    for step in steps:
        mark = "ok  " if step.ok else "FAIL"
        status = str(step.status) if step.status is not None else "---"
        print(f"  {step.name:<4}  {mark} {status:>4}  {step.ms:>7.0f} ms  {short(step.detail, 48)}")

    failed = [s for s in steps if not s.ok]
    print()
    if failed:
        print(f"{len(failed)} of {len(steps)} calls failed:")
        for step in failed:
            print(f"  - {step.name}: {step.detail}")
        return 1

    print(f"All 3 calls succeeded. Audio: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
