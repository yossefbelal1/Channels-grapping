import requests
import json

r = requests.get("http://127.0.0.1:8000/api/campaigns")
data = r.json()
if data.get("success"):
    print("Campaign Summary Object:")
    print(json.dumps(data["campaigns"][0], indent=2))
else:
    print("Error:", data.get("error"))
