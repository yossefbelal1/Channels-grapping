import paramiko
import traceback

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    ssh.connect('167.233.246.102', username='root', password='Ae9eM3H9wppv3cxaPibU', look_for_keys=False, allow_agent=False)
    print("SUCCESS CONNECTING!")
    stdin, stdout, stderr = ssh.exec_command("hostname; uptime")
    print(stdout.read().decode())
    ssh.close()
except Exception as e:
    print("ERROR:")
    traceback.print_exc()
