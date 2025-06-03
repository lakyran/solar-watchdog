"""
Route monitoring for Unisolar Watchdog Service.

This module provides decorators to instrument Flask routes with OpenTelemetry tracing
to measure invocations, success/failure rates, and latency.
"""

import functools
import time
import logging
import json
from flask import request, g
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode
from logging_config import serialize_dimensions
from monitoring.metrics import record_request, record_error

logger = logging.getLogger(__name__)

def instrument_route(blueprint_name):
    """
    Decorator to instrument a Flask route with OpenTelemetry tracing.
    
    This decorator tracks:
    - Number of invocations (automatically tracked by spans)
    - Success/failure rates
    - Request latency
    - HTTP method and path
    - Status code
    
    Args:
        blueprint_name: Name of the blueprint (e.g., 'auth', 'users')
        
    Returns:
        Decorated function
    """
    def decorator(route_func):
        @functools.wraps(route_func)
        def wrapper(*args, **kwargs):
            # Get tracer
            tracer = trace.get_tracer(f"{blueprint_name}_routes")
            
            # Extract route information
            route_name = route_func.__name__
            http_method = request.method
            path = request.path
            
            # Create span attributes
            attributes = {
                'http.method': http_method,
                'http.route': path,
                'blueprint': blueprint_name,
                'route': route_name
            }
            
            # Add query parameters (exclude sensitive data)
            safe_args = {}
            for key, value in request.args.items():
                if not _is_sensitive_param(key):
                    safe_args[key] = value
            
            if safe_args:
                attributes['http.query_params'] = str(safe_args)
            
            # Start timing for latency measurement
            start_time = time.time()
            
            # Start span for tracing
            with tracer.start_as_current_span(
                name=f"{blueprint_name}.{route_name}", 
                attributes=attributes
            ) as span:
                try:
                    # Execute the original route function
                    response = route_func(*args, **kwargs)
                    
                    # Calculate request latency
                    latency = (time.time() - start_time) * 1000  # Convert to milliseconds
                    
                    # Extract status code from response
                    if isinstance(response, tuple) and len(response) > 1:
                        status_code = response[1]
                    else:
                        status_code = 200
                    
                    # Add response attributes to span
                    span.set_attribute('http.status_code', status_code)
                    span.set_attribute('http.latency_ms', latency)
                    
                    # Set span status based on HTTP status code
                    if status_code < 400:
                        span.set_status(Status(StatusCode.OK))
                    else:
                        span.set_status(Status(StatusCode.ERROR))
                        span.set_attribute('error', True)
                    
                    # Record metrics
                    record_request(
                        blueprint=blueprint_name,
                        route=route_name,
                        method=http_method,
                        status_code=status_code,
                        latency_ms=latency
                    )
                    
                    # Log success with metrics
                    logger.info(
                        f"{blueprint_name}.{route_name} completed: status={status_code}, latency={latency:.2f}ms",
                        extra={'custom_dimensions_json': json.dumps({
                            'blueprint': blueprint_name,
                            'route': route_name,
                            'http_method': http_method,
                            'path': path,
                            'status_code': status_code,
                            'latency_ms': round(latency, 2)
                        })}
                    )
                    
                    return response
                
                except Exception as e:
                    # Calculate request latency even for failures
                    latency = (time.time() - start_time) * 1000
                    
                    # Record exception in the span
                    span.record_exception(e)
                    
                    # Add error attributes
                    span.set_attribute('error', True)
                    span.set_attribute('error.type', e.__class__.__name__)
                    span.set_attribute('error.message', str(e))
                    span.set_attribute('http.latency_ms', latency)
                    
                    # Set span status to ERROR
                    span.set_status(Status(StatusCode.ERROR))
                    
                    # Record error metrics
                    record_error(
                        blueprint=blueprint_name,
                        route=route_name,
                        method=http_method,
                        error_type=e.__class__.__name__
                    )
                    
                    # Log error with context
                    error_attributes = {
                        'blueprint': blueprint_name,
                        'route': route_name,
                        'http_method': http_method,
                        'path': path,
                        'error_type': e.__class__.__name__,
                        'error_message': str(e),
                        'latency_ms': round(latency, 2)
                    }
                    
                    logger.error(
                        f"{blueprint_name}.{route_name} failed: {str(e)}",
                        extra={'custom_dimensions_json': json.dumps(error_attributes)}
                    )
                    
                    # Re-raise the exception for Flask to handle
                    raise
                    
        return wrapper
    return decorator

def _is_sensitive_param(param_name):
    """
    Check if a parameter name suggests it contains sensitive information.
    
    Args:
        param_name: The name of the parameter to check
        
    Returns:
        bool: True if the parameter might contain sensitive data
    """
    sensitive_keywords = ['password', 'token', 'secret', 'key', 'auth', 'credential']
    param_lower = param_name.lower()
    return any(keyword in param_lower for keyword in sensitive_keywords)

def instrument_blueprint(blueprint_obj):
    """
    Instrument all routes in a Flask blueprint.
    
    This function finds all route handler functions in a blueprint and
    wraps them with the instrument_route decorator.
    
    Args:
        blueprint_obj: Flask Blueprint object to instrument
        
    Returns:
        The instrumented blueprint
    """
    blueprint_name = blueprint_obj.name
    
    # Loop through all deferred functions (which include route handlers)
    for deferred in blueprint_obj.deferred_functions:
        # Get the original route function
        if hasattr(deferred, 'original_function'):
            route_func = deferred.original_function
            endpoint = route_func.__name__
            
            # Get the view function from the blueprint
            view_func = blueprint_obj.view_functions.get(endpoint)
            
            if view_func:
                # Replace with instrumented version
                blueprint_obj.view_functions[endpoint] = instrument_route(blueprint_name)(view_func)
    
    return blueprint_obj

