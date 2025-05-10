#!/usr/bin/env python3
"""
Script to update all existing users with a default password hash
"""
import logging
import os
import sys

# Add parent directory to path so we can import modules from root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from azure_db import AzureDB

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    """Update all users with the same password hash"""
    # Load environment variables
    load_dotenv()
    
    # Default password for all users
    default_password = "<enter-password-here>"
    
    # Generate password hash
    password_hash = generate_password_hash(default_password)
    
    logger.info(f"Updating all users with default password")
    
    # Initialize database connection
    db = AzureDB()
    
    try:
        # Get connection from pool
        conn = db.connection_pool.getconn()
        cursor = conn.cursor()
        
        # First, check if users table has password_hash column
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='users' AND column_name='password_hash'
        """)
        
        if not cursor.fetchone():
            logger.error("The password_hash column does not exist in the users table. Run the ALTER TABLE command first.")
            return
        
        # Get all users
        cursor.execute("SELECT user_name FROM users")
        users = cursor.fetchall()
        
        if not users:
            logger.warning("No users found in the database.")
            return
        
        # Update each user with the same password hash
        cursor.execute(
            "UPDATE users SET password_hash = %s",
            (password_hash,)
        )
        
        # Commit the transaction
        conn.commit()
        
        logger.info(f"Successfully updated {len(users)} users with default password")
        
    except Exception as e:
        logger.error(f"Error updating users: {e}")
        if 'conn' in locals() and conn:
            conn.rollback()
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            db.connection_pool.putconn(conn)

if __name__ == "__main__":
    main() 