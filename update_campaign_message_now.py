import subprocess

key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
new_ip = "167.233.246.102"

new_message = """السلام عليكم. باختصار انا مدير اعلانات و تسويق قنوات فوركس. نوفر لك الوصول لجمهور حقيقي من المتداولين عبر شبكة تضم +100 قناة فوركس وأسواق مالية لزيادة تفاعل ونمو قناتك.

🎁 عرضك التجريبي الآن:
• 30 يوماً مجاناً بالكامل (بدون أي التزام مالي).
• 30$ فقط اشتراك شهري ثابت بعد انتهاء التجربة.
• أعضاء حقيقيون ومتداولون مستهدفون 100%.

🔹 خدماتنا لقناتك:
زوار ومتابعين متفاعلين | رفع مشاهدات المنشورات | خطة محتوى وتنظيم شامل للقناة.

✉️ لتفعيل الشهر المجاني اليوم:
أرسل رابط قناتك وسنتواصل معك فوراً: @tamerads1"""

# Escape single quotes for SQL
safe_message = new_message.replace("'", "''")

sql = f"UPDATE campaigns SET message_text = '{safe_message}' WHERE status = 'active';"

cmd = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    f"root@{new_ip}",
    f"docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c \"{sql}\""
]

res = subprocess.run(cmd, capture_output=True)
out = (res.stdout or b"").decode("utf-8", errors="replace")
err = (res.stderr or b"").decode("utf-8", errors="replace")
print("Result:", out)
if err:
    print("Stderr:", err)

# Verify the update
verify_cmd = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    f"root@{new_ip}",
    "docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c \"SELECT id, status, LEFT(message_text, 80) as msg_preview FROM campaigns WHERE status = 'active';\""
]

res2 = subprocess.run(verify_cmd, capture_output=True)
out2 = (res2.stdout or b"").decode("utf-8", errors="replace")
print("\nVerification:", out2)
