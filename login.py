import os
import sys
import json
import asyncio
from telethon import TelegramClient
from dotenv import load_dotenv

# Ensure we can import from workspace
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path, validate_telegram_credentials

async def login_session(session_name: str, api_id: int, api_hash: str):
    session_path = get_session_path(session_name)
    print(f"\n==================================================")
    print(f"Authenticating session: '{session_name}'")
    print(f"Session destination: {session_path}.session")
    print(f"==================================================")
    
    # Initialize client on the correct resolved path
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    
    authorized = await client.is_user_authorized()
    if authorized:
        print(f"Session '{session_name}' is ALREADY authorized and valid!")
    else:
        print(f"Session '{session_name}' is not authorized. Starting interactive login...")
        try:
            # Interactively prompts for phone, verification code, and 2FA password on stdin
            await client.start()
            print(f"Success! Session '{session_name}' is now authenticated.")
        except Exception as e:
            print(f"Error authenticating session '{session_name}': {e}")
            
    await client.disconnect()

async def main():
    load_dotenv()
    
    # Load accounts configuration
    accounts = []
    json_path = "accounts.json"
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                accounts = json.load(f)
        except Exception as e:
            print(f"Error reading accounts.json: {e}")
            
    if not accounts:
        api_id = os.getenv("API_ID")
        api_hash = os.getenv("API_HASH")
        if api_id and api_hash:
            accounts = [
                {
                    "session_name": os.getenv("SESSION_VALIDATOR", "validator_session"),
                    "api_id": api_id,
                    "api_hash": api_hash
                }
            ]
        else:
            print("Error: No configuration found in accounts.json or .env")
            sys.exit(1)
            
    # Validate credentials for ALL accounts before proceeding
    for acc in accounts:
        try:
            validate_telegram_credentials(acc.get("session_name"), acc.get("api_id"), acc.get("api_hash"))
        except ValueError as err:
            print(f"\n[VALIDATION FAILED] {err}")
            sys.exit(1)
            
    print("Available Sessions:")
    for idx, acc in enumerate(accounts, 1):
        print(f"{idx}. {acc['session_name']}")
    print(f"{len(accounts) + 1}. Authenticate ALL sessions")
    
    choice = input("\nSelect session to authenticate (number): ").strip()
    
    try:
        choice_idx = int(choice)
        if choice_idx == len(accounts) + 1:
            for acc in accounts:
                await login_session(acc["session_name"], acc["api_id"], acc["api_hash"])
        elif 1 <= choice_idx <= len(accounts):
            acc = accounts[choice_idx - 1]
            await login_session(acc["session_name"], acc["api_id"], acc["api_hash"])
        else:
            print("Invalid selection.")
    except ValueError:
        print("Invalid input.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBootstrap login interrupted.")
