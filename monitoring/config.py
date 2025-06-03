"""
OpenTelemetry configuration for Unisolar Watchdog Service.
This file provides the configuration for OpenTelemetry instrumentation and Azure Monitor integration.
"""

import os
import logging
import json
from dotenv import load_dotenv
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Load environment variables
load_dotenv()

def init_opentelemetry():
    """
    Initialize OpenTelemetry with Azure Monitor.
    
    This function configures OpenTelemetry to send telemetry data to Azure Monitor.
    It uses the connection string from environment variables and sets up proper sampling.
    """
    # Configure logging to reduce verbosity
    # Set Azure and OpenTelemetry loggers to WARNING level
    logging.getLogger('azure').setLevel(logging.WARNING)
    logging.getLogger('azure.core.pipeline').setLevel(logging.WARNING)
    logging.getLogger('azure.monitor').setLevel(logging.WARNING)
    logging.getLogger('azure.identity').setLevel(logging.WARNING)
    logging.getLogger('opentelemetry').setLevel(logging.WARNING)
    
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    
    if not connection_string:
        print("WARNING: No Application Insights connection string found. OpenTelemetry will not send data to Azure Monitor.")
        return
    
    # Define specific instrumentors to use
    instrumentations = [
        "flask",      # Flask web framework
        "requests",   # HTTP client
        "urllib",     # URL handling
        "urllib3"     # HTTP client
    ]
    
    # Suppress warnings about Django instrumentation
    logging.getLogger('azure.monitor.opentelemetry._configure').setLevel(logging.ERROR)
    
    try:
        # Configure Azure Monitor with OpenTelemetry
        configure_azure_monitor(
            connection_string=connection_string,
            # Set the sampling rate (50% of traces will be sampled)
            sampling_rate=0.5,
            # Explicitly specify which instrumentations to enable
            # This avoids trying to instrument frameworks we don't use
            enable_instrumentations=instrumentations,
            # Disable auto-instrumentation to prevent the Django error
            auto_instrumentation=False
        )
        
        print("OpenTelemetry initialized with Azure Monitor")
    except Exception as e:
        print(f"Error initializing OpenTelemetry: {e}")
        logging.error(f"Failed to initialize OpenTelemetry: {e}")

def get_tracer(name):
    """
    Get a tracer for the given name.
    
    Args:
        name (str): The name of the component using the tracer
        
    Returns:
        Tracer: An OpenTelemetry tracer instance
    """
    return trace.get_tracer(name)

def instrument_function(func, span_name=None):
    """
    Decorator to instrument a function with OpenTelemetry tracing.
    
    Args:
        func: The function to instrument
        span_name: Optional name for the span. If not provided, the function name will be used.
        
    Returns:
        The decorated function
    """
    def wrapper(*args, **kwargs):
        tracer = get_tracer(func.__module__)
        with tracer.start_as_current_span(span_name or func.__name__):
            return func(*args, **kwargs)
    return wrapper 