# Solar Watchdog Service

A monitoring and analysis service for solar power generation systems that ingests data from Growatt inverters, stores it in a database, analyzes generation patterns, and identifies disruption events.

## Overview

The Unisolar Watchdog Service is designed to:

- Fetch and store historical generation data from Growatt solar inverters
- Analyze generation patterns to identify disruptions or anomalies
- Store disruption events for further analysis and monitoring
- Provide API endpoints for data access and management
- Generate insights using AI to determine root causes of power disruptions

All timestamps in the system are handled in Indian Standard Time (IST, UTC+5:30).

## System Architecture

The solar monitoring system consists of several core components:

### Components
1. **Flask Web Application** (`app.py`) - Provides HTTP endpoints for various functions
2. **Core Modules** (`src/`) - Main business logic modules
   - **Watchdog Service** (`src/watchdog.py`) - Core business logic orchestration
   - **Growatt API Client** (`src/growatt.py`) - Handles communication with the Growatt solar monitoring API
   - **Azure Database Client** (`src/azure_db.py`) - Manages PostgreSQL database interactions
   - **AI Analysis Agent** (`src/ai_agent.py`) - Analyzes solar generation data for disruptions
3. **Service Layer** (`services/`) - Modular business logic implementation
4. **API Routes** (`routes/`) - HTTP endpoint handlers
5. **Automated WebJobs** - Scheduled tasks for batch operations (located in the `jobs/` directory)
6. **Monitoring System** (`monitoring/`) - OpenTelemetry-based monitoring for API routes, services, database operations, and external API calls

### Service Layer

The system implements a service-oriented architecture with specialized service classes:

1. **HistoryIngestionService** - Handles fetching and storing generation history data
2. **DisruptionAnalysisService** - Analyzes generation data to identify and store disruption events
3. **UserManagementService** - Manages user onboarding and user-related operations
4. **PlantManagementService** - Handles plant-specific operations and data collection

Each service encapsulates related business logic and database operations, promoting separation of concerns and maintainability.

### Key Features

#### User and Equipment Management
- Complete user onboarding workflow to register users, their plants, and inverter devices
- Database storage of user information, plants, inverters, and generation history
- API methods to fetch plant lists and device information

#### Data Collection
- Automated fetching and storing of solar generation data from Growatt API
- Support for historical data import and batch operations
- Device-specific data handling based on inverter type

#### Disruption Analysis
- AI-powered analysis to identify disruptions in power generation
- Detection of anomalies and potential issues in solar system performance
- Storage of disruption events with detailed analysis
- Date range analysis capabilities for historical data
- Background task support for long-running analyses

#### Monitoring and Reporting
- Dashboard functionality to view plant summaries and performance
- Current power output monitoring
- Plant energy summaries (daily, monthly, yearly, total generation)
- Carbon offset tracking
- Efficiency snapshot data for comparing plant performance

#### Scheduled Operations
- Automated WebJobs for recurring tasks:
  - Batch ingest of plant summaries (every 6 minutes)
  - Batch analysis of disruptions (every 10 minutes)
  - Batch ingest of generation history (scheduled regularly)
  - Batch ingest of plant energy daily data (every 6 hours)

### Database Schema

The system uses a PostgreSQL database with several tables:
- `users` - Stores user information
- `plants` - Stores solar plant details 
- `inverters` - Stores inverter/device information
- `power_gen_history` - Stores generation data points
- `disruption_events` - Stores detected disruption events
- `analysis_ledger` - Tracks analysis history
- `plant_energy_summary` - Stores energy summaries for plants

### Technical Design

The system follows a well-structured design pattern:
- **Modular Architecture**: Core business logic organized in `src/` directory
- **Service-oriented architecture** with clear separation of concerns
- **Import Structure**: Core modules imported with `src.` prefix for better organization
- Robust error handling and logging throughout
- Background task support for long-running operations
- Timezone handling for data consistency (IST standardization)
- Connection pooling for database efficiency (5-50 connections)
- Scheduled WebJobs for automated data processing

