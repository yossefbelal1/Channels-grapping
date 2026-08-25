import os

root_dir = "c:/Users/NV LAP/Downloads/Phone Link/Channels-grapping"

for dirpath, _, filenames in os.walk(root_dir):
    for f in filenames:
        if f.endswith(('.py', '.html', '.js', '.txt', '.json')):
            filepath = os.path.join(dirpath, f)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()
                    if "My_channels" in content or "المجلدات المخصصة" in content or "إحصائيات المزامنة" in content:
                        print(f"Found in {filepath}")
            except Exception as e:
                pass
