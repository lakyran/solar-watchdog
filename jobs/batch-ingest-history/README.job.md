# Unisolar Watchdog Batch Ingest WebJob

This WebJob runs every 6 minutes to trigger the batch ingest process for all inverters in the Unisolar Watchdog Service.

## Files

- `run.py` - The main Python script that calls the `/history/batch-ingest` endpoint
- `requirements.job.txt` - Dependencies required by the WebJob
- `settings.job` - Configuration for WebJob scheduling using CRON expression

## Deployment Instructions

1. Create a ZIP file containing:
   - `run.py`
   - `requirements.job.txt` (rename to `requirements.txt` in the ZIP)
   - `settings.job`

2. Log in to the Azure Portal and navigate to your App Service.

3. In the left menu, under **Settings**, select **WebJobs**.

4. Click **+ Add**:
   - **Name**: UnisolarBatchIngest (or another descriptive name)
   - **File Upload**: Select the ZIP file created in step 1
   - **Type**: Triggered
   - **Triggers**: CRON Expression

5. Click **OK** to create the WebJob.

## CRON Expression

The WebJob is configured to run every 6 minutes using the CRON expression: `0 */6 * * * *`

- First position (0): At the 0th second
- Second position (*/6): Every 6th minute
- Remaining positions (* * * *): Every hour, every day, every month, every day of the week

## Troubleshooting

To check if the WebJob is running properly:

1. In the WebJobs section of your App Service, click on the name of your WebJob.
2. Click on **Logs** to view the WebJob execution logs.
3. Check for successful API calls and responses in the logs. 