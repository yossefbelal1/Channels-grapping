import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("Testing connection with new password...")
    ssh.connect('167.233.246.102', username='root', password='TeleAuto2026Secure!', timeout=10, look_for_keys=False, allow_agent=False)
    print("SSH SUCCESSFUL!")
    stdin, stdout, stderr = ssh.exec_command("hostname && uptime && uname -a")
    print("Output:\n", stdout.read().decode())
    ssh.close()
except Exception as e:
    print("ERROR:", e)
