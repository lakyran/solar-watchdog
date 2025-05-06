import os
import json
from datetime import datetime, timedelta, timezone
import pytz
from flask import jsonify, request
import logging
from growatt import GrowattAPI
from azure_db import AzureDB
from ai_agent import GrowattAIAgent
import math
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
        self.background_tasks = {}
        
        # Initialize Growatt API client
        self.growatt_client = GrowattAPI()
        
        # Initialize Azure DB client
        self.db_client = AzureDB()

        # Initialize AI agent
        self.ai_agent = GrowattAIAgent()
        
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
    
    def fetch_and_store_device_generation_history(self, device_sn, date_str=None, overwrite=False, store_records=False):
        """Fetch generation history for a device on a date and store it in the database"""
        # device_sn = 'CLJACLR001', 'CZGBCL2141', 'CZGME630L4' 
        # user_name = 'blossomcity', 'veeraiah', 'vijayavani3kw'

        try:
            today = self.get_current_time_ist()

            # Get device metadata from inverter records
            self.logger.info(f"Fetching inverter record for device metadata: {device_sn}")
            inverter_metadata = self.db_client.get_inverter_record(device_sn)
            # Check if inverter record exists
            if not inverter_metadata:
                error_msg = f"No inverter record found for device {device_sn}, cannot proceed with fetching generation history"
                self.logger.warning(error_msg)
                raise Exception(error_msg)

            dont_change_date = True
            # If date not provided, fetch the date of the last record in the database. If no records, then use today
            if not date_str:
                dont_change_date = False
                last_record_date = self.db_client.get_last_record_date_for_device(device_sn)
                if last_record_date:
                    date_str = last_record_date
                    self.logger.info(f"Last record date found for device {device_sn}: {last_record_date}")
                else:
                    date_str = today.strftime('%Y-%m-%d')
                    self.logger.info(f"No last record date found for device {device_sn}, using today's date: {date_str}")

            # Get records from db for device and date
            records = self.db_client.get_device_records_by_date(device_sn=device_sn, date=date_str)
            records_count = len(records)
            self.logger.info(f"Records count for device {device_sn} on {date_str}: {len(records)}")

            # Get the total records on day from the first record
            if records_count > 0:
                total_records_on_day = records[0]['total_records_on_day']
                self.logger.info(f"Total records on day {date_str} for device {device_sn}: {total_records_on_day}")

            # If records exist and overwrite is True, then first delete the records for the device and date
            if records_count > 0 and overwrite:
                self.logger.info(f"Deleting records for device {device_sn} on {date_str}")
                db_result = self.db_client.delete_device_records_by_date(device_sn=device_sn, date=date_str)
                if db_result['status'] == 'success':
                    self.logger.info(f"Deleted {db_result['deleted_records']} records for device {device_sn} on {date_str}")
                else:
                    error_msg = f"Error deleting records for device {device_sn} on {date_str}: {db_result['message']}"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)

                # Reset records count
                records_count = 0

            # If not overwrite, and date is not today, and records count is equal to total records on day, then skip fetch and store
            if records_count > 0 and dont_change_date and records_count == total_records_on_day and not overwrite and date_str != today.strftime('%Y-%m-%d'):
                self.logger.info(f"All records for device {device_sn} on {date_str} already exist, skipping fetch and store")
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
                self.logger.info(f"Date changed to {date_str} for device {device_sn}")

            # Set page number to fetch
            # Page 1: 1 to 100, Page 2: 101 to 200, Page 3: 201 to 300, etc.
            all_database_entries = []
            all_db_results = []
            # page = math.floor(records_count / 100)
            page = 0

            # History Fetching Loop
            while True:
                page = page + 1

                # Fetch history for yesterday
                self.logger.info(f"Fetching history for device {device_sn} on {date_str} and page {page}")
                history_data = self.growatt_client.fetch_device_history(device_sn, inverter_metadata, date_str, date_str, page)
                self.logger.info(f"History data fetched - current_count: {len(history_data['datas'])}, total_count: {history_data['count']} records on {date_str} for device {device_sn}")
                
                if len(history_data['datas']) == 0:
                    break

                database_entries = []
                db_result = None
                if store_records:
                    self.logger.info(f"Preparing to store records for device {device_sn} on {date_str}")
                    # Process history data into database entries
                    database_entries = self.growatt_client.process_history_data_for_db(history_data, device_sn, date_str, inverter_metadata)

                    # Insert processed entries into database
                    self.logger.info(f"Storing {len(database_entries)} records for device {device_sn} on {date_str}")
                    db_result = self.db_client.insert_history_into_database(database_entries)
                    all_database_entries.extend(database_entries)
                    all_db_results.append(db_result)
                else:
                    self.logger.info(f"Not storing records for device {device_sn} on {date_str}")

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
            error_msg = f"Error processing history for {device_sn}: {str(e)}"
            self.logger.error(error_msg)
            return {'error': error_msg}, 500

    def analyze_device_generation_data_route(self, device_sn, date_str=None):
        """
        Fetches generation history for a specific device and analyzes it using the AI agent
        
        Args:
            device_sn (str): Device serial number
            date_str (str, optional): Date to analyze in YYYY-MM-DD format. Defaults to yesterday.
            
        Returns:
            dict: Response containing generation data and AI analysis
        """
        try:
            # Use yesterday if no date provided
            if not date_str:
                yesterday = self.get_current_time_ist() - timedelta(days=1)
                date_str = yesterday.strftime('%Y-%m-%d')
            
            self.logger.info(f"Analyzing generation data for device {device_sn} on {date_str}")
            
            # Fetch device records from database
            generation_history = self.db_client.get_device_records_by_date(device_sn=device_sn, date=date_str)
            self.logger.info(f"Number of records found for device on date {date_str}: {len(generation_history)}")
            
            if not generation_history:
                self.logger.info(f"No records found for device {device_sn} on {date_str}")
                return {
                    'device_id': device_sn,
                    'date': date_str,
                    'status': 'no_data',
                    'message': 'No data available for the requested date'
                }
            
            # Prepare analysis query
            query = f"Analyze the solar generation data for device {device_sn} on {date_str}. " \
            
            # Create context with generation data and device metadata
            context = {
                'device_sn': device_sn,
                'date': date_str,
                'device_type': generation_history[0]['device_type'],
                'generation_data': generation_history,
            }
            
            # Call AI agent to analyze the data
            import asyncio
            analysis_result = asyncio.run(self.ai_agent.process_query(query, context))
            
            # Build the response with all available data
            response = {
                'device_id': device_sn,
                'date': date_str,
                'count': len(analysis_result['disruption_events']),
                'disruption_events': analysis_result['disruption_events']
            }
            
            # Return the JSON response
            return response
            
        except Exception as e:
            error_msg = f"Error analyzing data for device {device_sn}: {str(e)}"
            self.logger.error(error_msg)
            return {'error': error_msg}, 500
        
    def analyze_device_generation_data_and_store_disruptions_route(self, device_sn, date_str=None, overwrite=False):
        """
        Reuses the analyze_device_generation_data_route method and additionally 
        stores any disruption events found in the DB table `disruption_events`

        Args:
            device_sn (str): Device serial number
            date_str (str, optional): Date to analyze in YYYY-MM-DD format. Defaults to yesterday.
            
        Returns:
            dict: Response containing generation data, AI analysis, and disruption storage results
        """
        try:
            # Get the disruption events from the database
            disruption_events = self.db_client.get_disruption_events(device_sn, date_str)
            # If records exist and overwrite is True, then first delete the records for the device and date
            if len(disruption_events) > 0 and overwrite:
                self.logger.info(f"Deleting disruption events for device {device_sn} on {date_str}")
                db_result = self.db_client.delete_disruption_events(device_sn, date_str)
                if db_result['status'] == 'success':
                    self.logger.info(f"Deleted {db_result['deleted_records']} disruption events for device {device_sn} on {date_str}")

            # First get the analysis results using the existing route
            analysis_response = self.analyze_device_generation_data_route(device_sn, date_str)
            
            # If the response was an error (tuple with status code), return it directly
            if isinstance(analysis_response, tuple):
                return analysis_response
            
            # If there's no data or an error occurred, return the original response
            if 'status' in analysis_response and analysis_response['status'] in ['no_data', 'error']:
                return analysis_response
            
            # Get the date from the response
            date_str = analysis_response.get('date', '')
            
            # Get disruption events from the analysis
            disruption_events = analysis_response.get('disruption_events', [])
            
            # Initialize response data with analysis response
            response_data = analysis_response

            # Get device metadata from inverter records
            self.logger.info(f"Fetching inverter record for device metadata: {device_sn}")
            inverter_record = self.db_client.get_inverter_record(device_sn)
             # Use inverter record for device metadata
            device_metadata = {
                'device_sn': inverter_record['device_sn'],
                'device_type': inverter_record['device_type'],
                'device_oem': inverter_record['device_oem'],
                'user_name': inverter_record['user_name'],
                'user_id': inverter_record['user_id'],
                'vendor': inverter_record['vendor'],
                'plant_id': inverter_record['plant_id'],
                'date': date_str
            }
            
            # If no disruption events were found, return the response with a note
            if not disruption_events:
                response_data['db_operation'] = {
                    'status': 'no_disruptions', 
                    'inserted_records': 0,
                    'updated_records': 0,
                    'skipped_records': 0,
                    'total_processed': 0
                }

                # Update the analysis ledger with the current date
                ledger_result = self.update_device_analysis_ledger(device_sn, date_str, device_metadata)
                response_data['ledger_update'] = ledger_result

                return response_data
            
            # Log that we found disruptions
            self.logger.info(f"Found {len(disruption_events)} disruption events for device {device_sn} on {date_str}")
            
            # Check if inverter record exists
            if not inverter_record:
                self.logger.warning(f"No inverter record found for device {device_sn}, cannot proceed with storing disruptions")
                response_data['db_operation'] = {
                    'status': 'error', 
                    'message': f'No inverter record found for device {device_sn}',
                    'inserted_records': 0,
                    'updated_records': 0,
                    'skipped_records': 0,
                    'total_processed': 0
                }
                return response_data
            
            # Insert or update disruption events in the database with ON CONFLICT handling
            db_result = self.db_client.insert_disruption_events(disruption_events, device_metadata)
            
            # Check if operation failed
            if db_result.get('status') == 'error':
                error_msg = f"Failed to store disruption events: {db_result.get('message')}"
                self.logger.error(error_msg)
                response_data['db_operation'] = db_result
                return response_data, 500
            
            # Enhanced logging for successful operations
            self.logger.info(
                f"Processed disruption events for {device_sn} on {date_str}: "
                f"Inserted {db_result.get('inserted_records', 0)}, "
                f"Updated {db_result.get('updated_records', 0)}, "
                f"Skipped {db_result.get('skipped_records', 0)}, "
                f"Total {db_result.get('total_processed', 0)}"
            )
            
            # Add the database operation result to the response
            response_data['db_operation'] = db_result
            
            # Update the analysis ledger with the current date
            ledger_result = self.update_device_analysis_ledger(device_sn, date_str, device_metadata)
            response_data['ledger_update'] = ledger_result
            
            # Return the enhanced response
            return response_data
            
        except Exception as e:
            error_msg = f"Error storing disruption events for device {device_sn}: {str(e)}"
            self.logger.error(error_msg)
            return {'error': error_msg}, 500

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

    def get_device_disruption_events_route(self, device_sn, date_str=None):
        """
        Route handler for fetching disruption events for a specific device
        
        Args:
            device_sn (str): Device serial number
            date_str (str, optional): Date to fetch in YYYY-MM-DD format. If None, returns all dates.
            
        Returns:
            dict: Response containing disruption events data
        """
        try:
            self.logger.info(f"Fetching disruption events for device {device_sn}{' on ' + date_str if date_str else ''}")
            
            # Validate device_sn
            if not device_sn:
                self.logger.error("Invalid device serial number provided")
                return {'status': 'error', 'message': 'Invalid device serial number'}, 400
            
            # Validate date format if provided
            if date_str:
                try:
                    datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    return {'status': 'error', 'message': 'Invalid date format. Use YYYY-MM-DD'}, 400
            
            # Get device metadata
            inverter_record = self.db_client.get_inverter_record(device_sn)
            
            # Fetch disruption events from database
            disruption_events = self.db_client.get_disruption_events(device_sn, date_str)
            
            # Return response
            response = {
                'status': 'success',
                'device_sn': device_sn,
                'device_info': inverter_record,
                'disruption_events': disruption_events,
                'count': len(disruption_events)
            }
            
            # Add date to response only if it was provided
            if date_str:
                response['date'] = date_str
            
            return response
            
        except Exception as e:
            error_msg = f"Error fetching disruption events for {device_sn}: {str(e)}"
            self.logger.error(error_msg)
            return {'status': 'error', 'message': error_msg}, 500

    def analyze_device_disruptions_date_range(self, device_sn, start_date=None, end_date=None, overwrite=False):
        """
        Creates and manages a background task for analyzing device disruptions over a date range.
        
        Args:
            device_sn (str): Device serial number
            start_date (str, optional): Start date in YYYY-MM-DD format. If None, will be determined based on latest analysis.
            end_date (str, optional): End date in YYYY-MM-DD format. Defaults to current date if None.
            overwrite (bool, optional): Whether to overwrite existing data. Defaults to False.
            
        Returns:
            dict: Response containing task information
        """
        import uuid
        import threading
        
        # Validate device_sn
        if not device_sn:
            return {'status': 'error', 'message': 'device_sn parameter is required'}, 400
            
        # Set default end_date to today if not provided
        if not end_date:
            end_date = self.get_current_time_ist().strftime('%Y-%m-%d')
            
        # If no start_date provided, determine based on latest analysis date
        if not start_date:
            # Try to get the latest analysis date from the database
            latest_analysis_date = self.get_latest_analysis_date_for_device(device_sn)
            self.logger.info(f"Latest analysis date for device {device_sn}: {latest_analysis_date}")
            
            if latest_analysis_date:
                # Parse the date string and set timezone to IST
                latest_date = datetime.strptime(latest_analysis_date, '%Y-%m-%d').replace(tzinfo=self.ist_timezone).date()
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=self.ist_timezone).date()
                
                if latest_date == end_date_obj:
                    # Re-analyze is okay for the current day, if after 6am and before 7pm
                    now = self.get_current_time_ist()
                    morning_time = datetime.strptime('06:00', '%H:%M').time()
                    evening_time = datetime.strptime('19:00', '%H:%M').time()
                    
                    if now.time() > morning_time:
                        start_date = latest_analysis_date
                    else:
                        # Return early if analysis is already done for today and outside operating hours
                        self.logger.info(f"Analysis already completed for today and outside operating hours")
                        return {'status': 'success', 'message': 'Analysis already completed for today'}, 200
                else:
                    # Use the day of latest analysis as the start date
                    start_date = latest_date.strftime('%Y-%m-%d')
            else:
                # If no latest analysis date, try to get the first record date from the database
                first_record_date = self.db_client.get_first_record_date_for_device(device_sn)
                self.logger.info(f"First record date for device {device_sn}: {first_record_date}")
                
                if first_record_date:
                    # Use the first record date as the start date
                    start_date = first_record_date
                    self.logger.info(f"Using first record date as start date: {start_date}")
                else:
                    # Default to 15 days before end_date if no previous analysis exists and no historical data
                    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=self.ist_timezone)
                    start_date = (end_date_obj - timedelta(days=15)).strftime('%Y-%m-%d')
                    self.logger.info(f"No first record date found, using default 15 days before end date: {start_date}")
        
        self.logger.info(f"Analyzing data for device {device_sn} from {start_date} to {end_date}")
        
        # Validate date format
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=self.ist_timezone)
            end = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=self.ist_timezone)
        except ValueError:
            return {'status': 'error', 'message': 'Invalid date format. Use YYYY-MM-DD'}, 400
        
        # Create a task ID
        task_id = str(uuid.uuid4())
        
        # Setup background task
        self.background_tasks[task_id] = {
            'id': task_id,
            'type': 'date_range_analysis',
            'device_sn': device_sn,
            'start_date': start_date,
            'end_date': end_date,
            'created_at': self.get_current_time_ist().isoformat(),
            'status': self.TASK_STATUS['PENDING'],
            'progress': {
                'days_processed': 0,
                'days_total': (end.date() - start.date()).days + 1
            }
        }
        
        # Start background thread
        thread = threading.Thread(
            target=self.run_date_range_analysis,
            args=(task_id, device_sn, start_date, end_date, overwrite)
        )
        thread.daemon = True
        thread.start()
        
        # Return task information
        return {
            'task_id': task_id,
            'status': 'accepted',
            'message': 'Analysis started in background',
            'start_date': start_date,
            'end_date': end_date,
            'check_status_url': f'/tasks/{task_id}'
        }
    
    def run_date_range_analysis(self, task_id, device_sn, start_date, end_date, overwrite):
        """
        Background function to run date range analysis
        
        Args:
            task_id (str): ID of the background task
            device_sn (str): Device serial number
            start_date (str): Start date in YYYY-MM-DD format
            end_date (str): End date in YYYY-MM-DD format
            overwrite (bool): Whether to overwrite existing data
        """
        try:
            task = self.background_tasks[task_id]
            task['status'] = self.TASK_STATUS['RUNNING']
            
            # Convert dates with IST timezone
            start = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=self.ist_timezone)
            end = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=self.ist_timezone)
            
            # Analyze each day in the range
            current_date = start
            all_results = []
            days_processed = 0
            days_total = (end - start).days + 1
            
            while current_date <= end:
                date_str = current_date.strftime('%Y-%m-%d')
                self.logger.info(f"Analyzing data for device {device_sn} on {date_str}")
                
                # Update task progress
                task['progress'] = {
                    'days_processed': days_processed,
                    'days_total': days_total,
                    'current_date': date_str
                }
                
                # Get analysis for this date
                result = self.analyze_device_generation_data_and_store_disruptions_route(device_sn, date_str, overwrite)
                
                # Skip error responses
                if isinstance(result, tuple) and len(result) > 1 and result[1] >= 400:
                    self.logger.error(f"Error analyzing {date_str}: {result[0]}")
                    current_date += timedelta(days=1)
                    days_processed += 1
                    # Add sleep to avoid hammering the API
                    import time
                    time.sleep(1)
                    continue
                    
                # Add date to the result
                if isinstance(result, dict):
                    result['date'] = date_str
                    all_results.append(result)

                self.logger.info(f"Analyzed {date_str} for device {device_sn}")
                
                # Move to next day
                current_date += timedelta(days=1)
                days_processed += 1
                
                # Add sleep to avoid hammering the API
                import time
                time.sleep(1)
            
            # Prepare response
            response = {
                'device_sn': device_sn,
                'start_date': start_date,
                'end_date': end_date,
                'days_analyzed': len(all_results),
                'results': all_results
            }
            
            # Update task
            task['status'] = self.TASK_STATUS['COMPLETED']
            task['result'] = response
            task['completed_at'] = self.get_current_time_ist().isoformat()
            
        except Exception as e:
            self.logger.error(f"Background task error: {str(e)}")
            if task_id in self.background_tasks:
                self.background_tasks[task_id]['status'] = self.TASK_STATUS['FAILED']
                self.background_tasks[task_id]['error'] = str(e)
                self.background_tasks[task_id]['completed_at'] = self.get_current_time_ist().isoformat()

    def get_latest_analysis_date_for_device(self, device_sn):
        """
        Get the latest date when analysis was performed for a device
        
        Args:
            device_sn (str): Device serial number
            
        Returns:
            str: Date string in YYYY-MM-DD format or None if no analysis has been done
        """
        try:
            return self.db_client.get_latest_analysis_date_for_device(device_sn)
        except Exception as e:
            self.logger.error(f"Error retrieving latest analysis date for device {device_sn}: {str(e)}")
            return None

    def update_device_analysis_ledger(self, device_sn, analysis_date, device_metadata=None):
        """
        Update the analysis ledger for a device with the latest analysis date
        
        Args:
            device_sn (str): Device serial number
            analysis_date (str): Date of analysis in YYYY-MM-DD format
            device_metadata (dict, optional): Device metadata containing vendor and device_oem
            
        Returns:
            dict: Result of the update operation
        """
        try:
            self.logger.info(f"Updating analysis ledger for device {device_sn} with date {analysis_date}")
            # Ensure the analysis_date has IST timezone context
            date_obj = datetime.strptime(analysis_date, '%Y-%m-%d').replace(tzinfo=self.ist_timezone)
            formatted_date = date_obj.strftime('%Y-%m-%d')
            result = self.db_client.update_analysis_ledger(device_sn, formatted_date, device_metadata)
            if result.get('status') == 'success':
                self.logger.info(f"Analysis ledger updated for device {device_sn} with date {formatted_date}")
            else:
                self.logger.warning(f"Failed to update analysis ledger for device {device_sn}: {result.get('message')}")
            return result
        except Exception as e:
            error_msg = f"Error updating analysis ledger for device {device_sn}: {str(e)}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}

    def get_task_status(self, task_id):
        """
        Get the status and details of a background task
        
        Args:
            task_id (str): ID of the background task
            
        Returns:
            dict: Task status information or error response
        """
        if task_id not in self.background_tasks:
            return {'status': 'error', 'message': 'Task not found'}, 404
            
        task = self.background_tasks[task_id]
        
        # If task is completed, include the result
        if task['status'] == self.TASK_STATUS['COMPLETED']:
            return {
                'task_id': task_id,
                'status': task['status'],
                'created_at': task['created_at'],
                'completed_at': task.get('completed_at'),
                'result': task.get('result')
            }
        # If task failed, include the error
        elif task['status'] == self.TASK_STATUS['FAILED']:
            return {
                'task_id': task_id,
                'status': task['status'],
                'created_at': task['created_at'],
                'completed_at': task.get('completed_at'),
                'error': task.get('error')
            }
        # If task is still running, include progress information
        else:
            return {
                'task_id': task_id,
                'status': task['status'],
                'created_at': task['created_at'],
                'progress': task.get('progress', {})
            }

    def fetch_and_store_plant_summary(self, plant_id):
        """
        Fetch plant energy summary from Growatt API and store it in the database
        
        Args:
            plant_id (str): Plant ID to fetch summary for
            
        Returns:
            dict: Result containing API data and database operation result
        """
        try:
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
            user_name = None
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
            self.logger.info(f"Step 3: Preparing and storing plant summary for plant_id: {plant_id}")
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
            error_msg = f"Error processing plant summary for {plant_id}: {str(e)}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}, 500

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
            plants = self.db_client.get_plants_list(username)
            
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
                
                # Get plant summary
                plant_summary = self.db_client.get_plant_energy_summary(plant_id)
                
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
            
    def onboard_new_user(self, username, user_id, vendor, phone=None, email=None):
        """
        Onboard a new user by:
        1. Inserting the user into the database
        2. Fetching their plants from Growatt
        3. Inserting each plant into the database
        4. Fetching and storing plant summary for each plant
        5. Fetching devices for each plant
        6. Inserting inverters (device type 1 or 7) into the database
        7. Bootstrap historical data ingestion for all inverters
        
        Args:
            username (str): Username for the new user
            user_id (str): User ID for the new user
            vendor (str): Vendor name (e.g., 'Growatt')
            phone (str, optional): User's phone number
            email (str, optional): User's email address
            
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
                'email': email
            }
            
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
                    summary_result = self.fetch_and_store_plant_summary(plant_id)
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
                
            # Step 7: Bootstrap historical data ingestion for all inverters
            self.logger.info(f"Step 7: Bootstrapping historical data ingestion for {summary['inverters_count']} inverters")
            
            for inverter in summary['inverters']:
                device_sn = inverter['device_sn']
                try:
                    # Bootstrap historical data for this inverter
                    bootstrap_result = self.bootstrap_history_ingestion_for_new_user(device_sn)
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
                import time
                time.sleep(2)
            
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
                import time
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

    def get_efficiency_snapshot_data(self, min_eff=0, max_eff=100, plant_name_selected=None):
        """
        Compute all data needed for the efficiency snapshot view, including:
        - Efficiency bins and legend
        - Filtered plants and all plants with efficiency
        - 7-day hourly efficiency for a selected plant
        Returns a dict suitable for passing to the template.
        """
        try:
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
                # Use watchdog.get_current_power_for_user for current power
                current_power = self.get_current_power_for_user(user_name, plant_id)
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
                        from datetime import datetime, timedelta
                        today = self.get_current_time_ist().date()
                        for i in range(6, -1, -1):  # 6 days ago to today
                            date_obj = today - timedelta(days=i)
                            date_str = date_obj.strftime('%Y-%m-%d')
                            records = self.get_device_history_records(plant_id=plant_id, date_str=date_str)
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