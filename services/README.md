# Service Layer Architecture

This package implements a service layer for the Unisolar Watchdog Service. The service layer is responsible for implementing business logic and acts as a bridge between the routes (controllers) and the data access layer.

## Architecture Overview

The service layer follows a few key principles:
- **Separation of Concerns**: Each service has a specific responsibility
- **Dependency Injection**: Services receive their dependencies through constructor parameters
- **Composability**: Services can use other services when needed
- **Reusability**: Services are designed to be reused across the application

## Services Structure

### BaseService

`BaseService` is the parent class that all services inherit from. It provides:
- Common functionality (timezone handling, logging)
- Access to shared resources (database, API clients)

### HistoryIngestionService

Responsible for:
- Fetching and storing device generation history
- Bootstrapping historical data for new users
- Retrieving device history records

### DisruptionAnalysisService

Responsible for:
- Analyzing device generation data to detect disruptions
- Processing AI analysis of generation patterns
- Storing disruption events in the database
- Managing background tasks for date range analysis

### UserManagementService

Responsible for:
- User onboarding and management
- Dashboard data retrieval
- Current power calculation for users

### PlantManagementService

Responsible for:
- Plant summary management
- Energy generation data processing
- Efficiency data calculation and reporting

## Usage

The Watchdog class now acts as an orchestrator, forwarding requests to the appropriate service. This keeps the codebase more maintainable and easier to test.

Example:

```python
# Initialize services
history_service = HistoryIngestionService(
    db_client=db_client,
    growatt_client=growatt_client
)

# Use the service
result = history_service.fetch_and_store_device_generation_history(
    device_sn='DEVICE_SN',
    date_str='2023-01-01'
)
```

## Benefits

This architecture provides several advantages:
- **Modularity**: Easy to maintain and extend
- **Testability**: Services can be tested in isolation
- **Readability**: Clear separation of responsibilities
- **Flexibility**: Services can be composed and reused
- **Scalability**: Easier to distribute functionality as the application grows 