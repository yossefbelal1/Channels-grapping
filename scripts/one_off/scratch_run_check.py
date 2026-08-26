import os
import subprocess

for line in open('.env'):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ[k] = v

subprocess.run(['python3', 'scratch_check_sessions.py'])
