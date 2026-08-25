import paramiko
import logging

logging.basicConfig(level=logging.DEBUG)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    ssh.connect('167.233.246.102', port=22, username='root', password='Ae9eM3H9wppv3cxaPibU', timeout=10)
    print("SUCCESS")
except Exception as e:
    print("FAILED:", e)
