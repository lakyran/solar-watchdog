"""
Device management routes for the Unisolar Watchdog Service
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
import logging
import time
from routes.users import admin_required

# Set up logger
logger = logging.getLogger(__name__)

# Create blueprint
devices_bp = Blueprint('devices', __name__, url_prefix='/devices')

# This function will be imported from watchdog instance in app.py
watchdog = None

# Helper function to check device access
def check_device_access(device_sn):
    """
    Check if the current user has access to the specified device
    
    Args:
        device_sn (str): Device serial number to check access for
        
    Returns:
        None if access is allowed, or a tuple with error response if not
    """
    # Get current user identity from JWT token
    current_username = get_jwt_identity()
    
    # Get the device metadata
    device_metadata = watchdog.db_client.get_inverter_record(device_sn)
    
    # If device doesn't exist, return error
    if not device_metadata:
        return jsonify({
            'status': 'error',
            'message': f'Device not found: {device_sn}'
        }), 404
    
    # If the device belongs to the user or user is admin, allow access
    if device_metadata.get('user_name') == current_username:
        return None
        
    # Check if user is admin
    current_user = watchdog.db_client.get_user(current_username)
    if current_user and current_user.get('role') == 'admin':
        return None
        
    # If we get here, user doesn't have access
    return jsonify({
        'status': 'error',
        'message': 'Unauthorized: You do not have access to this device'
    }), 403

@devices_bp.route('/list', methods=['GET'])
@jwt_required()
def get_inverters_list():
    """Get a list of all inverters in the database, optionally filtered by username"""
    try:
        # Get current user identity from JWT token
        current_username = get_jwt_identity()
        
        # Get optional username parameter
        username_param = request.args.get('username', None)
        
        # If a specific username is requested and it's not the current user, check admin privileges
        if username_param and username_param != current_username:
            # Check if user is admin
            current_user = watchdog.db_client.get_user(current_username)
            if not current_user or current_user.get('role') != 'admin':
                return jsonify({
                    'status': 'error',
                    'message': 'Unauthorized: Admin privileges required'
                }), 403
        
        # If no username is specified, check if user is admin
        if not username_param:
            # Get current user
            current_user = watchdog.db_client.get_user(current_username)
            
            # If not admin, use their own username
            if not current_user or current_user.get('role') != 'admin':
                username_param = current_username
        
        # Get the list of inverters from the database
        inverters = watchdog.db_client.get_inverters_list(username_param)
        
        # Get the list of plants (will be filtered by username if provided)
        plants = watchdog.db_client.get_plants_list(username_param)
        
        # Create a dictionary of plants by plant_id for easy lookup
        plants_dict = {plant['plant_id']: plant for plant in plants}
        
        # Add plant details to each inverter
        for inverter in inverters:
            plant_id = inverter.get('plant_id')
            if plant_id and plant_id in plants_dict:
                inverter['plant_details'] = plants_dict[plant_id]
            else:
                inverter['plant_details'] = None
        
        # Return the list as JSON
        return jsonify({
            'status': 'success',
            'count': len(inverters),
            'username_filter': username_param,
            'inverters': inverters
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@devices_bp.route('/history/test', methods=['GET'])
@jwt_required()
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
            
        # Check access to the device
        access_check = check_device_access(device_sn)
        if access_check:
            return access_check
            
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

@devices_bp.route('/history/ingest', methods=['GET'])
@jwt_required()
def ingest_device_generation_history():
    """Ingest device generation history from Growatt API into the database"""
    try:
        # Get device_sn and date from request data
        device_sn = request.args.get('device_sn')
        date = request.args.get('date', None)
        overwrite = request.args.get('overwrite', False)
        store_records = request.args.get('store_records', False)
        
        # Validate that both parameters are provided
        if not device_sn:
            return jsonify({'status': 'error', 'message': 'device_sn parameter is required'}), 400
            
        # Check access to the device
        access_check = check_device_access(device_sn)
        if access_check:
            return access_check
            
        response = watchdog.fetch_and_store_device_generation_history(device_sn, date, overwrite, store_records)
        return jsonify(response)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@devices_bp.route('/history', methods=['GET'])
@jwt_required()
def get_device_history():
    """Get device generation history records from the database"""
    try:
        # Get device_sn, plant_id, and date from request data
        device_sn = request.args.get('device_sn')
        plant_id = request.args.get('plant_id')
        date = request.args.get('date')
        
        # Validate that at least one of device_sn or plant_id and date are provided
        if (not device_sn and not plant_id) or not date:
            return jsonify({'status': 'error', 'message': 'device_sn or plant_id and date parameters are required'}), 400
        
        # Check access based on device_sn or plant_id
        if device_sn:
            access_check = check_device_access(device_sn)
            if access_check:
                return access_check
        elif plant_id:
            # Get current user
            current_username = get_jwt_identity()
            
            # Check if plant belongs to user or user is admin
            plant_info = None
            all_plants = watchdog.db_client.get_plants_list()
            for p in all_plants:
                if p.get('plant_id') == plant_id:
                    plant_info = p
                    break
            
            if not plant_info:
                return jsonify({'status': 'error', 'message': f'Plant not found: {plant_id}'}), 404
                
            if plant_info.get('user_name') != current_username:
                # Check if user is admin
                current_user = watchdog.db_client.get_user(current_username)
                if not current_user or current_user.get('role') != 'admin':
                    return jsonify({
                        'status': 'error',
                        'message': 'Unauthorized: Admin privileges required or not owner of the plant'
                    }), 403
        
        # If both device_sn and plant_id are provided, use device_sn
        records = watchdog.get_device_history_records(device_sn=device_sn, plant_id=plant_id, date_str=date)
        return jsonify({
            'device_sn': device_sn,
            'plant_id': plant_id,
            'date': date,
            'record_count': len(records) if records else 0,
            'records': records if records else []
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@devices_bp.route('/analyze_disruptions', methods=['GET'])
@jwt_required()
def analyze_device_generation_disruptions():
    """Analyze device generation data for disruptions"""
    try:
        # Get device_sn and date from request data
        device_sn = request.args.get('device_sn')
        date_str = request.args.get('date', None)
        
        # Validate that device_sn is provided
        if not device_sn:
            return jsonify({'status': 'error', 'message': 'device_sn parameter is required'}), 400
            
        # Check access to the device
        access_check = check_device_access(device_sn)
        if access_check:
            return access_check
            
        return jsonify(watchdog.analyze_device_generation_data_route(device_sn, date_str))
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@devices_bp.route('/analyze_and_store_disruptions', methods=['GET'])
@jwt_required()
def analyze_and_store_device_disruptions():
    """Analyze device generation data for disruptions and store results"""
    try:
        # Get device_sn and date from request data
        device_sn = request.args.get('device_sn')
        date_str = request.args.get('date', None)
        
        # Validate that device_sn is provided
        if not device_sn:
            return jsonify({'status': 'error', 'message': 'device_sn parameter is required'}), 400
            
        # Check access to the device
        access_check = check_device_access(device_sn)
        if access_check:
            return access_check
            
        return jsonify(watchdog.analyze_device_generation_data_and_store_disruptions_route(device_sn, date_str))
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@devices_bp.route('/analyze_disruptions_range', methods=['GET'])
@jwt_required()
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
        
        # Validate that device_sn is provided
        if not device_sn:
            return jsonify({'status': 'error', 'message': 'device_sn parameter is required'}), 400
            
        # Check access to the device
        access_check = check_device_access(device_sn)
        if access_check:
            return access_check
        
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

@devices_bp.route('/disruption_events', methods=['GET'])
@jwt_required()
def get_device_disruption_events():
    """Get disruption events for a device, optionally filtered by date"""
    try:
        # Get device_sn and optional date from request data
        device_sn = request.args.get('device_sn')
        date_str = request.args.get('date', None)
        
        # Validate that device_sn is provided
        if not device_sn:
            return jsonify({'status': 'error', 'message': 'device_sn parameter is required'}), 400
            
        # Check access to the device
        access_check = check_device_access(device_sn)
        if access_check:
            return access_check
            
        # Call the watchdog method to get disruption events
        result = watchdog.get_device_disruption_events_route(device_sn, date_str)
        
        # If the result is a tuple with status code, handle it
        if isinstance(result, tuple):
            return jsonify(result[0]), result[1]
            
        # Otherwise, return the result as JSON
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@devices_bp.route('/history/batch-ingest', methods=['GET'])
@jwt_required()
@admin_required
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
        device_sn = request.args.get('device_sn')
        
        # Get the list of all inverters
        if device_sn:
            inverters = [watchdog.db_client.get_inverter_record(device_sn)]
        else:
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
                    if ingest_result.get('date') == watchdog.get_current_time_ist().strftime('%Y-%m-%d'):
                        break
                    elif date:
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

@devices_bp.route('/disruptions/batch-analyze', methods=['GET'])
@jwt_required()
@admin_required
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