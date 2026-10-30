#!/bin/bash
# Wire the local machine's configuration into ios/Config/Secrets.xcconfig.
#
# Run with `make ios-config`. It does four things, all idempotent:
#
#   1. creates Secrets.xcconfig from the example if it is missing;
#   2. derives API_BASE_URL and PUBLIC_BASE_URL from backend/.env;
#   3. copies DEMO_AUTH_KEY across from backend/.env;
#   4. copies REVERSED_CLIENT_ID out of GoogleService-Info.plist.
#
# Step 2 exists because it is the step that breaks on demo day. An xcconfig
# treats "//" as a comment, so a hand-pasted "https://x.ngrok-free.app"
# silently becomes "https:" and the app then cannot reach anything, with no
# error that names the cause. This writes the "https:/$()/host" form for you.
#
# It NEVER prints a secret value - only which names were set (build plan 13.3).
# Secrets.xcconfig is gitignored.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_DIR="$REPO_ROOT/ios/Config"
SECRETS="$CONFIG_DIR/Secrets.xcconfig"
EXAMPLE="$CONFIG_DIR/Secrets.example.xcconfig"
BACKEND_ENV="$REPO_ROOT/backend/.env"
PLIST="$REPO_ROOT/ios/SpashtPaytm/Config/GoogleService-Info.plist"
PLIST_BUDDY=/usr/libexec/PlistBuddy

warnings=0

note() { printf '    %s\n' "$1"; }
warn() {
  printf '    ! %s\n' "$1" >&2
  warnings=$((warnings + 1))
}

# --- 1. make sure Secrets.xcconfig exists -----------------------------------

echo "==> ios/Config/Secrets.xcconfig"
if [[ ! -f "$SECRETS" ]]; then
  cp "$EXAMPLE" "$SECRETS"
  note "created from Secrets.example.xcconfig"
else
  note "already present, updating in place"
fi
chmod 600 "$SECRETS"

# Set `KEY = value` in the xcconfig, replacing any existing assignment.
# Values are written verbatim; callers must pre-escape "//" in URLs.
set_key() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp)"
  # Drop any existing assignment (allowing spaces around "="), keep everything else.
  grep -Ev "^[[:space:]]*${key}[[:space:]]*=" "$SECRETS" >"$tmp" || true
  printf '%s = %s\n' "$key" "$value" >>"$tmp"
  mv "$tmp" "$SECRETS"
  chmod 600 "$SECRETS"
}

# Read `KEY=value` out of a dotenv file without sourcing it (which would
# execute whatever is in there).
read_env() {
  local key="$1"
  [[ -f "$BACKEND_ENV" ]] || return 0
  sed -n -E "s/^[[:space:]]*${key}=//p" "$BACKEND_ENV" |
    head -n 1 |
    sed -E 's/[[:space:]]*#.*$//' |
    sed -E 's/^[[:space:]]+|[[:space:]]+$//g'
}

# --- 2. the backend URL ------------------------------------------------------
#
# Precedence: NGROK_DOMAIN (the phone demo) beats PUBLIC_BASE_URL (which may
# still say localhost), and localhost is the fallback for the Simulator.

echo "==> backend URL"

# Break the "//" of a URL with an empty variable reference, which is the only
# way to write one in an xcconfig. Done with sed rather than bash's own
# substitution, where escaping a slash in the *replacement* leaves the
# backslash in the output - which is how this was wrong the first time.
escape_url() {
  printf '%s\n' "$1" | sed -e 's|://|:/$()/|'
}

NGROK_DOMAIN="$(read_env NGROK_DOMAIN)"
ENV_PUBLIC_URL="$(read_env PUBLIC_BASE_URL)"

if [[ -n "$NGROK_DOMAIN" ]]; then
  # Tolerate a domain pasted with a scheme, which is the common slip.
  NGROK_DOMAIN="${NGROK_DOMAIN#https://}"
  NGROK_DOMAIN="${NGROK_DOMAIN#http://}"
  NGROK_DOMAIN="${NGROK_DOMAIN%/}"
  BACKEND_URL="https://$NGROK_DOMAIN"
  SOURCE="NGROK_DOMAIN"
elif [[ -n "$ENV_PUBLIC_URL" ]]; then
  BACKEND_URL="${ENV_PUBLIC_URL%/}"
  SOURCE="PUBLIC_BASE_URL"
else
  BACKEND_URL="http://localhost:8000"
  SOURCE="the default"
fi

