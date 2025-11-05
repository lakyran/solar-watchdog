"""
Base routes for the Unisolar Watchdog Service
"""
from flask import Blueprint, jsonify, request, render_template, send_from_directory
import logging
import markdown
import os
from datetime import datetime

# Set up logger
logger = logging.getLogger(__name__)

# Create blueprint without url_prefix so it handles root routes
base_bp = Blueprint('base', __name__)

# This will be imported from watchdog instance in app.py
watchdog = None

# Favicon route
@base_bp.route('/favicon.ico')
def favicon():
    """Serve the favicon"""
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

# Welcome page
@base_bp.route('/', methods=['GET'])
def hello():
    """Serve the welcome page"""
    return render_template('welcome.html')

# Health check
@base_bp.route('/health', methods=['GET'])
@base_bp.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint that verifies the /api/auth/login route is functional.

    We treat HTTP 200/400/401 from the login route as "reachable" (functional route),
    and anything 5xx or exceptions as unhealthy.
    """
    login_check = {
        'reachable': False,
        'status_code': None,
        'message': None
    }

    try:
        if watchdog and getattr(watchdog, 'app', None):
            with watchdog.app.test_client() as client:
                resp = client.post('/api/auth/login', json={})
                login_check['status_code'] = resp.status_code
                # Accept 200/400/401 as functional (route exists and processes request)
                login_check['reachable'] = resp.status_code in (200, 400, 401)
                try:
                    data = resp.get_json(silent=True)
                    if isinstance(data, dict) and 'message' in data:
                        login_check['message'] = data.get('message')
                except Exception:
                    pass
        else:
            login_check['message'] = 'Watchdog app not available'
    except Exception as e:
        login_check['message'] = f'Exception during login check: {str(e)}'

    overall_ok = bool(login_check['reachable'])

    return jsonify({
        'status': 'ok' if overall_ok else 'error',
        'service': 'unisolar-watchdog-service',
        'time': datetime.utcnow().isoformat() + 'Z',
        'checks': {
            'login_endpoint': login_check
        }
    }), 200 if overall_ok else 503

# Disruptions view page
@base_bp.route('/disruptions/view', methods=['GET'])
def view_device_disruption_events():
    """Display disruption events for a device in a human-readable HTML format"""
    try:
        # Get device_sn and optional date from request data
        device_sn = request.args.get('device_sn')
        date_str = request.args.get('date', None)
        
        # Get the list of inverters and plants using the plant service
        try:
            inverters = watchdog.plant_service.get_inverters_list()
            plants = watchdog.plant_service.get_plants_list()
            plants_dict = {plant['plant_id']: plant for plant in plants}
            # Augment inverters with plant details
            for inverter in inverters:
                plant_id = inverter.get('plant_id')
                if plant_id and plant_id in plants_dict:
                    inverter['plant_details'] = plants_dict[plant_id]
                else:
                    inverter['plant_details'] = None
        except Exception as e:
            logger.error(f"Error fetching inverters or plants list: {str(e)}")
            inverters = []
            plants_dict = {}
        
        # If device_sn is not provided, use the first inverter as default
        selected_device_sn = device_sn
        if not selected_device_sn and inverters:
            selected_device_sn = inverters[0]['device_sn']
        
        # Find selected inverter details from the augmented list
        selected_inverter = next((inv for inv in inverters if inv.get('device_sn') == selected_device_sn), None)
        plant_name = '--'
        city = '--'
        user_name = '--'
        if selected_inverter:
            user_name = selected_inverter.get('user_name', '--')
            if selected_inverter.get('plant_details'):
                plant_name = selected_inverter['plant_details'].get('plant_name', '--')
                city = selected_inverter['plant_details'].get('city', '--')

        # If still no device_sn, render with error
        if not selected_device_sn:
            return render_template('disruption_events.html', 
                                  device_sn='',
                                  date=None,
                                  events=[],
                                  inverters=inverters, # Pass augmented list
                                  user_name='--',
                                  plant_name='--',
                                  city='--',
                                  error='No device found to display disruptions.')
        
        # Call the watchdog method to get disruption events
        result = watchdog.get_device_disruption_events_route(selected_device_sn, date_str)
        
        # If the result is a tuple with status code, handle the error
        if isinstance(result, tuple):
            return render_template('disruption_events.html', 
                                  device_sn=selected_device_sn,
                                  date=date_str,
                                  events=[],
                                  inverters=inverters, # Pass augmented list
                                  user_name=user_name,
                                  plant_name=plant_name,
                                  city=city,
                                  error=result[0].get('message', 'Unknown error'))
        
        # Extract the events from the result
        events = result.get('disruption_events', [])
        
        # Render the template with the data
        return render_template('disruption_events.html', 
                              device_sn=selected_device_sn,
                              date=date_str if date_str else result.get('date'),
                              events=events,
                              inverters=inverters, # Pass augmented list
                              user_name=user_name,
                              plant_name=plant_name,
                              city=city)
                                  
    except Exception as e:
        # Use selected_device_sn if available in locals, otherwise fallback
        current_device_sn = selected_device_sn if 'selected_device_sn' in locals() and selected_device_sn else (device_sn if 'device_sn' in locals() else '')
        current_date_str = date_str if 'date_str' in locals() else None
        # Try to pass augmented inverters if available, else empty list
        current_inverters = inverters if 'inverters' in locals() else [] 
        return render_template('disruption_events.html', 
                              device_sn=current_device_sn,
                              date=current_date_str,
                              events=[],
                              inverters=current_inverters, # Pass potentially augmented list
                              user_name='--',
                              plant_name='--',
                              city='--',
                              error=str(e))

# Efficiency view page
@base_bp.route('/efficiency/view', methods=['GET'])
def view_efficiency_snapshot():
    """Display efficiency snapshot in a human-readable HTML format"""
    try:
        # Get filter parameters from request
        min_eff = int(request.args.get('min_eff', 0))
        max_eff = int(request.args.get('max_eff', 100))
        if min_eff < 0: min_eff = 0
        if max_eff > 100: max_eff = 100
        if min_eff > max_eff: min_eff, max_eff = max_eff, min_eff

        # Optional: plant_name for 7-day efficiency plot
        plant_name_selected = request.args.get('plant_name')

        # Delegate all processing to watchdog
        data = watchdog.get_efficiency_snapshot_data(min_eff=min_eff, max_eff=max_eff, plant_name_selected=plant_name_selected)
        return render_template('efficiency_snapshot.html', **data)
    except Exception as e:
        logger.error(f"Error rendering efficiency snapshot: {str(e)}")
        # Return empty data for template
        return render_template(
            'efficiency_snapshot.html',
            efficiency_bins=[],
            x_labels=[],
            min_eff=0,
            max_eff=100,
            filtered_plants=[],
            all_plants=[],
            efficiency_percentages=[],
            efficiency_legend=[],
            plant_name_selected=None,
            plant_efficiency_7d_hourly=[],
            plant_efficiency_7d_labels=[],
            plant_hour_labels=[],
            error=str(e)
        )

# Privacy policy page
@base_bp.route('/privacy-policy', methods=['GET'])
def privacy_policy():
    """Serve the privacy policy page"""
    try:
        # Read the privacy policy markdown file
        privacy_file_path = 'docs/privacy-policy.md'
        
        if not os.path.exists(privacy_file_path):
            logger.error(f"Privacy policy file not found: {privacy_file_path}")
            return render_template('privacy_policy.html', 
                                 privacy_content=None,
                                 error="Privacy policy file not found.")
        
        with open(privacy_file_path, 'r', encoding='utf-8') as file:
            privacy_markdown = file.read()
        
        # Convert markdown to HTML
        privacy_content = markdown.markdown(privacy_markdown)
        
        return render_template('privacy_policy.html', 
                             privacy_content=privacy_content,
                             error=None)
                             
    except FileNotFoundError:
        logger.error(f"Privacy policy file not found: {privacy_file_path}")
        return render_template('privacy_policy.html', 
                             privacy_content=None,
                             error="Privacy policy file not found.")
    except IOError as e:
        logger.error(f"Error reading privacy policy file: {str(e)}")
        return render_template('privacy_policy.html', 
                             privacy_content=None,
                             error="Error reading privacy policy file.")
    except Exception as e:
        logger.error(f"Error processing privacy policy: {str(e)}")
        # Fallback: try to display raw markdown content
        try:
            with open(privacy_file_path, 'r', encoding='utf-8') as file:
                raw_content = file.read()
            return render_template('privacy_policy.html', 
                                 privacy_content=f"<pre>{raw_content}</pre>",
                                 error="Markdown processing failed. Displaying raw content.")
        except:
            return render_template('privacy_policy.html', 
                                 privacy_content=None,
                                 error="Error processing privacy policy content.") 