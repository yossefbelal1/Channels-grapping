import subprocess
import os

new_ip = "167.233.246.102"
key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
local_dir = r"c:\Users\NV LAP\Downloads\Phone Link\Channels-grapping"
zip_path = r"c:\Users\NV LAP\Downloads\Phone Link\Channels-grapping\codebase_deploy.zip"

print("1. Zipping codebase...")
import zipfile

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(local_dir):
        # Exclude pycache and zip files
        if '__pycache__' in root or '.git' in root:
            continue
        for file in files:
            if file.endswith('.zip') or file.endswith('.sql'):
                continue
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, local_dir)
            zipf.write(abs_path, rel_path)

print("2. Uploading codebase_deploy.zip to new server...")
scp_cmd = [
    "scp", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    zip_path,
    f"root@{new_ip}:/root/codebase_deploy.zip"
]

res = subprocess.run(scp_cmd, capture_output=True, text=True)
if res.returncode != 0:
    print("SCP Error:", res.stderr)
else:
    print("Codebase zip uploaded successfully!")

print("3. Unzipping codebase on new server...")
unzip_cmd = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    f"root@{new_ip}",
    "apt install -y unzip && mkdir -p /root/Channels-grapping && unzip -o /root/codebase_deploy.zip -d /root/Channels-grapping/"
]

res_unzip = subprocess.run(unzip_cmd, capture_output=True, text=True)
print("Unzip stdout:\n", res_unzip.stdout)
print("Unzip stderr:\n", res_unzip.stderr)
