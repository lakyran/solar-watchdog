#!/usr/bin/env python

import requests
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('batch-ingest-webjob')

def main():
    """
    WebJob to trigger the batch ingest endpoint of the Unisolar Watchdog Service.
    This will fetch generation history for all inverters.
    """
    try:
        logger.info(f"Starting batch ingest job at {datetime.now().isoformat()}")
        
        # Get the website hostname from environment variables or use localhost
        # When running as a WebJob, WEBSITE_HOSTNAME will be available
        host = os.environ.get('WEBSITE_HOSTNAME', 'localhost')
        
        # Determine if we're running locally or on Azure
        if host == 'localhost':
            base_url = 'http://localhost:5000'
        else:
            # Use local connection when running as a WebJob on the same App Service
            base_url = f'http://127.0.0.1'
        
        endpoint = f"{base_url}/history/batch-ingest"
        logger.info(f"Calling endpoint: {endpoint}")
        
        # Make the request
        response = requests.get(endpoint, timeout=600)  # 10-minute timeout
        
        # Check if the request was successful
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Batch ingest successful. Processed {result.get('processed_inverters', 0)} inverters.")
        else:
            logger.error(f"Failed to call batch ingest. Status code: {response.status_code}")
            logger.error(f"Response: {response.text}")
    
    except Exception as e:
        logger.error(f"Error running batch ingest job: {str(e)}")

if __name__ == "__main__":
    main() 