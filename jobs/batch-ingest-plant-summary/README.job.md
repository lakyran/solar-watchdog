# Unisolar Watchdog Batch Ingest Plant Summary WebJob

This WebJob runs every 6 minutes to trigger the batch ingest process for all plant summaries in the Unisolar Watchdog Service.

## Files

- `batch-ingest-plant-summary.sh` - The main shell script that calls the `/api/plants/summary/batch-ingest` endpoint
- `requirements.job.txt` - Dependencies required by the WebJob
- `settings.job` - Configuration for WebJob scheduling using CRON expression

## Deployment Instructions

1. Create a ZIP file containing:
   - `batch-ingest-plant-summary.sh`
   - `requirements.job.txt` (rename to `requirements.txt` in the ZIP)
   - `settings.job`

2. Log in to the Azure Portal and navigate to your App Service.

3. In the left menu, under **Settings**, select **WebJobs**.

4. Click **+ Add**:
   - **Name**: UnisolarBatchIngestPlantSummary (or another descriptive name)
   - **File Upload**: Select the ZIP file created in step 1
   - **Type**: Triggered
   - **Triggers**: CRON Expression

5. Click **OK** to create the WebJob.

## CRON Expression

The WebJob is configured to run every 6 minutes using the CRON expression: `0 */6 * * * *`

- First position (0): At the 0th second
- Second position (*/6): Every 6th minute
- Remaining positions (* * * *): Every hour, every day, every month, every day of the week

## What This Job Does

This job:
1. Calls the `/api/plants/summary/batch-ingest` endpoint
2. Retrieves the latest energy summary data for all plants from the Growatt API
3. Updates the plant_energy_summary table in the database with the latest values

This ensures all plant summary data (total energy, daily energy, etc.) is kept up-to-date for dashboards and reporting.

## Troubleshooting

To check if the WebJob is running properly:

1. In the WebJobs section of your App Service, click on the name of your WebJob.
2. Click on **Logs** to view the WebJob execution logs.
3. Check for successful API calls and responses in the logs.
4. The log file `batch-ingest-plant-summary.log` will also contain detailed information. 