import subprocess

old_ip = "63.178.198.95"
new_ip = "167.233.246.102"
key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"

print("1. Syncing sessions from /home/ubuntu/leadhunter-project/ to new server...")
cmd1 = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    f"ubuntu@{old_ip}",
    f"rsync -avz /home/ubuntu/leadhunter-project/*.session /home/ubuntu/leadhunter-project/sessions/*.session root@{new_ip}:/root/Channels-grapping/sessions/"
]
res1 = subprocess.run(cmd1, capture_output=True, text=True)
print("Sync 1 stdout:\n", res1.stdout)
print("Sync 1 stderr:\n", res1.stderr)

print("2. Copying user_session.session to root folder on new server...")
cmd2 = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    f"root@{new_ip}",
    "cp /root/Channels-grapping/sessions/user_session.session /root/Channels-grapping/user_session.session && cp /root/Channels-grapping/sessions/*.session /root/Channels-grapping/"
]
res2 = subprocess.run(cmd2, capture_output=True, text=True)
print("Sync 2 stdout:\n", res2.stdout)
print("Sync 2 stderr:\n", res2.stderr)

print("3. Restarting worker_validator container...")
cmd3 = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    f"root@{new_ip}",
    "docker restart worker_validator"
]
res3 = subprocess.run(cmd3, capture_output=True, text=True)
print("Restart stdout:\n", res3.stdout)
