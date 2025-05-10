from flask import Flask, jsonify, request, render_template, send_from_directory
import logging
from dotenv import load_dotenv
from watchdog import Watchdog
import time
from datetime import datetime, timedelta
import pytz
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required, create_refresh_token, get_jwt, verify_jwt_in_request, jwt_required, current_user
import os
from werkzeug.security import check_password_hash

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

# Configure JWT
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)
jwt = JWTManager(app)

# JWT error handlers
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    """Handle expired tokens gracefully"""
    token_type = jwt_payload["type"]
    return jsonify({
        "status": "error",
        "message": f"The {token_type} token has expired",
        "code": "token_expired"
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    """Handle invalid tokens"""
    return jsonify({
        "status": "error",
        "message": "Invalid token",
        "code": "invalid_token"
    }), 401

@jwt.unauthorized_loader
def missing_token_callback(error):
    """Handle missing tokens"""
    return jsonify({
        "status": "error",
        "message": "Authentication required",
        "code": "authorization_required"
    }), 401

@jwt.needs_fresh_token_loader
def token_not_fresh_callback(jwt_header, jwt_payload):
    """Handle cases where a fresh token is required"""
    return jsonify({
        "status": "error",
        "message": "Fresh token required",
        "code": "fresh_token_required"
    }), 401

@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    """Handle revoked tokens"""
    return jsonify({
        "status": "error",
        "message": "Token has been revoked",
        "code": "token_revoked"
    }), 401

# Utility function for admin-only routes
def admin_required():
    """
    Decorator utility to check if the current user has admin role
    Must be used after @jwt_required()
    """
    current_username = get_jwt_identity()
    current_user = watchdog.db_client.get_user(current_username)
    
    if not current_user or current_user.get('role') != 'admin':
        return jsonify({
            'status': 'error',
            'message': 'Unauthorized: Admin privileges required'
        }), 403
    
    return None

# Utility function to check if a user has access to a device
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
    admin_check = admin_required()
    if not admin_check:
        return None
        
    # If we get here, user doesn't have access
    return jsonify({
        'status': 'error',
        'message': 'Unauthorized: You do not have access to this device'
    }), 403

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

@app.route('/login', methods=['POST'])
def login():
    """
    Authenticate user and issue JWT tokens
    
    Required POST parameters:
    - username: Username for authentication
    - password: User password
    
    Returns:
        JSON: Access token and refresh token if authentication is successful
    """
    try:
        # Get username and password from request
        username = request.json.get("username", None)
        password = request.json.get("password", None)
        
        # Validate required parameters
        if not username:
            return jsonify({"status": "error", "message": "Username is required"}), 400
        if not password:
            return jsonify({"status": "error", "message": "Password is required"}), 400
        
        # Get user from database
        user = watchdog.db_client.get_user(username)
        
        # Check if user exists
        if not user:
            return jsonify({"status": "error", "message": "Invalid username or password"}), 401
        
        # Check password
        if not user.get('password_hash') or not check_password_hash(user.get('password_hash'), password):
            return jsonify({"status": "error", "message": "Invalid username or password"}), 401
        
        # Create access token and refresh token
        additional_claims = {
            "role": user.get('role', 'user'),
            "user_id": user.get('user_id')
        }
        
        access_token = create_access_token(
            identity=username,
            additional_claims=additional_claims
        )
        
        refresh_token = create_refresh_token(
            identity=username,
            additional_claims=additional_claims
        )
        
        # Return tokens
        return jsonify({
            "status": "success",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "username": username,
                "role": user.get('role', 'user')
            }
        })
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({"status": "error", "message": "Authentication failed"}), 500

@app.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Issue a new access token using a valid refresh token
    
    Required: Valid refresh token in the Authorization header
    
    Returns:
        JSON: New access token
    """
    try:
        # Get current user identity from the refresh token
        current_username = get_jwt_identity()
        
        # Get the JWT claims from the refresh token
        jwt_claims = get_jwt()
        
        # Create a new access token with the same additional claims
        additional_claims = {
            "role": jwt_claims.get("role", "user"),
            "user_id": jwt_claims.get("user_id")
        }
        
        access_token = create_access_token(
            identity=current_username,
            additional_claims=additional_claims
        )
        
        # Return the new access token
        return jsonify({
            "status": "success",
            "access_token": access_token,
            "user": {
                "username": current_username,
                "role": jwt_claims.get("role", "user")
            }
        })
        
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return jsonify({"status": "error", "message": "Failed to refresh token"}), 500

@app.route('/validate', methods=['POST'])
@jwt_required()
def validate_token():
    """
    Validate that an access token is still valid
    
    Returns:
        JSON: Token validity status and user info
    """
    try:
        # Get current user identity
        current_username = get_jwt_identity()
        
        # Get the JWT claims
        jwt_claims = get_jwt()
        
        # Return success with user info
        return jsonify({
            "status": "success",
            "message": "Token is valid",
            "user": {
                "username": current_username,
                "role": jwt_claims.get("role", "user"),
                "user_id": jwt_claims.get("user_id")
            }
        })
        
    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        return jsonify({"status": "error", "message": "Invalid token"}), 401

@app.route('/', methods=['GET'])
def hello():
    return render_template('welcome.html')

@app.route('/device/history/test', methods=['GET'])
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

@app.route('/device/history/ingest', methods=['GET'])
@jwt_required()
def ingest_device_generation_history():
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

@app.route('/device/history', methods=['GET'])
@jwt_required()
def get_device_history():
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
                admin_check = admin_required()
                if admin_check:
                    return admin_check
        
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

@app.route('/device/analyze_disruptions', methods=['GET'])
@jwt_required()
def analyze_device_generation_disruptions():
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

@app.route('/device/analyze_and_store_disruptions', methods=['GET'])
@jwt_required()
def analyze_and_store_device_disruptions():
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
    
@app.route('/device/analyze_disruptions_range', methods=['GET'])
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

@app.route('/tasks/<task_id>', methods=['GET'])
@jwt_required()
def get_task_status(task_id):
    """Get the status of a background task"""
    try:
        task_status = watchdog.get_task_status(task_id)
        
        # Check if the task exists
        if isinstance(task_status, tuple) and task_status[1] == 404:
            return jsonify(task_status[0]), task_status[1]
            
        # Get the task details
        task = watchdog.background_tasks.get(task_id)
        
        # If the task is found, check if user has access to it
        if task and 'device_sn' in task:
            access_check = check_device_access(task['device_sn'])
            if access_check:
                return access_check
        
        # Return the task status
        return jsonify(task_status)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/device/disruption_events', methods=['GET'])
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
    
@app.route('/plant/summary/ingest', methods=['GET'])
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
        
        # Get plant details
        plant_details = None
        all_plants = watchdog.db_client.get_plants_list()
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
            admin_check = admin_required()
            if admin_check:
                return admin_check
        
        # Call the watchdog method to fetch and store plant summary
        result = watchdog.fetch_and_store_plant_summary(plant_id=plant_id)
        
        # If the result is a tuple with a status code, handle the error
        if isinstance(result, tuple) and len(result) > 1:
            return jsonify(result[0]), result[1]
            
        # Return the result as JSON
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/plant/summary', methods=['GET'])
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
        
        # Get plant details
        plant_details = None
        all_plants = watchdog.db_client.get_plants_list()
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
            admin_check = admin_required()
            if admin_check:
                return admin_check
        
        # Get the plant energy summary from the database
        summary = watchdog.db_client.get_plant_energy_summary(plant_id)
        
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

@app.route('/users/list', methods=['GET'])
@jwt_required()
def get_users_list():
    """Get a list of all users in the system"""
    try:
        # Check if current user has admin rights
        admin_check = admin_required()
        if admin_check:
            return admin_check
            
        # Get the list of users from the database
        users = watchdog.db_client.get_users_list()
        
        # Return the list as JSON
        return jsonify({
            'status': 'success',
            'count': len(users),
            'users': users
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/me', methods=['GET'])
@jwt_required()
def get_user_profile():
    """
    Get the current user's profile
    
    Returns:
        JSON: User profile information
    """
    try:
        # Get current user identity from JWT token
        current_username = get_jwt_identity()
        
        # Get user from database
        user = watchdog.db_client.get_user(current_username)
        
        # Check if user exists
        if not user:
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        # Return user profile (excluding sensitive information)
        return jsonify({
            "status": "success",
            "user": {
                "username": user.get('user_name'),
                "role": user.get('role', 'user'),
                "email": user.get('email'),
                "phone": user.get('phone'),
                "vendor": user.get('vendor')
            }
        })
        
    except Exception as e:
        logger.error(f"Error fetching user profile: {str(e)}")
        return jsonify({"status": "error", "message": "Failed to fetch user profile"}), 500

@app.route('/users/onboard', methods=['POST'])
@jwt_required()
def onboard_new_user():
    """
    Onboard a new user with plants and devices
    
    Required POST parameters:
    - username: Username for the new user
    - user_id: User ID for the new user
    - vendor: Vendor name (e.g., 'Growatt')
    
    Optional POST parameters:
    - phone: User's phone number
    - email: User's email address
    - password: User's password (will be hashed)
    - role: User's role (default is 'user')
    - bootstrap_history: Boolean indicating whether to fetch historical data (default is True)
    """
    try:
        # Check if current user has admin rights
        admin_check = admin_required()
        if admin_check:
            return admin_check
            
        # Get parameters from request JSON
        request_data = request.get_json()
        
        if not request_data:
            return jsonify({
                'status': 'error',
                'message': 'Request body is required with JSON data'
            }), 400
        
        # Extract required parameters
        username = request_data.get('username')
        user_id = request_data.get('user_id')
        vendor = request_data.get('vendor')
        
        # Validate required parameters
        if not username:
            return jsonify({'status': 'error', 'message': 'username parameter is required'}), 400
        if not user_id:
            return jsonify({'status': 'error', 'message': 'user_id parameter is required'}), 400
        if not vendor:
            return jsonify({'status': 'error', 'message': 'vendor parameter is required'}), 400
        
        # Extract optional parameters
        phone = request_data.get('phone')
        email = request_data.get('email')
        password = request_data.get('password')
        role = request_data.get('role')
        
        # Handle bootstrap_history parameter - convert to boolean
        bootstrap_history = True  # Default is True
        if 'bootstrap_history' in request_data:
            bootstrap_param = request_data.get('bootstrap_history')
            bootstrap_history = bootstrap_param.lower() in ('true', 'yes', '1')
        
        logger.info(f"User onboarding for {username} with bootstrap_history={bootstrap_history}")
        
        # Call the onboard_new_user method
        result = watchdog.onboard_new_user(
            username=username,
            user_id=user_id,
            vendor=vendor,
            phone=phone,
            email=email,
            password=password,
            role=role,
            bootstrap_history=bootstrap_history
        )
        
        # Return the result
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error onboarding new user: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/plants/list', methods=['GET'])
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
            admin_check = admin_required()
            if admin_check:
                return admin_check
        
        # If no username is specified, check if user is admin
        if not username_param:
            # Get current user
            current_user = watchdog.db_client.get_user(current_username)
            
            # If not admin, use their own username
            if not current_user or current_user.get('role') != 'admin':
                username_param = current_username
        
        # Get the list of plants from the database
        plants = watchdog.db_client.get_plants_list(username_param)
        
        # Return the list as JSON
        return jsonify({
            'status': 'success',
            'count': len(plants),
            'username_filter': username_param,
            'plants': plants
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/inverters/list', methods=['GET'])
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
            admin_check = admin_required()
            if admin_check:
                return admin_check
        
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

@app.route('/devices/history/batch-ingest', methods=['GET'])
@jwt_required()
def batch_ingest_inverters_history():
    """Get a list of all inverters and ingest generation history for each one"""
    try:
        # This is an admin-only endpoint
        admin_check = admin_required()
        if admin_check:
            return admin_check
            
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
                    if ingest_result.get('date') == get_current_time_ist().strftime('%Y-%m-%d'):
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

@app.route('/plants/summary/batch-ingest', methods=['GET'])
def batch_ingest_plants_summary():
    """Fetch and store energy summaries for all plants in the system"""
    try:
        # Get the list of all plants
        plants = watchdog.db_client.get_plants_list()
        
        if not plants:
            return jsonify({
                'status': 'error',
                'message': 'No plants found in the system'
            }), 404
        
        # Track results for each plant
        results = []
        successful_plants = 0
        failed_plants = 0
        
        # Process each plant
        for plant in plants:
            plant_id = plant.get('plant_id')
            
            # Skip if no plant_id
            if not plant_id:
                continue
                
            try:
                # Fetch and store summary for this plant
                result = watchdog.fetch_and_store_plant_summary(plant_id)
                
                # Handle case where response is a tuple (error response)
                if isinstance(result, tuple) and len(result) > 1:
                    error_data, status_code = result
                    # Create a standardized error result
                    plant_result = {
                        'plant_id': plant_id,
                        'user_name': plant.get('user_name', ''),
                        'status': 'error',
                        'error': error_data.get('message', 'Unknown error'),
                        'status_code': status_code
                    }
                    failed_plants += 1
                else:
                    # Success case
                    plant_result = {
                        'plant_id': plant_id,
                        'user_name': plant.get('user_name', ''),
                        'status': 'success',
                        'api_data': result.get('api_data'),
                        'db_result': result.get('db_result')
                    }
                    successful_plants += 1
                
                # Add result to results list
                results.append(plant_result)
                
                # Wait for 1 second before processing the next plant to avoid API rate limits
                time.sleep(1)
                
            except Exception as e:
                # If one plant fails, continue with others but log the error
                logger.error(f"Error processing plant {plant_id}: {str(e)}")
                results.append({
                    'plant_id': plant_id,
                    'user_name': plant.get('user_name', ''),
                    'status': 'error',
                    'error': str(e)
                })
                failed_plants += 1
        
        # Return the aggregated results
        return jsonify({
            'status': 'success',
            'total_plants': len(plants),
            'successful_plants': successful_plants,
            'failed_plants': failed_plants,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/devices/disruptions/batch-analyze', methods=['GET'])
@jwt_required()
def batch_analyze_inverters_disruptions():
    """Analyze disruptions for all inverters in the database, processing each one sequentially"""
    try:
        # Check if user is admin
        admin_check = admin_required()
        if admin_check:
            return admin_check
    
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

@app.route('/dashboard', methods=['GET'])
@jwt_required()
def get_user_dashboard():
    """Get dashboard data for a specific user including their plant details and summary"""
    try:
        # Get current user from JWT token
        current_username = get_jwt_identity()
        
        # Get optional username parameter (for admins to view other users' dashboards)
        username_param = request.args.get('username', current_username)
        
        # If requesting another user's dashboard, check admin privileges
        if username_param != current_username:
            admin_check = admin_required()
            if admin_check:
                return admin_check
        
        # Call the watchdog method to get dashboard data
        result = watchdog.get_user_dashboard_data(username_param)
        
        # If the result is a tuple with a status code, handle the error
        if isinstance(result, tuple) and len(result) > 1:
            return jsonify(result[0]), result[1]
            
        # Return the result as JSON
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
        
        # Get the list of inverters and plants
        try:
            inverters = watchdog.db_client.get_inverters_list()
            plants = watchdog.db_client.get_plants_list()
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

@app.route('/devices/efficiency/view', methods=['GET'])
def view_efficiency_snapshot():
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

@app.route('/plant/energy/daily/ingest', methods=['GET'])
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
        
        # Get plant details
        plant_details = None
        all_plants = watchdog.db_client.get_plants_list()
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
            admin_check = admin_required()
            if admin_check:
                return admin_check
        
        # Call the watchdog method to fetch and store plant energy data
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

@app.route('/plants/energy/daily/batch-ingest', methods=['GET'])
@jwt_required()
def batch_ingest_plant_energy_daily_data():
    """Fetch and store daily energy generation data for all plants"""
    try:
        # This is an admin-only endpoint
        admin_check = admin_required()
        if admin_check:
            return admin_check
            
        # Get optional date parameters with defaults
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Get the list of all plants
        plants = watchdog.db_client.get_plants_list()
        
        if not plants:
            return jsonify({
                'status': 'error',
                'message': 'No plants found in the system'
            }), 404
        
        # Track results for each plant
        results = []
        successful_plants = 0
        failed_plants = 0
        
        # Process each plant
        for plant in plants:
            plant_id = plant.get('plant_id')
            
            # Skip if no plant_id
            if not plant_id:
                continue
                
            try:
                # Fetch and store data for this plant
                result = watchdog.fetch_and_store_plant_energy_daily_generation(
                    plant_id=plant_id,
                    start_date=start_date,
                    end_date=end_date
                )
                
                # Handle case where response is a tuple (error response)
                if isinstance(result, tuple) and len(result) > 1:
                    error_data, status_code = result
                    # Create a standardized error result
                    plant_result = {
                        'plant_id': plant_id,
                        'user_name': plant.get('user_name', ''),
                        'status': 'error',
                        'error': error_data.get('message', 'Unknown error'),
                        'status_code': status_code
                    }
                    failed_plants += 1
                else:
                    # Success case
                    plant_result = {
                        'plant_id': plant_id,
                        'user_name': plant.get('user_name', ''),
                        'status': 'success',
                        'api_data': result.get('api_result', {}),
                        'db_result': result.get('db_result', {})
                    }
                    successful_plants += 1
                
                # Add result to results list
                results.append(plant_result)
                
                # Wait for 1 second before processing the next plant to avoid API rate limits
                time.sleep(1)
                
            except Exception as e:
                # If one plant fails, continue with others but log the error
                logger.error(f"Error processing plant {plant_id}: {str(e)}")
                results.append({
                    'plant_id': plant_id,
                    'user_name': plant.get('user_name', ''),
                    'status': 'error',
                    'error': str(e)
                })
                failed_plants += 1
        
        # Return the aggregated results
        return jsonify({
            'status': 'success',
            'total_plants': len(plants),
            'successful_plants': successful_plants,
            'failed_plants': failed_plants,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run()