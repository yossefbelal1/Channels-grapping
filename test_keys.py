import paramiko

keys = [
    r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem",
    r"C:\Users\NV LAP\Downloads\youssef-key.pem"
]

for key_path in keys:
    try:
        print(f"Testing key: {key_path}")
        k = paramiko.RSAKey.from_private_key_file(key_path)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('167.233.246.102', username='root', pkey=k, timeout=5)
        print("SUCCESS with key:", key_path)
        stdin, stdout, stderr = ssh.exec_command("hostname && uptime")
        print(stdout.read().decode())
        ssh.close()
        break
    except Exception as e:
        print(f"Failed with key {key_path}: {e}")
