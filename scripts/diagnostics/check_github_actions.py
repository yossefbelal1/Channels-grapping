import os
import requests
import sys
sys.stdout.reconfigure(encoding='utf-8')

token = os.getenv('GITHUB_TOKEN', '')
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

repo = 'yossefbelal1/Channels-grapping'
url = f'https://api.github.com/repos/{repo}/actions/runs'

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    runs = resp.json().get('workflow_runs', [])
    if runs:
        latest_run = runs[0]
        run_id = latest_run['id']
        print(f"Run ID: {run_id}")
        print(f"Status: {latest_run['status']}, Conclusion: {latest_run['conclusion']}")
        print(f"Commit: {latest_run['head_commit']['message']}")
        
        # Get jobs
        jobs_url = latest_run['jobs_url']
        jobs_resp = requests.get(jobs_url, headers=headers)
        if jobs_resp.status_code == 200:
            for job in jobs_resp.json().get('jobs', []):
                print(f"Job: {job['name']}, Conclusion: {job['conclusion']}")
                for step in job.get('steps', []):
                    print(f"  Step: {step['name']} -> {step.get('conclusion')}")
                    
        # Check logs if available
        logs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
        r = requests.get(logs_url, headers=headers)
        print("Jobs URL status:", r.status_code)
else:
    print(f"Error {resp.status_code}: {resp.text}")
