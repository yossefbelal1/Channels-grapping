import paramiko

def handler(title, instructions, prompt_list):
    print("Prompts:", prompt_list)
    return ["Ae9eM3H9wppv3cxaPibU" for _ in prompt_list]

trans = paramiko.Transport(('167.233.246.102', 22))
try:
    trans.connect()
    print("Authenticating interactive...")
    trans.auth_interactive('root', handler)
    print("Auth interactive SUCCESS!")
    sess = trans.open_session()
    sess.exec_command("echo SUCCESS_SSH_HELO")
    print(sess.recv(1024).decode())
    trans.close()
except Exception as e:
    print("Interactive Auth Error:", e)