### Project Structure
```
src/                    # Core business logic modules
├── watchdog.py        # Main orchestration service
├── azure_db.py        # Database operations and connection pooling
├── growatt.py         # External Growatt API client
└── ai_agent.py        # AI analysis service

services/              # Domain-specific business services
├── history_ingestion_service.py
├── disruption_analysis_service.py
├── user_management_service.py
└── plant_management_service.py

routes/                # API route handlers
├── auth.py           # Authentication endpoints
├── devices.py        # Device management endpoints
├── plants.py         # Plant management endpoints
├── users.py          # User management endpoints
└── dashboard.py      # Dashboard endpoints

monitoring/            # OpenTelemetry instrumentation
jobs/                  # Automated WebJob configurations
docs/                  # Project documentation
```

### Recent Enhancements

Several valuable features were recently added to the system:

#### Service-Oriented Architecture
- Restructured codebase with specialized service classes for better code organization
- Improved maintainability and testability with clear separation of concerns
- Centralized dependencies and consistent interface patterns

#### Automated WebJobs for Continuous Monitoring
- **Batch Ingest Plant Summary** - Runs every 6 minutes to fetch and store the latest energy summaries for all plants
- **Batch Analyze Disruptions** - Runs every 10 minutes to analyze and identify disruption events for all inverters
- **Batch Ingest History** - Scheduled task to fetch and store generation history for all inverters

#### User Onboarding Workflow
- Complete API integration for fetching user plants and devices from Growatt
- Database methods for inserting users, plants, and inverters
- Exposed via a new `/users/onboard` POST endpoint
- Automatic discovery and configuration of solar equipment

#### Deployment Infrastructure
- GitHub workflow for deploying to a 'databox' slot on Azure App Service
- Branch-specific deployment configuration for development and testing
- WebJob configuration for scheduled tasks

#### Enhanced Disruption Analysis
- Improved date handling to start analysis from the first available record when no start date is provided
- Better tracking of analysis history through the analysis ledger
- More accurate detection of ongoing disruptions
- Background task management for long-running analyses
- AI agent enhancements with token usage logging for input, output, and total tokens
- Context pruning capabilities to reduce context size by 30% for better performance
- Improved disruption event filtering to exclude events shorter than 30 minutes

#### Comprehensive Monitoring System
- OpenTelemetry-based monitoring for all components
- Route instrumentation to track API requests, response times, and success/failure rates
- Service monitoring to track business operations
- Database operation monitoring for performance tracking
- External API call monitoring
- Integration with Azure Monitor for centralized logging and metrics
- Custom metrics collection for business-specific measurements
- Detailed documentation in the `docs/monitoring.md` file

## Installation

### Prerequisites

- Python 3.12 or higher
- PostgreSQL database
- Growatt API credentials
- Azure AI credentials (for AI analysis features)
- Testing framework (pytest) for development and testing

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/unisolar-watchdog-service.git
   cd unisolar-watchdog-service
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv unisolar_env
   source unisolar_env/bin/activate  # On Windows: unisolar_env\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file with the required environment variables:
   ```
   # Flask configuration
   FLASK_APP=app.py
   FLASK_ENV=development
   
   # PostgreSQL database configuration
   POSTGRES_HOST=your_postgres_host
   POSTGRES_PORT=5432
   POSTGRES_DB=your_database_name
   POSTGRES_USER=your_username
   POSTGRES_PASSWORD=your_password
   
   # Growatt API configuration
   GROWATT_API_URL=https://api.growatt.com
   GROWATT_API_TOKEN=your_api_token
   
   # Azure AI configuration
   PROJECT_CONNECTION_STRING_AI=your_azure_ai_connection_string
   
   # Azure Monitor configuration
   APPLICATIONINSIGHTS_CONNECTION_STRING=your_application_insights_connection_string
   ```

5. Run the application:
   ```
   flask run
   ```

## WebJobs Configuration

The system includes several WebJobs for automated tasks:

