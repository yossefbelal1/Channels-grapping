import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"

# 1. Sync app/outreach folder
cmd1 = ["scp", "-r", "-i", REMOTE_KEY, "-o", "StrictHostKeyChecking=no", "app/outreach", f"root@{REMOTE_HOST}:/root/Channels-grapping/app/"]
res1 = subprocess.run(cmd1, capture_output=True, text=True)
print("SCP outreach returncode:", res1.returncode)

# 2. Docker cp into all workers & restart worker_radar
remote_commands = [
    "for c in worker_radar worker_validator worker_graph_expander worker_scavenger; do "
    "docker cp /root/Channels-grapping/app/outreach $c:/app/app/ || true; "
    "done",
    "docker restart worker_radar",
    "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep worker_radar"
]

full_cmd = " && ".join(remote_commands)
cmd2 = ["ssh", "-i", REMOTE_KEY, "-o", "StrictHostKeyChecking=no", f"root@{REMOTE_HOST}", full_cmd]
res2 = subprocess.run(cmd2, capture_output=True, text=True)
print("STDOUT:\n", res2.stdout)
if res2.stderr:
    print("STDERR:\n", res2.stderr)
