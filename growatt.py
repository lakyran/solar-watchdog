import requests
import os
import logging
import json
from datetime import datetime, timezone
import pytz

class GrowattAPI:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Growatt API configuration
        self.base_url = os.getenv('GROWATT_API_URL', '')
        self.api_token = os.getenv('GROWATT_API_TOKEN', '')
        
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
    
    def call_api(self, endpoint, method='GET', params=None, data=None):
        """
        Make a request to the Growatt API
        
        Args:
            endpoint (str): The API endpoint to call (e.g., '/device/list')
            method (str): HTTP method (GET, POST, etc.)
            params (dict): Query parameters
            data (dict): Request body data
        
        Returns:
            dict: JSON response from the API
        
        Raises:
            Exception: If the API request fails
        """
        if not self.base_url:
            raise ValueError("GROWATT_API_URL environment variable is not set")
        
        if not self.api_token:
            raise ValueError("GROWATT_API_TOKEN environment variable is not set")
        
        headers = {
            'Token': f'{self.api_token}',
            'Content-Type': 'application/json',
            'User-Agent': 'PostmanRuntime/7.43.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Accept': '*/*',
            'Cache-Control': 'no-cache'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            self.logger.info(f"Making API request to {url} with params {params}")
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data,
                timeout=30
            )
            response.raise_for_status()  # Raise an exception for bad status codes
            
            # Debug: Log the raw response content
            self.logger.debug(f"Raw API response: {response.text[:200]}...")
            
            # Check if response is empty
            if not response.text or response.text.isspace():
                error_msg = "API returned empty response"
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            try:
                json_response = response.json()
            except json.JSONDecodeError as e:
                error_msg = f"Failed to parse API response as JSON: {str(e)}. Raw response: {response.text[:500]}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Check if the response has a 'data' field and is successful
            if 'data' not in json_response:
                error_msg = f"Missing 'data' field in response: {json_response}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            if json_response.get('error_code', 0) != 0:
                error_msg = f"API error: {json_response.get('error_msg', 'Unknown error')}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Ensure history_data has the expected structure
            if not isinstance(json_response['data'], dict) or 'datas' not in json_response['data']:
                error_msg = f"Invalid response format from API: {json_response}. 'datas' key is missing"
                self.logger.error(error_msg)
                raise ValueError(error_msg)
                
            return json_response['data']
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {str(e)}")
            raise Exception(f"Failed to call Growatt API: {str(e)}")
        except ValueError as e:
            raise e
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            raise Exception(f"Error processing API response: {str(e)}")
    
    def fetch_device_history(self, device_sn, device_metadata, start_date, end_date, page=1):
        """
        Fetch energy history for a specific device from the Growatt API.

        Args:
            device_sn (str): The serial number of the device.
            device_metadata (dict): Metadata for the device
            start_date (str): The start date for the history (YYYY-MM-DD)
            end_date (str): The end date for the history (YYYY-MM-DD)
        
        Returns:
            dict: JSON response containing the device history.

        Raises:
            Exception: If the API request fails or device_sn is not provided.
        """
        if not device_sn:
            raise ValueError("Device serial number is required")

        # Select the appropriate endpoint based on device type
        device_type_endpoints = {
            1: '/device/inverter/data',
            7: '/device/tlx/tlx_data'
        }
        device_type_serials = {
            1: 'device_sn',
            7: 'tlx_sn'
        }
        api_method_mapping = {
            1: 'GET',
            7: 'POST'
        }
        
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'perpage': 100,
            'page': page
        }

        device_type = device_metadata['device_type']
        params.update({device_type_serials.get(device_type, 'device_sn'): device_sn})

        endpoint = device_type_endpoints.get(device_type, '/device/inverter/data')
        api_method = api_method_mapping.get(device_type, 'GET')
        
        try:
            response = self.call_api(endpoint, method=api_method, params=params)
            
            # Validate response structure
            if not isinstance(response, dict):
                self.logger.error(f"Invalid response type: {type(response)}. Expected dict.")
                raise ValueError(f"Invalid response format from Growatt API: {response}")
                
            if 'datas' not in response:
                self.logger.error(f"Missing 'datas' key in response: {response}")
                raise ValueError(f"Response missing 'datas' key: {response}")
                
            if not isinstance(response['datas'], list):
                self.logger.error(f"'datas' is not a list: {type(response['datas'])}")
                raise ValueError(f"'datas' field is not a list: {response['datas']}")
                
            return response
            
        except Exception as e:
            self.logger.error(f"Failed to fetch history for device {device_sn}: {e}")
            raise Exception(f"Failed to fetch history for device {device_sn}: {str(e)}")
        
    def process_history_data_for_db(self, history_data, device_sn, date_str, device_metadata):
        """
        Process raw history data and transform it into database-ready entries
        
        Args:
            history_data (dict): Raw history data from Growatt API
            device_sn (str): Device serial number
            date_str (str): Date string in YYYY-MM-DD format
            device_metadata (dict): Dictionary containing device metadata such as:
                - vendor (str): Vendor name
                - device_oem (str): Device OEM name
                - user_name (str): User name
                - plant_id (str): Plant ID
                - device_type (int): Device type
            
        Returns:
            list: Processed database entries
        """
        database_entries = []
        total_records_on_day = 0
        
        if 'count' in history_data:
            total_records_on_day = history_data['count']
            print(f"Total records on day {date_str} for device {device_sn}: {total_records_on_day}")
        
        # Extract relevant data from history_data
        if 'datas' in history_data and isinstance(history_data['datas'], list):
            for entry in history_data['datas']:
                # Transform each entry to include only necessary fields based on device type
                transformed_entry = self.transform_history_entry_by_device_type(entry, device_metadata['device_type'])
                
                # Parse datetime and ensure it has IST timezone
                datetime_str = entry.get('time', '')
                try:
                    # First try to parse the datetime string as is
                    dt_obj = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                    # Set timezone to IST
                    dt_obj = dt_obj.replace(tzinfo=self.ist_timezone)
                    # Format back to string
                    datetime_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    # If parsing fails, keep the original value
                    pass

                # Create a database-ready entry
                db_entry = {
                    'datetime': datetime_str,
                    'vendor': device_metadata['vendor'],
                    'device_oem': device_metadata['device_oem'],
                    'user_name': device_metadata['user_name'],
                    'plant_id': device_metadata['plant_id'],
                    'device_sn': device_sn,
                    'device_type': device_metadata['device_type'],
                    'status': transformed_entry['status'],
                    'ppv': transformed_entry['ppv'],
                    'pac': transformed_entry['pac'],
                    'eacToday': transformed_entry['eacToday'],
                    'vpv1': transformed_entry['vpv1'],
                    'vpv2': transformed_entry['vpv2'],
                    'vpv3': transformed_entry['vpv3'],
                    'vac1': transformed_entry['vac1'],
                    'vac2': transformed_entry['vac2'],
                    'vac3': transformed_entry['vac3'],
                    'temperature': transformed_entry['temperature'],
                    'faultType': transformed_entry['faultType'],
                    'total_records_on_day': total_records_on_day,
                    'data': json.dumps(transformed_entry)  # Store the processed data
                }
                database_entries.append(db_entry)
        
        return database_entries
        
    def transform_history_entry_by_device_type(self, entry, device_type):
        """
        Transform an entry from the Growatt API based on device type
        
        Args:
            entry (dict): Raw entry from Growatt API
            device_type (int): Type of device (1 for Inverter, 7 for TLX...)
            
        Returns:
            dict: Transformed entry with relevant fields
        """
        device_type_fields_mapping = {
            1: {
                'time': 'time',
                'status': 'status',
                'ppv': 'ppv',
                'pac': 'pac',
                'eacToday': 'eacToday',
                'vpv1': 'vpv1',
                'vpv2': 'vpv2',
                'vpv3': 'vpv3',
                'vac1': 'vac1',
                'vac2': 'vac2',
                'vac3': 'vac3',
                'temperature': 'temperature',
                'faultType': 'faultType'
            },
            7: {
                'time': 'time',
                'status': 'status',
                'ppv': 'ppv',
                'pac': 'pac',
                'eacToday': 'eacToday',
                'vpv1': 'vpv1',
                'vpv2': 'vpv2',
                'vpv3': 'vpv3',
                'vac1': 'vac1',
                'vac2': 'vac2',
                'vac3': 'vac3',
                'temp1': 'temperature',
                'faultType': 'faultType'

            }
        }

        status_mapping = {
            0: 'standby',
            1: 'normal',
            2: 'fault',
            3: 'fault'
        }

        transformed_entry = {}
        
        # Get field mapping for this device type
        current_mapping = device_type_fields_mapping.get(device_type)
        if not current_mapping:
            error_msg = f"No mapping found for device type {device_type}"
            self.logger.info(error_msg)
            raise ValueError(error_msg)
        
        for field, key in current_mapping.items():
            if field in entry:
                transformed_entry[key] = entry[field]
            else:
                error_msg = f"Required field '{field}' not found in data for device type {device_type}"
                self.logger.info(error_msg)
                raise ValueError(error_msg)
            
        transformed_entry['status'] = status_mapping.get(entry['status'])
        if not transformed_entry['status']:
            error_msg = f"No status mapping found for status {entry['status']}, device type {device_type}"
            self.logger.info(error_msg)
            raise ValueError(error_msg)
        
        return transformed_entry