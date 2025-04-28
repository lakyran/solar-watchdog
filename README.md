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

#### View Device Disruption Events (HTML)
- **Route**: `/device/disruptions/view`
- **Method**: GET
- **Query Parameters**:
  - `device_sn`: Device serial number (required)
  - `date`: Date in YYYY-MM-DD format (optional)
- **Description**: Displays disruption events in a human-readable HTML format.

### Inverter Management

#### Get Inverters List
- **Route**: `/inverters/list`
- **Method**: GET
- **Description**: Gets a list of all inverters in the database.

### Batch Operations

#### Batch Ingest History
- **Route**: `/devices/history/batch-ingest`
- **Method**: GET
- **Query Parameters**:
  - `date`: Date in YYYY-MM-DD format (optional)
  - `overwrite`: Whether to overwrite existing records (optional, default: false)
  - `store_records`: Whether to store the fetched records (optional, default: true)
- **Description**: Ingests generation history for all inverters.

#### Batch Analyze Disruptions
- **Route**: `/devices/disruptions/batch-analyze`
- **Method**: GET
- **Query Parameters**:
  - `start_date`: Start date in YYYY-MM-DD format (optional)
  - `end_date`: End date in YYYY-MM-DD format (optional, defaults to today)
  - `overwrite`: Whether to overwrite existing analysis (optional, default: true)
- **Description**: Analyzes disruptions for all inverters, processing each sequentially.

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
