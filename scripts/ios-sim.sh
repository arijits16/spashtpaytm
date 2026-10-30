#!/bin/bash
# Print the UDID of an iPhone Simulator to build and run against.
#
# Used by `make ios-build`, `make ios-test` and `make ios-run`. Resolving a
# concrete UDID beats passing `name=iPhone N Pro` to xcodebuild: a device name
# only exists on some runtimes (an "iPhone 17 Pro" is not in the iOS 27 runtime
# at all), and `OS:latest` then fails to match. A UDID is unambiguous.
#
#   scripts/ios-sim.sh ["preferred device name"]
#
# Prefers, in order:
#   1. the requested name, on the newest runtime that has it;
#   2. the newest iPhone on the newest runtime.
#
# Exits 1 with instructions when no iPhone Simulator is installed.

set -euo pipefail

PREFERRED="${1:-}"

UDID="$(
  xcrun simctl list devices available --json |
    PREFERRED="$PREFERRED" python3 -c '
import json, os, re, sys

preferred = os.environ.get("PREFERRED", "").strip()
data = json.load(sys.stdin)


def runtime_version(identifier: str) -> tuple[int, ...]:
    """Sort key from "com.apple.CoreSimulator.SimRuntime.iOS-26-5" -> (26, 5)."""
    match = re.search(r"iOS-([0-9-]+)$", identifier)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("-"))


candidates = []
for runtime, devices in data["devices"].items():
    if "iOS" not in runtime:
        continue
    version = runtime_version(runtime)
    for device in devices:
        if device.get("isAvailable") and device["name"].startswith("iPhone"):
            candidates.append((version, device["name"], device["udid"]))

if not candidates:
    raise SystemExit

# Newest runtime first.
candidates.sort(key=lambda item: item[0], reverse=True)

if preferred:
    for _, name, udid in candidates:
        if name == preferred:
            print(udid)
            raise SystemExit

print(candidates[0][2])
'
)"

if [[ -z "$UDID" ]]; then
  cat >&2 <<'EOF'
No iPhone Simulator is available.

Install one: Xcode > Settings > Components (or Platforms) > iOS Simulator,
then run `xcrun simctl list devices available` to confirm.
EOF
  exit 1
fi

echo "$UDID"
