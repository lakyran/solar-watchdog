#!/usr/bin/env python3
"""
Test script to verify Azure authentication using EnvironmentCredential
"""
import os
from dotenv import load_dotenv
from azure.identity import EnvironmentCredential

# Import the GrowattAIAgent class
from ai_agent import GrowattAIAgent

def main():
    """
    Test Azure authentication
    """
    # Load environment variables
    load_dotenv()
    
    # Check if environment variables are set
    print("Checking Azure environment variables...")
    required_env_vars = ['AZURE_TENANT_ID', 'AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'PROJECT_CONNECTION_STRING_AI']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Error: The following environment variables are missing: {', '.join(missing_vars)}")
        print("Please set them in the .env file or in your environment.")
        return
    
    print("Environment variables are set.")
    
    # Test EnvironmentCredential
    try:
        print("Testing EnvironmentCredential...")
        credential = EnvironmentCredential()
        print("EnvironmentCredential initialized successfully.")
        
        # Test GrowattAIAgent initialization
        print("Testing GrowattAIAgent initialization...")
        agent = GrowattAIAgent()
        print("GrowattAIAgent initialized successfully.")
        
        # Check if the agent was found or created
        if agent.agent:
            print("Agent status: Ready")
            print(f"Agent ID: {agent.agent.id}")
            print(f"Agent Name: {agent.agent.name}")
            print(f"Agent Model: {agent.agent.model}")
        else:
            print("Agent status: Not initialized correctly")
            
        print("Authentication test completed successfully.")
        
    except Exception as e:
        print(f"Error during authentication test: {str(e)}")
        
if __name__ == "__main__":
    main() 