import paramiko
import time

old_pass = "Ae9eM3H9wppv3cxaPibU"
new_pass = "Ae9eM3H9wppv3cxaPibU2026!" # New strong password for server root

trans = paramiko.Transport(('167.233.246.102', 22))
try:
    trans.connect(username='root', password=old_pass)
    print("Transport connect succeeded!")
except Exception as e:
    print("Transport connect failed:", e)

# Try channel request pty shell
try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    # Custom auth handler or transport channel
    session = trans.open_session()
    session.get_pty()
    session.invoke_shell()
    
    time.sleep(1)
    buf = ""
    if session.recv_ready():
        buf += session.recv(4096).decode('utf-8', errors='ignore')
    print("Buffer 1:\n", buf)
    
    # Send old pass / new pass
    session.send(old_pass + "\n")
    time.sleep(1)
    if session.recv_ready():
        buf += session.recv(4096).decode('utf-8', errors='ignore')
    print("Buffer 2:\n", buf)

    session.send(new_pass + "\n")
    time.sleep(1)
    if session.recv_ready():
        buf += session.recv(4096).decode('utf-8', errors='ignore')
    print("Buffer 3:\n", buf)

    session.send(new_pass + "\n")
    time.sleep(1)
    if session.recv_ready():
        buf += session.recv(4096).decode('utf-8', errors='ignore')
    print("Buffer 4:\n", buf)
    
    trans.close()
except Exception as e:
    print("Error:", e)
