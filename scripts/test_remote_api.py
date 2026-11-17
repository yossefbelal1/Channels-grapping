import subprocess
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"

cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"root@{REMOTE_HOST}",
    "curl -s http://localhost:8000/api/discovered-24h?status=qualified"
]

res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
if res.returncode == 0 and res.stdout:
    try:
        data = json.loads(res.stdout)
        summary = data.get("summary", {})
        channels = data.get("channels", [])
        print("=== 24H DISCOVERY SUMMARY ===")
        print(f"Total Discovered: {summary.get('total_discovered')}")
        print(f"Qualified Count: {summary.get('qualified_count')}")
        print(f"Verified Count: {summary.get('verified_count')}")
        print(f"With Contact Count: {summary.get('with_contact_count')}")
        print(f"Qualified With Contact: {summary.get('qualified_with_contact_count')}")
        print(f"\nReturned Channels in Qualified Filter ({len(channels)}):")
        for ch in channels:
            u = ch.get("channel_username")
            m = ch.get("member_count")
            t = ch.get("tier")
            f_score = ch.get("forex_intent_score")
            c_score = ch.get("commercial_fit_score")
            v = ch.get("vip")
            ac = ch.get("account_management")
            cp = ch.get("copy_trading")
            cu = ch.get("contact_username") or ch.get("whatsapp")
            print(f"  @{u:25} | Mem: {str(m):6} | Tier: {str(t):7} | Forex: {str(f_score):3} | Comm: {str(c_score):3} | VIP: {str(v):5} | Mgmt: {str(ac):5} | Contact: {str(cu)}")
    except Exception as e:
        print("JSON Parse error:", e)
        print("Raw output:", res.stdout[:500])
else:
    print("Error running curl:", res.stderr)
