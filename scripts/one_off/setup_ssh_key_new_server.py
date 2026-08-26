import paramiko

key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
rsa_key = paramiko.RSAKey.from_private_key_file(key_path)
pub_key_str = f"ssh-rsa {rsa_key.get_base64()} telegram-saas-key"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('167.233.246.102', username='root', password='TeleAuto2026Secure!', look_for_keys=False, allow_agent=False)

cmd = f"""
mkdir -p /root/.ssh
chmod 700 /root/.ssh
grep -qF "{pub_key_str}" /root/.ssh/authorized_keys 2>/dev/null || echo "{pub_key_str}" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
"""

stdin, stdout, stderr = ssh.exec_command(cmd)
print("Authorized keys updated:", stdout.read().decode())
print("Errors if any:", stderr.read().decode())
ssh.close()

# Test connecting with the key!
try:
    ssh2 = paramiko.SSHClient()
    ssh2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh2.connect('167.233.246.102', username='root', pkey=rsa_key, timeout=5)
    print("KEY-BASED SSH LOGIN TEST: SUCCESS!")
    ssh2.close()
except Exception as e:
    print("Key login test error:", e)
