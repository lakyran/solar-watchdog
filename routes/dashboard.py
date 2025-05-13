"""
Dashboard routes for the Unisolar Watchdog Service
"""
from flask import Blueprint, jsonify, request, render_template
from flask_jwt_extended import get_jwt_identity, jwt_required
import logging
from routes.devices import check_device_access

# Set up logger
logger = logging.getLogger(__name__)

# Create blueprint
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

# This function will be imported from watchdog instance in app.py
watchdog = None

@dashboard_bp.route('', methods=['GET'])
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
            # Check if user is admin
            current_user = watchdog.db_client.get_user(current_username)
            if not current_user or current_user.get('role') != 'admin':
                return jsonify({
                    'status': 'error',
                    'message': 'Unauthorized: Admin privileges required'
                }), 403
        
        # Call the watchdog method to get dashboard data
        result = watchdog.get_user_dashboard_data(username_param)
        
        # If the result is a tuple with a status code, handle the error
        if isinstance(result, tuple) and len(result) > 1:
            return jsonify(result[0]), result[1]
            
        # Return the result as JSON
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
