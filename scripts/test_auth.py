#!/usr/bin/env python3
"""
Test script to verify Azure authentication using DefaultAzureCredential
"""
import os
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential

# Ensure project root is on sys.path so `src` package resolves regardless of CWD
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import the GrowattAIAgent class after adjusting sys.path
from src.ai_agent import GrowattAIAgent

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
    
    # Check minimally required environment variables
    logger.info("Checking required environment variables...")
    if not os.getenv('PROJECT_CONNECTION_STRING_AI'):
        logger.error("PROJECT_CONNECTION_STRING_AI is missing. Set it in your environment or .env file.")
        return
    
    # Informative note about credential sources
    if not (os.getenv('AZURE_TENANT_ID') and os.getenv('AZURE_CLIENT_ID') and os.getenv('AZURE_CLIENT_SECRET')):
        logger.info("AZURE_* env vars not fully set — DefaultAzureCredential will try CLI/VSCode/Managed Identity.")
    else:
        logger.info("AZURE_* env vars detected — DefaultAzureCredential will use EnvironmentCredential first.")
    
    # Test DefaultAzureCredential
    try:
        logger.info("Testing DefaultAzureCredential token acquisition for Azure ML scope...")
        credential = DefaultAzureCredential()
        credential.get_token("https://ml.azure.com/.default")
        logger.info("DefaultAzureCredential acquired token successfully for Azure ML scope.")
        
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