"""
Service monitoring decorators for Unisolar Watchdog Service.

This module provides decorators to instrument service classes with OpenTelemetry tracing.
"""

import functools
import logging
import json
from opentelemetry import trace
from logging_config import serialize_dimensions

logger = logging.getLogger(__name__)

def instrument_service_class(service_name):
    """
    Generic decorator to instrument a service class with OpenTelemetry tracing.
    
    Args:
        service_name: Name of the service (e.g., 'HistoryIngestionService')
        
    Returns:
        Decorated class
    """
    def decorator(cls):
        # Get all methods from the class
        for attr_name in dir(cls):
            # Skip private methods and attributes
            if attr_name.startswith('__'):
                continue
                
            attr = getattr(cls, attr_name)
            
            # Only instrument methods, not attributes
            if callable(attr) and not isinstance(attr, type):
                # Replace the method with an instrumented version
                setattr(cls, attr_name, instrument_method(service_name, attr_name)(attr))
                
        return cls
    return decorator

def instrument_method(service_name, operation_name):
    """
    Decorator to instrument a service method with OpenTelemetry tracing.
    
    Args:
        service_name: Name of the service (e.g., 'HistoryIngestionService')
        operation_name: Name of the operation (e.g., 'fetch_and_store_device_generation_history')
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get tracer
            tracer = trace.get_tracer(f"{service_name}")
            
            # Extract useful information for span attributes
            # First arg is typically 'self' for methods
            device_sn = kwargs.get('device_sn', None)
            plant_id = kwargs.get('plant_id', None)
            date_str = kwargs.get('date_str', None) or kwargs.get('date', None)
            
            # Create span attributes
            attributes = {
                'service.name': service_name,
                'operation.name': operation_name
            }
            
            # Add additional context if available
            if device_sn:
                attributes['device_sn'] = str(device_sn)
            if plant_id:
                attributes['plant_id'] = str(plant_id)
            if date_str:
                attributes['date'] = str(date_str)
                
            # Start span for tracing
            with tracer.start_as_current_span(
                name=f"{service_name}.{operation_name}", 
                attributes=attributes
            ):
                try:
                    # Execute the original function
                    result = func(*args, **kwargs)
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
                        f"{service_name}.{operation_name} failed: {str(e)}",
                        extra={'custom_dimensions_json': json.dumps(attributes)}
                    )
                    
                    # Re-raise the exception
                    raise
                    
        return wrapper
    return decorator

# Specific service instrumentation decorators

def instrument_history_service(cls):
    """
    Decorator to instrument HistoryIngestionService with OpenTelemetry tracing.
    
    Args:
        cls: The service class to instrument
        
    Returns:
        Decorated class
    """
    return instrument_service_class('HistoryIngestionService')(cls)

def instrument_disruption_service(cls):
    """
    Decorator to instrument DisruptionAnalysisService with OpenTelemetry tracing.
    
    Args:
        cls: The service class to instrument
        
    Returns:
        Decorated class
    """
    return instrument_service_class('DisruptionAnalysisService')(cls)

def instrument_user_service(cls):
    """
    Decorator to instrument UserManagementService with OpenTelemetry tracing.
    
    Args:
        cls: The service class to instrument
        
    Returns:
        Decorated class
    """
    return instrument_service_class('UserManagementService')(cls)

def instrument_plant_service(cls):
    """
    Decorator to instrument PlantManagementService with OpenTelemetry tracing.
    
    Args:
        cls: The service class to instrument
        
    Returns:
        Decorated class
    """
    return instrument_service_class('PlantManagementService')(cls) 