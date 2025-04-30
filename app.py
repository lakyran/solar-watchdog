from flask import Flask, jsonify, request, render_template, send_from_directory
import os
import logging
from dotenv import load_dotenv
from ai_agent import GrowattAIAgent
import asyncio
from watchdog import Watchdog
import time
from datetime import datetime, timedelta
import pytz
import threading
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logger.info("Starting Unisolar Watchdog Service")

# Load environment variables
load_dotenv()

# Initialize the app
app = Flask(__name__, static_folder='static')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

# Initialize the Watchdog object
watchdog = Watchdog(app)

# Define the IST timezone
ist_timezone = pytz.timezone('Asia/Kolkata')

def get_current_time_ist():
    """
    Get the current time in Indian Standard Time (IST)
    
    Returns:
        datetime: Current datetime in IST
    """
    return datetime.now(ist_timezone)

@app.route('/', methods=['GET'])
def hello():
    return 'Hello from Azure App Service!'

@app.route('/device/history/test', methods=['GET'])
def test_growatt_device_history():
    """Test the Growatt API call to fetch device history without storing it"""
    try:
        # Get parameters from request
        device_sn = request.args.get('device_sn')
        date_str = request.args.get('date')
        page = int(request.args.get('page', '1'))
        
        # Validate required parameters
        if not device_sn:
            return jsonify({'status': 'error', 'message': 'device_sn parameter is required'}), 400
        if not date_str:
            return jsonify({'status': 'error', 'message': 'date parameter is required'}), 400
            
        # Get device metadata from inverter records
        inverter_metadata = watchdog.db_client.get_inverter_record(device_sn)
        
        # Check if inverter record exists
        if not inverter_metadata:
            return jsonify({
                'status': 'error', 
                'message': f'No inverter record found for device {device_sn}'
            }), 404
        
        # Call the Growatt API directly to fetch history data without storing it
        history_data = watchdog.growatt_client.fetch_device_history(
            device_sn=device_sn,
            device_metadata=inverter_metadata,
            start_date=date_str,
            end_date=date_str,
            page=page
        )
        
        # Return the raw API response with some additional metadata
        return jsonify({
            'status': 'success',
            'device_sn': device_sn,
            'date': date_str,
            'page': page,
            'device_metadata': {
                'user_name': inverter_metadata.get('user_name', ''),
                'device_type': inverter_metadata.get('device_type', ''),
                'vendor': inverter_metadata.get('vendor', ''),
                'device_oem': inverter_metadata.get('device_oem', '')
            },
            'history_data': history_data
        })
        
    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/device/history/ingest', methods=['GET'])
def ingest_device_generation_history():
    try:
        # Get device_sn and date from request data
        device_sn = request.args.get('device_sn')
        date = request.args.get('date', None)
        overwrite = request.args.get('overwrite', False)
        store_records = request.args.get('store_records', False)
        # Validate that both parameters are provided
        if not device_sn:
            return jsonify({'error': 'device_sn parameter is required'}), 400
            
        response = watchdog.fetch_and_store_device_generation_history(device_sn, date, overwrite, store_records)
        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/device/history', methods=['GET'])
