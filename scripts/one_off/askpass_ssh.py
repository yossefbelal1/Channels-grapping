import os
import subprocess
import sys

# Write helper askpass script
askpass_script = os.path.abspath("pass_helper.bat")
with open(askpass_script, "w") as f:
    f.write("@echo Ae9eM3H9wppv3cxaPibU\n")

env = os.environ.copy()
env["SSH_ASKPASS"] = askpass_script
env["SSH_ASKPASS_REQUIRE"] = "force"
env["DISPLAY"] = ":0"

cmd = [
    "ssh",
    "-o", "StrictHostKeyChecking=no",
    "root@167.233.246.102",
    "hostname && uptime"
]

print("Running ssh with SSH_ASKPASS...")
res = subprocess.run(cmd, env=env, capture_output=True, text=True)
print("STDOUT:\n", res.stdout)
print("STDERR:\n", res.stderr)
print("Returncode:", res.returncode)
