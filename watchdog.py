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
    def __init__(self, app=None):
        self.app = app
        self.logger = logging.getLogger(__name__)
        
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
                    yesterday = datetime.now() - timedelta(days=1)
                    date_str = yesterday.strftime('%Y-%m-%d')
                    print(f"No last record date found for device {device_sn}, using yesterday's date: {date_str}")

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
                yesterday = datetime.now() - timedelta(days=1)
                if records_count == total_records_on_day and (dont_change_date or date_str == yesterday.strftime('%Y-%m-%d')):
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
                return jsonify({
                    'device_id': device_sn,
                    'date': date_str,
                    'status': 'no_data',
                    'message': 'No data available for the requested date'
                }), 404
            
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
        
    def analyze_device_generation_data_and_store_disruptions_route(self, device_sn, date_str=None):
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
            
            # If no disruption events were found, return the response with a note
            if not disruption_events:
                response_data['db_operation'] = {
                    'status': 'no_disruptions', 
                    'inserted_records': 0,
                    'updated_records': 0,
                    'skipped_records': 0,
                    'total_processed': 0
                }
                return response_data
            
            # Log that we found disruptions
            self.logger.info(f"Found {len(disruption_events)} disruption events for device {device_sn} on {date_str}")
            
            # Get device metadata from inverter records
            self.logger.info(f"Fetching inverter record for device metadata: {device_sn}")
            inverter_record = self.db_client.get_inverter_record(device_sn)
            
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
            
            # Use inverter record for device metadata
            device_metadata = {
                'device_sn': inverter_record['device_sn'],
                'device_type': inverter_record['device_type'],
                'device_oem': inverter_record['device_oem'],
                'user_name': inverter_record['user_name'],
                'user_id': inverter_record['user_id'],
                'vendor': inverter_record['vendor'],
                'plant_id': inverter_record['plant_id']
            }
            
            # Add date to device metadata
            device_metadata['date'] = date_str
            
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