set_key "API_BASE_URL" "$(escape_url "$BACKEND_URL")"
set_key "PUBLIC_BASE_URL" "$(escape_url "$BACKEND_URL")"
note "API_BASE_URL and PUBLIC_BASE_URL set to $BACKEND_URL (from $SOURCE)"

if [[ "$BACKEND_URL" == http://localhost* ]]; then
  warn "localhost works in the Simulator but not on a real iPhone."
  warn "Set NGROK_DOMAIN in backend/.env, run 'make tunnel', then 'make ios-config'."
fi

if [[ -n "$NGROK_DOMAIN" && "$ENV_PUBLIC_URL" != "$BACKEND_URL" ]]; then
  warn "backend/.env has PUBLIC_BASE_URL=${ENV_PUBLIC_URL:-<unset>}"
  warn "Receipt QR codes are built from that, so a judge scanning one would"
  warn "reach the wrong host. Set PUBLIC_BASE_URL=$BACKEND_URL and restart the backend."
fi

# --- 3. demo key from backend/.env ------------------------------------------

echo "==> demo auth key"
if [[ ! -f "$BACKEND_ENV" ]]; then
  warn "backend/.env not found. Run 'make setup' then 'make keys'."
else
  DEMO_KEY="$(read_env DEMO_AUTH_KEY)"
  if [[ -z "$DEMO_KEY" ]]; then
    warn "DEMO_AUTH_KEY is empty in backend/.env. Run 'make keys'."
    warn "Until then the demo login button stays hidden."
  else
    set_key "DEMO_AUTH_KEY" "$DEMO_KEY"
    note "DEMO_AUTH_KEY copied from backend/.env (value not shown)"
  fi
fi

# --- 4. Google sign-in config from the plist --------------------------------

echo "==> GoogleService-Info.plist"
if [[ ! -f "$PLIST" ]]; then
  warn "not found at ios/SpashtPaytm/Config/GoogleService-Info.plist"
  warn "Google sign-in stays off until you add it (see Appendix D.2)."
  warn "Demo login still works, so the app is usable without it."
else
  REVERSED="$("$PLIST_BUDDY" -c 'Print :REVERSED_CLIENT_ID' "$PLIST" 2>/dev/null || true)"
  CLIENT_ID="$("$PLIST_BUDDY" -c 'Print :CLIENT_ID' "$PLIST" 2>/dev/null || true)"
  PLIST_BUNDLE="$("$PLIST_BUDDY" -c 'Print :BUNDLE_ID' "$PLIST" 2>/dev/null || true)"

  if [[ -z "$CLIENT_ID" ]]; then
    warn "CLIENT_ID is missing from the plist."
    warn "Enable Authentication > Sign-in method > Google in Firebase, then re-download it."
  fi

  if [[ -z "$REVERSED" ]]; then
    warn "REVERSED_CLIENT_ID is missing from the plist; the sign-in callback will not work."
  else
    set_key "GOOGLE_REVERSED_CLIENT_ID" "$REVERSED"
    note "GOOGLE_REVERSED_CLIENT_ID written"
  fi

  # The Firebase iOS app and the Xcode target must agree, or sign-in fails with
  # an error that does not name the real cause.
  CONFIGURED_BUNDLE="$(
    grep -E '^[[:space:]]*PRODUCT_BUNDLE_IDENTIFIER[[:space:]]*=' "$SECRETS" |
      head -n 1 | sed -E 's/^[^=]*=[[:space:]]*//' | tr -d '[:space:]'
  )"
  CONFIGURED_BUNDLE="${CONFIGURED_BUNDLE:-com.finovators.spashtpaytm}"

  if [[ -n "$PLIST_BUNDLE" && "$PLIST_BUNDLE" != "$CONFIGURED_BUNDLE" ]]; then
    warn "bundle ID mismatch:"
    warn "  plist:  $PLIST_BUNDLE"
    warn "  xcode:  $CONFIGURED_BUNDLE"
    warn "Make them match in Firebase and in ios/Config/Secrets.xcconfig."
  else
    note "bundle ID matches ($CONFIGURED_BUNDLE)"
  fi
fi

# --- 5. regenerate the project ----------------------------------------------

echo "==> regenerating the Xcode project"
if command -v xcodegen >/dev/null 2>&1; then
  (cd "$REPO_ROOT/ios" && xcodegen generate --quiet)
  note "SpashtPaytm.xcodeproj regenerated"
else
  warn "xcodegen not installed. Run: brew install xcodegen"
fi

echo
if [[ "$warnings" -gt 0 ]]; then
  echo "==> done with $warnings warning(s) above. The app still builds and runs."
else
  echo "==> done. Everything is configured."
fi
