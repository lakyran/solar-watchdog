import logging
import pytz
from datetime import datetime, timezone

class BaseService:
    """Base class for all services with common functionality"""
    
    def __init__(self, db_client=None, growatt_client=None, ai_agent=None):
        """
        Initialize the base service
        
        Args:
            db_client: Database client instance
            growatt_client: Growatt API client instance
            ai_agent: AI agent instance
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.db_client = db_client
        self.growatt_client = growatt_client
        self.ai_agent = ai_agent
        
        # Define the IST timezone
        self.ist_timezone = pytz.timezone('Asia/Kolkata')
    
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