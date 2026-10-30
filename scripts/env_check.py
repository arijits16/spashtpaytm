"""Compare a `.env` with its `.env.example` (`make env-check`).

A `.env` created three phases ago is missing the keys three phases of work have
added since, and the symptom is never "a key is missing". It is a receipt QR
pointing at localhost on demo day, or a tunnel with no static domain, or the
rescue agent using a contact window nobody set.

This prints what is missing, what is empty, and what is set - **never a value**
(build plan §13.3). It never edits anything: a `.env` is the human's, and a
script that silently rewrote it would be the worse surprise.

    python scripts/env_check.py
    python scripts/env_check.py --fix     # append the missing keys, commented
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PAIRS = (
    (REPO_ROOT / "backend" / ".env", REPO_ROOT / "backend" / ".env.example"),
    (REPO_ROOT / "frontend" / ".env", REPO_ROOT / "frontend" / ".env.example"),
)

# Keys the demo cannot be run without, as opposed to ones with a usable default.
# Named here rather than inferred, because "has a default" is a judgement about
# the product and not something a parser can see.
DEMO_CRITICAL = {
    "SARVAM_API_KEY": "speech, the LLM and KFS extraction (without it: demo mode)",
    "PUBLIC_BASE_URL": "receipt QR codes - a judge scanning one reaches this host",
    "NGROK_DOMAIN": "a static tunnel domain, so the phone needs no rebuild",
    "DEMO_AUTH_KEY": "the dev-only demo session on the phone and the website",
    "DASHBOARD_ADMIN_EMAILS": "who may open /dashboard",
    "TTS_CACHE_SECRET": "the audio cache keys",
    "OTP_PEPPER": "hashing the OTP",
    "TRANSCRIPT_KEY": "AES-256-GCM transcript encryption",
}


def parse(path: Path) -> dict[str, str]:
    """Read `KEY=value` lines. Comments and blanks are ignored."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Strip a trailing comment, which `.env.example` uses to document keys.
        values[key.strip()] = value.split("#", 1)[0].strip()
    return values


def check(env_path: Path, example_path: Path, fix: bool) -> int:
    """Report on one pair. Returns the number of problems found."""
    label = env_path.relative_to(REPO_ROOT)
    print(f"==> {label}")

    if not example_path.is_file():
        print(f"    ! no {example_path.name} to compare against")
        return 1

    if not env_path.is_file():
        print(f"    ! missing. Run `make setup`, or copy {example_path.name}.")
        return 1

    expected = parse(example_path)
    actual = parse(env_path)

    missing = [key for key in expected if key not in actual]
    empty = [key for key, value in actual.items() if not value and expected.get(key)]
    extra = [key for key in actual if key not in expected]

    problems = 0

    for key in missing:
        note = DEMO_CRITICAL.get(key)
        print(f"    ! MISSING  {key}" + (f"  - {note}" if note else ""))
        problems += 1

    for key in empty:
        note = DEMO_CRITICAL.get(key)
        print(f"    ! EMPTY    {key}" + (f"  - {note}" if note else ""))
        problems += 1

    if extra:
        # Not a problem: a local override is legitimate. Worth seeing, though,
        # because a typo'd key looks exactly like one.
        print(f"    i extra keys not in the example: {', '.join(sorted(extra))}")

    if fix and missing:
        with env_path.open("a", encoding="utf-8") as handle:
            handle.write("\n# --- appended by `make env-check --fix` ---\n")
            for key in missing:
                # Written commented out, with the example's own default as a
                # hint: appending a live value would change behaviour silently.
                handle.write(f"# {key}={expected[key]}\n")
        print(f"    + appended {len(missing)} key(s), commented out, for you to fill in")

    if problems == 0:
        print(f"    all {len(expected)} key(s) present and non-empty")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="append missing keys (commented out) rather than only reporting them",
    )
    args = parser.parse_args()

    problems = sum(check(env_path, example, args.fix) for env_path, example in PAIRS)

    print()
    if problems:
        print(f"==> {problems} problem(s). Nothing was read out loud; fill them in by hand.")
        print("    `make keys` generates the cryptographic ones.")
    else:
        print("==> every .env matches its example")

    # Deliberately 0 either way: this is a pre-flight report, and a non-zero
    # exit would break `make demo-reset` for a key with a usable default.
    return 0


if __name__ == "__main__":
    sys.exit(main())
