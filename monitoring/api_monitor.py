"""
API monitoring for Unisolar Watchdog Service.

This module provides decorators to instrument external API calls with OpenTelemetry tracing.
"""

import functools
import logging
import json
from opentelemetry import trace
from logging_config import serialize_dimensions

logger = logging.getLogger(__name__)

def instrument_api_method(api_name, operation_name):
    """
    Decorator to instrument an API method with OpenTelemetry tracing.
    
    Args:
        api_name: Name of the API (e.g., 'Growatt')
        operation_name: Name of the operation (e.g., 'fetch_device_history')
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get tracer
            tracer = trace.get_tracer(f"{api_name}API")
            
            # Extract useful information for span attributes
            device_sn = kwargs.get('device_sn', None)
            plant_id = kwargs.get('plant_id', None)
            start_date = kwargs.get('start_date', None)
            end_date = kwargs.get('end_date', None)
            
            # Create span attributes
            attributes = {
                'api.name': api_name,
                'api.operation': operation_name
            }
            
            # Add additional context if available
            if device_sn:
                attributes['device_sn'] = str(device_sn)
            if plant_id:
                attributes['plant_id'] = str(plant_id)
            if start_date:
                attributes['start_date'] = str(start_date)
            if end_date:
                attributes['end_date'] = str(end_date)
                
            # Start span for tracing
            with tracer.start_as_current_span(
                name=f"{api_name}API.{operation_name}", 
                attributes=attributes
            ):
                try:
                    # Execute the original function
                    result = func(*args, **kwargs)
                    
                    # Add result information to span
                    current_span = trace.get_current_span()
                    
                    # Track response size for data functions
                    if isinstance(result, dict) and 'datas' in result:
                        data_count = len(result.get('datas', []))
                        current_span.set_attribute('api.response.data_count', data_count)
                    elif isinstance(result, list):
                        current_span.set_attribute('api.response.data_count', len(result))
                    
                    return result
                except Exception as e:
                    # Record exception in the span
                    current_span = trace.get_current_span()
                    current_span.record_exception(e)
                    
                    # Add error attributes
                    current_span.set_attribute('error', True)
                    current_span.set_attribute('error.type', e.__class__.__name__)
                    current_span.set_attribute('error.message', str(e))
                    
                    # Log error with context - serialize dictionary for OpenTelemetry
                    logger.error(
                        f"{api_name}API.{operation_name} failed: {str(e)}",
                        extra={'custom_dimensions_json': json.dumps(attributes)}
                    )
                    
                    # Re-raise the exception
                    raise
                    
        return wrapper
    return decorator

def instrument_api_client(cls):
    """
    Class decorator to instrument a Growatt API client class with OpenTelemetry tracing.
    
    Args:
        cls: The API client class to instrument
        
    Returns:
        Decorated class
    """
    # Create a wrapper class to intercept initialization
    class TracedAPIClient(cls):
        def __init__(self, *args, **kwargs):
            # Initialize the original class
            super().__init__(*args, **kwargs)
            
    # Instrument the wrapper class methods
    # Plant-related operations
    TracedAPIClient.fetch_user_plant_list = instrument_api_method('Growatt', 'fetch_user_plant_list')(cls.fetch_user_plant_list)
    TracedAPIClient.fetch_plant_devices_list = instrument_api_method('Growatt', 'fetch_plant_devices_list')(cls.fetch_plant_devices_list)
    TracedAPIClient.fetch_plant_summary = instrument_api_method('Growatt', 'fetch_plant_summary')(cls.fetch_plant_summary)
    TracedAPIClient.fetch_plant_energy_data = instrument_api_method('Growatt', 'fetch_plant_energy_data')(cls.fetch_plant_energy_data)
    
    # Device-related operations
    TracedAPIClient.fetch_device_history = instrument_api_method('Growatt', 'fetch_device_history')(cls.fetch_device_history)
    TracedAPIClient.process_history_data_for_db = instrument_api_method('Growatt', 'process_history_data_for_db')(cls.process_history_data_for_db)
    
    return TracedAPIClient 