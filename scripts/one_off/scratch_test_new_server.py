import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("Connecting to new server 167.233.246.102...")
    ssh.connect('167.233.246.102', username='root', password='Ae9eM3H9wppv3cxaPibU', timeout=10)
    print("SSH Connection successful!")
    
    stdin, stdout, stderr = ssh.exec_command("uname -a && uptime")
    print("Server info:", stdout.read().decode())
    
    ssh.close()
except Exception as e:
    print("Connection error:", str(e))
