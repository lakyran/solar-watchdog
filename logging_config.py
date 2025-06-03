"""
Logging configuration for the Unisolar Watchdog Service.

This module contains logging configuration to make application logs
more visible while suppressing verbose logs from dependencies.
"""

import logging
import os
import sys
import json

def configure_logging(verbose=False):
    """
    Configure logging with appropriate levels for all components.
    
    Args:
        verbose (bool): If True, show more detailed logs for dependencies
    
    Returns:
        logging.Logger: The root logger
    """
    # Base configuration
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Determine log level for external dependencies
    deps_level = logging.WARNING
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        stream=sys.stdout
    )
    
    # Configure specific loggers
    
    # Application loggers - always at INFO level or based on environment
    app_level = os.environ.get('APP_LOG_LEVEL', 'INFO')
    logging.getLogger('app').setLevel(app_level)
    logging.getLogger('watchdog').setLevel(app_level)
    logging.getLogger('services').setLevel(app_level)
    logging.getLogger('routes').setLevel(app_level)
    
    # External dependencies - limited to WARNING by default
    logging.getLogger('azure').setLevel(deps_level)
    logging.getLogger('azure.core.pipeline').setLevel(deps_level)
    logging.getLogger('azure.monitor').setLevel(deps_level)
    logging.getLogger('azure.identity').setLevel(deps_level)
    logging.getLogger('opentelemetry').setLevel(deps_level)
    logging.getLogger('werkzeug').setLevel(deps_level)
    logging.getLogger('urllib3').setLevel(deps_level)
    
    # Return the root logger
    return logging.getLogger()

def enable_debug_for(logger_name):
    """
    Enable DEBUG logging for a specific logger.
    Useful for troubleshooting specific components.
    
    Args:
        logger_name (str): The name of the logger to enable debug for
    """
    logging.getLogger(logger_name).setLevel(logging.DEBUG)

def serialize_dimensions(dimensions):
    """
    Serialize dictionary data for logging to avoid OpenTelemetry errors.
    
    OpenTelemetry requires attributes to be primitive types (str, int, bool, etc.)
    and doesn't support dictionaries directly. This function converts dictionaries 
    to JSON strings.
    
    Args:
        dimensions (dict): Dictionary with dimensions/attributes to log
        
    Returns:
        dict: Dictionary with all values converted to appropriate types for logging
    """
    if not dimensions:
        return {}
        
    # Create a new dictionary to store serialized values
    serialized = {}
    
    for key, value in dimensions.items():
        if isinstance(value, dict):
            # Convert nested dictionaries to JSON strings
            serialized[key] = json.dumps(value)
        elif isinstance(value, (list, tuple)):
            # Convert lists and tuples to JSON strings
            serialized[key] = json.dumps(value)
        else:
            # Keep primitive types as they are
            serialized[key] = value
            
    return serialized 