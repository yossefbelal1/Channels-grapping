import os
import sys
import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"
REMOTE_USER = "root"
REMOTE_DIR = "/root/Channels-grapping"

files_to_sync = [
    ("app/discovery/taxonomy.py", f"{REMOTE_DIR}/app/discovery/taxonomy.py"),
    ("app/discovery/similar_channels_crawler.py", f"{REMOTE_DIR}/app/discovery/similar_channels_crawler.py"),
    ("validator.py", f"{REMOTE_DIR}/validator.py"),
    ("dashboard.py", f"{REMOTE_DIR}/dashboard.py"),
    ("tests/test_forex_qualification_gate.py", f"{REMOTE_DIR}/tests/test_forex_qualification_gate.py"),
]

for local_rel, remote_abs in files_to_sync:
    local_abs = os.path.abspath(local_rel)
    cmd = [
        "scp", "-i", REMOTE_KEY,
        "-o", "StrictHostKeyChecking=no",
        local_abs,
        f"{REMOTE_USER}@{REMOTE_HOST}:{remote_abs}"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"Uploaded: {local_rel} -> {remote_abs}")
    else:
        print(f"Failed to upload {local_rel}: {res.stderr}")

print("\n=== Rebuilding & Restarting Services on VPS ===")
restart_cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"{REMOTE_USER}@{REMOTE_HOST}",
    "cd /root/Channels-grapping && "
    "docker compose restart leadhunter_dashboard worker_validator worker_graph_expander worker_scavenger worker_radar"
]
res_restart = subprocess.run(restart_cmd, capture_output=True, text=True)
print("STDOUT:\n", res_restart.stdout)
if res_restart.stderr:
    print("STDERR:\n", res_restart.stderr)

print("\n=== Testing Dashboard API on VPS ===")
test_api_cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"{REMOTE_USER}@{REMOTE_HOST}",
    "curl -s http://localhost:8000/api/discovered-24h?status=qualified | python3 -c 'import sys, json; data = json.load(sys.stdin); print(\"Total Discovered:\", data.get(\"summary\", {}).get(\"total_discovered\")); print(\"Qualified:\", data.get(\"summary\", {}).get(\"qualified_count\")); print(\"Channels returned in qualified:\", len(data.get(\"channels\", []))); [print(\"  ->\", c[\"channel_username\"], c.get(\"tier\"), \"forex:\", c.get(\"forex_intent_score\"), \"comm:\", c.get(\"commercial_fit_score\")) for c in data.get(\"channels\", [])[:10]]'"
]
res_api = subprocess.run(test_api_cmd, capture_output=True, text=True)
print("API Response:\n", res_api.stdout)
if res_api.stderr:
    print("API Error:\n", res_api.stderr)
