from datetime import timedelta, datetime
import time
from services.base_service import BaseService

class HistoryIngestionService(BaseService):
    """Service for handling the ingestion of device generation history data"""
    
    def fetch_and_store_device_generation_history(self, device_sn, date_str=None, overwrite=False, store_records=True):
        """
        Fetch generation history for a device on a date and store it in the database
        
        Args:
            device_sn (str): Device serial number
            date_str (str, optional): Date to fetch in YYYY-MM-DD format. If None, will use logic to determine.
            overwrite (bool, optional): Whether to overwrite existing records. Defaults to False.
            store_records (bool, optional): Whether to store records in database. Defaults to True.
            
        Returns:
            dict: Response containing operation results
        """
        try:
            user_name = None
            today = self.get_current_time_ist()

            # Get device metadata from inverter records
            self.logger.info(f"Fetching inverter record for device metadata: {device_sn}")
            inverter_metadata = self.db_client.get_inverter_record(device_sn)
            # Check if inverter record exists
            if not inverter_metadata:
                error_msg = f"No inverter record found for device {device_sn}, cannot proceed with fetching generation history"
                self.logger.warning(error_msg)
                raise Exception(error_msg)

            # Extract user_name from inverter metadata for traceability in subsequent logs
            user_name = inverter_metadata.get('user_name', '')

            dont_change_date = True
            # If date not provided, fetch the date of the last record in the database. If no records, then use today
            if not date_str:
                dont_change_date = False
                last_record_date = self.db_client.get_last_record_date_for_device(device_sn)
                if last_record_date:
                    date_str = last_record_date
                    self.logger.info(f"Last record date found for device {device_sn} (user: {user_name}): {last_record_date}")
                else:
                    date_str = today.strftime('%Y-%m-%d')
                    self.logger.info(f"No last record date found for device {device_sn} (user: {user_name}), using today's date: {date_str}")

            # Get records from db for device and date
            records = self.db_client.get_device_records_by_date(device_sn=device_sn, date=date_str)
            records_count = len(records)
            self.logger.info(f"Records count for device {device_sn} (user: {user_name}) on {date_str}: {len(records)}")

            # Get the total records on day from the first record
            if records_count > 0:
                total_records_on_day = records[0]['total_records_on_day']
                self.logger.info(f"Total records on day {date_str} for device {device_sn} (user: {user_name}): {total_records_on_day}")

            # Check if the records are dummy for the date
            # records_dummy_for_date = self.growatt_client.is_device_history_dummy(records)

            # If records exist and overwrite is True, then first delete the records for the device and date
            if records_count > 0 and overwrite:
                self.logger.info(f"Deleting records for device {device_sn} (user: {user_name}) on {date_str}")
                db_result = self.db_client.delete_device_records_by_date(device_sn=device_sn, date=date_str)
                if db_result['status'] == 'success':
                    self.logger.info(f"Deleted {db_result['deleted_records']} records for device {device_sn} (user: {user_name}) on {date_str}")
                else:
                    error_msg = f"Error deleting records for device {device_sn} (user: {user_name}) on {date_str}: {db_result['message']}"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)

                # Reset records count
                records_count = 0

            # If not overwrite, and date is not today, and records count is equal to total records on day, then skip fetch and store
            if records_count > 0 and dont_change_date and records_count == total_records_on_day and not overwrite and date_str != today.strftime('%Y-%m-%d'):
                self.logger.info(f"All records for device {device_sn} (user: {user_name}) on {date_str} already exist, skipping fetch and store")
                response = {
                    'device_id': device_sn,
                    'date': date_str,
                    'entries_count': len(records),
                    'db_operation': None,
                    'status': 'skipped'
                }
                return response

            # If records count is equal to total records on day and date is not today, then change the date to the next day
            if records_count > 0 and records_count == total_records_on_day and date_str != today.strftime('%Y-%m-%d'):
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                date_obj = date_obj.replace(tzinfo=self.ist_timezone)
                date_str = (date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
                records_count = 0
                self.logger.info(f"Date changed to {date_str} for device {device_sn} (user: {user_name})")

            # Set page number to fetch
            # Page 1: 1 to 100, Page 2: 101 to 200, Page 3: 201 to 300, etc.
            all_database_entries = []
            all_db_results = []
            page = 0

            # History Fetching Loop
            while True:
                page = page + 1

                # Fetch history for yesterday
                self.logger.info(f"Fetching history for device {device_sn} (user: {user_name}) on {date_str} and page {page}")
                history_data = self.growatt_client.fetch_device_history(device_sn, inverter_metadata, date_str, date_str, page)
                self.logger.info(f"History data fetched - current_count: {len(history_data['datas'])}, total_count: {history_data['count']} records on {date_str} for device {device_sn} (user: {user_name})")

                database_entries = []
                db_result = None
                if store_records:
                    self.logger.info(f"Preparing to store records for device {device_sn} (user: {user_name}) on {date_str}")
                    # Process history data into database entries
                    database_entries = self.growatt_client.process_history_data_for_db(history_data, device_sn, date_str, inverter_metadata)

                    # Insert processed entries into database
                    self.logger.info(f"Storing {len(database_entries)} records for device {device_sn} (user: {user_name}) on {date_str}")
                    db_result = self.db_client.insert_history_into_database(database_entries)
                    all_database_entries.extend(database_entries)
                    all_db_results.append(db_result)
                else:
                    self.logger.info(f"Not storing records for device {device_sn} (user: {user_name}) on {date_str}")

                if len(history_data['datas']) == 0:
                    break

            response = {
                'device_id': device_sn,
                'date': date_str,
                'entries_count': len(all_database_entries),
                'db_operation': all_db_results,
                'status': 'success'
            }
            return response

        except ValueError as ve:
            error_msg = f"Validation error: {str(ve)}"
            self.logger.error(error_msg)
            return {'error': error_msg}, 400
        except Exception as e:
            error_msg = f"Error processing history for device {device_sn} (user: {user_name}): {str(e)}"
            self.logger.error(error_msg)
            return {'error': error_msg}, 500

    def fetch_and_store_device_generation_history_range(self, device_sn, start_date, end_date, overwrite=False, store_records=True):
        """
        Fetch and store generation history for a device over a range of dates.

        Iterates day by day from start_date to end_date (inclusive), calling
        fetch_and_store_device_generation_history for each date.

        Args:
            device_sn (str): Device serial number
            start_date (str): Start date in YYYY-MM-DD format
            end_date (str): End date in YYYY-MM-DD format
            overwrite (bool, optional): Whether to overwrite existing records. Defaults to False.
            store_records (bool, optional): Whether to store records in the database. Defaults to True.

        Returns:
            dict: Summary of the ingestion process including per-day results
        """
        try:
            # Initialized to None so the outer except can still reference it if resolution fails
            user_name = None

            # Resolve user_name from inverter metadata for traceability in subsequent logs.
            # Raises if no inverter record exists for the device.
            user_name = self._get_user_name_for_device(device_sn)

            self.logger.info(f"Starting history ingestion over range for device {device_sn} (user: {user_name}): "
                            f"{start_date} to {end_date} (overwrite={overwrite}, store_records={store_records})")

            # Parse and validate the date range
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            except (ValueError, TypeError):
                error_msg = (f"Invalid date format for device {device_sn} (user: {user_name}): "
                             f"start_date={start_date}, end_date={end_date}. Expected YYYY-MM-DD.")
                self.logger.error(error_msg)
                return {'status': 'error', 'device_sn': device_sn, 'message': error_msg}, 400

            if start_date_obj > end_date_obj:
                error_msg = (f"start_date ({start_date}) must be on or before end_date ({end_date}) "
                             f"for device {device_sn} (user: {user_name})")
                self.logger.error(error_msg)
                return {'status': 'error', 'device_sn': device_sn, 'message': error_msg}, 400

            # Summary to track progress
            summary = {
                'device_sn': device_sn,
                'start_date': start_date,
                'end_date': end_date,
                'overwrite': overwrite,
                'store_records': store_records,
                'days_processed': 0,
                'days_total': (end_date_obj - start_date_obj).days + 1,
                'days_with_data': 0,
                'days_skipped': 0,
                'days_failed': 0,
                'days_details': []
            }

            # Process each day in the range
            current_date = start_date_obj
            while current_date <= end_date_obj:
                date_str = current_date.strftime('%Y-%m-%d')
                self.logger.info(f"Ingesting history for device {device_sn} (user: {user_name}) on {date_str}")

                try:
                    result = self.fetch_and_store_device_generation_history(
                        device_sn=device_sn,
                        date_str=date_str,
                        overwrite=overwrite,
                        store_records=store_records
                    )

                    # Initialize day summary with just the date
                    day_summary = {'date': date_str}

                    # Check if it's a tuple with an error
                    if isinstance(result, tuple) and len(result) > 1:
                        error_data, _ = result
                        day_summary['status'] = 'error'
                        if isinstance(error_data, dict):
                            day_summary['error'] = error_data.get('error', 'Unknown error')
                        else:
                            day_summary['error'] = str(error_data)
                        summary['days_failed'] += 1
                        summary['days_details'].append(day_summary)

                        # Stop the range ingestion on Growatt rate limit to avoid burning further requests
                        if isinstance(error_data, dict) and 'error_frequently_access' in error_data.get('error', ''):
                            self.logger.warning(f"API rate limit hit for device {device_sn} (user: {user_name}). Stopping range ingestion.")
                            summary['status'] = 'rate_limited'
                            break
                    else:
                        # For normal dictionary responses
                        day_summary['status'] = result.get('status', 'unknown')

                        if day_summary['status'] == 'success':
                            day_summary['entries_count'] = result.get('entries_count', 0)
                            summary['days_with_data'] += 1
                        elif day_summary['status'] == 'skipped':
                            summary['days_skipped'] += 1

                        summary['days_details'].append(day_summary)

                except Exception as e:
                    self.logger.error(f"Error ingesting history for device {device_sn} (user: {user_name}) on {date_str}: {str(e)}")
                    summary['days_failed'] += 1
                    summary['days_details'].append({
                        'date': date_str,
                        'status': 'error',
                        'error': str(e)
                    })

                # Move to next day
                current_date += timedelta(days=1)
                summary['days_processed'] += 1

                # Add sleep to avoid hammering the API
                time.sleep(1)

            # Add overall status if not already set (e.g. rate_limited)
            if 'status' not in summary:
                if summary['days_failed'] > 0:
                    summary['status'] = 'partial'
                elif summary['days_with_data'] > 0:
                    summary['status'] = 'success'
                else:
                    summary['status'] = 'no_data'

            self.logger.info(f"Completed range ingestion for device {device_sn} (user: {user_name}): "
                            f"Processed {summary['days_processed']}/{summary['days_total']} days, "
                            f"Found data for {summary['days_with_data']} days, "
                            f"Skipped {summary['days_skipped']} days, "
                            f"Failed {summary['days_failed']} days")

            return summary

        except Exception as e:
            error_msg = f"Error ingesting history over range for device {device_sn} (user: {user_name}): {str(e)}"
            self.logger.error(error_msg)
            return {
                'status': 'error',
                'device_sn': device_sn,
                'message': error_msg
            }, 500

    def _get_user_name_for_device(self, device_sn):
        """
        Resolve the user_name associated with a device from its inverter metadata.

        Used for traceability in logs. The lookup is intentionally lightweight — it
        only reads the user_name and does not validate device fitness for ingestion.

        Args:
            device_sn (str): Device serial number

        Returns:
            str: The user_name (empty string if the record exists but has no user_name).

        Raises:
            Exception: If no inverter record exists for the device.
        """
        self.logger.info(f"Fetching inverter record for device metadata: {device_sn}")
        inverter_metadata = self.db_client.get_inverter_record(device_sn)
        if not inverter_metadata:
            error_msg = f"No inverter record found for device {device_sn}, cannot resolve user_name"
            self.logger.warning(error_msg)
            raise Exception(error_msg)
        
        return inverter_metadata.get('user_name', '')

    def bootstrap_history_ingestion_for_new_user(self, device_sn):
        """
        Bootstrap historical data ingestion for a newly onboarded inverter.
        Fetches and stores generation history for the past 30 days.
        
        Args:
            device_sn (str): Device serial number of the inverter
            
        Returns:
            dict: Summary of the bootstrapping process
        """
        try:
            self.logger.info(f"Starting historical data bootstrap for device: {device_sn}")
            
            # Calculate start and end dates
            end_date = self.get_current_time_ist()
            start_date = end_date - timedelta(days=30)
            
            # Format dates as strings
            end_date_str = end_date.strftime('%Y-%m-%d')
            
            # Summary to track progress
            summary = {
                'device_sn': device_sn,
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date_str,
                'days_processed': 0,
                'days_total': 31,  # 30 days + today
                'days_with_data': 0,
                'days_details': []
            }
            
            # Process each day
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                self.logger.info(f"Bootstrapping history for device {device_sn} on {date_str}")
                
                try:
                    # Fetch and store history for this date
                    result = self.fetch_and_store_device_generation_history(
                        device_sn=device_sn,
                        date_str=date_str,
                        overwrite=False,
                        store_records=True
                    )
                    
                    # Initialize day summary with just the date
                    day_summary = {
                        'date': date_str
                    }
                    
                    # Check if it's a tuple with an error
                    if isinstance(result, tuple) and len(result) > 1:
                        error_data, _ = result
                        day_summary['status'] = 'error'
                        if isinstance(error_data, dict):
                            day_summary['error'] = error_data.get('error', 'Unknown error')
                        else:
                            day_summary['error'] = str(error_data)
                            
                            # If there's a rate limit error, wait longer
                            if isinstance(error_data, dict) and 'error' in error_data:
                                error_msg = error_data['error']
                                if 'error_frequently_access' in error_msg:
                                    self.logger.warning(f"API rate limit hit for device {device_sn}. Stopping historical data bootstrap for this device.")
                                    break
                    else:
                        # For normal dictionary responses
                        day_summary['status'] = result.get('status', 'unknown')
                        
                        # Add counts if successful
                        if result.get('status') == 'success':
                            day_summary['entries_count'] = result.get('entries_count', 0)
                            summary['days_with_data'] += 1
                    
                    summary['days_details'].append(day_summary)
                    
                except Exception as e:
                    self.logger.error(f"Error bootstrapping history for date {date_str}: {str(e)}")
                    summary['days_details'].append({
                        'date': date_str,
                        'status': 'error',
                        'error': str(e)
                    })
                
                # Move to next day
                current_date += timedelta(days=1)
                summary['days_processed'] += 1
                
                # Add sleep to avoid hammering the API
                time.sleep(1)
            
            self.logger.info(f"Completed historical data bootstrap for device {device_sn}: "
                           f"Processed {summary['days_processed']} days, "
                           f"Found data for {summary['days_with_data']} days")
            
            # Add overall status
            if summary['days_with_data'] > 0:
                summary['status'] = 'success'
            else:
                summary['status'] = 'no_data'
                
            return summary
            
        except Exception as e:
            error_msg = f"Error bootstrapping historical data for device {device_sn}: {str(e)}"
            self.logger.error(error_msg)
            return {
                'status': 'error',
                'device_sn': device_sn,
                'message': error_msg
            }
            
    def get_device_history_records(self, device_sn=None, plant_id=None, date_str=None):
        """
        Get history records for a device or plant and date from the database.
        Args:
            device_sn (str, optional): Device serial number
            plant_id (str, optional): Plant ID
            date_str (str): Date in YYYY-MM-DD format
        Returns:
            list: List of history records (dicts) or None if error
        """
        try:
            if not date_str:
                self.logger.error("date_str parameter is required")
                return None
            # If both device_sn and plant_id are provided, use device_sn
            if device_sn:
                self.logger.info(f"Fetching history records for device {device_sn} on {date_str}")
                records = self.db_client.get_device_records_by_date(device_sn=device_sn, date=date_str)
                self.logger.info(f"Fetched {len(records)} history records for device {device_sn} on {date_str}")
            elif plant_id:
                self.logger.info(f"Fetching history records for plant {plant_id} on {date_str}")
                records = self.db_client.get_device_records_by_date(plant_id=plant_id, date=date_str)
                self.logger.info(f"Fetched {len(records)} history records for plant {plant_id} on {date_str}")
            else:
                self.logger.error("Either device_sn or plant_id must be provided")
                return None
            return records
        except Exception as e:
            self.logger.error(f"Error fetching history records for device_sn={device_sn}, plant_id={plant_id} on {date_str}: {str(e)}")
            return None 