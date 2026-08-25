import paramiko
import time

try:
    trans = paramiko.Transport(('167.233.246.102', 22))
    trans.connect(username='root', password='Ae9eM3H9wppv3cxaPibU')
    print("Transport connect succeeded!")
    session = trans.open_session()
    session.get_pty()
    session.invoke_shell()
    
    time.sleep(2)
    output = ""
    if session.recv_ready():
        output += session.recv(4096).decode('utf-8', errors='ignore')
    print("Shell Output 1:\n", output)
    
    trans.close()
except Exception as e:
    print("Error:", e)
