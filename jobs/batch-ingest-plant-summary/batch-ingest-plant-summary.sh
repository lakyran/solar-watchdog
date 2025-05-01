#!/bin/bash

# Exit on error
set -e

# Set variables
ENDPOINT="https://unisolartech-watchdog-cua9c4ghegcqcndf.centralindia-01.azurewebsites.net/plants/summary/batch-ingest"
TIMEOUT=600
LOG_FILE="batch-ingest-plant-summary.log"

# Function to log messages
log_message() {
  local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
  echo "$timestamp - $1" | tee -a "$LOG_FILE"
}

# Start logging
log_message "Starting batch ingest plant summary job at $(date)"
log_message "Calling endpoint: $ENDPOINT"

# Make the request with curl
# -s for silent, -S to show errors, -f to fail on HTTP errors, -m for timeout
RESPONSE=$(curl -s -S -f -m $TIMEOUT "$ENDPOINT")
CURL_STATUS=$?

# Check if the request was successful
if [ $CURL_STATUS -eq 0 ]; then
  # Extract processed_plants count from JSON response
  # Requires jq to be installed for proper JSON parsing
  if command -v jq &> /dev/null; then
    SUCCESSFUL_PLANTS=$(echo "$RESPONSE" | jq -r '.successful_plants // 0')
    TOTAL_PLANTS=$(echo "$RESPONSE" | jq -r '.total_plants // 0')
    FAILED_PLANTS=$(echo "$RESPONSE" | jq -r '.failed_plants // 0')
    log_message "Batch ingest successful. Processed $SUCCESSFUL_PLANTS/$TOTAL_PLANTS plants. Failed: $FAILED_PLANTS"
  else
    # Fallback if jq isn't available
    log_message "Batch ingest successful. Response received."
    # Print first 100 chars of response for logging
    PREVIEW=$(echo "$RESPONSE" | head -c 100)
    log_message "Response preview: $PREVIEW..."
  fi
else
  # Handle error
  log_message "Failed to call batch ingest plant summary. Curl exit code: $CURL_STATUS"
  log_message "Response: $RESPONSE"
fi

log_message "Batch ingest plant summary job completed at $(date)"

exit $CURL_STATUS 