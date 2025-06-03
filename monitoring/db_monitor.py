"""
Database monitoring for Unisolar Watchdog Service.

This module provides decorators to instrument database operations with OpenTelemetry tracing.
"""

import functools
import logging
import json
from opentelemetry import trace
from logging_config import serialize_dimensions

logger = logging.getLogger(__name__)

def instrument_db_method(operation_name):
    """
    Decorator to instrument a database method with OpenTelemetry tracing.
    
    Args:
        operation_name: Name of the database operation
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get tracer
            tracer = trace.get_tracer("database")
            
            # Create span attributes
            attributes = {
                'db.operation': operation_name,
                'db.type': 'postgresql'
            }
            
            # Add query parameters if available
            for key, value in kwargs.items():
                if isinstance(value, (str, int, float, bool)):
                    attributes[f'db.parameter.{key}'] = str(value)
                
            # Start span for tracing
            with tracer.start_as_current_span(
                name=f"Database.{operation_name}", 
                attributes=attributes
            ):
                try:
                    # Execute the original function
                    result = func(*args, **kwargs)
                    
                    # Add result information to span
                    current_span = trace.get_current_span()
                    
                    # Track result counts if available
                    if isinstance(result, dict):
                        # For insert/update operations that return counts
                        if 'inserted_records' in result:
                            current_span.set_attribute('db.result.inserted_records', result.get('inserted_records', 0))
                        if 'updated_records' in result:
                            current_span.set_attribute('db.result.updated_records', result.get('updated_records', 0))
                        if 'deleted_records' in result:
                            current_span.set_attribute('db.result.deleted_records', result.get('deleted_records', 0))
                    elif isinstance(result, list):
                        # For query operations that return lists of records
                        current_span.set_attribute('db.result.count', len(result))
                    
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
                        f"Database.{operation_name} failed: {str(e)}",
                        extra={'custom_dimensions_json': json.dumps(attributes)}
                    )
                    
                    # Re-raise the exception
                    raise
                    
        return wrapper
    return decorator

# Create a custom wrapper specifically for get_inverters_list that preserves its signature
def instrument_get_inverters_list(cls):
    """
    Special instrumentation for get_inverters_list that preserves the original function signature.
    """
    original_method = cls.get_inverters_list
    
    @functools.wraps(original_method)
    def wrapped_method(self, username=None, *args, **kwargs):
        # Get tracer
        tracer = trace.get_tracer("database")
        
        # Create span attributes
        attributes = {
            'db.operation': 'get_inverters_list',
            'db.type': 'postgresql'
        }
        
        if username:
            attributes['db.parameter.username'] = str(username)
            
        # Start span for tracing
        with tracer.start_as_current_span(
            name="Database.get_inverters_list", 
            attributes=attributes
        ):
            try:
                # Execute the original function with the correct arguments
                result = original_method(self, username)
                
                # Add result information to span
                current_span = trace.get_current_span()
                
                # Track result count
                if isinstance(result, list):
                    current_span.set_attribute('db.result.count', len(result))
                
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
                    f"Database.get_inverters_list failed: {str(e)}",
                    extra={'custom_dimensions_json': json.dumps(attributes)}
                )
                
                # Re-raise the exception
                raise
    
    # Replace the original method with our wrapped version
    cls.get_inverters_list = wrapped_method
    return cls

def instrument_db_client(cls):
    """
    Class decorator to instrument a database client class with OpenTelemetry tracing.
    
    Args:
        cls: The database client class to instrument
        
    Returns:
        Decorated class
    """
    # User-related operations
    cls.get_users_list = instrument_db_method('get_users_list')(cls.get_users_list)
    cls.get_user = instrument_db_method('get_user')(cls.get_user)
    cls.insert_user = instrument_db_method('insert_user')(cls.insert_user)
    
    # Plant-related operations
    cls.get_plants_list = instrument_db_method('get_plants_list')(cls.get_plants_list)
    cls.insert_plant = instrument_db_method('insert_plant')(cls.insert_plant)
    cls.get_plant_energy_summary = instrument_db_method('get_plant_energy_summary')(cls.get_plant_energy_summary)
    cls.insert_plant_energy_summary = instrument_db_method('insert_plant_energy_summary')(cls.insert_plant_energy_summary)
    cls.insert_plant_daily_generation_history = instrument_db_method('insert_plant_daily_generation_history')(cls.insert_plant_daily_generation_history)
    
    # Device-related operations - Use custom wrapper for get_inverters_list
    instrument_get_inverters_list(cls)
    cls.get_inverter_record = instrument_db_method('get_inverter_record')(cls.get_inverter_record)
    cls.insert_inverter = instrument_db_method('insert_inverter')(cls.insert_inverter)
    
    # History-related operations
    cls.get_device_records_by_date = instrument_db_method('get_device_records_by_date')(cls.get_device_records_by_date)
    cls.get_last_record_date_for_device = instrument_db_method('get_last_record_date_for_device')(cls.get_last_record_date_for_device)
    cls.insert_history_into_database = instrument_db_method('insert_history_into_database')(cls.insert_history_into_database)
    cls.delete_device_records_by_date = instrument_db_method('delete_device_records_by_date')(cls.delete_device_records_by_date)
    
    # Disruption analysis operations
    cls.get_disruption_events = instrument_db_method('get_disruption_events')(cls.get_disruption_events)
    cls.insert_disruption_events = instrument_db_method('insert_disruption_events')(cls.insert_disruption_events)
    cls.delete_disruption_events = instrument_db_method('delete_disruption_events')(cls.delete_disruption_events)
    cls.update_analysis_ledger = instrument_db_method('update_analysis_ledger')(cls.update_analysis_ledger)
    
    # Current output operations
    cls.get_current_output_for_user = instrument_db_method('get_current_output_for_user')(cls.get_current_output_for_user)
    
    return cls 