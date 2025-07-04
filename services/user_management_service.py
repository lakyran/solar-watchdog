from services.base_service import BaseService
from werkzeug.security import generate_password_hash, check_password_hash
import time

class UserManagementService(BaseService):
    """Service for managing users and user-related operations"""
    
    def get_users_list(self):
        """
        Get a list of all users in the system
        
        Returns:
            list: List of user records
        """
        try:
            self.logger.info("Getting list of all users")
            return self.db_client.get_users_list()
        except Exception as e:
            error_msg = f"Error getting users list: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_user(self, username):
        """
        Get a single user by username
        
        Args:
            username (str): Username to lookup
            
        Returns:
            dict: User record or None if not found
        """
        try:
            self.logger.info(f"Getting user: {username}")
            return self.db_client.get_user(username)
        except Exception as e:
            error_msg = f"Error getting user {username}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def check_admin_role(self, username):
        """
        Check if a user has admin role
        
        Args:
            username (str): Username to check
            
        Returns:
            bool: True if user is an admin, False otherwise
        """
        try:
            user = self.get_user(username)
            if not user:
                return False
            return user.get('role') == 'admin'
        except Exception as e:
            self.logger.error(f"Error checking admin role for {username}: {str(e)}")
            return False
    
    def authenticate_user(self, username, password):
        """
        Authenticate a user with username and password
        
        Args:
            username (str): Username to authenticate
            password (str): Password to verify
            
        Returns:
            tuple: (is_authenticated, user_data, error_message)
                - is_authenticated (bool): True if authentication succeeded
                - user_data (dict): User data if authenticated, None otherwise
                - error_message (str): Error message if authentication failed, None otherwise
        """
        try:
            self.logger.info(f"Authenticating user: {username}")
            
            # Get user from database
            user = self.get_user(username)
            
            # Check if user exists
            if not user:
                self.logger.info(f"User {username} not found")
                return False, None, "Invalid username or password"
            
            # Check password
            if not user.get('password_hash') or not check_password_hash(user.get('password_hash'), password):
                self.logger.info(f"Invalid username or password for user: {username}")
                return False, None, "Invalid username or password"
            
            # Authentication successful
            return True, user, None
            
        except Exception as e:
            error_msg = f"Error authenticating user {username}: {str(e)}"
            self.logger.error(error_msg)
            return False, None, "Authentication failed"
    
    def onboard_new_user(self, username, user_id, vendor, phone=None, email=None, password=None, role=None, bootstrap_history=True):
        """
        Onboard a new user by:
        1. Inserting the user into the database
        2. Fetching their plants from Growatt
        3. Inserting each plant into the database
        4. Fetching and storing plant summary for each plant
        5. Fetching devices for each plant
        6. Inserting inverters (device type 1 or 7) into the database
        7. (Optional) Bootstrap historical data ingestion for all inverters
        
        Args:
            username (str): Username for the new user
            user_id (str): User ID for the new user
            vendor (str): Vendor name (e.g., 'Growatt')
            phone (str, optional): User's phone number
            email (str, optional): User's email address
            password (str, optional): User's password
            role (str, optional): User's role (default is 'user')
            bootstrap_history (bool, optional): Whether to bootstrap historical data (default is True)
            
        Returns:
            dict: Summary of the onboarding process
        """
        try:
            self.logger.info(f"Starting onboarding process for user: {username} (ID: {user_id})")
            
            # Summary statistics to track progress
            summary = {
                'user': {'username': username, 'user_id': user_id, 'vendor': vendor},
                'plants_count': 0,
                'plants': [],
                'inverters_count': 0,
                'inverters': [],
                'status': 'success',
                'history_bootstrap': []
            }
            
            # Step 1: Insert user into database
            self.logger.info(f"Step 1: Inserting user {username} into database")
            user_data = {
                'user_id': user_id,
                'user_name': username, 
                'vendor': vendor,
                'phone': phone,
                'email': email,
                'role': role or 'user'
            }
            
            # If password is provided, hash it
            if password:
                user_data['password_hash'] = generate_password_hash(password)
            
            user_result = self.db_client.insert_user(user_data)
            if user_result['status'] != 'success':
                error_msg = f"Failed to insert user: {user_result['message']}"
                self.logger.error(error_msg)
                summary['status'] = 'error'
                summary['message'] = error_msg
                return summary
                
            self.logger.info(f"User {username} inserted successfully")
            
            # Step 2: Fetch plants for this user from Growatt
            self.logger.info(f"Step 2: Fetching plants for user {username} from Growatt API")
            try:
                plants = self.growatt_client.fetch_user_plant_list(username)
                self.logger.info(f"Found {len(plants)} plants for user {username}")
                summary['plants_count'] = len(plants)
            except Exception as e:
                error_msg = f"Failed to fetch plants for user {username}: {str(e)}"
                self.logger.error(error_msg)
                summary['status'] = 'partial'
                summary['message'] = error_msg
                return summary
            
            # Step 3: Insert each plant into the database
            self.logger.info(f"Step 3: Inserting {len(plants)} plants into database")
            
            for plant in plants:
                plant_id = str(plant.get('plant_id'))
                plant_name = plant.get('name', '')
                
                self.logger.info(f"Inserting plant {plant_name} (ID: {plant_id})")
                
                plant_data = {
                    'plant_id': plant_id,
                    'plant_name': plant_name,
                    'user_name': username,
                    'user_id': user_id,
                    'vendor': vendor,
                    'city': plant.get('city', ''),
                    'latitude': plant.get('latitude', '0.0'),
                    'longitude': plant.get('longitude', '0.0'),
                    'peak_power': float(plant.get('peak_power', 0))
                }
                
                try:
                    plant_result = self.db_client.insert_plant(plant_data)
                    if plant_result['status'] == 'success':
                        self.logger.info(f"Plant {plant_name} (ID: {plant_id}) inserted successfully")
                        plant_summary = {
                            'plant_id': plant_id,
                            'plant_name': plant_name,
                            'peak_power': plant_data['peak_power'],
                            'devices_count': 0,
                            'devices': []
                        }
                        summary['plants'].append(plant_summary)
                    else:
                        self.logger.error(f"Failed to insert plant {plant_name} (ID: {plant_id}): {plant_result['message']}")
                        continue
                except Exception as e:
                    self.logger.error(f"Failed to insert plant {plant_name} (ID: {plant_id}): {str(e)}")
                    continue

                # Step 4: Fetch and store plant summary
                self.logger.info(f"Step 4: Fetching and storing summary for plant {plant_name} (ID: {plant_id})")
                try:
                    # Use PlantManagementService to fetch and store plant summary
                    from services.plant_management_service import PlantManagementService
                    plant_service = PlantManagementService(
                        db_client=self.db_client,
                        growatt_client=self.growatt_client
                    )
                    summary_result = plant_service.fetch_and_store_plant_summary(plant_id)
                    
                    if isinstance(summary_result, tuple) or summary_result.get('status') != 'success':
                        self.logger.warning(f"Plant summary fetch for {plant_name} (ID: {plant_id}) was not successful: {summary_result}")
                    else:
                        self.logger.info(f"Plant summary for {plant_name} (ID: {plant_id}) fetched successfully")
                except Exception as e:
                    self.logger.error(f"Failed to fetch summary for plant {plant_name} (ID: {plant_id}): {str(e)}")
                
                # Step 5: Fetch devices for this plant
                self.logger.info(f"Step 5: Fetching devices for plant {plant_name} (ID: {plant_id})")
                try:
                    devices = self.growatt_client.fetch_plant_devices_list(plant_id)
                    self.logger.info(f"Found {len(devices)} devices for plant {plant_name} (ID: {plant_id})")
                except Exception as e:
                    self.logger.error(f"Failed to fetch devices for plant {plant_name} (ID: {plant_id}): {str(e)}")
                    continue
                
                # Step 6: Filter and insert inverters (device type 1 or 7)
                self.logger.info(f"Step 6: Filtering and inserting inverters from {len(devices)} devices")
                
                inverters = [device for device in devices if device.get('type') in [1, 7]]
                plant_summary['devices_count'] = len(inverters)
                
                for inverter in inverters:
                    device_sn = inverter.get('device_sn', '')
                    device_type = inverter.get('type', 0)
                    
                    self.logger.info(f"Inserting inverter {device_sn} (Type: {device_type})")
                    
                    inverter_data = {
                        'device_sn': device_sn,
                        'user_name': username,
                        'user_id': user_id,
                        'vendor': vendor,
                        'plant_id': plant_id,
                        'device_oem': inverter.get('manufacturer', 'Unknown'),
                        'device_type': device_type,
                        'latitude': float(plant.get('latitude', 0.0)),
                        'longitude': float(plant.get('longitude', 0.0))
                    }
                    
                    try:
                        inverter_result = self.db_client.insert_inverter(inverter_data)
                        if inverter_result['status'] == 'success':
                            self.logger.info(f"Inverter {device_sn} inserted successfully")
                            summary['inverters_count'] += 1
                            summary['inverters'].append({
                                'device_sn': device_sn,
                                'device_type': device_type,
                                'plant_id': plant_id
                            })
                            plant_summary['devices'].append({
                                'device_sn': device_sn,
                                'device_type': device_type
                            })
                        else:
                            self.logger.error(f"Failed to insert inverter {device_sn}: {inverter_result['message']}")
                    except Exception as e:
                        self.logger.error(f"Failed to insert inverter {device_sn}: {str(e)}")
            
            # Step 7: Bootstrap historical data ingestion for all inverters (if enabled)
            if bootstrap_history:
                self.logger.info(f"Step 7: Bootstrapping historical data ingestion for {summary['inverters_count']} inverters")
                
                # Use HistoryIngestionService for bootstrapping
                from services.history_ingestion_service import HistoryIngestionService
                history_service = HistoryIngestionService(
                    db_client=self.db_client,
                    growatt_client=self.growatt_client
                )
                
                for inverter in summary['inverters']:
                    device_sn = inverter['device_sn']
                    try:
                        # Bootstrap historical data for this inverter
                        bootstrap_result = history_service.bootstrap_history_ingestion_for_new_user(device_sn)
                        summary['history_bootstrap'].append({
                            'device_sn': device_sn,
                            'result': bootstrap_result
                        })
                    except Exception as e:
                        self.logger.error(f"Failed to bootstrap history for inverter {device_sn}: {str(e)}")
                        summary['history_bootstrap'].append({
                            'device_sn': device_sn,
                            'status': 'error',
                            'error': str(e)
                        })
                    
                    # Add a small delay to avoid overwhelming the API
                    time.sleep(2)
            else:
                self.logger.info("Step 7: Bootstrap historical data ingestion skipped as per request")
                summary['bootstrap_history'] = False
            
            # Return the complete summary
            self.logger.info(f"Completed onboarding for user {username}: {summary['plants_count']} plants, {summary['inverters_count']} inverters")
            return summary
            
        except Exception as e:
            error_msg = f"Error during onboarding process for user {username}: {str(e)}"
            self.logger.error(error_msg)
            return {
                'status': 'error',
                'message': error_msg,
                'user': {'username': username, 'user_id': user_id, 'vendor': vendor}
            }
    
    def get_user_dashboard_data(self, username):
        """
        Get dashboard data for a specific user
        
        Args:
            username (str): Username to fetch dashboard data for
            
        Returns:
            dict: Dashboard data including all the user's plants details and summaries.
                 For backward compatibility, also includes first plant's details at the top level.
        """
        try:
            self.logger.info(f"Getting dashboard data for user: {username}")
            
            # Validate username
            if not username:
                error_msg = "Username is required"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}, 400
            
            # Step 1: Get all plants for the user
            from services.plant_management_service import PlantManagementService
            plant_service = PlantManagementService(
                db_client=self.db_client,
                growatt_client=self.growatt_client
            )
            plants = plant_service.get_plants_list(username)
            
            if not plants or len(plants) == 0:
                self.logger.info(f"No plant found for user: {username}")
                return {
                    "status": "error", 
                    "message": f"No plant found for user: {username}"
                }, 404
            
            # Initialize response structure
            response = {
                "status": "success",
                "username": username,
                "plants": []
            }
            
            # Process each plant
            for plant in plants:
                plant_id = plant.get('plant_id')
                
                if not plant_id:
                    self.logger.warning(f"Invalid plant data found for user: {username}, skipping")
                    continue
                
                # Get plant summary using plant service
                plant_summary = plant_service.get_plant_energy_summary(plant_id)
                
                # If plant_summary is None, initialize it as an empty dict
                if plant_summary is None:
                    plant_summary = {}
                
                # Get current power specific to this plant
                plant_current_power = self.get_current_power_for_user(username, plant_id)
                plant_summary['current_power'] = plant_current_power
                
                # Add plant to the plants array
                response["plants"].append({
                    "plant_details": plant,
                    "plant_summary": plant_summary
                })
            
            # For backward compatibility, include first plant data at top level
            if len(response["plants"]) > 0:
                response["plant_details"] = response["plants"][0]["plant_details"]
                response["plant_summary"] = response["plants"][0]["plant_summary"]
            
            # Return the dashboard data
            return response
                
        except Exception as e:
            error_msg = f"Error getting dashboard data for user {username}: {str(e)}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}, 500
            
    def get_current_power_for_user(self, username, plant_id=None):
        """
        Get the current power output for a specific user
        
        Args:
            username (str): The username to get current power for
            plant_id (str, optional): Plant ID to filter results. If None, returns for all plants of the user.
            
        Returns:
            float: Current power output in Watts (W)
        """
        try:
            self.logger.info(f"Getting current power output for user: {username}{' for plant: ' + plant_id if plant_id else ''}")
            
            # Get current output in watts from the database
            current_output_watts = self.db_client.get_current_output_for_user(username, plant_id)
            
            # Convert watts to kilowatts (1 kW = 1000 W)
            if current_output_watts is not None:
                current_power_kw = current_output_watts / 1000.0
                # Round to 2 decimal places
                current_power_kw = round(current_power_kw, 2)
                self.logger.info(f"Current power for user {username}{' plant ' + plant_id if plant_id else ''}: {current_power_kw} kW")
                return current_power_kw
            else:
                self.logger.info(f"No current power data available for user {username}{' plant ' + plant_id if plant_id else ''}, returning 0")
                return 0.0
                
        except Exception as e:
            error_msg = f"Error getting current power for user {username}{' plant ' + plant_id if plant_id else ''}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def register_device_token(self, username, device_id, token, device_platform, notification_enabled=True):
        """
        Register a device token for push notifications
        
        Args:
            username (str): Username of the user
            device_id (str): Unique identifier for the device
            token (str): Device token for push notifications
            device_platform (str): Platform of the device (android, ios)
            notification_enabled (bool, optional): Whether notifications are enabled
            
        Returns:
            dict: Result of the operation
        """
        try:
            self.logger.info(f"Registering device token for user {username}, device {device_id}, platform {device_platform}")
            
            # Get user from database
            user = self.get_user(username)
            
            # Check if user exists
            if not user:
                self.logger.warning(f"User {username} not found when registering device token")
                return {
                    "status": "error",
                    "message": "User not found"
                }
            
            user_id = user.get('user_id')
            
            # Register token based on platform
            if device_platform.lower() == 'android':
                result = self.db_client.insert_android_device_token(
                    user_id=user_id,
                    token=token,
                    device_id=device_id,
                    notification_enabled=notification_enabled
                )
                return result
            else:
                self.logger.warning(f"Unsupported device platform: {device_platform}")
                return {
                    "status": "error",
                    "message": f"Unsupported device platform: {device_platform}"
                }
                
        except Exception as e:
            error_msg = f"Error registering device token: {str(e)}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg
            }
    
    def get_user_device_tokens(self, username):
        """
        Get all device tokens for a user
        
        Args:
            username (str): Username to get tokens for
            
        Returns:
            dict: Dictionary containing device tokens by platform
        """
        try:
            self.logger.info(f"Getting device tokens for user {username}")
            
            # Get user from database
            user = self.get_user(username)
            
            # Check if user exists
            if not user:
                self.logger.warning(f"User {username} not found when getting device tokens")
                return {
                    "status": "error",
                    "message": "User not found"
                }
            
            user_id = user.get('user_id')
            
            # Get Android tokens
            android_tokens = self.db_client.get_android_device_tokens(user_id=user_id)
            
            return {
                "status": "success",
                "tokens": {
                    "android": android_tokens,
                    # Add other platforms here in the future
                }
            }
                
        except Exception as e:
            error_msg = f"Error getting user device tokens: {str(e)}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg
            } 