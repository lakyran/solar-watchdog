#!/bin/bash

# Exit on error
set -e

# Log starting execution
echo "Starting batch ingest history job at $(date)"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# If we're on Azure, we might need to check for Python in a specific location
if [ -f "$HOME/python/python.exe" ]; then
    PYTHON="$HOME/python/python.exe"
elif [ -f "$HOME/python/bin/python" ]; then
    PYTHON="$HOME/python/bin/python"
else
    PYTHON=$(which python || which python3)
fi

# Display Python version for logging purposes
echo "Using Python: $PYTHON ($(${PYTHON} --version 2>&1))"

# Execute the Python script
${PYTHON} "${SCRIPT_DIR}/batch-ingest-history.py"

# Log completion
echo "Batch ingest history job completed at $(date) with exit code $?" 