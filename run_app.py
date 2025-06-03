#!/usr/bin/env python
"""
Startup script for the Unisolar Watchdog Service.
This directly launches the Flask application without relying on the flask command.
"""

import argparse
from logging_config import configure_logging, enable_debug_for
from app import app

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Run the Unisolar Watchdog Service')
    parser.add_argument('-v', '--verbose', action='store_true', 
                        help='Enable verbose logging for dependencies')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Enable Flask debug mode')
    parser.add_argument('-p', '--port', type=int, default=5001,
                        help='Port to run the service on (default: 5001)')
    parser.add_argument('--host', default='0.0.0.0',
                        help='Host to run the service on (default: 0.0.0.0)')
    return parser.parse_args()

if __name__ == '__main__':
    # Parse command line arguments
    args = parse_args()
    
    # Configure logging based on verbosity
    logger = configure_logging(verbose=args.verbose)
    
    # Log startup message
    logger.info("Starting Unisolar Watchdog Service...")
    
    # Run the Flask application
    app.run(
        host=args.host, 
        port=args.port, 
        debug=args.debug
    ) 