import subprocess

ssh_cmd = [
    "ssh", "-o", "StrictHostKeyChecking=no",
    "-i", r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem",
    "ubuntu@63.178.198.95",
    "sudo docker exec -i leadhunter_postgres psql -U postgres -d leadhunter_db -A -F ',' -c \"SELECT channel_username, is_group, member_count, lead_score, tier, status, language, website, whatsapp, contact_username, description FROM leads ORDER BY is_group DESC, lead_score DESC NULLS LAST;\""
]

print("Connecting to 63.178.198.95...")
res = subprocess.run(ssh_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
if res.returncode != 0:
    print(f"SSH Error: {res.stderr}")
else:
    output = res.stdout.strip()
    lines = output.splitlines()
    print(f"Total lines received from DB: {len(lines)}")
    
    # Save raw CSV
    csv_path = r"c:\Users\NV LAP\Downloads\Phone Link\Channels-grapping\all_discovered_telegram_groups_and_channels.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(output)
    print(f"CSV successfully written to {csv_path}!")
