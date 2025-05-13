# Unisolar Watchdog Batch Analysis WebJob

This WebJob runs every 10 minutes to trigger the batch analysis process for disruptions in all inverters in the Unisolar Watchdog Service.

## Files

- `batch-analyze-disruptions.sh` - The main shell script that calls the `/api/devices/disruptions/batch-analyze` endpoint
- `requirements.job.txt` - Dependencies required by the WebJob (if using Python instead of bash)
- `settings.job` - Configuration for WebJob scheduling using CRON expression

## Purpose

This job performs the following tasks:
1. Calls the batch analysis endpoint that processes all inverters in sequence
2. For each inverter, it analyzes disruptions in solar generation based on their latest analysis date
3. Stores disruption events and updates the analysis ledger with the latest date
4. Logs the results of the batch process

## Deployment Instructions

1. Create a ZIP file containing:
   - `batch-analyze-disruptions.sh`
   - `settings.job`
   - `requirements.job.txt` (if needed)

2. Log in to the Azure Portal and navigate to your App Service.

3. In the left menu, under **Settings**, select **WebJobs**.

4. Click **+ Add**:
   - **Name**: UnisolarBatchAnalysis (or another descriptive name)
   - **File Upload**: Select the ZIP file created in step 1
   - **Type**: Triggered
   - **Triggers**: CRON Expression

5. Click **OK** to create the WebJob.

## CRON Expression

The WebJob is configured to run every 10 minutes using the CRON expression: `0 */10 * * * *`

- First position (0): At the 0th second
- Second position (*/10): Every 10th minute
- Remaining positions (* * * *): Every hour, every day, every month, every day of the week

## Troubleshooting

To check if the WebJob is running properly:

1. In the WebJobs section of your App Service, click on the name of your WebJob.
2. Click on **Logs** to view the WebJob execution logs.
3. Check for successful API calls and responses in the logs.
4. The batch analysis may take some time as it processes each inverter sequentially.

## Manual Triggering

To trigger the WebJob manually for testing or to run an out-of-schedule analysis:

1. In the WebJobs section of your App Service, locate your WebJob.
2. Select the WebJob and click on **Run**.
3. Monitor the logs to see the progress and results. 