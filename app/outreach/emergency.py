"""
Emergency controls for the outreach engine.
Fail-closed architecture with multi-tier kill switches.
"""

import os
import logging
from typing import Any, Tuple, Optional

logger = logging.getLogger(__name__)

# File-based kill switch locations (immediate cut even without Redis/DB)
KILL_SWITCH_FILES = [
    "OUTREACH_KILL_SWITCH",
    "/app/OUTREACH_KILL_SWITCH",
    "/tmp/OUTREACH_KILL_SWITCH"
]

def is_kill_switch_active(redis_conn: Any = None) -> Tuple[bool, str]:
    """
    Checks if any kill switch is tripped:
    1. Physical file kill switch on filesystem
    2. Redis emergency stop flag (`outreach:emergency_stop == '1'`)
    3. Redis global disable (`outreach:global:enabled == '0'`)
    Returns: (is_killed, reason)
    """
    # 1. Check physical file kill switches
    for path in KILL_SWITCH_FILES:
        if os.path.exists(path):
            return True, f"File-based Kill Switch present at '{path}'"

    # 2. Check Redis flags if connected
    if redis_conn:
        try:
            # Explicit emergency stop flag
            stop_flag = redis_conn.get("outreach:emergency_stop")
            if stop_flag is not None:
                str_stop = stop_flag.decode("utf-8") if isinstance(stop_flag, bytes) else str(stop_flag)
                if str_stop == "1":
                    return True, "Redis 'outreach:emergency_stop' flag active"

            # Global disable flag
            val = redis_conn.get("outreach:global:enabled")
            if val is not None:
                str_val = val.decode("utf-8") if isinstance(val, bytes) else str(val)
                if str_val == "0":
                    return True, "Redis 'outreach:global:enabled' is set to 0"
        except Exception as e:
            logger.error(f"Error checking kill switch in Redis (failing closed): {e}")
            return True, f"Redis error during safety check: {e}"

    return False, ""

def is_outreach_enabled(redis_conn: Any = None) -> bool:
    """
    Check if outreach is globally enabled via environment and Redis.
    FAIL-CLOSED: Defaults to False (Disabled by Default).
    Only enabled if OUTREACH_ENABLED is explicitly set to 'true' AND no kill switches are tripped.
    """
    # 1. Environment MUST be explicitly set to 'true' (Default is FALSE)
    env_enabled = os.environ.get("OUTREACH_ENABLED", "false").lower() == "true"
    if not env_enabled:
        return False

    # 2. Kill switch check
    is_killed, _ = is_kill_switch_active(redis_conn)
    if is_killed:
        return False

    # 3. If Redis is present, must not be disabled
    if redis_conn:
        try:
            val = redis_conn.get("outreach:global:enabled")
            if val is not None:
                str_val = val.decode("utf-8") if isinstance(val, bytes) else str(val)
                if str_val != "1":
                    return False
        except Exception as e:
            logger.error(f"Error checking global outreach status in Redis (failing closed): {e}")
            return False

    return True

def check_outreach_safety_gate(
    redis_conn: Any,
    session_name: str,
    target_username: Optional[str],
    log_status: str,
    campaign_mode: str = "dry_run"
) -> Tuple[bool, str]:
    """
    Multi-Layer Hard Safety Gate before ANY Telegram DM dispatch:
    Layer 1: Emergency Kill Switch (File + Redis)
    Layer 2: Global Configuration (OUTREACH_ENABLED must be explicitly True)
    Layer 3: Single-Account Guard (session_name MUST be 'user_session')
    Layer 4: Approval Gate (log_status MUST be 'approved', NOT 'pending' or 'pending_review')
    Layer 5: Dry Run Gate (blocks real dispatch if mode is 'dry_run')
    Layer 6: Target Legitimacy (target_username must not be empty, bot, or system keyword)
    Returns: (is_allowed, reason)
    """
    # Layer 1: Kill Switch
    is_killed, kill_reason = is_kill_switch_active(redis_conn)
    if is_killed:
        return False, f"BLOCKED_BY_KILL_SWITCH: {kill_reason}"

    # Layer 2: Configuration Enabled
    if not is_outreach_enabled(redis_conn):
        return False, "OUTREACH_DISABLED: OUTREACH_ENABLED is not 'true' or globally disabled"

    # Layer 3: Single-Account Guard (Tamer's account ONLY)
    if session_name != "user_session":
        return False, f"SECURITY_VIOLATION: Non-Tamer session '{session_name}' attempted outreach"

    # Layer 4: Approval Gate
    if str(log_status).lower() != "approved":
        return False, f"APPROVAL_REQUIRED: Lead status is '{log_status}', must be 'approved' by human review"

    # Layer 5: Dry Run Check
    if campaign_mode.lower() == "dry_run" or os.environ.get("CAMPAIGN_MODE", "dry_run").lower() == "dry_run":
        return False, "DRY_RUN: System is in dry_run mode (no outbound dispatch allowed)"

    # Layer 6: Target Legitimacy
    if not target_username or not target_username.strip():
        return False, "INVALID_TARGET: Target username is empty"
    
    t_clean = target_username.strip().lower().lstrip('@')
    if t_clean.endswith('bot') or t_clean.endswith('_bot') or t_clean in (
        'addlist', 'everyone', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'admin', 'support'
    ):
        return False, f"INVALID_TARGET: '{target_username}' is a bot or system alias"

    return True, "ALLOWED"

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
        redis_conn.set("outreach:emergency_stop", "1")
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
        redis_conn.delete("outreach:emergency_stop")
        redis_conn.set("outreach:global:enabled", "1")
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
