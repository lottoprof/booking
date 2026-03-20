#!/usr/bin/env bash
set -e

# ===== Load env =====
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
set -a
source "$PROJECT_DIR/.env"
set +a

# ===== Checks =====
: "${TG_BOT_TOKEN:?TG_BOT_TOKEN not set}"
: "${TG_WEBHOOK_SECRET:?TG_WEBHOOK_SECRET not set}"
: "${WEBHOOK_URL:?WEBHOOK_URL not set}"

API="https://api.telegram.org/bot${TG_BOT_TOKEN}"

# ===== Tunnel (optional) =====
# When TG_PROXY_URL is set, outgoing API calls go through ssh -L tunnel.
# When TG_VPS_IP is also set, webhook points to VPS (incoming via ssh -R + socat).
CURL_TUNNEL=""
EFFECTIVE_WEBHOOK_URL="$WEBHOOK_URL"
CERT_ARG=""

if [[ -n "$TG_PROXY_URL" ]]; then
  CURL_TUNNEL="--resolve api.telegram.org:${TG_PROXY_URL}:127.0.0.1"
  API="https://api.telegram.org:${TG_PROXY_URL}/bot${TG_BOT_TOKEN}"
  echo "[INFO] Using outgoing tunnel on port $TG_PROXY_URL"

  if [[ -n "$TG_VPS_IP" ]]; then
    EFFECTIVE_WEBHOOK_URL="https://${TG_VPS_IP}:${TG_PROXY_URL}/tg/webhook"
    echo "[INFO] Webhook via VPS: $EFFECTIVE_WEBHOOK_URL"

    # Self-signed cert for VPS IP (uploaded to Telegram with setWebhook)
    TG_VPS_CERT="${TG_VPS_CERT:-${PROJECT_DIR}/data/tg-webhook.pem}"
    if [[ -f "$TG_VPS_CERT" ]]; then
      CERT_ARG="-F certificate=@${TG_VPS_CERT}"
      echo "[INFO] Will upload cert: $TG_VPS_CERT"
    else
      echo "[WARN] VPS cert not found at $TG_VPS_CERT — webhook may fail"
    fi
  fi
fi

# ===== Get webhook info =====
INFO=$(curl -s $CURL_TUNNEL "${API}/getWebhookInfo")

CURRENT_URL=$(echo "$INFO" | jq -r '.result.url // empty')
LAST_ERROR_DATE=$(echo "$INFO" | jq -r '.result.last_error_date // empty')
PENDING=$(echo "$INFO" | jq -r '.result.pending_update_count // 0')

NEED_RESET=0

# 1. URL mismatch or empty
if [[ -z "$CURRENT_URL" || "$CURRENT_URL" != "$EFFECTIVE_WEBHOOK_URL" ]]; then
  NEED_RESET=1
fi

# 2. Telegram reports error
if [[ -n "$LAST_ERROR_DATE" && "$LAST_ERROR_DATE" != "null" ]]; then
  NEED_RESET=1
fi

# 3. Too many pending updates (залип)
if [[ "$PENDING" -gt 50 ]]; then
  NEED_RESET=1
fi

# 4. allowed_updates missing channel_post or message_reaction
HAS_CHANNEL=$(echo "$INFO" | jq '.result.allowed_updates // [] | index("channel_post")')
HAS_REACTION=$(echo "$INFO" | jq '.result.allowed_updates // [] | index("message_reaction")')
if [[ "$HAS_CHANNEL" == "null" || "$HAS_REACTION" == "null" ]]; then
  NEED_RESET=1
fi

if [[ "$NEED_RESET" -eq 0 ]]; then
  echo "[OK] Webhook is healthy"
  exit 0
fi

echo "[WARN] Webhook looks broken → resetting"

# ===== Reset webhook =====
ALLOWED='["message","edited_message","callback_query","channel_post","edited_channel_post","message_reaction","message_reaction_count"]'

if [[ -n "$CERT_ARG" ]]; then
  # VPS mode: use -F (multipart) to upload self-signed cert
  curl -s $CURL_TUNNEL \
    -F "url=${EFFECTIVE_WEBHOOK_URL}" \
    -F "secret_token=${TG_WEBHOOK_SECRET}" \
    $CERT_ARG \
    -F "allowed_updates=${ALLOWED}" \
    "${API}/setWebhook" \
  | jq .
else
  # Direct mode: simple form data
  curl -s $CURL_TUNNEL -X POST \
    "${API}/setWebhook" \
    -d "url=${EFFECTIVE_WEBHOOK_URL}" \
    -d "secret_token=${TG_WEBHOOK_SECRET}" \
    -d "allowed_updates=${ALLOWED}" \
  | jq .
fi

echo "[DONE] Webhook reset completed"

