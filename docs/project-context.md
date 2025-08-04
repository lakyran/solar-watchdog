# Unisolar Watchdog Service - Project Context

## Project Overview
The Unisolar Watchdog Service is a Flask-based monitoring and analytics platform for solar power generation systems. It integrates with the Growatt API to collect device data, analyze performance disruptions using AI, and provide dashboard insights for users managing solar installations.

## Architecture Overview

### Core Components
- **Flask Application** (`app.py`) - Main web server with JWT authentication
- **Core Modules** (`src/`) - Main business logic modules
  - **Database Layer** (`src/azure_db.py`) - PostgreSQL connection pool and data operations
  - **External API Client** (`src/growatt.py`) - Growatt API integration for device data
  - **AI Agent** (`src/ai_agent.py`) - Azure OpenAI integration for disruption analysis
  - **Watchdog Service** (`src/watchdog.py`) - Main orchestration service
- **Service Layer** (`services/`) - Business logic organized by domain
- **Monitoring** (`monitoring/`) - OpenTelemetry instrumentation with Azure Monitor

### Key Services
1. **History Ingestion Service** - Fetches and stores device generation data
2. **Disruption Analysis Service** - AI-powered analysis of performance issues
3. **User Management Service** - User onboarding and authentication
4. **Plant Management Service** - Solar plant and device management

## Database Schema

### Core Tables
- `power_gen_history` - Time-series data for device power generation
- `disruption_events` - AI-analyzed performance disruptions
- `inverters` - Device registry with metadata
- `plants` - Solar plant information
- `users` - User accounts and roles

### Key Relationships
- Users own multiple plants
- Plants contain multiple devices (inverters)
- Devices generate history records and disruption events

## API Structure

### Authentication
- JWT-based authentication with refresh tokens
- Role-based access control (admin/user)
- Device-level access control

### Main Endpoints
- `/api/auth/*` - Authentication and token management
- `/api/users/*` - User management (admin only)
- `/api/devices/*` - Device operations and data retrieval
- `/api/plants/*` - Plant management and summaries
- `/api/dashboard/*` - User dashboard data
- `/api/tasks/*` - Background task status

## Development Patterns

### Error Handling
- Consistent JSON error responses with status/message/code
- Exception logging with OpenTelemetry context
- Graceful degradation for external API failures

### Data Processing Flow
1. **Ingestion**: Fetch data from Growatt API → Transform → Store in PostgreSQL
2. **Analysis**: Retrieve stored data → AI analysis → Store disruption events
3. **Presentation**: Query processed data → Format for dashboard → Return JSON

### Background Tasks
- Long-running operations (bulk analysis) use background task system
- Task status tracking with unique IDs
- Sequential processing to avoid API rate limits

## Configuration

### Environment Variables
- `POSTGRES_*` - Database connection settings
- `GROWATT_API_*` - External API credentials
- `AZURE_OPENAI_*` - AI service configuration
- `JWT_SECRET_KEY` - Authentication secret
- `APPLICATIONINSIGHTS_CONNECTION_STRING` - Monitoring

### Connection Pools
- Database: 5-50 connections (recently increased for scalability)
- External API: Single connection with 30s timeout

## Scaling Considerations

### Current Bottlenecks
- Synchronous external API calls
- Single-threaded Flask development server
- Memory-based background task storage
- No caching layer

### Performance Patterns
- Batch operations process devices sequentially
- Date-based queries on large time-series tables
- AI analysis can take 30+ seconds per device

## Code Organization

### Project Structure
```
src/                    # Core business logic modules
├── watchdog.py        # Main orchestration service
├── azure_db.py        # Database operations
├── growatt.py         # External API client
└── ai_agent.py        # AI analysis service

services/              # Domain-specific business services
├── history_ingestion_service.py
├── disruption_analysis_service.py
├── user_management_service.py
└── plant_management_service.py

routes/                # API route handlers
monitoring/            # OpenTelemetry instrumentation
```

### Service Layer Pattern
```python
# Services inherit from BaseService and use dependency injection
class HistoryIngestionService(BaseService):
    def __init__(self, db_client, growatt_client, ai_agent):
        # Service initialization with dependencies
```

### Import Pattern
```python
# Core modules are imported from src/
from src.watchdog import Watchdog
from src.azure_db import AzureDB
from src.growatt import GrowattAPI
from src.ai_agent import GrowattAIAgent
```

### Monitoring Integration
- All services instrumented with OpenTelemetry
- Database operations tracked with custom spans
- Request/response metrics collected

### Error Propagation
- Services return tuples `(data, status_code)` for errors
- Controllers handle tuple responses appropriately
- Consistent error message format across all endpoints

## Development Guidelines

### Adding New Features
1. Create service class in `services/` directory
2. Add monitoring instrumentation
3. Create route handlers in `routes/` directory
4. Add authentication/authorization checks
5. Update database schema if needed

### Testing Patterns
- Use device access control helper functions
- Mock external API calls for unit tests
- Test both success and error scenarios

### Deployment
- Currently uses Flask development server
- Production should use Gunicorn with multiple workers
- Requires PostgreSQL database and Azure services

## Common Operations

### Device Data Flow
```python
# Import core modules
from src.growatt import GrowattAPI
from src.azure_db import AzureDB

# 1. Fetch from external API
history_data = growatt_client.fetch_device_history(device_sn, metadata, date, date)

# 2. Transform for database
db_entries = growatt_client.process_history_data_for_db(history_data, device_sn, date, metadata)

# 3. Store in database
result = db_client.insert_history_into_database(db_entries)
```

### AI Analysis Pattern
```python
# Import core modules
from src.azure_db import AzureDB
from src.ai_agent import GrowattAIAgent

# 1. Get device data
records = db_client.get_device_records_by_date(device_sn, date)

# 2. AI analysis
analysis = ai_agent.analyze_device_generation_data(records, metadata)

# 3. Store results
db_client.insert_disruption_events(analysis['disruption_events'], metadata)
```

This context should provide sufficient understanding for any LLM coding agent to contribute effectively to the project.