class RequestMonitoringMiddleware:
    """
    WSGI middleware to monitor all Flask requests.
    
    This middleware provides global metrics for all requests, capturing:
    - Total request count
    - Request latency
    - Success/failure rates
    - HTTP method and path distribution
    - Status code distribution
    """
    
    def __init__(self, app):
        """
        Initialize the middleware.
        
        Args:
            app: Flask application instance
        """
        self.app = app
        self.logger = logging.getLogger(__name__)
        self.tracer = trace.get_tracer("flask_app")
        
        # Register before_request and after_request handlers
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        app.teardown_request(self._teardown_request)
    
    def _before_request(self):
        """Handle the start of a request"""
        # Store start time
        g.start_time = time.time()
        
        # Extract request information
        http_method = request.method
        path = request.path
        
        # Create span attributes
        attributes = {
            'http.method': http_method,
            'http.route': path,
        }
        
        # Start span for the request
        g.current_span = self.tracer.start_span(
            name=f"HTTP {http_method} {path}",
            attributes=attributes
        )
        
        # Store request information in g for later use
        g.request_info = {
            'http_method': http_method,
            'path': path
        }
    
    def _after_request(self, response):
        """
        Handle the end of a successful request.
        
        Args:
            response: Flask response object
            
        Returns:
            The response object
        """
        # Calculate request latency
        if hasattr(g, 'start_time'):
            latency = (time.time() - g.start_time) * 1000  # Convert to milliseconds
            
            # Get the current span
            if hasattr(g, 'current_span'):
                span = g.current_span
                
                # Add response attributes to span
                span.set_attribute('http.status_code', response.status_code)
                span.set_attribute('http.latency_ms', latency)
                
                # Set span status based on HTTP status code
                if response.status_code < 400:
                    span.set_status(Status(StatusCode.OK))
                else:
                    span.set_status(Status(StatusCode.ERROR))
                    span.set_attribute('error', True)
                
                # Get request info
                request_info = getattr(g, 'request_info', {})
                http_method = request_info.get('http_method', request.method)
                path = request_info.get('path', request.path)
                
                # Record metrics
                # Extract blueprint and route from path if possible
                path_parts = path.strip('/').split('/')
                if len(path_parts) > 1:
                    blueprint = path_parts[0]
                    route = '/'.join(path_parts[1:])
                else:
                    blueprint = 'app'
                    route = path_parts[0] if path_parts else 'root'
                
                record_request(
                    blueprint=blueprint,
                    route=route,
                    method=http_method,
                    status_code=response.status_code,
                    latency_ms=latency
                )
                
                # Log success with metrics
                self.logger.info(
                    f"HTTP {http_method} {path} completed: status={response.status_code}, latency={latency:.2f}ms",
                    extra={'custom_dimensions_json': json.dumps({
                        'http_method': http_method,
                        'path': path,
                        'status_code': response.status_code,
                        'latency_ms': round(latency, 2)
                    })}
                )
                
                # End the span
                span.end()
                delattr(g, 'current_span')
        
        return response
    
    def _teardown_request(self, exception):
        """
        Handle request teardown, including exceptions.
        
        Args:
            exception: Exception raised during request handling, if any
        """
        # If there was an exception and we have a current span
        if exception and hasattr(g, 'current_span'):
            span = g.current_span
            
            # Calculate request latency
            if hasattr(g, 'start_time'):
                latency = (time.time() - g.start_time) * 1000
                span.set_attribute('http.latency_ms', latency)
            
            # Record exception in the span
            span.record_exception(exception)
            
            # Add error attributes
            span.set_attribute('error', True)
            span.set_attribute('error.type', exception.__class__.__name__)
            span.set_attribute('error.message', str(exception))
            
            # Set span status to ERROR
            span.set_status(Status(StatusCode.ERROR))
            
            # Get request info
            request_info = getattr(g, 'request_info', {})
            http_method = request_info.get('http_method', request.method)
            path = request_info.get('path', request.path)
            
            # Extract blueprint and route from path if possible
            path_parts = path.strip('/').split('/')
            if len(path_parts) > 1:
                blueprint = path_parts[0]
                route = '/'.join(path_parts[1:])
            else:
                blueprint = 'app'
                route = path_parts[0] if path_parts else 'root'
            
            # Record error metrics
            record_error(
                blueprint=blueprint,
                route=route,
                method=http_method,
                error_type=exception.__class__.__name__
            )
            
            # Log error with context
            error_attributes = {
                'http_method': http_method,
                'path': path,
                'error_type': exception.__class__.__name__,
                'error_message': str(exception),
            }
            
            if hasattr(g, 'start_time'):
                latency = (time.time() - g.start_time) * 1000
                error_attributes['latency_ms'] = round(latency, 2)
            
            self.logger.error(
                f"HTTP {http_method} {path} failed: {str(exception)}",
                extra={'custom_dimensions_json': json.dumps(error_attributes)}
            )
            
            # End the span
            span.end()
            delattr(g, 'current_span') 