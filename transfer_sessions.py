import subprocess

old_ip = "63.178.198.95"
new_ip = "167.233.246.102"
key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"

print("Copying sessions directory from old server to new server...")
ssh_cmd = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    f"ubuntu@{old_ip}",
    f"rsync -avz -e 'ssh -o StrictHostKeyChecking=no -i /home/ubuntu/.ssh/id_rsa' /home/ubuntu/Channels-grapping/sessions/ root@{new_ip}:/root/Channels-grapping/sessions/"
]

res = subprocess.run(ssh_cmd, capture_output=True, text=True)
print("Rsync stdout:\n", res.stdout)
print("Rsync stderr:\n", res.stderr)
