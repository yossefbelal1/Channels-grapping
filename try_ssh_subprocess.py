import subprocess
import time

cmd = [
    "ssh",
    "-o", "StrictHostKeyChecking=no",
    "-o", "PreferredAuthentications=password",
    "-o", "PubkeyAuthentication=no",
    "root@167.233.246.102",
    "echo LOGGED_IN_SUCCESSFULLY"
]

print("Executing SSH subprocess...")
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Give it 2 seconds to prompt for password
time.sleep(2)

print("Sending password...")
stdout, stderr = proc.communicate(input="Ae9eM3H9wppv3cxaPibU\n", timeout=10)

print("STDOUT:\n", stdout)
print("STDERR:\n", stderr)
