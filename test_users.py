import paramiko

users = ["root", "teleauto", "kamel", "ubuntu", "admin"]
password = "Ae9eM3H9wppv3cxaPibU"

for user in users:
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print(f"Testing user: {user}")
        ssh.connect('167.233.246.102', username=user, password=password, timeout=4, look_for_keys=False, allow_agent=False)
        print(f"SUCCESS with user: {user}!")
        stdin, stdout, stderr = ssh.exec_command("whoami && hostname")
        print("Output:", stdout.read().decode())
        ssh.close()
        break
    except Exception as e:
        print(f"Failed user {user}: {e}")