def get_device_history():
    try:
        # Get device_sn and date from request data
        device_sn = request.args.get('device_sn')
        date = request.args.get('date')
        
        # Validate that both parameters are provided
        if not device_sn or not date:
            return jsonify({'error': 'Both device_sn and date parameters are required'}), 400
            
        records = watchdog.db_client.get_device_records_by_date(device_sn, date)
        return jsonify({
            'device_sn': device_sn,
            'date': date,
            'record_count': len(records),
            'records': records
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/device/analyze_disruptions', methods=['GET'])
def analyze_device_generation_disruptions():
    try:
        # Get device_sn and date from request data
        device_sn = request.args.get('device_sn')
        date_str = request.args.get('date', None)
        
        # Validate that device_sn is provided
        if not device_sn:
            return jsonify({'error': 'device_sn parameter is required'}), 400
            
        return jsonify(watchdog.analyze_device_generation_data_route(device_sn, date_str))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/device/analyze_and_store_disruptions', methods=['GET'])
def analyze_and_store_device_disruptions():
    try:
        # Get device_sn and date from request data
        device_sn = request.args.get('device_sn')
        date_str = request.args.get('date', None)
        
        # Validate that device_sn is provided
        if not device_sn:
            return jsonify({'error': 'device_sn parameter is required'}), 400
            
        return jsonify(watchdog.analyze_device_generation_data_and_store_disruptions_route(device_sn, date_str))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/device/analyze_disruptions_range', methods=['GET'])
def analyze_device_disruptions_date_range():
    """Analyze disruptions for a device over a range of dates (as a background task)"""
    try:
        # Get parameters from request
        device_sn = request.args.get('device_sn')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        overwrite = request.args.get('overwrite', 'true')
        if overwrite.lower() == 'false':
            overwrite = False
        else:
            overwrite = True
        
        # Delegate to the watchdog service to handle all logic including date population
        result = watchdog.analyze_device_disruptions_date_range(
            device_sn=device_sn, 
            start_date=start_date, 
            end_date=end_date, 
            overwrite=overwrite
        )
        
        # If the result is a tuple with status code, handle it
        if isinstance(result, tuple) and len(result) > 1:
            return jsonify(result[0]), result[1]
            
        # Return the result
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get the status of a background task"""
    task_status = watchdog.get_task_status(task_id)
    
    # If the result is a tuple with status code, handle it
    if isinstance(task_status, tuple) and len(task_status) > 1:
        return jsonify(task_status[0]), task_status[1]
    
    # Otherwise return the result as JSON
    return jsonify(task_status)

@app.route('/device/disruption_events', methods=['GET'])
def get_device_disruption_events():
    """Get disruption events for a device, optionally filtered by date"""
    try:
        # Get device_sn and optional date from request data
        device_sn = request.args.get('device_sn')
        date_str = request.args.get('date', None)
        
        # Validate that device_sn is provided
        if not device_sn:
            return jsonify({'status': 'error', 'message': 'device_sn parameter is required'}), 400
            
        # Call the watchdog method to get disruption events
        result = watchdog.get_device_disruption_events_route(device_sn, date_str)
        
        # If the result is a tuple with status code, handle it
        if isinstance(result, tuple):
            return jsonify(result[0]), result[1]
            
        # Otherwise, return the result as JSON
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/device/disruptions/view', methods=['GET'])
def view_device_disruption_events():
    """Display disruption events for a device in a human-readable HTML format"""
    try:
        # Get device_sn and optional date from request data
        device_sn = request.args.get('device_sn')
        date_str = request.args.get('date', None)
        
        # Get the list of inverters for the dropdown
        try:
            inverters = watchdog.db_client.get_inverters_list()
        except Exception as e:
            logger.error(f"Error fetching inverters list: {str(e)}")
            inverters = []
        
        # Validate that device_sn is provided
        if not device_sn:
            return render_template('disruption_events.html', 
                                  device_sn='',
                                  date=None,
                                  events=[],
                                  inverters=inverters,
                                  error='device_sn parameter is required')
            
        # Call the watchdog method to get disruption events
        result = watchdog.get_device_disruption_events_route(device_sn, date_str)
        
        # If the result is a tuple with status code, handle the error
        if isinstance(result, tuple):
            return render_template('disruption_events.html', 
                                  device_sn=device_sn,
                                  date=date_str,
                                  events=[],
                                  inverters=inverters,
                                  error=result[0].get('message', 'Unknown error'))
            
        # Extract the events from the result
        events = result.get('disruption_events', [])
        
        # Render the template with the data
        return render_template('disruption_events.html', 
                              device_sn=device_sn,
                              date=date_str if date_str else result.get('date'),
                              events=events,
                              inverters=inverters)
                              
    except Exception as e:
        return render_template('disruption_events.html', 
                              device_sn=device_sn if 'device_sn' in locals() else '',
                              date=date_str if 'date_str' in locals() else None,
                              events=[],
                              inverters=[],
                              error=str(e))

@app.route('/inverters/list', methods=['GET'])
def get_inverters_list():
    """Get a list of all inverters in the database, optionally filtered by username"""
    try:
        # Get optional username parameter
        username = request.args.get('username', None)
        
        # Get the list of inverters from the database
        inverters = watchdog.db_client.get_inverters_list(username)
        
        # Return the list as JSON
        return jsonify({
            'status': 'success',
            'count': len(inverters),
            'username_filter': username,
            'inverters': inverters
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/devices/history/batch-ingest', methods=['GET'])
def batch_ingest_inverters_history():
    """Get a list of all inverters and ingest generation history for each one"""
    try:
        # Optional query parameters
        date = request.args.get('date', None)
        overwrite = request.args.get('overwrite', 'false')
        if overwrite.lower() == 'true':
            overwrite = True
        else:
            overwrite = False
        store_records = request.args.get('store_records', 'true')
        if store_records.lower() == 'false':
            store_records = False
        else:
            store_records = True
        
        # Get the list of all inverters
        inverters = watchdog.db_client.get_inverters_list()
        
        # Track results for each inverter
        results = []
        
        # Process each inverter
        for inverter in inverters:
            device_sn = inverter['device_sn']
            device_results = []
            current_date = date
            
            try:
                # Keep fetching history until we get a 'skipped' status
                while True:
                    # Ingest generation history for this inverter
                    ingest_result = watchdog.fetch_and_store_device_generation_history(
                        device_sn, current_date, overwrite, store_records)
                    
                    # Handle case where response is a tuple (error response)
                    if isinstance(ingest_result, tuple):
                        error_data, status_code = ingest_result
                        # Create a standardized error result
                        ingest_result = {
                            'device_id': device_sn,
                            'date': current_date,
                            'status': 'error',
                            'error': error_data.get('error', 'Unknown error'),
                            'status_code': status_code
                        }
                        # Break the loop on error
                        device_results.append(ingest_result)
                        break
                    
                    # Add device info to the result
                    ingest_result['user_name'] = inverter.get('user_name', '')
                    ingest_result['device_type'] = inverter.get('device_type', '')
                    
                    # Add to device results
                    device_results.append(ingest_result)

                    # If date in the result is today, we're done with this device
                    if ingest_result.get('date') == get_current_time_ist().strftime('%Y-%m-%d'):
                        break

                    # Wait for 2 seconds before fetching the next page
                    time.sleep(2)
                    
                # Add all results for this device
                results.append({
                    'device_id': device_sn,
                    'user_name': inverter.get('user_name', ''),
                    'device_type': inverter.get('device_type', ''),
                    'status': 'success',
                    'results_count': len(device_results),
                    'results': device_results
                })
                
            except Exception as e:
                # If one inverter fails, continue with others but log the error
                logger.error(f"Error ingesting history for device {device_sn}: {str(e)}")
                results.append({
                    'device_id': device_sn,
                    'user_name': inverter.get('user_name', ''),
                    'device_type': inverter.get('device_type', ''),
                    'status': 'error',
                    'error': str(e),
                    'partial_results': device_results
                })
        
        # Return the aggregated results
        return jsonify({
            'status': 'success',
            'total_inverters': len(inverters),
            'processed_inverters': len(results),
            'date': date,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/devices/disruptions/batch-analyze', methods=['GET'])
def batch_analyze_inverters_disruptions():
    """Analyze disruptions for all inverters in the database, processing each one sequentially"""
    try:
        # Get parameters from request
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        overwrite = request.args.get('overwrite', 'true')
        if overwrite.lower() == 'false':
            overwrite = False
        else:
            overwrite = True

        if start_date and end_date and start_date > end_date:
            return jsonify({'status': 'error', 'message': 'start_date must be before end_date'}), 400
            
        # Get the list of all inverters
        inverters = watchdog.db_client.get_inverters_list()
        
        # Track results for each inverter
        results = []
        total_inverters = len(inverters)
        processed_inverters = 0
        failed_inverters = 0
        
        # Process each inverter sequentially
        for inverter in inverters:
            device_sn = inverter['device_sn']
            device_name = inverter.get('user_name', '')
            
            logger.info(f"Processing device {device_sn} ({device_name})")
            
            try:
                # Call the existing analyze_device_disruptions_date_range route
                analysis_result = watchdog.analyze_device_disruptions_date_range(
                    device_sn=device_sn, 
                    start_date=start_date, 
                    end_date=end_date, 
                    overwrite=overwrite
                )
                
                # If the result is a tuple with an error status code, handle it
                if isinstance(analysis_result, tuple) and len(analysis_result) > 1:
                    error_data, status_code = analysis_result
                    if status_code >= 400:
                        results.append({
                            'device_sn': device_sn,
                            'user_name': device_name,
                            'status': 'error',
                            'error': error_data.get('message', 'Unknown error'),
                            'status_code': status_code
                        })
                        failed_inverters += 1
                        continue

                task_id = analysis_result.get('task_id') if isinstance(analysis_result, dict) else None
                
                if task_id:
                    # Wait for the task to complete before moving to the next inverter
                    while True:
                        # Use the watchdog's get_task_status method
                        task_status = watchdog.get_task_status(task_id)
                        logger.debug(f"Task status: {task_status}")
                        
                        # If the result is a tuple with a status code, handle it
                        if isinstance(task_status, tuple) and len(task_status) > 1:
                            task_data, status_code = task_status
                            if status_code == 404:
                                # Task not found
                                results.append({
                                    'device_sn': device_sn,
                                    'user_name': device_name,
                                    'status': 'error',
                                    'error': 'Task not found',
                                    'task_id': task_id
                                })
                                failed_inverters += 1
                                break
                        else:
                            # Normal task data
                            task_data = task_status
                            
                        # Check task status
                        status = task_data.get('status')
                        logger.debug(f"Task status: {status}")
                        
                        if status == watchdog.TASK_STATUS['COMPLETED']:
                            results.append({
                                'device_sn': device_sn,
                                'user_name': device_name,
                                'status': 'success',
                                'task_id': task_id,
                                'task_data': task_data
                            })
                            processed_inverters += 1
                            break
                        elif status == watchdog.TASK_STATUS['FAILED']:
                            results.append({
                                'device_sn': device_sn,
                                'user_name': device_name,
                                'status': 'error',
                                'error': task_data.get('error', 'Task failed'),
                                'task_id': task_id
                            })
                            failed_inverters += 1
                            break
                        
                        # Wait before checking again
                        time.sleep(2)
                else:
                    # No task ID, immediate result
                    results.append({
                        'device_sn': device_sn,
                        'user_name': device_name,
                        'status': 'success',
                        'result': analysis_result
                    })
                    processed_inverters += 1
                    
            except Exception as e:
                logger.error(f"Error processing device {device_sn}: {str(e)}")
                results.append({
                    'device_sn': device_sn,
                    'user_name': device_name,
                    'status': 'error',
                    'error': str(e)
                })
                failed_inverters += 1
        
        # Return the aggregated results
        return jsonify({
            'status': 'success',
            'total_inverters': total_inverters,
            'processed_inverters': processed_inverters,
            'failed_inverters': failed_inverters,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run()