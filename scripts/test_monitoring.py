#!/usr/bin/env python
"""
Test script for monitoring instrumentation.

This script makes a series of requests to the API to test the monitoring instrumentation.
It can be used to verify that metrics are being collected correctly.
"""

import argparse
import requests
import time
import random
import json
import sys
import os
from datetime import datetime

# Add parent directory to path to allow importing from app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Test monitoring instrumentation')
    parser.add_argument('-b', '--base-url', default='http://localhost:5001',
                      help='Base URL of the API (default: http://localhost:5001)')
    parser.add_argument('-n', '--num-requests', type=int, default=10,
                      help='Number of requests to make (default: 10)')
    parser.add_argument('-i', '--interval', type=float, default=0.5,
                      help='Interval between requests in seconds (default: 0.5)')
    parser.add_argument('-e', '--error-rate', type=float, default=0.2,
                      help='Percentage of requests that should generate errors (0.0-1.0, default: 0.2)')
    return parser.parse_args()

def make_random_request(base_url, should_error=False):
    """
    Make a random request to the API.
    
    Args:
        base_url (str): Base URL of the API
        should_error (bool): Whether the request should generate an error
        
    Returns:
        tuple: (status_code, response_time, endpoint)
    """
    # Define available endpoints
    endpoints = [
        '/api/auth/validate',
        '/api/users',
        '/api/plants',
        '/api/devices',
        '/api/dashboard/summary'
    ]
    
    # Force an error if requested
    if should_error:
        endpoints.append('/api/nonexistent/endpoint')
        endpoints.append('/api/plants/invalid-id')
        endpoints.append('/api/devices/invalid-device')
    
    # Choose a random endpoint
    endpoint = random.choice(endpoints)
    
    # Make the request with timing
    start_time = time.time()
    try:
        response = requests.get(f"{base_url}{endpoint}")
        status_code = response.status_code
    except requests.exceptions.RequestException as e:
        status_code = 500
        print(f"Request error: {e}")
    
    response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
    
    return status_code, response_time, endpoint

def main():
    """Main function"""
    args = parse_args()
    
    print(f"Testing monitoring instrumentation")
    print(f"Base URL: {args.base_url}")
    print(f"Number of requests: {args.num_requests}")
    print(f"Interval: {args.interval} seconds")
    print(f"Error rate: {args.error_rate * 100}%")
    print("-" * 50)
    
    # Make requests
    for i in range(args.num_requests):
        # Determine if this request should generate an error
        should_error = random.random() < args.error_rate
        
        # Make the request
        status_code, response_time, endpoint = make_random_request(args.base_url, should_error)
        
        # Print result
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status_str = "ERROR" if status_code >= 400 else "OK"
        print(f"{timestamp} | Request {i+1}/{args.num_requests} | {endpoint} | {status_code} {status_str} | {response_time:.2f}ms")
        
        # Sleep between requests
        if i < args.num_requests - 1:
            time.sleep(args.interval)
    
    print("-" * 50)
    print("Test completed")

if __name__ == '__main__':
    main() 