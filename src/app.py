from flask import Flask, jsonify, request
import os
from dotenv import load_dotenv
from ai_agent import GrowattAIAgent
import asyncio
from watchdog import Watchdog

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
def fetch_and_store_device_history():
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

if __name__ == '__main__':
    app.run()