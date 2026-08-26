import socket

ip = "167.233.246.102"
for port, name in [(6379, "Redis"), (5432, "PostgreSQL"), (8000, "Dashboard"), (22, "SSH")]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect((ip, port))
        print(f"[{name}] Port {port}: OPEN (Accessible)")
        s.close()
    except Exception as e:
        print(f"[{name}] Port {port}: BLOCKED / SECURED ({e})")
