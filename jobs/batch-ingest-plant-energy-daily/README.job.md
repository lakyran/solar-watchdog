# Unisolar Watchdog Batch Ingest Plant Daily Energy WebJob

This WebJob runs every 6 hours to trigger the batch ingest process for daily energy generation data for all plants in the Unisolar Watchdog Service.

## Files

- `batch-ingest-plant-energy-daily.sh` - The main shell script that calls the `/api/plants/energy/daily/batch-ingest` endpoint
- `requirements.job.txt` - Dependencies required by the WebJob
- `settings.job` - Configuration for WebJob scheduling using CRON expression

## Deployment Instructions

1. Create a ZIP file containing:
   - `batch-ingest-plant-energy-daily.sh`
   - `requirements.job.txt` (rename to `requirements.txt` in the ZIP)
   - `settings.job`

2. Log in to the Azure Portal and navigate to your App Service.

3. In the left menu, under **Settings**, select **WebJobs**.

4. Click **+ Add**:
   - **Name**: UnisolarBatchIngestPlantEnergyDaily (or another descriptive name)
   - **File Upload**: Select the ZIP file created in step 1
   - **Type**: Triggered
   - **Triggers**: CRON Expression

5. Click **OK** to create the WebJob.

## CRON Expression

The WebJob is configured to run every 6 hours using the CRON expression: `0 0 */6 * * *`

- First position (0): At the 0th second
- Second position (0): At the 0th minute
- Third position (*/6): Every 6th hour
- Remaining positions (* * *): Every day, every month, every day of the week

## What This Job Does

This job:
1. Calls the `/api/plants/energy/daily/batch-ingest` endpoint
2. Retrieves daily energy generation data for all plants from the Growatt API over the default date range
3. Stores the data in the database

This ensures daily generation data remains accurate and up-to-date for analytics and reporting.

## Troubleshooting

To check if the WebJob is running properly:

1. In the WebJobs section of your App Service, click on the name of your WebJob.
2. Click on **Logs** to view the WebJob execution logs.
3. Check for successful API calls and responses in the logs.
4. The log file `batch-ingest-plant-energy-daily.log` will also contain detailed information.


