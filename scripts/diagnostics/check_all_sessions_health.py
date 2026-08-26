import os
import redis
import json
from dotenv import load_dotenv

load_dotenv()

# Connect to Redis
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
    password=os.getenv("REDIS_PASSWORD", ""),
    decode_responses=True
)

print("====================================================")
print("     TELEGRAM SESSIONS HEALTH & STATUS REPORT")
print("====================================================\n")

# Load accounts from accounts.json
accounts_path = "accounts.json"
if os.path.exists(accounts_path):
    with open(accounts_path) as f:
        accounts = json.load(f)
else:
    print("[!] accounts.json not found locally!")
    accounts = []

for acc in accounts:
    name = acc['session_name']
    role = acc.get('role', 'scanner/backup')
    
    # Fetch health metrics from Redis
    health_score = r.get(f"health:{name}:score")
    health_status = r.get(f"health:{name}:status")
    cooldown = r.get(f"health:{name}:rate_limited_until")
    
    status_str = "ACTIVE / HEALTHY ✅"
    if health_status:
        status_str = health_status
        
    score_str = health_score if health_score else "100"
    
    cooldown_str = "None"
    if cooldown:
        import time
        diff = float(cooldown) - time.time()
        if diff > 0:
            cooldown_str = f"Rate limited/cooldown for {int(diff)} seconds ⏳"
        else:
            cooldown_str = "Cooldown expired (healthy) ✅"
            
    print(f"👤 Session: {name}")
    print(f"   Role: {role}")
    print(f"   Status: {status_str}")
    print(f"   Health Score: {score_str}/100")
    print(f"   Cooldowns: {cooldown_str}")
    print("-" * 50)

print("\nRedis active connection check completed.")
