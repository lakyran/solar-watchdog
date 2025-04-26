import os
import json
from datetime import datetime, timedelta
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
    
    def fetch_and_store_device_generation_history(self, device_sn, date_str=None, overwrite=False, store_records=False):
        """Route handler for fetching generation history for a device on a date and storing it in the database"""
        # device_sn = 'CLJACLR001', 'CZGBCL2141', 'CZGME630L4' 
        # user_name = 'blossomcity', 'veeraiah', 'vijayavani3kw'

        try:
            # If date not provided, fetch the date of the last record in the database. If no records, then use yesterday
            dont_change_date = True
            if not date_str:
                dont_change_date = False
                last_record_date = self.db_client.get_last_record_date_for_device(device_sn)
                if last_record_date:
                    date_str = last_record_date
                    print(f"Last record date found for device {device_sn}: {last_record_date}")
                else:
                    today = datetime.now()
                    date_str = today.strftime('%Y-%m-%d')
                    print(f"No last record date found for device {device_sn}, using today's date: {date_str}")

            # Get records from db for device and date
            records = self.db_client.get_device_records_by_date(device_sn, date_str)
            records_count = len(records)
            print(f"Records count for device {device_sn} on {date_str}: {len(records)}")

            # Get the total records on day from the first record
            if records_count > 0:
                total_records_on_day = records[0]['total_records_on_day']
                print(f"Total records on day {date_str} for device {device_sn} : {total_records_on_day}")
            
            # If records exist and overwrite is True, then first delete the records for the device and date
            if records_count > 0 and overwrite:
                self.logger.info(f"Deleting records for device {device_sn} on {date_str}")
                print(f"Deleting records for device {device_sn} on {date_str}")
                db_result = self.db_client.delete_device_records_by_date(device_sn, date_str)
                if db_result['status'] == 'success':
                    print(f"Deleted {db_result['deleted_records']} records for device {device_sn} on {date_str}")
                    self.logger.info(f"Deleted {db_result['deleted_records']} records for device {device_sn} on {date_str}")
                else:
                    error_msg = f"Error deleting records for device {device_sn} on {date_str}: {db_result['message']}"
                    print(f"Error deleting records for device {device_sn} on {date_str}: {db_result['message']}")
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
            
            # If records exist and overwrite is false, then decide the page
            # based on number of records and total records for that day. 100 records per page
            page = 1
            if records_count == 0 or overwrite:
                page = 1
            else:
                today = datetime.now()
                if records_count == total_records_on_day and (dont_change_date or date_str == today.strftime('%Y-%m-%d')):
                    self.logger.info(f"All records for device {device_sn} on {date_str} already exist, skipping fetch and store")
                    print(f"All records for device {device_sn} on {date_str} already exist, skipping fetch and store")
                    response = {
                        'device_id': device_sn,
                        'date': date_str,
                        'entries_count': len(records),
                        'db_operation': None,
                        'status': 'skipped'
                    }
                    return response
                elif records_count == total_records_on_day:
                    date_str = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
                    page = 1
                else:
                    page = math.floor(len(records) / 100) + 1

            print(f"Page to fetch for device {device_sn} on {date_str}: {page}")
            # Get device metadata from inverter records
            self.logger.info(f"Fetching inverter record for device metadata: {device_sn}")
            inverter_metadata = self.db_client.get_inverter_record(device_sn)
            # Check if inverter record exists
            if not inverter_metadata:
                error_msg = f"No inverter record found for device {device_sn}, cannot proceed with fetching generation history"
                self.logger.warning(error_msg)
                raise Exception(error_msg)

            # Fetch history for yesterday
            self.logger.info(f"Fetching history for device {device_sn} on {date_str}")
            history_data = self.growatt_client.fetch_device_history(device_sn, inverter_metadata, date_str, date_str, page)                
            self.logger.info(f"Fetched {len(history_data['datas'])} records for {device_sn}")
            print(f"History data fetched - current_count: {len(history_data['datas'])}, total_count: {history_data['count']} records on {date_str} for device {device_sn}")
            
            database_entries = []
            db_result = None
            if store_records:
                print(f"Storing records for device {device_sn} on {date_str}")
                # Process history data into database entries
                database_entries = self.growatt_client.process_history_data_for_db(history_data, device_sn, date_str, inverter_metadata)
                
                # Insert processed entries into database
                db_result = self.db_client.insert_history_into_database(database_entries)
            else:
                print(f"Not storing records for device {device_sn} on {date_str}")

            response = {
                'device_id': device_sn,
                'date': date_str,
                'entries_count': len(database_entries),
                'db_operation': db_result,
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
                yesterday = datetime.now() - timedelta(days=1)
                date_str = yesterday.strftime('%Y-%m-%d')
            
            self.logger.info(f"Analyzing generation data for device {device_sn} on {date_str}")
            
            # Fetch device records from database
            generation_history = self.db_client.get_device_records_by_date(device_sn, date_str)
            print(f"Number of records found for device on date {date_str}: {len(generation_history)}")
            
            if not generation_history:
                self.logger.info(f"No records found for device {device_sn} on {date_str}")
                print(f"No records found for device {device_sn} on {date_str}")
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
                print(f"Deleting disruption events for device {device_sn} on {date_str}")
                db_result = self.db_client.delete_disruption_events(device_sn, date_str)
                if db_result['status'] == 'success':
                    print(f"Deleted {db_result['deleted_records']} disruption events for device {device_sn} on {date_str}")

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
            
            # Enhanced logging for better visibility of conflict resolution
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
        from datetime import datetime, timedelta
        
        # Validate device_sn
        if not device_sn:
            return {'status': 'error', 'message': 'device_sn parameter is required'}, 400
            
        # Set default end_date to today if not provided
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
            
        # If no start_date provided, determine based on latest analysis date
        if not start_date:
            # Try to get the latest analysis date from the database
            latest_analysis_date = self.get_latest_analysis_date_for_device(device_sn)
            print(f"Latest analysis date for device {device_sn}: {latest_analysis_date}")
            self.logger.info(f"Latest analysis date for device {device_sn}: {latest_analysis_date}")
            
            if latest_analysis_date:
                # Parse the date string
                latest_date = datetime.strptime(latest_analysis_date, '%Y-%m-%d').date()
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                if latest_date == end_date_obj:
                    # Re-analyze is okay for the current day, if after 6am and before 7pm
                    now = datetime.now()
                    morning_time = datetime.strptime('06:00', '%H:%M').time()
                    evening_time = datetime.strptime('19:00', '%H:%M').time()
                    
                    if now.time() > morning_time and now.time() < evening_time:
                        start_date = latest_analysis_date
                    else:
                        # Return early if analysis is already done for today and outside operating hours
                        print(f"Analysis already completed for today and outside operating hours")
                        return {'status': 'success', 'message': 'Analysis already completed for today'}, 200
                else:
                    # Use the day after the latest analysis as the start date
                    start_date = (latest_date + timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                # Default to 15 days before end_date if no previous analysis exists
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                start_date = (end_date_obj - timedelta(days=15)).strftime('%Y-%m-%d')
        
        print(f"Analyzing data for device {device_sn} from {start_date} to {end_date}")
        self.logger.info(f"Analyzing data for device {device_sn} from {start_date} to {end_date}")
        
        # Validate date format
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
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
            'created_at': datetime.now().isoformat(),
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
            
            # Convert dates
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            
            # Analyze each day in the range
            current_date = start
            all_results = []
            days_processed = 0
            days_total = (end - start).days + 1
            
            while current_date <= end:
                date_str = current_date.strftime('%Y-%m-%d')
                print(f"Analyzing data for device {device_sn} on {date_str}")
                
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
                    print(f"Error analyzing {date_str}: {result[0]}")
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

                print(f"Analyzed {date_str} for device {device_sn}")
                
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
            task['completed_at'] = datetime.now().isoformat()
            
        except Exception as e:
            print(f"Background task error: {str(e)}")
            if task_id in self.background_tasks:
                self.background_tasks[task_id]['status'] = self.TASK_STATUS['FAILED']
                self.background_tasks[task_id]['error'] = str(e)
                self.background_tasks[task_id]['completed_at'] = datetime.now().isoformat()

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
            print(f"Updating analysis ledger for device {device_sn} with date {analysis_date}")
            self.logger.info(f"Updating analysis ledger for device {device_sn} with date {analysis_date}")
            result = self.db_client.update_analysis_ledger(device_sn, analysis_date, device_metadata)
            if result.get('status') == 'success':
                self.logger.info(f"Analysis ledger updated for device {device_sn} with date {analysis_date}")
                print(f"Analysis ledger updated for device {device_sn} with date {analysis_date}")
            else:
                self.logger.warning(f"Failed to update analysis ledger for device {device_sn}: {result.get('message')}")
                print(f"Failed to update analysis ledger for device {device_sn}: {result.get('message')}")
            return result
        except Exception as e:
            error_msg = f"Error updating analysis ledger for device {device_sn}: {str(e)}"
            print(error_msg)
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