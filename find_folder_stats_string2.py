import os

root_dir = "c:/Users/NV LAP/Downloads/Phone Link/Channels-grapping"

for dirpath, _, filenames in os.walk(root_dir):
    for f in filenames:
        if f.endswith(('.py', '.html', '.js', '.txt', '.json', '.md')):
            filepath = os.path.join(dirpath, f)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()
                    if "المجلدات" in content or "My_channels1" in content or "إحصائيات" in content or "No_Post" in content:
                        print(f"Found in {filepath}")
                        # Print matching lines
                        for line in content.splitlines():
                            if any(k in line for k in ["المجلدات", "My_channels1", "No_Post", "My_channels3"]):
                                print(f"   -> {line.strip()[:100]}")
            except Exception as e:
                pass
