#!/usr/bin/env python3
"""
Test script to verify Azure authentication using EnvironmentCredential
"""
import os
import logging
from dotenv import load_dotenv
from azure.identity import EnvironmentCredential

# Import the GrowattAIAgent class
from ai_agent import GrowattAIAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    """
    Test Azure authentication
    """
    # Load environment variables
    load_dotenv()
    
    # Check if environment variables are set
    logger.info("Checking Azure environment variables...")
    required_env_vars = ['AZURE_TENANT_ID', 'AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'PROJECT_CONNECTION_STRING_AI']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Error: The following environment variables are missing: {', '.join(missing_vars)}")
        logger.error("Please set them in the .env file or in your environment.")
        return
    
    logger.info("Environment variables are set.")
    
    # Test EnvironmentCredential
    try:
        logger.info("Testing EnvironmentCredential...")
        credential = EnvironmentCredential()
        logger.info("EnvironmentCredential initialized successfully.")
        
        # Test GrowattAIAgent initialization
        logger.info("Testing GrowattAIAgent initialization...")
        agent = GrowattAIAgent()
        logger.info("GrowattAIAgent initialized successfully.")
        
        # Check if the agent was found or created
        if agent.agent:
            logger.info("Agent status: Ready")
            logger.info(f"Agent ID: {agent.agent.id}")
            logger.info(f"Agent Name: {agent.agent.name}")
            logger.info(f"Agent Model: {agent.agent.model}")
        else:
            logger.warning("Agent status: Not initialized correctly")
            
        logger.info("Authentication test completed successfully.")
        
    except Exception as e:
        logger.error(f"Error during authentication test: {str(e)}")
        
if __name__ == "__main__":
    main() 