#!/usr/bin/env python
"""Generate the local secrets into `backend/.env` (build plan sections 13.3, 14.1).

Run with `make keys`. Three rules, all of them deliberate:

1. **Never overwrite.** A value that is already set is left alone, so running
   this twice cannot invalidate yesterday's receipts or log you out of a demo.
2. **Never print a secret.** The output says which names were filled, never what
   they were filled with - the terminal is often on a projector.
3. **Never touch git.** `backend/.env` is gitignored; this script refuses to
   write anywhere else.

The Ed25519 signing keypair belongs to the trust layer and is generated in
phase 6, when PyNaCl is added; this script reports that rather than pretending.
"""

from __future__ import annotations

import argparse
import base64
import secrets
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"
ENV_EXAMPLE_PATH = BACKEND_DIR / ".env.example"


def _random_urlsafe(length: int = 48) -> str:
    """A URL-safe random string. Used for peppers and the demo key."""
    return secrets.token_urlsafe(length)


def _random_base64_key(num_bytes: int = 32) -> str:
    """Base64 of `num_bytes` random bytes - the AES-256-GCM transcript key."""
    return base64.b64encode(secrets.token_bytes(num_bytes)).decode("ascii")


# name -> (generator, what it is for). Order is the order they get written.
GENERATED: dict[str, tuple[object, str]] = {
    "TRANSCRIPT_KEY": (_random_base64_key, "AES-256-GCM key for conversation transcripts"),
    "CUSTOMER_REF_PEPPER": (_random_urlsafe, "HMAC pepper for receipt customer_ref"),
    "OTP_PEPPER": (_random_urlsafe, "HMAC pepper for OTP code hashes"),
    "TTS_CACHE_SECRET": (_random_urlsafe, "HMAC secret for TTS cache keys"),
    "DEMO_AUTH_KEY": (_random_urlsafe, "shared secret for the dev demo login"),
}


def read_env(path: Path) -> list[str]:
    """The .env file as lines, or the example as a starting point."""
    if path.is_file():
        return path.read_text(encoding="utf-8").splitlines()
    if ENV_EXAMPLE_PATH.is_file():
        print(f"==> {path.name} does not exist; starting from .env.example")
        return ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    return []


def current_value(lines: list[str], name: str) -> str | None:
    """The value assigned to `name`, or None when the key is absent.

    Returns an empty string for `NAME=`, which is what "needs generating" looks
    like. An inline `# comment` after the value is stripped, matching how
    pydantic-settings reads the file.
    """
    prefix = f"{name}="
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix) :]
            return value.split("#", 1)[0].strip()
    return None


def set_value(lines: list[str], name: str, value: str) -> list[str]:
    """Assign `name`, preserving any trailing comment, appending if absent."""
    prefix = f"{name}="
    for index, line in enumerate(lines):
        if line.strip().startswith(prefix):
            comment = ""
            if "#" in line:
                comment = "   " + line[line.index("#") :].rstrip()
            lines[index] = f"{name}={value}{comment}"
            return lines
    return [*lines, f"{name}={value}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-names",
        action="store_true",
        help="list the secrets this script manages and exit (no values, no writes)",
    )
    args = parser.parse_args()

    if args.print_names:
        for name, (_, purpose) in GENERATED.items():
            print(f"  {name:22} {purpose}")
        return 0

    lines = read_env(ENV_PATH)

    filled: list[str] = []
    kept: list[str] = []

    for name, (generator, _purpose) in GENERATED.items():
        existing = current_value(lines, name)
        if existing:
            kept.append(name)
            continue
        # Absent or empty: generate. `generator` is one of the two helpers above.
        lines = set_value(lines, name, generator())  # type: ignore[operator]
        filled.append(name)

    if filled:
        # 0600: the file now holds real secrets, so no other account may read it.
        ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        ENV_PATH.chmod(0o600)

    print(f"==> {ENV_PATH.relative_to(BACKEND_DIR.parent)}")
    if filled:
        print(f"    generated: {', '.join(filled)}")
    if kept:
        print(f"    unchanged: {', '.join(kept)}  (already set)")
    if not filled:
        print("    nothing to do - every secret already has a value")

    print("    values are never printed; read them from backend/.env if you must")
    print("==> Ed25519 receipt signing keypair: generated in phase 6 (needs PyNaCl)")

    if filled:
        print("\n    Restart the backend so it picks up the new values.")
        if "DEMO_AUTH_KEY" in filled:
            print("    DEMO_AUTH_KEY changed: run `make ios-config` and rebuild the app,")
            print("    and copy it into frontend/.env as VITE_DEMO_AUTH_KEY for the website.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
