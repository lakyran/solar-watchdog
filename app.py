from flask import Flask, jsonify
from dotenv import load_dotenv
from watchdog import Watchdog
from datetime import datetime, timedelta
import pytz
from flask_jwt_extended import JWTManager
import os

# Import blueprints
from routes.auth import auth_bp
from routes.users import users_bp
from routes.plants import plants_bp
from routes.devices import devices_bp
from routes.dashboard import dashboard_bp
from routes.tasks import tasks_bp
from routes.base import base_bp

# Import monitoring
from monitoring.config import init_opentelemetry
from monitoring.route_monitor import instrument_blueprint, RequestMonitoringMiddleware
from monitoring.metrics import init_metrics
from logging_config import configure_logging

logger = configure_logging(verbose=False)
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

# Initialize OpenTelemetry
init_opentelemetry()
logger.info("OpenTelemetry monitoring initialized")

# Initialize metrics
init_metrics()
logger.info("Metrics collection initialized")

# Initialize the Watchdog object
watchdog = Watchdog(app)

# Apply request monitoring middleware
request_monitoring = RequestMonitoringMiddleware(app)
logger.info("Request monitoring middleware initialized")

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

# Define the IST timezone
ist_timezone = pytz.timezone('Asia/Kolkata')

def get_current_time_ist():
    """
    Get the current time in Indian Standard Time (IST)
    
    Returns:
        datetime: Current datetime in IST
    """
    return datetime.now(ist_timezone)

# Instrument all blueprints for monitoring
logger.info("Instrumenting API blueprints with monitoring")
instrumented_blueprints = [
    instrument_blueprint(auth_bp),
    instrument_blueprint(users_bp),
    instrument_blueprint(plants_bp),
    instrument_blueprint(devices_bp),
    instrument_blueprint(dashboard_bp),
    instrument_blueprint(tasks_bp),
    instrument_blueprint(base_bp)
]

# Register base blueprint (no /api prefix)
app.register_blueprint(base_bp)

# Register API blueprints with /api prefix
app.register_blueprint(auth_bp, url_prefix='/api' + auth_bp.url_prefix)
app.register_blueprint(users_bp, url_prefix='/api' + users_bp.url_prefix)
app.register_blueprint(plants_bp, url_prefix='/api' + plants_bp.url_prefix)
app.register_blueprint(devices_bp, url_prefix='/api' + devices_bp.url_prefix)
app.register_blueprint(dashboard_bp, url_prefix='/api' + dashboard_bp.url_prefix)
app.register_blueprint(tasks_bp, url_prefix='/api' + tasks_bp.url_prefix)

# Inject watchdog instance into each blueprint module
import routes.auth as auth_module
import routes.users as users_module
import routes.plants as plants_module
import routes.devices as devices_module
import routes.dashboard as dashboard_module
import routes.tasks as tasks_module
import routes.base as base_module

auth_module.watchdog = watchdog
users_module.watchdog = watchdog
plants_module.watchdog = watchdog
devices_module.watchdog = watchdog
dashboard_module.watchdog = watchdog
tasks_module.watchdog = watchdog
base_module.watchdog = watchdog

if __name__ == '__main__':
    app.run()