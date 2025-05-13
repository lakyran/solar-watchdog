"""
Tasks routes for the Unisolar Watchdog Service
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
import logging
from routes.devices import check_device_access

# Set up logger
logger = logging.getLogger(__name__)

# Create blueprint
tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')

# This function will be imported from watchdog instance in app.py
watchdog = None

@tasks_bp.route('/<task_id>', methods=['GET'])
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