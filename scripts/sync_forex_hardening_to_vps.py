import os
import sys
import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"
REMOTE_USER = "root"
REMOTE_DIR = "/root/Channels-grapping"

files_to_sync = [
    ("app/discovery/similar_channels_crawler.py", f"{REMOTE_DIR}/app/discovery/similar_channels_crawler.py"),
    ("scripts/backfill_contacts_v2.py", f"{REMOTE_DIR}/scripts/backfill_contacts_v2.py"),
    ("scripts/reclaim_and_deep_mine_forex_leads.py", f"{REMOTE_DIR}/scripts/reclaim_and_deep_mine_forex_leads.py"),
    ("scripts/cleanup_and_reconcile_outreach_queue.py", f"{REMOTE_DIR}/scripts/cleanup_and_reconcile_outreach_queue.py"),
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

print("=== Rebuilding worker_validator on VPS ===")
rebuild_cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"{REMOTE_USER}@{REMOTE_HOST}",
    "cd /root/Channels-grapping && docker compose build worker_validator && docker compose up -d worker_validator"
]
res_build = subprocess.run(rebuild_cmd, capture_output=True, text=True)
print("STDOUT:\n", res_build.stdout)
print("STDERR:\n", res_build.stderr)
