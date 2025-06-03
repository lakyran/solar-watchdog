"""
Authentication routes for the Unisolar Watchdog Service
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token, create_refresh_token, 
    get_jwt_identity, jwt_required, get_jwt
)
import logging
from werkzeug.security import check_password_hash

# Set up logger
logger = logging.getLogger(__name__)

# Create blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# This function will be imported from watchdog instance in app.py
watchdog = None

@auth_bp.route('/login', methods=['POST'])
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
        
        # Authenticate user using the user service
        is_authenticated, user, error_message = watchdog.user_service.authenticate_user(username, password)
        
        if not is_authenticated:
            logger.info(f"Invalid username or password for user: {username}")
            return jsonify({"status": "error", "message": error_message}), 401
        
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

@auth_bp.route('/refresh', methods=['POST'])
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

@auth_bp.route('/validate', methods=['POST'])
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