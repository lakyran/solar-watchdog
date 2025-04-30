import os
import logging
from psycopg2 import pool
import json
from datetime import datetime, timezone
import pytz

class AzureDB:
    def __init__(self):
        # Set up logger for this class
        self.logger = logging.getLogger(__name__)
        
        # Database Configuration
        self.db_host = os.getenv('POSTGRES_HOST')
        self.db_port = os.getenv('POSTGRES_PORT', '5432')
        self.db_name = os.getenv('POSTGRES_DB')
        self.db_user = os.getenv('POSTGRES_USER')
        self.db_password = os.getenv('POSTGRES_PASSWORD')
        
        # Check if required database environment variables are set
        if not self.db_host or not self.db_name or not self.db_user or not self.db_password:
            self.logger.error("Missing database configuration environment variables")
            raise ValueError("Database configuration is missing. Please check your environment variables.")
        
        # Define the IST timezone
        self.ist_timezone = pytz.timezone('Asia/Kolkata')
        
        # Create connection pool
        self.connection_pool = None
        self.init_connection()
    
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
    
    def init_connection(self):
        """Initialize database connection pool"""
        try:
            self.connection_pool = pool.SimpleConnectionPool(
                1, 10,
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            self.logger.info("PostgreSQL connection pool created successfully")
        except Exception as e:
            self.logger.error(f"Error creating PostgreSQL connection pool: {e}")
            self.connection_pool = None
    
    def insert_history_into_database(self, entries):
        """
        Insert processed entries into PostgreSQL database
        
        Args:
            entries (list): List of processed database entries
            
        Returns:
            dict: Result of the operation with count of inserted records
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        inserted_count = 0
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            self.logger.debug(f"Attempting to insert {len(entries)} records into database")
            
            # Insert entries into database table
            for entry in entries:
                cursor.execute(
                    """
                    INSERT INTO power_gen_history 
                    (datetime, vendor, user_name, device_sn, device_oem, plant_id, device_type, status, ppv, pac, eac_today, vpv1, vpv2, vpv3, vac1, vac2, vac3, temperature, fault_type, total_records_on_day, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (device_sn, datetime) DO UPDATE
                    SET vendor = EXCLUDED.vendor,
                        user_name = EXCLUDED.user_name,
                        device_oem = EXCLUDED.device_oem,
                        plant_id = EXCLUDED.plant_id,
                        device_type = EXCLUDED.device_type,
                        data = EXCLUDED.data,
                        status = EXCLUDED.status,
                        ppv = EXCLUDED.ppv,
                        pac = EXCLUDED.pac,
                        eac_today = EXCLUDED.eac_today,
                        vpv1 = EXCLUDED.vpv1,
                        vpv2 = EXCLUDED.vpv2,
                        vpv3 = EXCLUDED.vpv3,
                        vac1 = EXCLUDED.vac1,
                        vac2 = EXCLUDED.vac2,
                        vac3 = EXCLUDED.vac3,
                        temperature = EXCLUDED.temperature,
                        fault_type = EXCLUDED.fault_type,
                        total_records_on_day = EXCLUDED.total_records_on_day
                    """,
                    (
                        entry['datetime'],
                        entry['vendor'],
                        entry['user_name'],
                        entry['device_sn'],
                        entry['device_oem'],
                        entry['plant_id'],
                        entry['device_type'],
                        entry['status'],
                        entry['ppv'],
                        entry['pac'],
                        entry['eacToday'],
                        entry['vpv1'],
                        entry['vpv2'],
                        entry['vpv3'],
                        entry['vac1'],
                        entry['vac2'],
                        entry['vac3'],
                        entry['temperature'],
                        entry['faultType'],
                        entry['total_records_on_day'],
                        entry['data']
                    )
                )
                inserted_count += 1
            
            # Commit the transaction
            conn.commit()
            
            self.logger.info(f"Successfully inserted {inserted_count} records into database")
            
            return {
                "status": "success",
                "inserted_records": inserted_count
            }
            
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Database error during insertion: {e}")
            raise Exception(f"Database error: {str(e)}")
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def get_device_records_by_date(self, device_sn, date):
        """
        Retrieve all records for a specific device on a specific date
        
        Args:
            device_sn (str): Device serial number
            date (str): Date string in YYYY-MM-DD format
            
        Returns:
            list: List of records for the device on the specified date
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            self.logger.debug(f"Querying records for device {device_sn} on date {date}")
            
            # Query to get all records for the device on the specified date
            cursor.execute(
                """
                SELECT TO_CHAR(datetime, 'YYYY-MM-DD HH24:MI:SS') as datetime, vendor, user_name, device_sn, device_oem, plant_id, 
                       device_type, status, ppv, pac, eac_today, vpv1, vpv2, vpv3, 
                       vac1, vac2, vac3, temperature, fault_type, total_records_on_day
                FROM power_gen_history 
                WHERE device_sn = %s AND DATE(datetime) = %s
                ORDER BY datetime
                """,
                (device_sn, date)
            )
            
            # Get column names
            column_names = [desc[0] for desc in cursor.description]
            
            # Fetch all rows and convert to dictionaries
            records = []
            for row in cursor.fetchall():
                record = dict(zip(column_names, row))
                records.append(record)
            
            self.logger.info(f"Retrieved {len(records)} records for device {device_sn} on date {date}")
            return records
            
        except Exception as e:
            error_msg = f"Database error: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def insert_disruption_events(self, disruption_events, device_metadata):
        """
        Insert disruption events into the disruption_events table
        
        Args:
            disruption_events (list): List of disruption event objects
            device_metadata (dict): Device metadata including user_name, vendor, device_sn, etc.
            
        Returns:
            dict: Result of the operation with count of inserted records
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        inserted_count = 0
        updated_count = 0
        skipped_count = 0
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            self.logger.debug(f"Attempting to insert {len(disruption_events)} disruption events")
            
            # Extract metadata fields with defaults for missing values
            user_name = device_metadata.get('user_name', '')
            user_id = device_metadata.get('user_id', '')
            vendor = device_metadata.get('vendor', '')
            device_sn = device_metadata.get('device_sn', '')
            device_oem = device_metadata.get('device_oem', '')
            device_type = device_metadata.get('device_type', 0)
            plant_id = device_metadata.get('plant_id', '')
            event_date = device_metadata.get('date', '')
            
            # Get current timestamp in IST
            created_at = self.get_current_time_ist().isoformat()
            
            # Insert each disruption event
            for event in disruption_events:
                # Handle default values for optional fields
                further_action = event.get('further_action_required', '')
                if event.get('is_ongoing_event', '').lower() == 'true' and not further_action:
                    further_action = 'Ongoing event - monitoring required'
                
                try:
                    # First check if the record exists
                    cursor.execute(
                        """
                        SELECT 1 FROM disruption_events 
                        WHERE device_sn = %s AND event_date = %s AND start_time = %s
                        LIMIT 1
                        """,
                        (device_sn, event_date, event.get('start_time', ''))
                    )
                    
                    # Determine if this will be an insert or update
                    record_exists = cursor.fetchone() is not None
                    
                    # Use ON CONFLICT to handle duplicate entries
                    cursor.execute(
                        """
                        INSERT INTO disruption_events 
                        (event_id, created_at, user_name, user_id, vendor, device_sn, device_oem, device_type, 
                        plant_id, event_date, start_time, end_time, total_duration, fault_details, 
                        root_cause_analysis, power_generation_during_disruption, 
                        parameters_behaviour_during_disruption, is_ongoing_event, further_action_required)
                        VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (device_sn, event_date, start_time) DO UPDATE SET
                            end_time = EXCLUDED.end_time,
                            total_duration = EXCLUDED.total_duration,
                            fault_details = EXCLUDED.fault_details,
                            root_cause_analysis = EXCLUDED.root_cause_analysis,
                            power_generation_during_disruption = EXCLUDED.power_generation_during_disruption,
                            parameters_behaviour_during_disruption = EXCLUDED.parameters_behaviour_during_disruption,
                            is_ongoing_event = EXCLUDED.is_ongoing_event,
                            further_action_required = EXCLUDED.further_action_required
                        """,
                        (
                            created_at,
                            user_name,
                            user_id,
                            vendor,
                            device_sn,
                            device_oem,
                            device_type,
                            plant_id,
                            event_date,
                            event.get('start_time', ''),
                            event.get('end_time', ''),
                            event.get('total_duration', ''),
                            event.get('fault_details', ''),
                            event.get('root_cause_analysis', ''),
                            event.get('power_generation_during_disruption', ''),
                            event.get('parameters_behaviour_during_disruption', ''),
                            event.get('is_ongoing_event', ''),
                            further_action
                        )
                    )
                    
                    # Increment the appropriate counter based on whether it was an insert or update
                    if record_exists:
                        updated_count += 1
                        self.logger.info(f"Updated existing disruption event for {device_sn} on {event_date} starting at {event.get('start_time', '')}")
                    else:
                        inserted_count += 1
                        self.logger.info(f"Inserted new disruption event for {device_sn} on {event_date} starting at {event.get('start_time', '')}")
                    
                except Exception as insert_error:
                    # Log the error and return failed status
                    error_msg = f"Error processing disruption event: {str(insert_error)}"
                    self.logger.error(error_msg)
                    if conn:
                        conn.rollback()
                    return {
                        "status": "error",
                        "message": error_msg,
                        "inserted_records": inserted_count,
                        "updated_records": updated_count,
                        "skipped_records": skipped_count,
                        "total_processed": inserted_count + updated_count + skipped_count
                    }
            
            # If we get here, all events were processed successfully
            # Commit the transaction
            conn.commit()
            
            return {
                "status": "success",
                "inserted_records": inserted_count,
                "updated_records": updated_count,
                "skipped_records": skipped_count,
                "total_processed": inserted_count + updated_count + skipped_count
            }
            
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Error inserting disruption events: {str(e)}")
            raise Exception(f"Database error: {str(e)}")
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def get_inverter_record(self, device_sn):
        """
        Fetch inverter record for a specific device from the inverters table
        
        Args:
            device_sn (str): Device serial number
            
        Returns:
            dict: Inverter record or None if not found
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            self.logger.debug(f"Querying inverter record for device_sn: {device_sn}")
            
            # Query to get inverter record by device_sn
            cursor.execute(
                """
                SELECT device_sn, user_name, user_id, vendor, plant_id, device_oem, 
                       device_type, latitude, longitude
                FROM inverters 
                WHERE device_sn = %s
                """,
                (device_sn,)
            )
            
            # Get column names
            column_names = [desc[0] for desc in cursor.description]
            
            # Fetch the first matching record
            row = cursor.fetchone()
            if not row:
                self.logger.warning(f"No inverter record found for device_sn: {device_sn}")
                return None
                
            # Convert row to dictionary
            inverter_record = dict(zip(column_names, row))
            
            self.logger.info(f"Retrieved inverter record for device_sn: {device_sn}")
            return inverter_record
            
        except Exception as e:
            error_msg = f"Database error retrieving inverter record: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def get_disruption_events(self, device_sn, date=None):
        """
        Fetch disruption events for a specific device, optionally filtered by date
        
        Args:
            device_sn (str): Device serial number
            date (str, optional): Date string in YYYY-MM-DD format. If None, returns all dates.
            
        Returns:
            list: List of disruption events for the device
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            if date:
                self.logger.debug(f"Querying disruption events for device {device_sn} on date {date}")
            else:
                self.logger.debug(f"Querying all disruption events for device {device_sn}")
            
            # Prepare the query based on whether date is provided
            if date:
                # Query for a specific date
                cursor.execute(
                    """
                    SELECT 
                        TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at,
                        event_id,
                        user_name, 
                        user_id, 
                        vendor, 
                        device_sn, 
                        device_oem, 
                        device_type, 
                        plant_id, 
                        TO_CHAR(event_date, 'YYYY-MM-DD') as event_date, 
                        TO_CHAR(start_time, 'YYYY-MM-DD HH24:MI:SS') as start_time, 
                        TO_CHAR(end_time, 'YYYY-MM-DD HH24:MI:SS') as end_time, 
                        total_duration, 
                        fault_details, 
                        root_cause_analysis, 
                        power_generation_during_disruption, 
                        parameters_behaviour_during_disruption, 
                        is_ongoing_event, 
                        further_action_required
                    FROM disruption_events 
                    WHERE device_sn = %s AND event_date = %s
                    ORDER BY event_date DESC, start_time DESC
                    """,
                    (device_sn, date)
                )
            else:
                # Query for all dates
                cursor.execute(
                    """
                    SELECT 
                        event_id, 
                        user_name, 
                        user_id, 
                        vendor, 
                        device_sn, 
                        device_oem, 
                        device_type, 
                        plant_id, 
                        TO_CHAR(event_date, 'YYYY-MM-DD') as event_date, 
                        start_time, 
                        end_time, 
                        total_duration, 
                        fault_details, 
                        root_cause_analysis, 
                        power_generation_during_disruption, 
                        parameters_behaviour_during_disruption, 
                        is_ongoing_event, 
                        further_action_required,
                        TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at
                    FROM disruption_events 
                    WHERE device_sn = %s
                    ORDER BY event_date DESC, start_time DESC
                    """,
                    (device_sn,)
                )
            
            # Get column names
            column_names = [desc[0] for desc in cursor.description]
            
            # Fetch all rows and convert to dictionaries
            disruption_events = []
            for row in cursor.fetchall():
                event = dict(zip(column_names, row))
                disruption_events.append(event)
            
            self.logger.info(f"Retrieved {len(disruption_events)} disruption events for device {device_sn}")
            return disruption_events
            
        except Exception as e:
            error_msg = f"Database error getting disruption events: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def get_last_record_date_for_device(self, device_sn):
        """
        Get the date of the most recent record for a specific device
        
        Args:
            device_sn (str): Device serial number
            
        Returns:
            str: Date of the last record in YYYY-MM-DD format, or None if no records exist
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            self.logger.debug(f"Querying last record date for device: {device_sn}")
            
            # Query to get the most recent date for the device
            cursor.execute(
                """
                SELECT TO_CHAR(MAX(datetime), 'YYYY-MM-DD') as last_date
                FROM power_gen_history 
                WHERE device_sn = %s
                """,
                (device_sn,)
            )
            
            # Fetch the result
            result = cursor.fetchone()
            if result:
                self.logger.info(f"Last record date for device {device_sn}: {result[0]}")
                return result[0]  # Return the date string
            else:
                self.logger.info(f"No records found for device {device_sn}")
                return None  # No records found
            
        except Exception as e:
            error_msg = f"Database error retrieving last record date: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def delete_device_records_by_date(self, device_sn, date):
        """
        Delete all records for a specific device on a specific date from the power_gen_history table
        
        Args:
            device_sn (str): Device serial number
            date (str): Date string in YYYY-MM-DD format
            
        Returns:
            dict: Result of the operation with count of deleted records
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            self.logger.debug(f"Deleting records for device {device_sn} on date {date}")
            
            # Query to delete all records for the device on the specified date
            cursor.execute(
                """
                DELETE FROM power_gen_history 
                WHERE device_sn = %s AND DATE(datetime) = %s
                """,
                (device_sn, date)
            )
            
            # Get number of deleted rows
            deleted_count = cursor.rowcount
            
            # Commit the transaction
            conn.commit()
            
            self.logger.info(f"Deleted {deleted_count} records for device {device_sn} on date {date}")
            
            return {
                "status": "success",
                "deleted_records": deleted_count
            }
            
        except Exception as e:
            if conn:
                conn.rollback()
            error_msg = f"Database error deleting records: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def get_inverters_list(self, username=None):
        """
        Get a list of all inverters in the database with their serial numbers and user names.
        
        Args:
            username (str, optional): If provided, filter inverters by this username
            
        Returns:
            list: A list of dictionaries containing device_sn and user_name for each inverter
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            if username:
                self.logger.debug(f"Querying list of inverters for user: {username}")
                # Query to get inverters for a specific user
                cursor.execute(
                    """
                    SELECT DISTINCT device_sn, user_name, device_type, vendor, plant_id
                    FROM inverters
                    WHERE LOWER(user_name) = LOWER(%s)
                    ORDER BY user_name, device_sn
                    """,
                    (username,)
                )
            else:
                self.logger.debug("Querying list of all inverters")
                # Query to get all distinct inverters
                cursor.execute(
                    """
                    SELECT DISTINCT device_sn, user_name, device_type, vendor, plant_id
                    FROM inverters
                    ORDER BY user_name, device_sn
                    """
                )
            
            # Get column names
            column_names = ['device_sn', 'user_name', 'device_type', 'vendor', 'plant_id']
            
            # Fetch all rows and convert to dictionaries
            inverters = []
            for row in cursor.fetchall():
                inverter = dict(zip(column_names, row))
                inverters.append(inverter)
                
            self.logger.info(f"Retrieved {len(inverters)} inverters from database")
            return inverters
            
        except Exception as e:
            error_msg = f"Error fetching inverters list: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def delete_disruption_events(self, device_sn, date):
        """
        Delete all disruption events for a specific device on a specific date
        
        Args:
            device_sn (str): Device serial number
            date (str): Date string in YYYY-MM-DD format
            
        Returns:
            dict: Result of the operation with count of deleted records
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            self.logger.debug(f"Deleting disruption events for device {device_sn} on date {date}")
            
            # Query to delete all disruption events for the device on the specified date
            cursor.execute(
                """
                DELETE FROM disruption_events 
                WHERE device_sn = %s AND event_date = %s
                """,
                (device_sn, date)
            )
            
            # Get number of deleted rows
            deleted_count = cursor.rowcount
            
            # Commit the transaction
            conn.commit()
            
            self.logger.info(f"Deleted {deleted_count} disruption events for device {device_sn} on date {date}")
            
            return {
                "status": "success",
                "deleted_records": deleted_count
            }
            
        except Exception as e:
            if conn:
                conn.rollback()
            error_msg = f"Database error deleting disruption events: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def get_latest_analysis_date_for_device(self, device_sn):
        """
        Retrieve the latest analysis date for a specific device from the analysis_ledger table
        
        Args:
            device_sn (str): Device serial number
            
        Returns:
            str: Date string in YYYY-MM-DD format of the latest analysis or None if no record found
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            self.logger.debug(f"Querying latest analysis date for device {device_sn}")
            
            # Query to get the latest analysis date for the device
            cursor.execute(
                """
                SELECT TO_CHAR(latest_analysis_date, 'YYYY-MM-DD') as latest_date
                FROM analysis_ledger 
                WHERE device_sn = %s
                ORDER BY latest_analysis_date DESC
                LIMIT 1
                """,
                (device_sn,)
            )
            
            result = cursor.fetchone()
            
            if result:
                self.logger.info(f"Latest analysis date for device {device_sn}: {result[0]}")
                return result[0]  # Return the date string
            else:
                self.logger.info(f"No analysis record found for device {device_sn}")
                return None  # No record found
            
        except Exception as e:
            error_msg = f"Database error while getting latest analysis date: {str(e)}"
            self.logger.error(error_msg)
            return None
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn)
    
    def update_analysis_ledger(self, device_sn, analysis_date, device_metadata=None):
        """
        Update or insert a record in the analysis_ledger table with the latest analysis date
        
        Args:
            device_sn (str): Device serial number
            analysis_date (str): Date of analysis in YYYY-MM-DD format
            device_metadata (dict, optional): Dictionary containing vendor and device_oem. 
                                             If not provided, will attempt to get from inverters table.
            
        Returns:
            dict: Result of the operation
        """
        if not self.connection_pool:
            self.logger.error("Database connection pool not available")
            raise ValueError("Database connection pool not available")
        
        conn = None
        cursor = None
        
        try:
            # Get connection from pool
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            self.logger.debug(f"Updating analysis ledger for device {device_sn} with date {analysis_date}")
            
            # If device_metadata not provided, get it from inverters table
            vendor = None
            device_oem = None
            
            if device_metadata:
                vendor = device_metadata.get('vendor')
                device_oem = device_metadata.get('device_oem')
                
            # Convert string date to timestamp for PostgreSQL
            try:
                if isinstance(analysis_date, str):
                    # Parse date string to datetime
                    analysis_timestamp = datetime.strptime(analysis_date, '%Y-%m-%d')
                else:
                    # Use the provided datetime object
                    analysis_timestamp = analysis_date
            except ValueError:
                error_msg = "Invalid date format. Expected YYYY-MM-DD"
                self.logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg
                }
            
            # Get current IST time for last_updated_at
            last_updated_at = self.get_current_time_ist()
            
            # Check if a record already exists
            cursor.execute(
                """
                SELECT 1 FROM analysis_ledger
                WHERE device_sn = %s AND vendor = %s
                """,
                (device_sn, vendor)
            )
            
            record_exists = cursor.fetchone() is not None
            
            if record_exists:
                self.logger.debug(f"Existing record found for device {device_sn}, updating analysis date to {analysis_date}")
                # Update existing record
                cursor.execute(
                    """
                    UPDATE analysis_ledger
                    SET device_oem = %s,
                        latest_analysis_date = %s,
                        last_updated_at = %s
                    WHERE device_sn = %s AND vendor = %s
                    """,
                    (device_oem, analysis_timestamp, last_updated_at, device_sn, vendor)
                )
                self.logger.info(f"Updated analysis ledger for device {device_sn} with date {analysis_date}")
            else:
                self.logger.debug(f"No existing record found for device {device_sn}, creating new entry")
                # Insert new record
                cursor.execute(
                    """
                    INSERT INTO analysis_ledger
                    (device_sn, vendor, device_oem, latest_analysis_date, last_updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (device_sn, vendor, device_oem, analysis_timestamp, last_updated_at)
                )
                self.logger.info(f"Created new analysis ledger entry for device {device_sn} with date {analysis_date}")
            
            # Commit the transaction
            conn.commit()
            
            return {
                "status": "success",
                "message": f"Analysis ledger {'updated' if record_exists else 'inserted'} for device {device_sn}"
            }
            
        except Exception as e:
            if conn:
                conn.rollback()
            error_msg = f"Database error updating analysis ledger: {str(e)}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg
            }
        
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.connection_pool.putconn(conn) 