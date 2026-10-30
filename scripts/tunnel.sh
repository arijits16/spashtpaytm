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

    Two things to do in another terminal, in this order:

    1. backend/.env
           PUBLIC_BASE_URL=$URL
       Receipt QR codes are built from this, so a judge scanning one on their
       own phone reaches this host. Restart the backend afterwards.

    2. make ios-config
       Writes API_BASE_URL and PUBLIC_BASE_URL into ios/Config/Secrets.xcconfig
       from NGROK_DOMAIN, with the "//" escaped as "/\$()/" - an xcconfig
       treats "//" as a comment, and a hand-pasted URL silently truncates to
       "https:" with no error that names the cause. It also regenerates the
       Xcode project.

    Then rebuild in Xcode (or \`make ios-build\`) and install on the phone.

    Check it from the phone's browser before you trust it:  $URL/api/health

EOF

exec ngrok "${ARGS[@]}"
