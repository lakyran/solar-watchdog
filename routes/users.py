"""
User management routes for the Unisolar Watchdog Service
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
import logging
from functools import wraps

# Set up logger
logger = logging.getLogger(__name__)

# Create blueprint
users_bp = Blueprint('users', __name__, url_prefix='/users')

# This function will be imported from watchdog instance in app.py
watchdog = None

# Admin required decorator
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        current_username = get_jwt_identity()
        if not current_username:
             return jsonify({
                'status': 'error',
                'message': 'Authentication required'
            }), 401

        # Use the user service to check admin role
        is_admin = watchdog.user_service.check_admin_role(current_username)
        
        if not is_admin:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized: Admin privileges required'
            }), 403
        return fn(*args, **kwargs)
    return wrapper

@users_bp.route('/list', methods=['GET'])
@jwt_required()
@admin_required
def get_users_list():
    """Get a list of all users in the system"""
    try:
        # Get the list of users using the user service
        users = watchdog.user_service.get_users_list()
        
        # Return the list as JSON
        return jsonify({
            'status': 'success',
            'count': len(users),
            'users': users
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@users_bp.route('/me', methods=['GET'])
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
        
        # Get user from database using the user service
        user = watchdog.user_service.get_user(current_username)
        
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

@users_bp.route('/onboard', methods=['POST'])
@jwt_required()
@admin_required
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