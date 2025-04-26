from flask import Flask, jsonify, request, render_template
import os
from dotenv import load_dotenv
from ai_agent import GrowattAIAgent
import asyncio
from watchdog import Watchdog
import time
from datetime import datetime, timedelta
import threading
import uuid

# Load environment variables
load_dotenv()

# Initialize the app
app = Flask(__name__)

# Initialize the Watchdog object
watchdog = Watchdog(app)

@app.route('/', methods=['GET'])
def hello():
    return 'Hello from Azure App Service!'

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
        
        # Validate required parameters
        if not device_sn:
            return jsonify({'status': 'error', 'message': 'device_sn parameter is required'}), 400
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            # Try to get the latest analysis date from the database
            latest_analysis_date = watchdog.get_latest_analysis_date_for_device(device_sn)
            print(f"Latest analysis date for device {device_sn}: {latest_analysis_date}")
            if latest_analysis_date:
                if latest_analysis_date == end_date:
                    # Re-analyze is okay for the current day, if after 6am and before 7pm
                    if datetime.now() > datetime.strptime('06:00', '%H:%M') and datetime.now() < datetime.strptime('19:00', '%H:%M'):
                        start_date = latest_analysis_date
                    else:
                        # Use the day after the latest analysis as the start date
                        return jsonify({'status': 'success', 'message': 'Analysis already completed for today'}), 200
                else:
                    # Use the day after the latest analysis as the start date
                    start_date = (latest_analysis_date + timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                # Default to 15 days before end_date if no previous analysis exists
                start_date = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')

        print(f"Start date: {start_date}")
        print(f"End date: {end_date}")
        # Validate date format
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid date format. Use YYYY-MM-DD'}), 400
            
        # Check that start date is before end date
        if start > end:
            return jsonify({'status': 'error', 'message': 'start_date must be before end_date'}), 400
            
        # Delegate to the watchdog service to handle the background task
        result = watchdog.analyze_device_disruptions_date_range(device_sn, start_date, end_date, overwrite)
        
        # Return the result
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get the status of a background task"""
    if task_id not in watchdog.background_tasks:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404
        
    task = watchdog.background_tasks[task_id]
    
    # If task is completed, include the result
    if task['status'] == watchdog.TASK_STATUS['COMPLETED']:
        return jsonify({
            'task_id': task_id,
            'status': task['status'],
            'created_at': task['created_at'],
            'completed_at': task.get('completed_at'),
            'result': task.get('result')
        })
    # If task failed, include the error
    elif task['status'] == watchdog.TASK_STATUS['FAILED']:
        return jsonify({
            'task_id': task_id,
            'status': task['status'],
            'created_at': task['created_at'],
            'completed_at': task.get('completed_at'),
            'error': task.get('error')
        })
    # If task is still running, include progress information
    else:
        return jsonify({
            'task_id': task_id,
            'status': task['status'],
            'created_at': task['created_at'],
            'progress': task.get('progress', {})
        })

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
            print(f"Error fetching inverters list: {str(e)}")
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
    """Get a list of all inverters in the database"""
    try:
        # Get the list of inverters from the database
        inverters = watchdog.db_client.get_inverters_list()
        
        # Return the list as JSON
        return jsonify({
            'status': 'success',
            'count': len(inverters),
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
        overwrite = request.args.get('overwrite', False)
        store_records = request.args.get('store_records', True)
        
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
                    
                    # If status is skipped, we're done with this device
                    if ingest_result.get('status') == 'skipped':
                        break
                    
                    # If there was a date change in the result, update our current date
                    if current_date != ingest_result.get('date'):
                        current_date = ingest_result.get('date')
                    
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
                print(f"Error ingesting history for device {device_sn}: {str(e)}")
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

if __name__ == '__main__':
    app.run()