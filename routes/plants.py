"""
Plant management routes for the Unisolar Watchdog Service
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
import logging
import time
from routes.users import admin_required

# Set up logger
logger = logging.getLogger(__name__)

# Create blueprint
plants_bp = Blueprint('plants', __name__, url_prefix='/plants')

# This function will be imported from watchdog instance in app.py
watchdog = None

@plants_bp.route('/list', methods=['GET'])
@jwt_required()
def get_plants_list():
    """Get a list of all plants in the system, optionally filtered by username"""
    try:
        # Get current user identity from JWT token
        current_username = get_jwt_identity()
        
        # Get optional username parameter
        username_param = request.args.get('username', None)
        
        # If a specific username is requested and it's not the current user, check admin privileges
        if username_param and username_param != current_username:
            # Check if user is admin using the user service
            is_admin = watchdog.user_service.check_admin_role(current_username)
            if not is_admin:
                return jsonify({
                    'status': 'error',
                    'message': 'Unauthorized: Admin privileges required'
                }), 403
        
        # If no username is specified, check if user is admin
        if not username_param:
            # Check if user is admin using the user service
            is_admin = watchdog.user_service.check_admin_role(current_username)
            
            # If not admin, use their own username
            if not is_admin:
                username_param = current_username
        
        # Get the list of plants using the plant service
        plants = watchdog.plant_service.get_plants_list(username_param)
        
        # Return the list as JSON
        return jsonify({
            'status': 'success',
            'count': len(plants),
            'username_filter': username_param,
            'plants': plants
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@plants_bp.route('/summary', methods=['GET'])
@jwt_required()
def get_plant_summary():
    """Get energy summary for a specific plant"""
    try:
        # Get required plant_id parameter
        plant_id = request.args.get('plant_id')
        
        # Validate the parameter
        if not plant_id:
            return jsonify({
                'status': 'error',
                'message': 'plant_id parameter is required'
            }), 400
            
        # Check if user has access to this plant
        current_username = get_jwt_identity()
        
        # Get plant details using the plant service
        plant_details = None
        all_plants = watchdog.plant_service.get_plants_list()
        for p in all_plants:
            if p.get('plant_id') == plant_id:
                plant_details = p
                break
                
        if not plant_details:
            return jsonify({
                'status': 'error',
                'message': f'Plant not found: {plant_id}'
            }), 404
            
        # Check if plant belongs to current user or if user is admin
        if plant_details.get('user_name') != current_username:
            # Check if user is admin using the user service
            is_admin = watchdog.user_service.check_admin_role(current_username)
            if not is_admin:
                return jsonify({
                    'status': 'error',
                    'message': 'Unauthorized: Admin privileges required or not owner of the plant'
                }), 403
        
        # Get the plant energy summary using the plant service
        summary = watchdog.plant_service.get_plant_energy_summary(plant_id)
        
        # Check if summary was found
        if not summary:
            return jsonify({
                'status': 'error',
                'message': f'No energy summary found for plant_id: {plant_id}'
            }), 404
        
        # Return the summary as JSON
        return jsonify({
            'status': 'success',
            'plant_id': plant_id,
            'summary': summary
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@plants_bp.route('/summary/ingest', methods=['GET'])
@jwt_required()
def ingest_plant_energy_summary():
    """Fetch plant energy summary from Growatt API and store it in the database"""
    try:
        # Get required plant_id parameter
        plant_id = request.args.get('plant_id')
        
        # Validate the required parameter
        if not plant_id:
            return jsonify({
                'status': 'error',
                'message': 'plant_id parameter is required'
            }), 400
            
        # Check if the user has access to this plant
        current_username = get_jwt_identity()
        
        # Get plant details using the plant service
        plant_details = None
        all_plants = watchdog.plant_service.get_plants_list()
        for p in all_plants:
            if p.get('plant_id') == plant_id:
                plant_details = p
                break
                
        if not plant_details:
            return jsonify({
                'status': 'error',
                'message': f'Plant not found: {plant_id}'
            }), 404
            
        # Check if plant belongs to current user or if user is admin
        if plant_details.get('user_name') != current_username:
            # Check if user is admin using the user service
            is_admin = watchdog.user_service.check_admin_role(current_username)
            if not is_admin:
                return jsonify({
                    'status': 'error',
                    'message': 'Unauthorized: Admin privileges required or not owner of the plant'
                }), 403
        
        # Call the watchdog method to fetch and store plant summary
        result = watchdog.fetch_and_store_plant_summary(plant_id=plant_id)
        
        # If the result is a tuple with a status code, handle the error
        if isinstance(result, tuple) and len(result) > 1:
            return jsonify(result[0]), result[1]
            
        # Return the result as JSON
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@plants_bp.route('/energy/daily/ingest', methods=['GET'])
@jwt_required()
def ingest_plant_energy_daily_data():
    """Fetch and store daily energy generation data for a plant over a date range"""
    try:
        # Get required plant_id parameter
        plant_id = request.args.get('plant_id')
        
        # Get optional date parameters with defaults
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Validate the required parameter
        if not plant_id:
            return jsonify({
                'status': 'error',
                'message': 'plant_id parameter is required'
            }), 400
            
        # Check if the user has access to this plant
        current_username = get_jwt_identity()
        
        # Get plant details using the plant service
        plant_details = None
        all_plants = watchdog.plant_service.get_plants_list()
        for p in all_plants:
            if p.get('plant_id') == plant_id:
                plant_details = p
                break
                
        if not plant_details:
            return jsonify({
                'status': 'error',
                'message': f'Plant not found: {plant_id}'
            }), 404
            
        # Check if plant belongs to current user or if user is admin
        if plant_details.get('user_name') != current_username:
            # Check if user is admin using the user service
            is_admin = watchdog.user_service.check_admin_role(current_username)
            if not is_admin:
                return jsonify({
                    'status': 'error',
                    'message': 'Unauthorized: Admin privileges required or not owner of the plant'
                }), 403
        
        # Call the watchdog method to fetch and store plant energy daily generation
        result = watchdog.fetch_and_store_plant_energy_daily_generation(
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # If the result is a tuple with a status code, handle the error
        if isinstance(result, tuple) and len(result) > 1:
            return jsonify(result[0]), result[1]
            
        # Return the result as JSON
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@plants_bp.route('/summary/batch-ingest', methods=['GET'])
@jwt_required()
@admin_required
def batch_ingest_plants_summary():
    """Fetch and store energy summaries for all plants in the system"""
    try:
        # Get all plants using the plant service
        plants = watchdog.plant_service.get_plants_list()
        
        if not plants:
            return jsonify({'status': 'error', 'message': 'No plants found in the system'}), 404
            
        # Initialize statistics
        stats = {
            'total': len(plants),
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'plants': []
        }
        
        # Process each plant
        start_time = time.time()
        
        for plant in plants:
            plant_id = plant.get('plant_id')
            plant_name = plant.get('plant_name', 'Unknown')
            
            if not plant_id:
                logger.warning(f"Skipping plant with no ID: {plant}")
                stats['failed'] += 1
                stats['plants'].append({
                    'plant_id': 'unknown',
                    'plant_name': plant_name,
                    'status': 'skipped',
                    'message': 'No plant_id found'
                })
                continue
                
            try:
                logger.info(f"Processing plant {plant_name} (ID: {plant_id})")
                
                # Call the watchdog method to fetch and store plant summary
                result = watchdog.fetch_and_store_plant_summary(plant_id)
                
                # Increment counters and collect stats
                stats['processed'] += 1
                
                if isinstance(result, tuple) or result.get('status') != 'success':
                    stats['failed'] += 1
                    error_msg = result[0].get('message') if isinstance(result, tuple) else result.get('message', 'Unknown error')
                    stats['plants'].append({
                        'plant_id': plant_id,
                        'plant_name': plant_name,
                        'status': 'failed',
                        'message': error_msg
                    })
                else:
                    stats['successful'] += 1
                    stats['plants'].append({
                        'plant_id': plant_id,
                        'plant_name': plant_name,
                        'status': 'success'
                    })
                
                # Add a small delay to avoid overwhelming the API
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing plant {plant_name} (ID: {plant_id}): {str(e)}")
                stats['failed'] += 1
                stats['processed'] += 1
                stats['plants'].append({
                    'plant_id': plant_id,
                    'plant_name': plant_name,
                    'status': 'error',
                    'message': str(e)
                })
        
        # Calculate processing time
        elapsed_time = time.time() - start_time
        stats['elapsed_time'] = elapsed_time
        
        # Return the statistics
        return jsonify({
            'status': 'success',
            'message': f'Batch ingest completed. Processed {stats["processed"]} plants ({stats["successful"]} successful, {stats["failed"]} failed) in {elapsed_time:.2f} seconds',
            'stats': stats
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@plants_bp.route('/energy/daily/batch-ingest', methods=['GET'])
@jwt_required()
@admin_required
def batch_ingest_plant_energy_daily_data():
    """Fetch and store daily energy generation data for all plants over a date range"""
    try:
        # Get optional date parameters with defaults
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Get all plants using the plant service
        plants = watchdog.plant_service.get_plants_list()
        
        if not plants:
            return jsonify({'status': 'error', 'message': 'No plants found in the system'}), 404
            
        # Initialize statistics
        stats = {
            'total': len(plants),
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'plants': []
        }
        
        # Process each plant
        start_time = time.time()
        
        for plant in plants:
            plant_id = plant.get('plant_id')
            plant_name = plant.get('plant_name', 'Unknown')
            
            if not plant_id:
                logger.warning(f"Skipping plant with no ID: {plant}")
                stats['failed'] += 1
                stats['plants'].append({
                    'plant_id': 'unknown',
                    'plant_name': plant_name,
                    'status': 'skipped',
                    'message': 'No plant_id found'
                })
                continue
                
            try:
                logger.info(f"Processing plant {plant_name} (ID: {plant_id})")
                
                # Call the watchdog method to fetch and store plant energy daily generation
                result = watchdog.fetch_and_store_plant_energy_daily_generation(
                    plant_id=plant_id,
                    start_date=start_date,
                    end_date=end_date
                )
                
                # Increment counters and collect stats
                stats['processed'] += 1
                
                if isinstance(result, tuple) or result.get('status') != 'success':
                    stats['failed'] += 1
                    error_msg = result[0].get('message') if isinstance(result, tuple) else result.get('message', 'Unknown error')
                    stats['plants'].append({
                        'plant_id': plant_id,
                        'plant_name': plant_name,
                        'status': 'failed',
                        'message': error_msg
                    })
                else:
                    stats['successful'] += 1
                    stats['plants'].append({
                        'plant_id': plant_id,
                        'plant_name': plant_name,
                        'status': 'success'
                    })
                
                # Add a small delay to avoid overwhelming the API
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing plant {plant_name} (ID: {plant_id}): {str(e)}")
                stats['failed'] += 1
                stats['processed'] += 1
                stats['plants'].append({
                    'plant_id': plant_id,
                    'plant_name': plant_name,
                    'status': 'error',
                    'message': str(e)
                })
        
        # Calculate processing time
        elapsed_time = time.time() - start_time
        stats['elapsed_time'] = elapsed_time
        
        # Return the statistics
        return jsonify({
            'status': 'success',
            'message': f'Batch ingest completed. Processed {stats["processed"]} plants ({stats["successful"]} successful, {stats["failed"]} failed) in {elapsed_time:.2f} seconds',
            'stats': stats
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500 