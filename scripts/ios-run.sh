#!/bin/bash
# Build the app, boot a Simulator, install and launch it (`make ios-run`).
#
# Picks a usable iPhone Simulator rather than assuming one exists: the named
# device may not be installed on a teammate's machine, and a hard-coded UDID
# would break the moment Xcode updates.
#
#   scripts/ios-run.sh "<simulator name>" "<configuration>" "<derived data path>"

set -euo pipefail

PREFERRED_SIM="${1:-}"
CONFIG="${2:-Debug}"
DERIVED="${3:-ios/build}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PROJECT="ios/SpashtPaytm.xcodeproj"
SCHEME="SpashtPaytm"
BUNDLE_ID="$(
  sed -n -E 's/^[[:space:]]*PRODUCT_BUNDLE_IDENTIFIER[[:space:]]*=[[:space:]]*//p' \
    ios/Config/Secrets.xcconfig ios/Config/Base.xcconfig 2>/dev/null |
    head -n 1 | tr -d '[:space:]'
)"
BUNDLE_ID="${BUNDLE_ID:-com.finovators.spashtpaytm}"

# --- pick a simulator --------------------------------------------------------

# Shared with `make ios-build` / `make ios-test`, so all three run against the
# same device and there is one place that knows how to choose it.
UDID="$("$REPO_ROOT/scripts/ios-sim.sh" "$PREFERRED_SIM")"

SIM_NAME="$(xcrun simctl list devices --json |
  python3 -c "
import json, sys
udid = sys.argv[1]
for devices in json.load(sys.stdin)['devices'].values():
    for device in devices:
        if device['udid'] == udid:
            print(device['name'])
" "$UDID")"

echo "==> simulator: $SIM_NAME ($UDID)"

# --- build -------------------------------------------------------------------

echo "==> building $SCHEME ($CONFIG)"
set -o pipefail
xcodebuild build \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration "$CONFIG" \
  -destination "id=$UDID" \
  -derivedDataPath "$DERIVED" \
  -quiet \
  CODE_SIGNING_ALLOWED=NO

APP_PATH="$DERIVED/Build/Products/$CONFIG-iphonesimulator/SpashtPaytm.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Build succeeded but $APP_PATH is missing." >&2
  exit 1
fi

# --- boot, install, launch ---------------------------------------------------

echo "==> booting"
# Already-booted is not an error; we just want it running.
xcrun simctl boot "$UDID" 2>/dev/null || true
xcrun simctl bootstatus "$UDID" -b >/dev/null 2>&1 || true

# Bring up the Simulator window. Best effort only: the device boots headlessly
# above, so install, launch and screenshots all work without it, and Xcode has
# moved this app between releases. Never fail the run over a missing window.
open_simulator_ui() {
  local app
  app="$(xcode-select -p 2>/dev/null)/Applications/Simulator.app"
  if [[ -d "$app" ]]; then
    open -a "$app" --args -CurrentDeviceUDID "$UDID" && return 0
  fi
  open -a Simulator --args -CurrentDeviceUDID "$UDID" 2>/dev/null && return 0
  open -b com.apple.iphonesimulator 2>/dev/null && return 0
  return 1
}

if ! open_simulator_ui; then
  echo "    (could not open the Simulator window; the device is booted headlessly,"
  echo "     so install, launch and screenshots still work. Open Xcode > Open"
  echo "     Developer Tool > Simulator to watch it.)"
fi

echo "==> installing"
xcrun simctl install "$UDID" "$APP_PATH"

echo "==> launching $BUNDLE_ID"
xcrun simctl launch "$UDID" "$BUNDLE_ID" >/dev/null

echo
echo "==> running. Useful follow-ups:"
echo "    screenshot : xcrun simctl io $UDID screenshot docs/screens/home.png"
echo "    logs       : xcrun simctl spawn $UDID log stream --predicate 'process == \"SpashtPaytm\"'"
echo "    uninstall  : xcrun simctl uninstall $UDID $BUNDLE_ID"
