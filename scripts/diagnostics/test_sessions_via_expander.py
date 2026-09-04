import paramiko
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

test_script = """
import os, asyncio
from telethon import TelegramClient
from telethon.errors import AuthKeyDuplicatedError, SessionPasswordNeededError

API_ID = int(os.getenv('API_ID', 39064636))
API_HASH = os.getenv('API_HASH', 'd873d6bb6c3e9a7e08922cfb94fa8ec5')
sessions_dir = '/app/sessions'

async def test_session(sname):
    spath = os.path.join(sessions_dir, sname)
    client = TelegramClient(spath, API_ID, API_HASH)
    try:
        await client.connect()
        authorized = await client.is_user_authorized()
        if authorized:
            me = await client.get_me()
            name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            print(f"[OK] {sname}: Authorized as @{me.username} ({name}, ID: {me.id})")
        else:
            print(f"[NOT AUTHORIZED] {sname}: Session is not logged in.")
    except AuthKeyDuplicatedError:
        print(f"[REVOKED] {sname}: AuthKeyDuplicatedError (session revoked by Telegram).")
    except Exception as e:
        print(f"[ERROR] {sname}: {type(e).__name__}: {e}")
    finally:
        await client.disconnect()

async def main():
    print("=== Testing All Telegram Sessions in /app/sessions ===")
    for f in sorted(os.listdir(sessions_dir)):
        if f.endswith('.session'):
            sname = f[:-8]
            await test_session(sname)

asyncio.run(main())
"""

cmd = f"docker exec -i worker_graph_expander python - << 'EOF'\n{test_script}\nEOF"
stdin, stdout, stderr = ssh.exec_command(cmd)
print(stdout.read().decode())
err = stderr.read().decode()
if err:
    print("Stderr:", err)

ssh.close()
