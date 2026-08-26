import urllib.request
import json

endpoints = [
    "/",
    "/api/campaigns",
    "/api/leads?minScore=10&arabicOnly=true",
    "/api/group_metrics",
    "/api/discovery_stats",
    "/api/quality_stats",
    "/api/leaderboards",
    "/api/graph/stats",
    "/api/graph/network"
]

print("=== TESTING ALL DASHBOARD ENDPOINTS ===")
all_pass = True
for ep in endpoints:
    url = f"http://localhost:8000{ep}"
    try:
        req = urllib.request.urlopen(url)
        content = req.read()
        print(f"✅ {ep:45} -> Status: {req.status} OK | Size: {len(content)} bytes")
    except Exception as e:
        all_pass = False
        print(f"❌ {ep:45} -> ERROR: {e}")

if all_pass:
    print("\n🎉 ALL 9 ENDPOINTS PASSED WITH 100% SUCCESS!")
