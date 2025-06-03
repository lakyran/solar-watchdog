"""
Monitoring package for Unisolar Watchdog Service.
"""

# OpenTelemetry monitoring
from monitoring.config import init_opentelemetry, get_tracer, instrument_function
from monitoring.route_monitor import instrument_route, instrument_blueprint, RequestMonitoringMiddleware
from monitoring.service_monitors import (
    instrument_service_class, instrument_method,
    instrument_history_service, instrument_disruption_service,
    instrument_user_service, instrument_plant_service
)
from monitoring.db_monitor import instrument_db_client, instrument_db_method
from monitoring.api_monitor import instrument_api_client, instrument_api_method
from monitoring.metrics import init_metrics, record_request, record_error

__all__ = [
    # OpenTelemetry monitoring
    'init_opentelemetry',
    'get_tracer',
    'instrument_function',
    'instrument_service_class',
    'instrument_method',
    'instrument_history_service',
    'instrument_disruption_service',
    'instrument_user_service',
    'instrument_plant_service',
    'instrument_db_client',
    'instrument_db_method',
    'instrument_api_client',
    'instrument_api_method',
    'instrument_route',
    'instrument_blueprint',
    'RequestMonitoringMiddleware',
    'init_metrics',
    'record_request',
    'record_error'
] 