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

# ===== Get webhook info =====
INFO=$(curl -s "${API}/getWebhookInfo")

CURRENT_URL=$(echo "$INFO" | jq -r '.result.url // empty')
LAST_ERROR_DATE=$(echo "$INFO" | jq -r '.result.last_error_date // empty')
PENDING=$(echo "$INFO" | jq -r '.result.pending_update_count // 0')

NEED_RESET=0

# 1. URL mismatch or empty
if [[ -z "$CURRENT_URL" || "$CURRENT_URL" != "$WEBHOOK_URL" ]]; then
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

if [[ "$NEED_RESET" -eq 0 ]]; then
  echo "[OK] Webhook is healthy"
  exit 0
fi

echo "[WARN] Webhook looks broken → resetting"

# ===== Reset webhook =====
curl -s -X POST \
  "${API}/setWebhook" \
  -d "url=${WEBHOOK_URL}" \
  -d "secret_token=${TG_WEBHOOK_SECRET}" \
| jq .

echo "[DONE] Webhook reset completed"

