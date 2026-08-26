with open("c:/Users/NV LAP/Downloads/Phone Link/Channels-grapping/dashboard.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "My_channels" in line or "My_Channels" in line or "المجلدات" in line or "discovery_stats" in line or "quality_stats" in line:
        print(f"Line {i+1}: {line.strip()}")
