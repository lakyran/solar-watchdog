from azure.ai.projects import AIProjectClient
from azure.identity import EnvironmentCredential
import os
from dotenv import load_dotenv
import json
import openmeteo_requests
import requests_cache
from datetime import datetime, timedelta, timezone
import pytz
import pandas as pd
import re
import logging

# Load environment variables
load_dotenv()

class GrowattAIAgent:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        self.project_connection_string = os.getenv('PROJECT_CONNECTION_STRING_AI')
        if not self.project_connection_string:
            raise ValueError("Azure AI Project configuration is missing. Please set PROJECT_CONNECTION_STRING in .env file")

        self.project_client = AIProjectClient.from_connection_string(
           conn_str=self.project_connection_string,
           credential=EnvironmentCredential()
        )
        
        # Setup weather API client
        self.weather_client = openmeteo_requests.Client(session=requests_cache.CachedSession('.cache', expire_after=3600))
        
        # Define the IST timezone
        self.ist_timezone = pytz.timezone('Asia/Kolkata')
        
        # Define the agent's tools
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather data for a specific location and date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {
                                "type": "number",
                                "description": "Latitude of the location"
                            },
                            "longitude": {
                                "type": "number",
                                "description": "Longitude of the location"
                            },
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format"
                            }
                        },
                        "required": ["latitude", "longitude", "date"]
                    }
                }
            }
        ]
        self.tools = []
        
        # Create the agent
        self.agent = self.project_client.agents.get_agent(
            agent_id="asst_xROwjSlL2vN2Kiy75w26TBns" # GPT-4o
            # agent_id="asst_zvkxE4kbYsYoYiW6vP8VrHSz" # GPT-4o-mini
        )
        if self.agent:
            self.logger.info("Existing agent found")
        else:
            self.logger.info("Agent not found. Creating new agent")
            self.agent = self.project_client.agents.create_agent(
                model="gpt-4o",  # or your preferred model
                name="watchdog-solar-agent",
                instructions="""You are a solar monitoring AI assistant specialized in analyzing solar energy generation and identifying anomalies. Your role is to:

                1. Analyze the provided solar power generation data.
                2. Identify disruption events or efficiency drops in the data and analyze potential causes.
                3. Look for the following if a disruption is identified:
                    a) Drop in grid voltage at the same time, indicating a power cut.
                    b) Increase in inverter temperature indicating thermal degradation.
                    c) Refer to the fault code descriptions in the context.
                4. Report only disruption periods. Consider the duration between start event of disruption to end event as a single reportable event. Once a disruption event starts, till generation is back on track, consider this entire period as a single event. Don't return a disruption event if duration is shorter than 30 minutes.
                5. Response should be in JSON format. One object for each disruption period. No other section apart from JSON required. No extra whitespace. Pure JSON which should be parseable.
                6. Include the following fields for each disruption period: start_time, end_time, total_duration, fault_details, root_cause_analysis, power_generation_during_disruption, parameters_behaviour_during_disruption, is_ongoing_event, further_action_required ignore for ongoing events.
                7. Value of each key should be in simple english. No nested objects allowed.
                8. Include only the most relevant information to the disruptions in the report.

                Legend for fields present in the data:
                    1. status - Standy, Normal or Fault
                    2. ppv - Power output from panels to inverter
                    3. pac - Power output from inverter to
                    4. eacToday - Today's cumulative power generated
                    5. vac1, vac2, vac3 - Grid/AC connected voltage across 3 phases
                    6. vpv1, vpv2, vpv3 - Panel/DC connected voltages across multiple inputs
                    7. temperature - Inverter temperature
                    8. Fault Type - Fault code of the inverter
                """,
            tools=self.tools
        )
        
        # Initialize thread management
        self.active_threads = {}
    
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
    
    def get_weather(self, latitude: float, longitude: float, date: str) -> dict:
        """
        Get weather data for a specific location and date (current or historical only)
        
        Args:
            latitude (float): Latitude of the location
            longitude (float): Longitude of the location
            date (str): Date in YYYY-MM-DD format (must be current or past date)
        
        Returns:
            dict: Weather data including temperature, cloud cover, solar radiation, rain, and sunrise/sunset times
        
        Raises:
            ValueError: If the requested date is in the future
        """
        try:
            # Convert date to datetime
            target_date = datetime.strptime(date, "%Y-%m-%d")
            current_date = self.get_current_time_ist().date()
            
            # Check if the date is in the future
            if target_date.date() > current_date:
                raise ValueError("Weather data is only available for current and historical dates")
            
            # For historical data, use the historical API
            if target_date.date() < current_date:
                url = "https://archive-api.open-meteo.com/v1/archive"
            else:
                url = "https://api.open-meteo.com/v1/forecast"
            
            # Make API request
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": target_date.strftime("%Y-%m-%d"),
                "end_date": target_date.strftime("%Y-%m-%d"),
                "hourly": ["temperature_2m", "cloud_cover", "direct_radiation", "rain", "precipitation"],
                "daily": ["sunrise", "sunset"],  # Add sunrise and sunset to daily parameters
                "timezone": "Asia/Kolkata"  # Use IST timezone
            }
            
            responses = self.weather_client.weather_api(url, params=params)
            response = responses[0]
            
            # Process the hourly response
            hourly = response.Hourly()
            hourly_temperature = hourly.Variables(0).ValuesAsNumpy()
            hourly_cloud_cover = hourly.Variables(1).ValuesAsNumpy()
            hourly_radiation = hourly.Variables(2).ValuesAsNumpy()
            hourly_rain = hourly.Variables(3).ValuesAsNumpy()
            hourly_precipitation = hourly.Variables(4).ValuesAsNumpy()
            
            # Process the daily response for sunrise and sunset
            daily = response.Daily()
            sunrise_time = daily.Variables(0).ValuesAsNumpy()
            sunset_time = daily.Variables(1).ValuesAsNumpy()
            
            # Create DataFrame for hourly data
            data = {
                "date": pd.date_range(
                    start=pd.to_datetime(hourly.Time(), unit="s"),
                    end=pd.to_datetime(hourly.TimeEnd(), unit="s"),
                    freq=pd.Timedelta(seconds=hourly.Interval()),
                    inclusive="left"
                )
            }
            data["temperature"] = hourly_temperature
            data["cloud_cover"] = hourly_cloud_cover
            data["radiation"] = hourly_radiation
            data["rain"] = hourly_rain
            data["precipitation"] = hourly_precipitation
            
            df = pd.DataFrame(data=data)
            
            # Format sunrise and sunset times
            sunrise = pd.to_datetime(sunrise_time[0], unit="s").strftime("%H:%M:%S")
            sunset = pd.to_datetime(sunset_time[0], unit="s").strftime("%H:%M:%S")
            
            return {
                "date": date,
                "location": {"latitude": latitude, "longitude": longitude},
                "weather_data": df.to_dict(orient='records'),
                "sunrise": sunrise,
                "sunset": sunset,
                "source": "historical" if target_date.date() < current_date else "current"
            }
            
        except Exception as e:
            raise Exception(f"Failed to fetch weather data: {str(e)}")
    
    def _extract_json_from_llm_response(self, text):
        """
        Extract valid JSON from a text that may contain JSON mixed with other content.
        This is specifically designed to handle the LLM responses that contain JSON objects.
        
        Args:
            text (str): Text that may contain JSON
            
        Returns:
            list: List of disruption events as proper JSON objects
        """
        # First try to find a JSON array in the text
        json_array_match = re.search(r'\[\s*\{.*?\}\s*\]', text, re.DOTALL)
        if json_array_match:
            try:
                json_str = json_array_match.group(0)
                # Clean up any potential markdown formatting
                json_str = json_str.replace('```json', '').replace('```', '')
                json_data = json.loads(json_str)
                if isinstance(json_data, list):
                    self.logger.debug(f"Extracted JSON using specialized parser: {json_data}")
                    return json_data
            except json.JSONDecodeError:
                pass
        
        # If we couldn't find a valid JSON array, look for an object pattern
        # that matches exactly what we expect, like in the example
        pattern = r'\{\s*"start_time"\s*:\s*"([^"]*)"\s*,\s*"end_time"\s*:\s*"([^"]*)"\s*,\s*"total_duration"\s*:\s*"([^"]*)"\s*,\s*"fault_details"\s*:\s*"([^"]*)"\s*,\s*"root_cause_analysis"\s*:\s*"([^"]*)"\s*,\s*"power_generation_during_disruption"\s*:\s*"([^"]*)"\s*,\s*"parameters_behaviour_during_disruption"\s*:\s*"([^"]*)"\s*,\s*"is_ongoing_event"\s*:\s*"([^"]*)"\s*,\s*"further_action_required"\s*:\s*"([^"]*)"\s*\}'
        
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            events = []
            for match in matches:
                event = {
                    "start_time": match[0],
                    "end_time": match[1],
                    "total_duration": match[2],
                    "fault_details": match[3],
                    "root_cause_analysis": match[4],
                    "power_generation_during_disruption": match[5],
                    "parameters_behaviour_during_disruption": match[6],
                    "is_ongoing_event": match[7],
                    "further_action_required": match[8]
                }
                events.append(event)
            return events
            
        # If still no match, try to find individual JSON objects anywhere in the text
        pattern = r'\{\s*"[^"]+"\s*:\s*"[^"]*"(?:\s*,\s*"[^"]+"\s*:\s*"[^"]*")*\s*\}'
        matches = re.findall(pattern, text)
        if matches:
            events = []
            for potential_json in matches:
                try:
                    event = json.loads(potential_json)
                    events.append(event)
                except json.JSONDecodeError:
                    continue
            if events:
                return events
                
        # If no JSON could be found, return an empty list
        return []
        
    def _parse_markdown_to_json(self, markdown_text):
        """
        Parse markdown bullet points into a structured JSON format.
        
        Args:
            markdown_text (str): Markdown text from AI response
            
        Returns:
            list: List of disruption events as JSON objects
        """
        try:
            # First try to use our specialized JSON extractor
            json_data = self._extract_json_from_llm_response(markdown_text)
            if json_data:
                return json_data
                
            # First, check if the response already contains a valid JSON array enclosed in []
            json_match = re.search(r'\[\s*\{.*?\}\s*\]', markdown_text, re.DOTALL)
            if json_match:
                try:
                    json_str = json_match.group(0)
                    json_data = json.loads(json_str)
                    if isinstance(json_data, list) and len(json_data) > 0:
                        self.logger.debug(f"Found and parsed JSON array: {json_data}")
                        return json_data
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Found JSON-like structure but couldn't parse: {e}")
                    pass

            # Try to parse the entire string as JSON
            try:
                json_data = json.loads(markdown_text)
                self.logger.debug(f"Parsed entire response as JSON: {json_data}")
                return json_data
            except json.JSONDecodeError:
                pass
                
            # If we reach here, we need to manually parse the markdown
            # Extract disruption events - each event is a paragraph
            paragraphs = markdown_text.strip().split('\n\n')
            disruption_events = []
            
            for paragraph in paragraphs:
                if not paragraph.strip():
                    continue
                    
                event = {}
                # Extract key details using more specific regex patterns
                # These patterns now look for the field name followed by actual content
                start_time_match = re.search(r'start\s*time:?\s*([^,\n]+)', paragraph, re.IGNORECASE)
                end_time_match = re.search(r'end\s*time:?\s*([^,\n]+)', paragraph, re.IGNORECASE)
                duration_match = re.search(r'(?:total\s*)?duration:?\s*([^,\n]+)', paragraph, re.IGNORECASE)
                fault_match = re.search(r'fault\s*details:?\s*([^,\n]+)', paragraph, re.IGNORECASE)
                power_match = re.search(r'power\s*generation(?:\s*during\s*disruption)?:?\s*([^,\n]+)', paragraph, re.IGNORECASE)
                root_cause_match = re.search(r'root\s*cause(?:\s*analysis)?:?\s*([^,\n]+)', paragraph, re.IGNORECASE)
                ongoing_match = re.search(r'(?:is\s*)?ongoing(?:\s*disruption)?(?:\s*event)?:?\s*([^,\n]+)', paragraph, re.IGNORECASE)
                parameters_match = re.search(r'parameters(?:_|\s+)behaviour(?:\s*during\s*disruption)?:?\s*([^,\n]+)', paragraph, re.IGNORECASE)
                action_match = re.search(r'(?:further\s*)?action(?:\s*required)?:?\s*([^,\n]+)', paragraph, re.IGNORECASE)
                
                if start_time_match:
                    event['start_time'] = start_time_match.group(1).strip()
                if end_time_match:
                    event['end_time'] = end_time_match.group(1).strip()
                if duration_match:
                    event['total_duration'] = duration_match.group(1).strip()
                if fault_match:
                    event['fault_details'] = fault_match.group(1).strip()
                if power_match:
                    event['power_generation_during_disruption'] = power_match.group(1).strip()
                if root_cause_match:
                    event['root_cause_analysis'] = root_cause_match.group(1).strip()
                if ongoing_match:
                    event['is_ongoing_event'] = ongoing_match.group(1).strip()
                if parameters_match:
                    event['parameters_behaviour_during_disruption'] = parameters_match.group(1).strip()
                if action_match:
                    event['further_action_required'] = action_match.group(1).strip()
                
                if event:  # Only add if we extracted something
                    disruption_events.append(event)
            
            # If no structured events were found, try to directly parse JSON from the text
            if not disruption_events:
                # Look for JSON-like structures in the text - this is a more aggressive approach
                json_regex = r'({[^{}]*}|\[[^\[\]]*\])'
                json_matches = re.findall(json_regex, markdown_text)
                
                for potential_json in json_matches:
                    try:
                        parsed = json.loads(potential_json)
                        return [parsed] if isinstance(parsed, dict) else parsed
                    except json.JSONDecodeError:
                        continue
                
                # If still no luck, return the original text
                return {"analysis": markdown_text}
                
            return disruption_events
            
        except Exception as e:
            self.logger.error(f"Error parsing markdown to JSON: {str(e)}")
            # Return original text as fallback
            return {"analysis": markdown_text, "parse_error": str(e)}
    
    def _prune_short_disruption_events(self, disruption_events, min_duration_minutes=30):
        """
        Prune disruption events with duration less than the specified minimum minutes.
        
        Args:
            disruption_events (list): List of disruption event dictionaries
            min_duration_minutes (int): Minimum duration in minutes to keep an event
            
        Returns:
            list: Filtered list of disruption events
        """
        if not isinstance(disruption_events, list):
            return disruption_events
            
        filtered_events = []
        for event in disruption_events:
            # Check if total_duration field exists
            if "total_duration" in event:
                duration_str = event["total_duration"]
                # Try to match patterns like "25 minutes", "1 hour 15 minutes", etc.
                hours_match = re.search(r'(\d+)\s*(?:hour|hr|h)s?', duration_str, re.IGNORECASE)
                minutes_match = re.search(r'(\d+)\s*(?:minute|min|m)s?', duration_str, re.IGNORECASE)
                seconds_match = re.search(r'(\d+)\s*(?:second|sec|s)s?', duration_str, re.IGNORECASE)
                
                # Calculate total minutes
                total_minutes = 0
                if hours_match:
                    total_minutes += int(hours_match.group(1)) * 60
                if minutes_match:
                    total_minutes += int(minutes_match.group(1))
                if seconds_match and not (hours_match or minutes_match):
                    # Only seconds specified, convert to minutes
                    total_seconds = int(seconds_match.group(1))
                    if total_seconds < 60:
                        # Less than a minute, prune this event
                        continue
                    total_minutes += total_seconds // 60
                    # If there are leftover seconds, round up to 1 minute
                    if total_seconds % 60 != 0:
                        total_minutes += 1
                
                # If we couldn't parse the duration or it's >= min_duration_minutes, keep the event
                if not (hours_match or minutes_match or seconds_match) or total_minutes >= min_duration_minutes:
                    filtered_events.append(event)
            else:
                # If there's no total_duration field, keep the event
                filtered_events.append(event)
        
        return filtered_events

    async def process_query(self, user_query: str, context: dict = None) -> dict:
        """
        Process a user query using the Azure AI agent
        
        Args:
            user_query (str): The user's question or request
            context (dict): Optional context data (e.g., current solar system status)
        
        Returns:
            dict: Response containing the AI's answer and any relevant data
        """
        self.logger.info("Entered process query")
        try:
            # Create a new thread or use existing one from context
            thread_id = context.get('thread_id') if context else None
            if not thread_id:
                thread = self.project_client.agents.create_thread()
                thread_id = thread.id
                self.active_threads[thread_id] = thread
            
            # Add context to the message if provided
            full_message = user_query
            if context:
                full_message = f"User Query: {user_query} \n\n Context as JSON format: {json.dumps(context)}"

            self.logger.debug(f"Full Message length: {len(full_message)}")
            # self.logger.debug(f"Full Message: {full_message}")
            
            # Create message in the thread
            message = self.project_client.agents.create_message(
                thread_id=thread_id,
                role="user",
                content=full_message
            )
            
            self.logger.info(f"Invoking AI agent")
            # Create and process a run
            run = self.project_client.agents.create_and_process_run(
                thread_id=thread_id,
                agent_id=self.agent.id
            )
            self.logger.info(f"Run finished with status: {run.status}")
            if run.status == "failed":
                # Check if you got "Rate limit is exceeded.", then you want to get more quota
                self.logger.error(f"Run failed: {run.last_error}")
            
            # Wait for the run to complete and get messages
            messages = self.project_client.agents.list_messages(thread_id=thread_id)
            
            # Get the latest assistant message
            last_msg = messages.get_last_text_message_by_role("assistant")
            if last_msg:
                self.logger.debug(f"Last Message: {last_msg.text.value}")
            
            # Get the response text
            response_text = last_msg.text.value if last_msg else "No response generated"
            
            # Create initial response object with empty disruption events
            response = {
                "thread_id": thread_id,
                "disruption_events": [],
                "status": "success"
            }
            
            # Try to extract JSON from the response text
            disruption_events = self._parse_markdown_to_json(response_text)
            self.logger.info(f"Disruption events count before pruning: {len(disruption_events)}")

            # Prune disruption events to remove events that have duration less than 30 minutes
            disruption_events = self._prune_short_disruption_events(disruption_events)
            self.logger.info(f"Disruption events count after pruning: {len(disruption_events)}")
            
            # Update the response with any disruption events found
            if isinstance(disruption_events, list) and disruption_events:
                response["disruption_events"] = disruption_events
            elif isinstance(disruption_events, dict) and "parse_error" in disruption_events:
                response["parse_error"] = disruption_events.get("parse_error")
            
            self.cleanup_thread(thread_id)
            return response
            
        except Exception as e:
            self.logger.error(f"Exception in process_query: {e}")
            return {
                "error": str(e),
                "status": "error"
            }
    
    def cleanup_thread(self, thread_id: str) -> None:
        """
        Clean up a conversation thread
        
        Args:
            thread_id (str): The ID of the thread to clean up
        """
        if thread_id in self.active_threads:
            del self.active_threads[thread_id] 