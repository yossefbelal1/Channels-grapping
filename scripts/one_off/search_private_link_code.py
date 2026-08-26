import os
import re

def search_files(dir_path):
    for root, dirs, files in os.walk(dir_path):
        for f in files:
            if f.endswith('.py'):
                p = os.path.join(root, f)
                try:
                    with open(p, 'r', encoding='utf-8', errors='ignore') as file:
                        content = file.read()
                        if 'ImportChatInviteRequest' in content or 'CheckChatInviteRequest' in content or 'joinchat' in content or 'ImportChat' in content:
                            print(f"\n=== FILE: {p} ===")
                            lines = content.split('\n')
                            for idx, line in enumerate(lines, 1):
                                if any(k in line for k in ['ImportChatInviteRequest', 'CheckChatInviteRequest', 'joinchat', 'ImportChat']):
                                    print(f"  Line {idx}: {line.strip()}")
                except Exception as e:
                    pass

search_files('.')
