import socket

ip = "167.233.246.102"
port = 6379

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect((ip, port))
    print("WARNING: Redis port 6379 is STILL OPEN!")
    s.close()
except Exception as e:
    print(f"SUCCESS: Redis port 6379 is SECURED & BLOCKED! ({e})")
