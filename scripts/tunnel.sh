#!/bin/bash
# Expose the backend over HTTPS so a real iPhone can reach it (`make tunnel`).
#
# Only the backend (port 8000) is tunnelled. The website stays on localhost and
# is never exposed (build plan 13.4).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ENV="$REPO_ROOT/backend/.env"

if ! command -v ngrok >/dev/null 2>&1; then
  cat >&2 <<'EOF'
ngrok is not installed.

  1. brew install ngrok
  2. sign up at https://ngrok.com and copy your authtoken
  3. ngrok config add-authtoken <token>
  4. claim your free static domain in the ngrok dashboard
  5. put it in backend/.env as NGROK_DOMAIN=<your-domain>   (no scheme)

Then run `make tunnel` again.
EOF
  exit 1
fi

# Read NGROK_DOMAIN without sourcing the file (which would execute its contents).
DOMAIN=""
if [[ -f "$BACKEND_ENV" ]]; then
  DOMAIN="$(
    sed -n -E 's/^[[:space:]]*NGROK_DOMAIN=//p' "$BACKEND_ENV" |
      head -n 1 | sed -E 's/[[:space:]]*#.*$//' | tr -d '[:space:]'
  )"
fi

if [[ -n "$DOMAIN" ]]; then
  URL="https://$DOMAIN"
  ARGS=(http 8000 "--url=$URL")
else
  URL="https://<the URL ngrok prints below>"
  ARGS=(http 8000)
  echo "!   NGROK_DOMAIN is not set in backend/.env, so the URL changes every run."
  echo "!   Claim a free static domain in the ngrok dashboard to stop re-editing the config."
  echo
fi

cat <<EOF
==> tunnelling the backend (127.0.0.1:8000) over HTTPS
    The website is NOT tunnelled - it stays on http://localhost:5173.

    Once ngrok is up, set these and rebuild the app:

    ios/Config/Secrets.xcconfig
        API_BASE_URL    = ${URL/:\/\//:\/\$()\/}
        PUBLIC_BASE_URL = ${URL/:\/\//:\/\$()\/}
        (xcconfig treats "//" as a comment, hence the \$() in the middle)

    backend/.env
        PUBLIC_BASE_URL=$URL
        (receipt QR codes are built from this)

    Then: restart the backend, run \`make ios-gen\`, and rebuild in Xcode.

EOF

exec ngrok "${ARGS[@]}"