### Batch Ingest Plant Summary
- **Schedule**: Runs every 6 minutes (`0 */6 * * * *`)
- **Purpose**: Fetches and stores the latest energy summary data for all plants
- **Endpoint**: `/plants/summary/batch-ingest`

### Batch Analyze Disruptions
- **Schedule**: Runs every 10 minutes (`0 */10 * * * *`)
- **Purpose**: Analyzes disruptions for all inverters based on their latest analysis date
- **Endpoint**: `/devices/disruptions/batch-analyze`

### Batch Ingest History
- **Purpose**: Fetches and stores generation history for all inverters
- **Endpoint**: `/devices/history/batch-ingest`

### Batch Ingest Plant Energy Daily
- **Schedule**: Runs every 6 hours (`0 0 */6 * * *`)
- **Purpose**: Fetches and stores daily energy generation data for all plants over a date range
- **Endpoint**: `/plants/energy/daily/batch-ingest`

## API Routes

All API routes are prefixed with `/api` unless otherwise noted.

### Authentication

#### Login
- **Route**: `/api/auth/login`
- **Method**: POST
- **Request Body**:
  - `username`: Username for authentication (required)
  - `password`: User password (required)
  - `device_id`: Device identifier for push notifications (optional)
  - `device_token`: Device token for push notifications (optional)
  - `device_platform`: Platform of the device (android, ios) (optional)
- **Description**: Authenticate user and issue JWT tokens.

#### Refresh Token
- **Route**: `/api/auth/refresh`
- **Method**: POST
- **Headers**: `Authorization: Bearer <refresh_token>`
- **Description**: Issue a new access token using a valid refresh token.

#### Validate Token
- **Route**: `/api/auth/validate`
- **Method**: POST
- **Headers**: `Authorization: Bearer <access_token>`
- **Description**: Validate that an access token is still valid.

#### Register Device Token
- **Route**: `/api/auth/register_device_token`
- **Method**: POST
- **Headers**: `Authorization: Bearer <access_token>`
- **Request Body**:
  - `device_id`: Unique identifier for the device (required)
  - `token`: Device token for push notifications (required)
  - `device_platform`: Platform of the device (android, ios) (required)
  - `notification_enabled`: Whether notifications are enabled (optional, default: true)
- **Description**: Register a device token for push notifications.

### User Management

#### Get User Profile
- **Route**: `/api/users/me`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Description**: Get the current user's profile information.

#### List Users (Admin Only)
- **Route**: `/api/users/list`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Description**: Get a list of all users in the system (admin only).

#### Onboard New User (Admin Only)
- **Route**: `/api/users/onboard`
- **Method**: POST
- **Headers**: `Authorization: Bearer <access_token>`
- **Request Body**:
  - `username`: Username for the new user (required)
  - `user_id`: User ID from Growatt (required)
  - `vendor`: Vendor name (required)
  - `phone`: Phone number (optional)
  - `email`: Email address (optional)
  - `password`: Password (optional)
  - `role`: User role (optional)
  - `bootstrap_history`: Whether to bootstrap history (optional, default: true)
- **Description**: Onboards a new user with their plants and devices.

### Dashboard

