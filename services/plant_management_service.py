from datetime import datetime, timedelta
import time
from services.base_service import BaseService

class PlantManagementService(BaseService):
    """Service for managing solar plants and plant-related operations"""
    
    def get_plants_list(self, username=None):
        """
        Get a list of all plants, optionally filtered by username
        
        Args:
            username (str, optional): Username to filter plants by
            
        Returns:
            list: List of plant records
        """
        try:
            if username:
                self.logger.info(f"Getting plants list for user: {username}")
            else:
                self.logger.info("Getting list of all plants")
                
            return self.db_client.get_plants_list(username)
        except Exception as e:
            error_msg = f"Error getting plants list{' for user: ' + username if username else ''}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_plant_energy_summary(self, plant_id):
        """
        Get energy summary for a specific plant
        
        Args:
            plant_id (str): Plant ID to get summary for
            
        Returns:
            dict: Plant energy summary record
        """
        try:
            self.logger.info(f"Getting energy summary for plant: {plant_id}")
            return self.db_client.get_plant_energy_summary(plant_id)
        except Exception as e:
            error_msg = f"Error getting energy summary for plant {plant_id}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_inverters_list(self, username=None, plant_id=None):
        """
        Get a list of all inverters, optionally filtered by username or plant_id
        
        Args:
            username (str, optional): Username to filter inverters by
            plant_id (str, optional): Plant ID to filter inverters by
            
        Returns:
            list: List of inverter records
        """
        try:
            filters = []
            if username:
                filters.append(f"user: {username}")
            if plant_id:
                filters.append(f"plant: {plant_id}")
                
            filter_str = ", ".join(filters)
            if filter_str:
                self.logger.info(f"Getting inverters list filtered by {filter_str}")
            else:
                self.logger.info("Getting list of all inverters")
                
            # Get the base list of inverters by username from the database
            # Note: AzureDB.get_inverters_list only accepts username parameter
            inverters = self.db_client.get_inverters_list(username)
            
            # If plant_id is specified, filter the results in memory
            if plant_id:
                self.logger.info(f"Filtering inverters by plant_id: {plant_id}")
                inverters = [inv for inv in inverters if inv.get('plant_id') == plant_id]
            
            return inverters
        except Exception as e:
            error_msg = f"Error getting inverters list: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_inverter_record(self, device_sn):
        """
        Get metadata for a specific inverter
        
        Args:
            device_sn (str): Device serial number
            
        Returns:
            dict: Inverter record
        """
        try:
            self.logger.info(f"Getting inverter record for device: {device_sn}")
            return self.db_client.get_inverter_record(device_sn)
        except Exception as e:
            error_msg = f"Error getting inverter record for device {device_sn}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def fetch_and_store_plant_summary(self, plant_id):
        """
        Fetch plant energy summary from Growatt API and store it in the database
        
        Args:
            plant_id (str): Plant ID to fetch summary for
            
        Returns:
            dict: Result containing API data and database operation result
        """
        try:
            user_name = None
            self.logger.info(f"Fetching and storing energy summary for plant: {plant_id}")
            
            # Validate plant_id
            if not plant_id:
                error_msg = "Plant ID is required"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}, 400
            
            # Step 1: Fetch plant summary from Growatt API
            self.logger.info(f"Step 1: Fetching plant summary from API for plant: {plant_id}")
            api_summary = self.growatt_client.fetch_plant_summary(plant_id)
            
            # Initialize variables for required metadata
            vendor = None
            plant_name = None
            peak_power = float(api_summary.get('peak_power_actual', 0))
            
            # Step 2: If any required fields are missing, get them from plants table
            self.logger.info(f"Step 2: Getting required metadata for plant: {plant_id}")
            plants = self.db_client.get_plants_list()
            for plant in plants:
                if plant.get('plant_id') == plant_id:
                    user_name = plant.get('user_name')
                    vendor = plant.get('vendor')
                    plant_name = plant.get('plant_name')
                    if not peak_power and 'peak_power' in plant:
                        peak_power = float(plant.get('peak_power', 0))
                    break
            
            # Validate that we have the required fields
            if not user_name:
                error_msg = f"Could not determine user_name for plant_id: {plant_id}"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}, 400
                
            if not vendor:
                error_msg = f"Could not determine vendor for plant_id: {plant_id}"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}, 400
            
            # Step 3: Prepare data and insert/update in the database
            self.logger.info(f"Step 3: Preparing and storing plant summary for plant_id: {plant_id} (user: {user_name})")
            plant_data = {
                'plant_id': plant_id,
                'plant_name': plant_name or '',
                'user_name': user_name,
                'vendor': vendor,
                'peak_power': peak_power,
                'current_power': float(api_summary.get('current_power', 0)),
                'total_energy': float(api_summary.get('total_energy', 0)),
                'yearly_energy': float(api_summary.get('yearly_energy', 0)),
                'monthly_energy': float(api_summary.get('monthly_energy', 0)),
                'today_energy': float(api_summary.get('today_energy', 0)),
                'carbon_offset': float(api_summary.get('carbon_offset', 0))
            }
            
            # Insert/update plant summary in database
            db_result = self.db_client.insert_plant_energy_summary(plant_data)
            
            # Return result
            if db_result.get('status') == 'success':
                return {
                    'status': 'success',
                    'message': 'Plant energy summary updated successfully',
                    'plant_id': plant_id,
                    'api_data': api_summary,
                    'db_result': db_result
                }
            else:
                return {
                    'status': 'error',
                    'message': db_result.get('message', 'Failed to update plant energy summary'),
                    'plant_id': plant_id
                }, 500
                
        except ValueError as ve:
            error_msg = f"Validation error: {str(ve)}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}, 400
        except Exception as e:
            error_msg = f"Error processing plant summary for plant {plant_id} (user: {user_name}): {str(e)}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}, 500
    
    def fetch_and_store_plant_energy_daily_generation(self, plant_id, start_date=None, end_date=None):
        """
        Fetch daily generation summary for a plant from Growatt API and store it in the database
        
        Args:
            plant_id (str): Plant ID to fetch summary for
            start_date (str, optional): Start date in YYYY-MM-DD format. Defaults to 6 days ago.
            end_date (str, optional): End date in YYYY-MM-DD format. Defaults to today.
            
        Returns:
            dict: Result containing operation status and database result
        """
        try:
            user_name = None
            # Set default dates if not provided
            current_time = self.get_current_time_ist()
            if not end_date:
                end_date = current_time.strftime('%Y-%m-%d')
            
            if not start_date:
                # Default to 6 days ago 
                start_date = (current_time - timedelta(days=6)).strftime('%Y-%m-%d')
            
            self.logger.info(f"Starting fetch_and_store_plant_energy_daily_generation for plant: {plant_id}")
            self.logger.info(f"Date range: {start_date} to {end_date}")

            # Get plant data from the plants table to get user_name, vendor, and plant_name
            plant_data = None
            plants = self.db_client.get_plants_list()
            for plant in plants:
                if plant.get('plant_id') == plant_id:
                    plant_data = plant
                    break
            
            if not plant_data:
                error_msg = f"No plant record found for plant_id: {plant_id}"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}, 404
            
            self.logger.info(f"Retrieved plant data: {plant_data.get('plant_name', '')} (ID: {plant_id}), user: {plant_data.get('user_name')}")

            # Get user_name and vendor from plant_data
            user_name = plant_data.get('user_name', '')
            vendor = plant_data.get('vendor', 'unisolarpower')
            plant_name = plant_data.get('plant_name', '')
            
            # Parse input dates
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                days_difference = (end_date_obj - start_date_obj).days + 1  # Include both start and end dates
                
                self.logger.info(f"Processing date range of {days_difference} days using chunking approach for plant {plant_id} (user: {user_name})")
                
                # Initialize tracking variables
                all_energy_entries = []
                db_results = []
                chunk_count = 0
                current_start = start_date_obj
                
                # Process the date range in chunks
                while current_start <= end_date_obj:
                    chunk_count += 1
                    
                    # Calculate chunk end date (either 6 days after start or the original end date, whichever is earlier)
                    chunk_end = min(current_start + timedelta(days=6), end_date_obj)
                    
                    chunk_start_str = current_start.strftime('%Y-%m-%d')
                    chunk_end_str = chunk_end.strftime('%Y-%m-%d')
                    
                    self.logger.info(f"Processing chunk {chunk_count}: {chunk_start_str} to {chunk_end_str} for plant {plant_id} (user: {user_name})")
                    
                    # Fetch data for this chunk
                    try:
                        # Call API for this date range chunk
                        self.logger.info(f"Calling Growatt API to fetch energy data for plant {plant_id} (user: {user_name}), chunk {chunk_count}")
                        energy_data = self.growatt_client.fetch_plant_energy_data(
                            plant_id=plant_id,
                            start_date=chunk_start_str,
                            end_date=chunk_end_str
                        )
                        
                        if energy_data:
                            self.logger.info(f"Received {len(energy_data)} entries for plant {plant_id} (user: {user_name}), chunk {chunk_count}")
                            
                            # Format the data for database insertion
                            chunk_entries = []
                            for entry in energy_data:
                                date_value = entry['date']
                                energy_value = entry['energy']
                                self.logger.debug(f"Processing energy entry: date={date_value}, energy={energy_value}")
                                
                                # Create database entry
                                chunk_entries.append({
                                    'plant_id': plant_id,
                                    'plant_name': plant_name,
                                    'user_name': user_name,
                                    'vendor': vendor,
                                    'date': date_value,
                                    'day_energy': float(energy_value)
                                })
                            
                            # Insert entries for this chunk into the database
                            if chunk_entries:
                                self.logger.info(f"Inserting {len(chunk_entries)} entries for plant {plant_id} (user: {user_name}), chunk {chunk_count}")
                                chunk_db_result = self.db_client.insert_plant_daily_generation_history(chunk_entries)
                                db_results.append(chunk_db_result)
                                all_energy_entries.extend(chunk_entries)
                                self.logger.info(f"Chunk {chunk_count} database operation completed for plant {plant_id} (user: {user_name}): inserted={chunk_db_result.get('inserted_records', 0)}, updated={chunk_db_result.get('updated_records', 0)}")
                            
                        else:
                            self.logger.warning(f"No data received for plant {plant_id} (user: {user_name}), chunk {chunk_count}")
                        
                    except Exception as chunk_error:
                        self.logger.error(f"Error processing chunk {chunk_count} for plant {plant_id} (user: {user_name}): {str(chunk_error)}")
                        # Continue with the next chunk
                    
                    # Move to the next chunk
                    current_start = chunk_end + timedelta(days=1)
                    
                    # Add a small delay between API calls to avoid rate limiting
                    time.sleep(1)
                
                # Compile final results
                total_inserted = sum(result.get('inserted_records', 0) for result in db_results if isinstance(result, dict))
                total_updated = sum(result.get('updated_records', 0) for result in db_results if isinstance(result, dict))
                
                self.logger.info(f"All chunks processed for plant {plant_id} (user: {user_name}). Total entries: {len(all_energy_entries)}, inserted: {total_inserted}, updated: {total_updated}")
                
                # Return combined results
                if not all_energy_entries:
                    return {
                        "status": "warning",
                        "message": "No generation data found for the specified date range",
                        "plant_id": plant_id,
                        "start_date": start_date,
                        "end_date": end_date,
                        "db_result": None
                    }
                
                return {
                    "status": "success",
                    "message": f"Successfully fetched and stored plant generation data for {plant_id}",
                    "plant_id": plant_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "chunks_processed": chunk_count,
                    "entry_count": len(all_energy_entries),
                    "database_summary": {
                        "total_inserted": total_inserted,
                        "total_updated": total_updated,
                        "total_processed": total_inserted + total_updated
                    },
                    "db_results": db_results
                }
                
            except ValueError as date_error:
                error_msg = f"Error parsing dates: {str(date_error)}"
                self.logger.error(error_msg)
                return {"status": "error", "message": error_msg}, 400
            
        except Exception as e:
            error_msg = f"Error fetching and storing plant generation data for plant {plant_id} (user: {user_name}): {str(e)}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}, 500
    
    def get_efficiency_snapshot_data(self, min_eff=0, max_eff=100, plant_name_selected=None):
        """
        Compute all data needed for the efficiency snapshot view, including:
        - Efficiency bins and legend
        - Filtered plants and all plants with efficiency
        - 7-day hourly efficiency for a selected plant
        
        Args:
            min_eff (int): Minimum efficiency filter value
            max_eff (int): Maximum efficiency filter value
            plant_name_selected (str, optional): Name of the plant to get detailed efficiency for
            
        Returns:
            dict: Data suitable for passing to the template
        """
        try:
            # Initialize lists for efficiency data
            plant_efficiency_7d_hourly = []  # List of 7 lists, each with 24 hourly values
            plant_efficiency_7d_labels = []  # List of 7 date strings
            plant_hour_labels = [f"{str(h).zfill(2)}:00" for h in range(24)]

            # Get all plants
            plants = self.db_client.get_plants_list()
            efficiency_bins = [0]*10  # 0-10, 10-20, ..., 90-100
            filtered_plants = []
            plant_efficiency_data = []
            total_plants = 0

            for plant in plants:
                plant_id = plant.get('plant_id')
                user_name = plant.get('user_name')
                summary = self.db_client.get_plant_energy_summary(plant_id)
                if not summary:
                    continue
                peak_power = summary.get('peak_power')
                
                # Get current power using user management service
                from services.user_management_service import UserManagementService
                user_service = UserManagementService(
                    db_client=self.db_client,
                    growatt_client=self.growatt_client
                )
                current_power = user_service.get_current_power_for_user(user_name, plant_id)
                summary['current_power'] = current_power  # override for table
                
                if not peak_power or peak_power == 0:
                    efficiency = 0
                else:
                    efficiency = round((float(current_power) / float(peak_power)) * 100, 2)
                
                # Bin the efficiency
                bin_index = min(int(efficiency // 10), 9)
                efficiency_bins[bin_index] += 1
                total_plants += 1
                
                # Store for table if in filter range
                if min_eff <= efficiency < max_eff or (max_eff == 100 and efficiency == 100):
                    filtered_plants.append({
                        'plant': plant,
                        'summary': summary,
                        'efficiency': efficiency
                    })
                plant_efficiency_data.append({
                    'plant': plant,
                    'summary': summary,
                    'efficiency': efficiency
                })

            # Prepare x-axis labels
            x_labels = [f"{i*10}-{(i+1)*10}" for i in range(10)]

            # Calculate legend percentages
            if total_plants > 0:
                efficiency_percentages = [round((count / total_plants) * 100) for count in efficiency_bins]
            else:
                efficiency_percentages = [0]*10
                
            # Precompute legend as a list of dicts
            efficiency_legend = [
                {'label': f"{label}: {count} ({percent}%)"}
                for label, count, percent in zip(x_labels, efficiency_bins, efficiency_percentages)
                if count > 0
            ]

            # 7-day hourly efficiency for a selected plant
            if plant_name_selected:
                # Find the plant_id and user_name for the given plant_name
                selected_plant = next((p for p in plants if p.get('plant_name') == plant_name_selected), None)
                if selected_plant:
                    plant_id = selected_plant.get('plant_id')
                    user_name = selected_plant.get('user_name')
                    summary = self.db_client.get_plant_energy_summary(plant_id)
                    peak_power = summary.get('peak_power') if summary else None
                    
                    if peak_power and peak_power != 0:
                        today = self.get_current_time_ist().date()
                        
                        # Use HistoryIngestionService to get device history records
                        from services.history_ingestion_service import HistoryIngestionService
                        history_service = HistoryIngestionService(
                            db_client=self.db_client,
                            growatt_client=self.growatt_client
                        )
                        
                        for i in range(6, -1, -1):  # 6 days ago to today
                            date_obj = today - timedelta(days=i)
                            date_str = date_obj.strftime('%Y-%m-%d')
                            records = history_service.get_device_history_records(plant_id=plant_id, date_str=date_str)
                            
                            # Ensure records is a list, even if None was returned
                            if records is None:
                                records = []
                                
                            # For each hour, average pac for that hour
                            hourly_eff = []
                            for hour in range(24):
                                hour_str = str(hour).zfill(2)
                                hour_records = [r for r in records if r.get('datetime', '').startswith(f"{date_str} {hour_str}")]
                                pac_values = [r.get('pac', 0) for r in hour_records if r.get('pac') is not None]
                                
                                if pac_values:
                                    avg_pac = sum(pac_values) / len(pac_values)
                                    # peak_power is in kW, pac is in W, so multiply peak_power by 1000
                                    if peak_power:
                                        eff = round((float(avg_pac) / (float(peak_power) * 1000)) * 100, 2)
                                    else:
                                        eff = 0
                                else:
                                    eff = 0
                                    
                                hourly_eff.append(eff)
                                
                            plant_efficiency_7d_hourly.append(hourly_eff)
                            plant_efficiency_7d_labels.append(date_str)

            # Sort filtered_plants by efficiency descending
            filtered_plants = sorted(filtered_plants, key=lambda x: x['efficiency'], reverse=True)

            return {
                'efficiency_bins': efficiency_bins,
                'x_labels': x_labels,
                'min_eff': min_eff,
                'max_eff': max_eff,
                'filtered_plants': filtered_plants,
                'all_plants': plant_efficiency_data,
                'efficiency_percentages': efficiency_percentages,
                'efficiency_legend': efficiency_legend,
                'plant_name_selected': plant_name_selected,
                'plant_efficiency_7d_hourly': plant_efficiency_7d_hourly,
                'plant_efficiency_7d_labels': plant_efficiency_7d_labels,
                'plant_hour_labels': plant_hour_labels
            }
            
        except Exception as e:
            self.logger.error(f"Error computing efficiency snapshot data: {str(e)}")
            # Return empty data for template
            return {
                'efficiency_bins': [],
                'x_labels': [],
                'min_eff': min_eff,
                'max_eff': max_eff,
                'filtered_plants': [],
                'all_plants': [],
                'efficiency_percentages': [],
                'efficiency_legend': [],
                'plant_name_selected': None,
                'plant_efficiency_7d_hourly': [],
                'plant_efficiency_7d_labels': [],
                'plant_hour_labels': []
            } 