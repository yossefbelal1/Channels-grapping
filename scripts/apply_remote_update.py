import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"

remote_commands = [
    "for c in worker_validator worker_graph_expander worker_scavenger worker_radar; do "
    "echo Updating $c...; "
    "docker cp /root/Channels-grapping/app/core/concurrency.py $c:/app/app/core/concurrency.py || true; "
    "docker cp /root/Channels-grapping/app/validator/contact_extractor.py $c:/app/app/validator/contact_extractor.py || true; "
    "docker cp /root/Channels-grapping/tg_manager.py $c:/app/tg_manager.py || true; "
    "docker cp /root/Channels-grapping/validator.py $c:/app/validator.py || true; "
    "docker cp /root/Channels-grapping/graph_expander.py $c:/app/graph_expander.py || true; "
    "docker cp /root/Channels-grapping/app/discovery/similar_channels_crawler.py $c:/app/app/discovery/similar_channels_crawler.py || true; "
    "done",
    "docker restart worker_validator worker_graph_expander worker_scavenger worker_radar",
    "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep worker_"
]

full_cmd = " && ".join(remote_commands)

cmd = ["ssh", "-i", REMOTE_KEY, "-o", "StrictHostKeyChecking=no", f"root@{REMOTE_HOST}", full_cmd]
res = subprocess.run(cmd, capture_output=True, text=True)
print("STDOUT:\n", res.stdout)
if res.stderr:
    print("STDERR:\n", res.stderr)