#### Get User Dashboard
- **Route**: `/api/dashboard`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `username`: Username (optional, for admins to view other users' dashboards)
- **Description**: Gets dashboard data for a user including their plant details and summary.

### Device Management

#### List Devices
- **Route**: `/api/devices/list`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `username`: Username filter (optional, admin only)
- **Description**: Get a list of all inverters, optionally filtered by username.

#### Test Growatt Device History
- **Route**: `/api/devices/history/test`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (required)
  - `page`: Page number for pagination (default: 1)
- **Description**: Tests the Growatt API call to fetch device history without storing it.

#### Ingest Device Generation History
- **Route**: `/api/devices/history/ingest`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (optional, defaults to the latest record date or today)
  - `overwrite`: Whether to overwrite existing records (optional, default: false)
  - `store_records`: Whether to store the fetched records (optional, default: false)
- **Description**: Fetches and stores device generation history.

#### Get Device History
- **Route**: `/api/devices/history`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `plant_id`: Plant ID (alternative to device_sn)
  - `date`: Date in YYYY-MM-DD format (required)
- **Description**: Retrieves stored history records for a device on a specific date.

#### Batch Ingest Device History (Admin Only)
- **Route**: `/api/devices/history/batch-ingest`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `date`: Date in YYYY-MM-DD format (optional)
  - `overwrite`: Whether to overwrite existing records (optional, default: false)
  - `store_records`: Whether to store the fetched records (optional, default: true)
  - `device_sn`: Specific device serial number (optional)
- **Description**: Batch ingest generation history for all inverters.

### Disruption Analysis

#### Analyze Device Disruptions
- **Route**: `/api/devices/analyze_disruptions`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (optional, defaults to yesterday)
- **Description**: Analyzes generation data to identify disruptions without storing them.

#### Analyze and Store Disruptions
- **Route**: `/api/devices/analyze_and_store_disruptions`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (optional, defaults to yesterday)
- **Description**: Analyzes generation data and stores identified disruption events.

#### Analyze Disruptions for Date Range
- **Route**: `/api/devices/analyze_disruptions_range`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `start_date`: Start date in YYYY-MM-DD format (optional)
  - `end_date`: End date in YYYY-MM-DD format (optional, defaults to today)
  - `overwrite`: Whether to overwrite existing analysis (optional, default: true)
- **Description**: Analyzes disruptions over a date range as a background task.

#### Batch Analyze Disruptions (Admin Only)
- **Route**: `/api/devices/disruptions/batch-analyze`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `start_date`: Start date in YYYY-MM-DD format (optional)
  - `end_date`: End date in YYYY-MM-DD format (optional)
  - `overwrite`: Whether to overwrite existing analysis (optional, default: true)
- **Description**: Analyze disruptions for all inverters in the database.

#### Get Device Disruption Events
- **Route**: `/api/devices/disruption_events`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (optional)
- **Description**: Retrieves stored disruption events for a device.

### Plant Management

#### List Plants
- **Route**: `/api/plants/list`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `username`: Username filter (optional, admin only)
- **Description**: Get a list of all plants, optionally filtered by username.

#### Get Plant Summary
- **Route**: `/api/plants/summary`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `plant_id`: Plant ID (required)
- **Description**: Get energy summary for a specific plant.

#### Ingest Plant Summary
- **Route**: `/api/plants/summary/ingest`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `plant_id`: Plant ID (required)
- **Description**: Fetch plant energy summary from Growatt API and store it in the database.

#### Batch Ingest Plant Summaries (Admin Only)
- **Route**: `/api/plants/summary/batch-ingest`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Description**: Fetch and store energy summaries for all plants in the system.

#### Ingest Plant Energy Daily Data
- **Route**: `/api/plants/energy/daily/ingest`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `plant_id`: Plant ID (required)
  - `start_date`: Start date in YYYY-MM-DD format (optional)
  - `end_date`: End date in YYYY-MM-DD format (optional)
- **Description**: Fetch and store daily energy generation data for a plant over a date range.

#### Batch Ingest Plant Energy Daily Data (Admin Only)
- **Route**: `/api/plants/energy/daily/batch-ingest`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Query Parameters**:
  - `start_date`: Start date in YYYY-MM-DD format (optional)
  - `end_date`: End date in YYYY-MM-DD format (optional)
- **Description**: Fetch and store daily energy generation data for all plants over a date range.

### Task Management

#### Get Task Status
- **Route**: `/api/tasks/<task_id>`
- **Method**: GET
- **Headers**: `Authorization: Bearer <access_token>`
- **Parameters**:
  - `task_id`: ID of the background task
- **Description**: Gets the status of a background analysis task.

### Web Interface (No /api prefix)

#### Welcome Page
- **Route**: `/`
- **Method**: GET
- **Description**: Serve the welcome page.

#### View Disruption Events
- **Route**: `/disruptions/view`
- **Method**: GET
- **Query Parameters**:
  - `device_sn`: Device serial number (optional)
  - `date`: Date in YYYY-MM-DD format (optional)
- **Description**: Display disruption events for a device in a human-readable HTML format.

#### View Efficiency Snapshot
- **Route**: `/efficiency/view`
- **Method**: GET
- **Query Parameters**:
  - `min_eff`: Minimum efficiency (optional, default: 0)
  - `max_eff`: Maximum efficiency (optional, default: 100)
  - `plant_name`: Selected plant name for 7-day efficiency plot (optional)
- **Description**: Display efficiency snapshot in a human-readable HTML format.

## Service Architecture

The service layer is organized as follows:

### BaseService
- Common functionality for all services
- Shared resources like logging, database connections, and API clients

### HistoryIngestionService
- Manages the ingestion of generation history data
- Handles fetching, processing, and storing of device generation records
- Supports bootstrapping history for new users

### DisruptionAnalysisService
- Analyzes generation data to identify disruptions
- Manages background task execution for long-running analyses
- Tracks analysis history in the analysis ledger

### UserManagementService
- Handles user onboarding and management
- Manages user dashboard data and current power information
- Links users to their plants and devices

### PlantManagementService
- Manages plant-specific operations
- Handles plant summary and energy generation data
- Provides efficiency analysis and comparison
- Fetches and stores daily energy generation data for plants over date ranges
- Supports batch processing of daily energy data for all plants

## Timezone Handling

This application uses Indian Standard Time (IST, UTC+5:30) for all timestamp operations. This ensures consistent date/time handling across the application regardless of server location.

## Usage Example

To fetch and analyze yesterday's data for a specific inverter:

```
# Fetch the generation history
GET /device/history/ingest?device_sn=CLJACLR001&date=2023-07-15&overwrite=true&store_records=true

# Analyze for disruptions and store results
GET /device/analyze_and_store_disruptions?device_sn=CLJACLR001&date=2023-07-15

# View the disruption events
GET /device/disruption_events?device_sn=CLJACLR001&date=2023-07-15
```

For batch processing of all inverters:

```
# Ingest history for all inverters
GET /devices/history/batch-ingest?date=2023-07-15&overwrite=true

# Analyze disruptions for all inverters
GET /devices/disruptions/batch-analyze?start_date=2023-07-15&end_date=2023-07-15
```

## Environment Configuration

The application requires a `.env` file with the following variables:

```
# Application settings
FLASK_APP=app.py
FLASK_ENV=development
APP_VERSION=1.0.0

# Azure Database configuration
AZURE_DB_SERVER=your-db-server.database.windows.net
AZURE_DB_NAME=your-db-name
AZURE_DB_USER=your-db-user
AZURE_DB_PASSWORD=your-db-password
AZURE_DB_DRIVER={ODBC Driver 17 for SQL Server}

# JWT Authentication
JWT_SECRET_KEY=your-jwt-secret-key

# Monitoring configuration (used for both App Insights and OpenTelemetry)
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=your-instrumentation-key;IngestionEndpoint=https://your-region.in.applicationinsights.azure.com/

# OpenAI configuration (for AI agent)
OPENAI_API_KEY=your-openai-api-key

# Growatt API credentials
GROWATT_API_USER=your-growatt-username
GROWATT_API_PASSWORD=your-growatt-password
```

## Monitoring and Instrumentation

The application uses OpenTelemetry, a modern open-source observability framework, for comprehensive monitoring:

### OpenTelemetry Instrumentation

- **Service Monitoring**: All service classes are instrumented to track method execution with detailed spans
- **Database Monitoring**: Database operations are tracked with query information and execution times
- **API Monitoring**: External API calls to Growatt are monitored with detailed timing and response data
- **Azure Integration**: Telemetry is sent to Azure Monitor using the Azure Monitor OpenTelemetry Distro

This approach provides unified traces, metrics, and logs for better observability, making it easier to:

- Track request flows across services
- Identify performance bottlenecks
- Debug issues with detailed context
- Monitor system health in real-time

The OpenTelemetry implementation follows the vendor-neutral approach while leveraging Azure-specific capabilities when sending data to Azure Monitor.
