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
def analyze_and_store_disruptions():
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
    
# Store for background tasks
background_tasks = {}

# Task status constants
TASK_STATUS = {
    'PENDING': 'pending',
    'RUNNING': 'running',
    'COMPLETED': 'completed',
    'FAILED': 'failed'
}

def run_date_range_analysis(task_id, device_sn, start_date, end_date):
    """
    Background function to run date range analysis
    """
    try:
        task = background_tasks[task_id]
        task['status'] = TASK_STATUS['RUNNING']
        
        # Convert dates
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Analyze each day in the range
        current_date = start
        all_results = []
        days_processed = 0
        days_total = (end - start).days + 1
        
        while current_date <= end:
            date_str = current_date.strftime('%Y-%m-%d')
            print(f"Analyzing data for device {device_sn} on {date_str}")
            
            # Update task progress
            task['progress'] = {
                'days_processed': days_processed,
                'days_total': days_total,
                'current_date': date_str
            }
            
            # Get analysis for this date
            result = watchdog.analyze_device_generation_data_and_store_disruptions_route(device_sn, date_str)
            
            # Skip error responses
            if isinstance(result, tuple) and len(result) > 1 and result[1] >= 400:
                print(f"Error analyzing {date_str}: {result[0]}")
                current_date += timedelta(days=1)
                days_processed += 1
                # Add sleep to avoid hammering the API
                time.sleep(1)
                continue
                
            # Add date to the result
            if isinstance(result, dict):
                result['date'] = date_str
                all_results.append(result)
            
            # Move to next day
            current_date += timedelta(days=1)
            days_processed += 1
            
            # Add sleep to avoid hammering the API
            time.sleep(1)
        
        # Prepare response
        response = {
            'device_sn': device_sn,
            'start_date': start_date,
            'end_date': end_date,
            'days_analyzed': len(all_results),
            'results': all_results
        }
        
        # Update task
        task['status'] = TASK_STATUS['COMPLETED']
        task['result'] = response
        task['completed_at'] = datetime.now().isoformat()
        
    except Exception as e:
        print(f"Background task error: {str(e)}")
        if task_id in background_tasks:
            background_tasks[task_id]['status'] = TASK_STATUS['FAILED']
            background_tasks[task_id]['error'] = str(e)
            background_tasks[task_id]['completed_at'] = datetime.now().isoformat()

@app.route('/device/analyze_disruptions_range', methods=['GET'])
def analyze_device_disruptions_date_range():
    """Analyze disruptions for a device over a range of dates (as a background task)"""
    try:
        # Get parameters from request
        device_sn = request.args.get('device_sn')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Validate required parameters
        if not device_sn:
            return jsonify({'status': 'error', 'message': 'device_sn parameter is required'}), 400
        if not start_date or not end_date:
            return jsonify({'status': 'error', 'message': 'Both start_date and end_date parameters are required'}), 400
            
        # Validate date format
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid date format. Use YYYY-MM-DD'}), 400
            
        # Check that start date is before end date
        if start > end:
            return jsonify({'status': 'error', 'message': 'start_date must be before end_date'}), 400
            
        # Create a task ID
        task_id = str(uuid.uuid4())
        
        # Setup background task
        background_tasks[task_id] = {
            'id': task_id,
            'type': 'date_range_analysis',
            'device_sn': device_sn,
            'start_date': start_date,
            'end_date': end_date,
            'created_at': datetime.now().isoformat(),
            'status': TASK_STATUS['PENDING'],
            'progress': {
                'days_processed': 0,
                'days_total': (end - start).days + 1
            }
        }
        
        # Start background thread
        thread = threading.Thread(
            target=run_date_range_analysis,
            args=(task_id, device_sn, start_date, end_date)
        )
        thread.daemon = True
        thread.start()
        
        # Return task information
        return jsonify({
            'task_id': task_id,
            'status': 'accepted',
            'message': 'Analysis started in background',
            'check_status_url': f'/tasks/{task_id}'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get the status of a background task"""
    if task_id not in background_tasks:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404
        
    task = background_tasks[task_id]
    
    # If task is completed, include the result
    if task['status'] == TASK_STATUS['COMPLETED']:
        return jsonify({
            'task_id': task_id,
            'status': task['status'],
            'created_at': task['created_at'],
            'completed_at': task.get('completed_at'),
            'result': task.get('result')
        })
    # If task failed, include the error
    elif task['status'] == TASK_STATUS['FAILED']:
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
        
        # Validate that device_sn is provided
        if not device_sn:
            return render_template('disruption_events.html', 
                                  device_sn='',
                                  date=None,
                                  events=[],
                                  error='device_sn parameter is required')
            
        # Call the watchdog method to get disruption events
        result = watchdog.get_device_disruption_events_route(device_sn, date_str)
        
        # If the result is a tuple with status code, handle the error
        if isinstance(result, tuple):
            return render_template('disruption_events.html', 
                                  device_sn=device_sn,
                                  date=date_str,
                                  events=[],
                                  error=result[0].get('message', 'Unknown error'))
            
        # Extract the events from the result
        events = result.get('disruption_events', [])
        
        # Debug: Print the first event to see its structure
        if events and len(events) > 0:
            print("First event structure:", events[0])
            print("Event keys:", events[0].keys())
        
        # Render the template with the data
        return render_template('disruption_events.html', 
                              device_sn=device_sn,
                              date=date_str if date_str else result.get('date'),
                              events=events)
                              
    except Exception as e:
        return render_template('disruption_events.html', 
                              device_sn=device_sn if 'device_sn' in locals() else '',
                              date=date_str if 'date_str' in locals() else None,
                              events=[],
                              error=str(e))

if __name__ == '__main__':
    app.run()