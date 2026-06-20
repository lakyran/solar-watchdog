from datetime import datetime, timedelta, timezone
import pytz
from flask import jsonify, request
import logging
import time
from src.growatt import GrowattAPI
from src.azure_db import AzureDB
from src.ai_agent import GrowattAIAgent

# Import service classes
from services import (
    HistoryIngestionService,
    DisruptionAnalysisService,
    UserManagementService,
    PlantManagementService
)

# Import monitoring decorators (OpenTelemetry only)
from monitoring import (
    instrument_history_service,
    instrument_disruption_service,
    instrument_user_service,
    instrument_plant_service,
    instrument_db_client,
    instrument_api_client
)

class Watchdog:
    # Task status constants
    TASK_STATUS = {
        'PENDING': 'pending',
        'RUNNING': 'running',
        'COMPLETED': 'completed',
        'FAILED': 'failed'
    }
    
    def __init__(self, app=None):
        self.app = app
        self.logger = logging.getLogger(__name__)
        
        # Initialize Growatt API client with OpenTelemetry instrumentation
        self.growatt_client = instrument_api_client(GrowattAPI)()
        
        # Initialize Azure DB client with OpenTelemetry instrumentation
        self.db_client = instrument_db_client(AzureDB)()

        # Initialize AI agent
        self.ai_agent = GrowattAIAgent()
        
        # Define the IST timezone
        self.ist_timezone = pytz.timezone('Asia/Kolkata')
        
        # Initialize service objects with OpenTelemetry monitoring
        self.history_service = instrument_history_service(HistoryIngestionService)(
            db_client=self.db_client,
            growatt_client=self.growatt_client,
            ai_agent=self.ai_agent
        )
        
        self.disruption_service = instrument_disruption_service(DisruptionAnalysisService)(
            db_client=self.db_client,
            growatt_client=self.growatt_client,
            ai_agent=self.ai_agent
        )
        
        self.user_service = instrument_user_service(UserManagementService)(
            db_client=self.db_client,
            growatt_client=self.growatt_client,
            ai_agent=self.ai_agent
        )
        
        self.plant_service = instrument_plant_service(PlantManagementService)(
            db_client=self.db_client,
            growatt_client=self.growatt_client,
            ai_agent=self.ai_agent
        )
        
        # Keep reference to background tasks
        self.background_tasks = self.disruption_service.background_tasks
    
    def get_current_time_ist(self):
        """
        Get the current time in Indian Standard Time (IST)
        
        Returns:
            datetime: Current datetime in IST
        """
        return datetime.now(self.ist_timezone)
    
    def convert_to_ist(self, dt):
        """
        Convert a datetime object to Indian Standard Time
        
        Args:
            dt (datetime): Datetime object to convert
            
        Returns:
            datetime: Datetime object in IST timezone
        """
        if dt.tzinfo is None:
            # If datetime has no timezone, assume it's in UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(self.ist_timezone)
    
    # ==== History Ingestion Methods ====
    
    def fetch_and_store_device_generation_history(self, device_sn, date_str=None, overwrite=False, store_records=False):
        """Fetch generation history for a device on a date and store it in the database"""
        return self.history_service.fetch_and_store_device_generation_history(
            device_sn=device_sn,
            date_str=date_str,
            overwrite=overwrite,
            store_records=store_records
        )

    def fetch_and_store_device_generation_history_range(self, device_sn, start_date, end_date, overwrite=False, store_records=True):
        """Fetch and store generation history for a device over a range of dates"""
        return self.history_service.fetch_and_store_device_generation_history_range(
            device_sn=device_sn,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite,
            store_records=store_records
        )
    
    def get_device_history_records(self, device_sn=None, plant_id=None, date_str=None):
        """Get history records for a device or plant and date from the database"""
        return self.history_service.get_device_history_records(
            device_sn=device_sn,
            plant_id=plant_id,
            date_str=date_str
        )
    
    # ==== Disruption Analysis Methods ====
    
    def analyze_device_generation_data_route(self, device_sn, date_str=None):
        """Analyze device generation data using AI agent"""
        return self.disruption_service.analyze_device_generation_data(
            device_sn=device_sn,
            date_str=date_str
        )
    
    def analyze_device_generation_data_and_store_disruptions_route(self, device_sn, date_str=None, overwrite=False):
        """Analyze device generation data and store disruptions in database"""
        return self.disruption_service.analyze_and_store_disruptions(
            device_sn=device_sn,
            date_str=date_str,
            overwrite=overwrite
        )
    
    def get_device_disruption_events_route(self, device_sn, date_str=None):
        """Get disruption events for a device"""
        return self.disruption_service.get_device_disruption_events(
            device_sn=device_sn,
            date_str=date_str
        )
    
    def analyze_device_disruptions_date_range(self, device_sn, start_date=None, end_date=None, overwrite=False):
        """Analyze device disruptions for a date range"""
        return self.disruption_service.analyze_device_disruptions_date_range(
            device_sn=device_sn,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite
        )
    
    def get_latest_analysis_date_for_device(self, device_sn):
        """Get the latest analysis date for a device"""
        return self.disruption_service.get_latest_analysis_date_for_device(device_sn)
    
    def update_device_analysis_ledger(self, device_sn, analysis_date, device_metadata=None):
        """Update the analysis ledger for a device"""
        return self.disruption_service.update_device_analysis_ledger(
            device_sn=device_sn,
            analysis_date=analysis_date,
            device_metadata=device_metadata
        )
    
    def get_task_status(self, task_id):
        """Get the status of a background task"""
        return self.disruption_service.get_task_status(task_id)
    
    # ==== User Management Methods ====
    
    def onboard_new_user(self, username, user_id, vendor, phone=None, email=None, password=None, role=None, bootstrap_history=True):
        """Onboard a new user"""
        return self.user_service.onboard_new_user(
            username=username,
            user_id=user_id,
            vendor=vendor,
            phone=phone,
            email=email,
            password=password,
            role=role,
            bootstrap_history=bootstrap_history
        )
    
    def get_user_dashboard_data(self, username):
        """Get dashboard data for a user"""
        return self.user_service.get_user_dashboard_data(username)
    
    def get_current_power_for_user(self, username, plant_id=None):
        """Get current power output for a user"""
        return self.user_service.get_current_power_for_user(
            username=username,
            plant_id=plant_id
        )
    
    def bootstrap_history_ingestion_for_new_user(self, device_sn):
        """Bootstrap history ingestion for a new user"""
        return self.history_service.bootstrap_history_ingestion_for_new_user(device_sn)
    
    # ==== Plant Management Methods ====
    
    def fetch_and_store_plant_summary(self, plant_id):
        """Fetch and store plant summary"""
        return self.plant_service.fetch_and_store_plant_summary(plant_id)
    
    def fetch_and_store_plant_energy_daily_generation(self, plant_id, start_date=None, end_date=None):
        """Fetch and store plant energy daily generation"""
        return self.plant_service.fetch_and_store_plant_energy_daily_generation(
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date
        )
    
    def get_efficiency_snapshot_data(self, min_eff=0, max_eff=100, plant_name_selected=None):
        """Get efficiency snapshot data for plants"""
        return self.plant_service.get_efficiency_snapshot_data(
            min_eff=min_eff,
            max_eff=max_eff,
            plant_name_selected=plant_name_selected
        )