# Unisolar Watchdog Service Monitoring Guide

This document describes the monitoring capabilities of the Unisolar Watchdog Service and how to use them.

## Overview

The monitoring system is built on OpenTelemetry and provides the following capabilities:

1. **Route Monitoring**: Tracks HTTP requests to all API endpoints, measuring:
   - Request count
   - Success/failure rates
   - Latency
   - HTTP method and path distribution
   - Status code distribution

2. **Service Monitoring**: Instruments service classes to track operations:
   - Operation execution
   - Success/failure rates
   - Context information (plant_id, device_sn, etc.)

3. **Database Monitoring**: Tracks database operations:
   - Query execution
   - Success/failure rates
   - Record counts (inserted, updated, deleted)

4. **API Monitoring**: Instruments external API calls:
   - API call execution
   - Success/failure rates
   - Response data metrics

## Metrics Collection

All metrics are collected and sent to Azure Monitor using OpenTelemetry. The following metrics are collected:

| Metric Name | Type | Description |
|-------------|------|-------------|
| http.server.request.count | Counter | Number of HTTP requests by route, method, status |
| http.server.request.duration | Histogram | Latency of HTTP requests in milliseconds |
| http.server.error.count | Counter | Number of HTTP errors by route, method, error type |

## Logging

Logs are enriched with structured data and sent to Azure Monitor. The log format includes:

- Timestamp
- Logger name
- Log level
- Message
- Custom dimensions (serialized as JSON)

### Custom Dimensions

Custom dimensions are used to add context to log messages. They are serialized as JSON to avoid OpenTelemetry errors with dictionary values.

Example:
```python
logger.info(
    "Plant summary updated successfully",
    extra={'custom_dimensions_json': json.dumps({
        'plant_id': plant_id,
        'user_name': user_name,
        'current_power': current_power
    })}
)
```

## Route Instrumentation

Routes are automatically instrumented when the application starts. Each route handler is wrapped with a decorator that:

1. Creates a span for the request
2. Records latency and status code
3. Logs success or failure
4. Collects metrics

## Troubleshooting

### Common Issues

1. **Invalid type dict for attribute 'custom_dimensions'**
   - Use `custom_dimensions_json` instead of `custom_dimensions`
   - Serialize dictionaries with `json.dumps()`

2. **No module named 'django'**
   - Fixed by explicitly disabling Django instrumentation in `monitoring/config.py`

3. **Mismatch between function signature and decorator**
   - Custom wrappers are used for specific functions like `get_inverters_list`

### Testing the Monitoring System

Use the included test script to verify that monitoring is working correctly:

```bash
# Run with default settings
./scripts/test_monitoring.py

# Run with custom settings
./scripts/test_monitoring.py --base-url http://localhost:5002 --num-requests 20 --interval 0.2 --error-rate 0.1
```

## Azure Monitor Integration

Metrics and logs are sent to Azure Monitor using the OpenTelemetry exporter. To configure the connection:

1. Set the `APPLICATIONINSIGHTS_CONNECTION_STRING` environment variable
2. Adjust sampling rate in `monitoring/config.py` if needed
3. Set appropriate log levels in `logging_config.py`

## Dashboard Examples

In Azure Monitor, you can create dashboards with the following queries:

### Request Rate by Endpoint

```kusto
requests
| where timestamp > ago(1h)
| summarize count() by name, bin(timestamp, 1m)
| render timechart
```

### Error Rate by Endpoint

```kusto
requests
| where timestamp > ago(1h) and success == false
| summarize count() by name, bin(timestamp, 1m)
| render timechart
```

### Latency by Endpoint

```kusto
requests
| where timestamp > ago(1h)
| summarize avg(duration) by name, bin(timestamp, 1m)
| render timechart
```

## Adding Custom Instrumentation

To add custom instrumentation to your code:

### For Services

```python
from monitoring import instrument_service_class

@instrument_service_class('CustomService')
class CustomService:
    def method_to_monitor(self):
        # Method will be automatically instrumented
        pass
```

### For Individual Functions

```python
from monitoring import instrument_function

@instrument_function
def function_to_monitor():
    # Function will be instrumented
    pass
```

### For Database Operations

```python
from monitoring import instrument_db_method

@instrument_db_method('custom_db_operation')
def custom_db_operation(self, ...):
    # Database operation will be instrumented
    pass
```

### For External API Calls

```python
from monitoring import instrument_api_method

@instrument_api_method('ExternalAPI', 'custom_api_call')
def custom_api_call(self, ...):
    # API call will be instrumented
    pass
``` 