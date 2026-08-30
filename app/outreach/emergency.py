"""
Emergency controls for the outreach engine.
"""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

def is_outreach_enabled(redis_conn: Any) -> bool:
    """
    Check if outreach is globally enabled via environment and Redis.
    
    Args:
        redis_conn: Redis connection object
        
    Returns:
        bool: True if enabled, False otherwise (fail-closed on error)
    """
    env_enabled = os.environ.get("OUTREACH_ENABLED", "true").lower() == "true"
    if not env_enabled:
        return False
        
    try:
        val = redis_conn.get("outreach:global:enabled")
        # If key doesn't exist, it defaults to enabled (if env says so)
        # If key exists and is '0', it's disabled
        if val is not None:
            str_val = val.decode("utf-8") if isinstance(val, bytes) else str(val)
            if str_val == "0":
                return False
        return True
    except Exception as e:
        logger.error(f"Error checking global outreach status in Redis: {e}")
        return False

def is_account_enabled(redis_conn: Any, session_name: str) -> bool:
    """
    Check if a specific account is enabled for outreach.
    
    Args:
        redis_conn: Redis connection object
        session_name: The account session name
        
    Returns:
        bool: True if enabled, False otherwise (fail-closed on error)
    """
    try:
        val = redis_conn.get(f"outreach:account:{session_name}:enabled")
        if val is not None:
            str_val = val.decode("utf-8") if isinstance(val, bytes) else str(val)
            if str_val == "0":
                return False
        return True
    except Exception as e:
        logger.error(f"Error checking account {session_name} status in Redis: {e}")
        return False

def emergency_stop(redis_conn: Any) -> None:
    """
    Globally stop all outreach operations.
    
    Args:
        redis_conn: Redis connection object
    """
    try:
        redis_conn.set("outreach:global:enabled", "0")
        logger.warning("EMERGENCY STOP triggered globally.")
    except Exception as e:
        logger.error(f"Failed to trigger global emergency stop: {e}")

def emergency_resume(redis_conn: Any) -> None:
    """
    Resume global outreach operations.
    
    Args:
        redis_conn: Redis connection object
    """
    try:
        redis_conn.delete("outreach:global:enabled")
        logger.warning("Global emergency stop lifted.")
    except Exception as e:
        logger.error(f"Failed to lift global emergency stop: {e}")

def disable_account(redis_conn: Any, session_name: str) -> None:
    """
    Disable a specific account from outreach operations.
    
    Args:
        redis_conn: Redis connection object
        session_name: The account session name
    """
    try:
        redis_conn.set(f"outreach:account:{session_name}:enabled", "0")
        logger.warning(f"Account {session_name} disabled from outreach.")
    except Exception as e:
        logger.error(f"Failed to disable account {session_name}: {e}")

def enable_account(redis_conn: Any, session_name: str) -> None:
    """
    Enable a specific account for outreach operations.
    
    Args:
        redis_conn: Redis connection object
        session_name: The account session name
    """
    try:
        redis_conn.delete(f"outreach:account:{session_name}:enabled")
        logger.info(f"Account {session_name} enabled for outreach.")
    except Exception as e:
        logger.error(f"Failed to enable account {session_name}: {e}")
