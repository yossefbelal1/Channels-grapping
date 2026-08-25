import paramiko

password = "Ae9eM3H9wppv3cxaPibU"
variations = [
    password,
    password.strip(),
    password + "\n",
    password + "\r\n"
]

for var in set(variations):
    try:
        print(f"Trying password repr: {repr(var)}")
        t = paramiko.Transport(('167.233.246.102', 22))
        t.connect()
        t.auth_password('root', var)
        print("SUCCESSFULLY AUTHENTICATED!")
        t.close()
        break
    except Exception as e:
        print("Failed:", e)
