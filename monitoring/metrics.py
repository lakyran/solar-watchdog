"""
Metrics aggregation and export for Unisolar Watchdog Service.

This module provides utilities to aggregate metrics from route monitoring
and export them to Azure Monitor.
"""

import logging
import json
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader
)
from logging_config import serialize_dimensions

logger = logging.getLogger(__name__)

# Global metric instruments
_request_counter = None
_latency_recorder = None
_error_counter = None
_meter = None

def init_metrics():
    """
    Initialize metrics instrumentation.
    
    This function sets up metric instruments for tracking:
    - Request counts (by route, method, status)
    - Request latency (by route, method)
    - Error counts (by route, method, error type)
    """
    global _request_counter, _latency_recorder, _error_counter, _meter
    
    # Create a meter provider
    metric_reader = PeriodicExportingMetricReader(
        ConsoleMetricExporter(),
        export_interval_millis=60000  # Export metrics every 60 seconds
    )
    
    provider = MeterProvider(metric_readers=[metric_reader])
    metrics.set_meter_provider(provider)
    
    # Create a meter
    _meter = metrics.get_meter("unisolar_watchdog")
    
    # Create metric instruments
    _request_counter = _meter.create_counter(
        name="http.server.request.count",
        description="Number of HTTP requests",
        unit="1"
    )
    
    _latency_recorder = _meter.create_histogram(
        name="http.server.request.duration",
        description="HTTP request latency",
        unit="ms"
    )
    
    _error_counter = _meter.create_counter(
        name="http.server.error.count",
        description="Number of HTTP errors",
        unit="1"
    )
    
    logger.info("Metrics instrumentation initialized")

def record_request(blueprint, route, method, status_code, latency_ms):
    """
    Record metrics for a completed HTTP request.
    
    Args:
        blueprint (str): Blueprint name
        route (str): Route name
        method (str): HTTP method
        status_code (int): HTTP status code
        latency_ms (float): Request latency in milliseconds
    """
    if _request_counter is None or _latency_recorder is None:
        return
    
    # Define attributes for metrics
    attributes = {
        "blueprint": blueprint,
        "route": route,
        "http.method": method,
        "http.status_code": status_code
    }
    
    # Record request count
    _request_counter.add(1, attributes)
    
    # Record latency
    _latency_recorder.record(latency_ms, attributes)
    
    # Record error if status code >= 400
    if status_code >= 400 and _error_counter is not None:
        _error_counter.add(1, attributes)
    
def record_error(blueprint, route, method, error_type):
    """
    Record metrics for an HTTP request that resulted in an error.
    
    Args:
        blueprint (str): Blueprint name
        route (str): Route name
        method (str): HTTP method
        error_type (str): Type of error
    """
    if _error_counter is None:
        return
    
    # Define attributes for metrics
    attributes = {
        "blueprint": blueprint,
        "route": route,
        "http.method": method,
        "error.type": error_type
    }
    
    # Record error count
    _error_counter.add(1, attributes)

def get_metric_instruments():
    """
    Get the current metric instruments.
    
    Returns:
        tuple: (request_counter, latency_recorder, error_counter)
    """
    return (_request_counter, _latency_recorder, _error_counter) 