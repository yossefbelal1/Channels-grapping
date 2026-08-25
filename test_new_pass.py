import paramiko

for password in ["Ae9eM3H9wppv3cxaPibU", "Ae9eM3H9wppv3cxaPibU2026!"]:
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print(f"Testing password: {password}")
        ssh.connect('167.233.246.102', username='root', password=password, timeout=5, look_for_keys=False, allow_agent=False)
        print(f"SUCCESS with password: {password}")
        stdin, stdout, stderr = ssh.exec_command("hostname && uptime")
        print("Output:", stdout.read().decode())
        ssh.close()
        break
    except Exception as e:
        print(f"Failed with {password}: {e}")
