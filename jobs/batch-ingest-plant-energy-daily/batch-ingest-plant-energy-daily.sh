#!/bin/bash

# Exit on error
set -e

# Set variables
ENDPOINT="https://unisolartech-watchdog-databox-bgdqfzedhnd5ecbt.centralindia-01.azurewebsites.net/api/plants/energy/daily/batch-ingest"
LOGIN_ENDPOINT="https://unisolartech-watchdog-databox-bgdqfzedhnd5ecbt.centralindia-01.azurewebsites.net/api/auth/login"
ADMIN_USER="admin"
ADMIN_PASS="admin"
TIMEOUT=600
LOG_FILE="batch-ingest-plant-energy-daily.log"

# Function to log messages
log_message() {
  local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
  echo "$timestamp - $1" | tee -a "$LOG_FILE"
}

# Start logging
log_message "Starting plant daily energy batch ingest job at $(date)"
log_message "Calling endpoint: $ENDPOINT"

# Authenticate and get JWT token
log_message "Authenticating as admin..."
LOGIN_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" -d '{"username":"'$ADMIN_USER'","password":"'$ADMIN_PASS'"}' "$LOGIN_ENDPOINT")
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d '"' -f4)
if [ -z "$ACCESS_TOKEN" ]; then
  log_message "Failed to obtain access token. Login response: $LOGIN_RESPONSE"
  exit 1
fi
log_message "Obtained access token."

# Make the request with curl
# -s for silent, -S to show errors, -f to fail on HTTP errors, -m for timeout
RESPONSE=$(curl -s -S -f -m $TIMEOUT -H "Authorization: Bearer $ACCESS_TOKEN" "$ENDPOINT")
CURL_STATUS=$?

# Check if the request was successful
if [ $CURL_STATUS -eq 0 ]; then
  if command -v jq &> /dev/null; then
    PROCESSED=$(echo "$RESPONSE" | jq -r '.processed // .processed_plants // 0')
    SUCCESSFUL=$(echo "$RESPONSE" | jq -r '.successful // 0')
    FAILED=$(echo "$RESPONSE" | jq -r '.failed // 0')
    log_message "Batch ingest successful. Processed: $PROCESSED, Successful: $SUCCESSFUL, Failed: $FAILED."
  else
    log_message "Batch ingest successful. Response received."
    PREVIEW=$(echo "$RESPONSE" | head -c 200)
    log_message "Response preview: $PREVIEW..."
  fi
else
  log_message "Failed to call batch ingest. Curl exit code: $CURL_STATUS"
  log_message "Response: $RESPONSE"
fi

log_message "Plant daily energy batch ingest job completed at $(date)"

exit $CURL_STATUS


