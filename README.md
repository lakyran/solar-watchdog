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
2. **Watchdog Service** (`watchdog.py`) - Core business logic orchestration
3. **Service Layer** (`services/`) - Modular business logic implementation
4. **Growatt API Client** (`growatt.py`) - Handles communication with the Growatt solar monitoring API
5. **Azure Database Client** (`azure_db.py`) - Manages PostgreSQL database interactions
6. **AI Analysis Agent** (`ai_agent.py`) - Analyzes solar generation data for disruptions
7. **Automated WebJobs** - Scheduled tasks for batch operations (located in the `jobs/` directory)

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
- Service-oriented architecture with clear separation of concerns
- Robust error handling and logging throughout
- Background task support for long-running operations
- Timezone handling for data consistency (IST standardization)
- Connection pooling for database efficiency
- Scheduled WebJobs for automated data processing

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

## Installation

### Prerequisites

- Python 3.12 or higher
- PostgreSQL database
- Growatt API credentials
- Azure AI credentials (for AI analysis features)

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

## API Routes

### Device History Management

#### Test Growatt Device History
- **Route**: `/device/history/test`
- **Method**: GET
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (required)
  - `page`: Page number for pagination (default: 1)
- **Description**: Tests the Growatt API call to fetch device history without storing it.

#### Ingest Device Generation History
- **Route**: `/device/history/ingest`
- **Method**: GET
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (optional, defaults to the latest record date or today)
  - `overwrite`: Whether to overwrite existing records (optional, default: false)
  - `store_records`: Whether to store the fetched records (optional, default: false)
- **Description**: Fetches and stores device generation history.

#### Get Device History
- **Route**: `/device/history`
- **Method**: GET
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (required)
- **Description**: Retrieves stored history records for a device on a specific date.

### Disruption Analysis

#### Analyze Device Disruptions
- **Route**: `/device/analyze_disruptions`
- **Method**: GET
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (optional, defaults to yesterday)
- **Description**: Analyzes generation data to identify disruptions without storing them.

#### Analyze and Store Disruptions
- **Route**: `/device/analyze_and_store_disruptions`
- **Method**: GET
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (optional, defaults to yesterday)
- **Description**: Analyzes generation data and stores identified disruption events.

#### Analyze Disruptions for Date Range
- **Route**: `/device/analyze_disruptions_range`
- **Method**: GET
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `start_date`: Start date in YYYY-MM-DD format (optional)
  - `end_date`: End date in YYYY-MM-DD format (optional, defaults to today)
  - `overwrite`: Whether to overwrite existing analysis (optional, default: true)
- **Description**: Analyzes disruptions over a date range as a background task.

#### Get Task Status
- **Route**: `/tasks/<task_id>`
- **Method**: GET
- **Parameters**:
  - `task_id`: ID of the background task
- **Description**: Gets the status of a background analysis task.

#### Get Device Disruption Events
- **Route**: `/device/disruption_events`
- **Method**: GET
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (optional)
- **Description**: Retrieves stored disruption events for a device.

### User Management

#### Onboard New User
- **Route**: `/users/onboard`
- **Method**: POST
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

#### Get User Dashboard Data
- **Route**: `/users/dashboard`
- **Method**: GET
- **Query Parameters**:
  - `username`: Username (required)
- **Description**: Gets dashboard data for a user.

#### Get Current Power for User
- **Route**: `/users/current-power`
- **Method**: GET
- **Query Parameters**:
  - `username`: Username (required)
  - `plant_id`: Plant ID (optional)
- **Description**: Gets current power output for a user's plants.

### Plant Management

#### Fetch and Store Plant Summary
- **Route**: `/plants/summary`
- **Method**: GET
- **Query Parameters**:
  - `plant_id`: Plant ID (required)
- **Description**: Fetches and stores plant summary data.

#### Fetch and Store Plant Energy Daily Generation
- **Route**: `/plants/energy/daily`
- **Method**: GET
- **Query Parameters**:
  - `plant_id`: Plant ID (required)
  - `start_date`: Start date in YYYY-MM-DD format (optional)
  - `end_date`: End date in YYYY-MM-DD format (optional)
- **Description**: Fetches and stores plant energy daily generation data.

#### Get Efficiency Snapshot Data
- **Route**: `/plants/efficiency/snapshot`
- **Method**: GET
- **Query Parameters**:
  - `min_eff`: Minimum efficiency (optional, default: 0)
  - `max_eff`: Maximum efficiency (optional, default: 100)
  - `plant_name_selected`: Selected plant name (optional)
- **Description**: Gets efficiency snapshot data for plants.

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
