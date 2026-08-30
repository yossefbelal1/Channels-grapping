import os
import sys
import time
import requests

token = os.getenv('GITHUB_TOKEN', '')
if not token:
    print("GITHUB_TOKEN not set.")
    sys.exit(0)

headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

repo = 'yossefbelal1/Channels-grapping'
url = f"https://api.github.com/repos/{repo}/actions/runs"

r = requests.get(url, headers=headers)
if r.status_code == 200:
    data = r.json()
    if data['workflow_runs']:
        latest = data['workflow_runs'][0]
        print(f"Latest run ID: {latest['id']}, status: {latest['status']}, conclusion: {latest['conclusion']}")
