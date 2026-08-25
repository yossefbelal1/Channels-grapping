import psycopg2
import sys
sys.path.append('/app')

try:
    conn = psycopg2.connect("postgresql://postgres:leadhunter_pass@postgres/leadhunter_db")
    cur = conn.cursor()
    
    for username in ['ITradly', 'alskndry']:
        cur.execute("""
            SELECT channel_username, description, is_group, forex_intent_score, status 
            FROM leads 
            WHERE channel_username = %s
        """, (username,))
        row = cur.fetchone()
        if row:
            u, desc, is_group, forex, status = row
            print(f"@{u} details:")
            print(f"Is Group: {is_group}")
            print(f"Description: {desc}")
            print(f"Forex Intent: {forex}")
            print(f"Status: {status}")
            
            # Fetch posts
            cur.execute("SELECT message_text FROM channel_posts WHERE channel_username = %s ORDER BY timestamp DESC LIMIT 50", (u,))
            posts = cur.fetchall()
            print(f"Total posts: {len(posts)}")
            sample_text = " \n ".join([p[0] for p in posts if p[0]])
            print(f"Sample text snippet: {sample_text[:500]}")
            
            # Hits check
            general_marketplace_blacklist = [
                "fortnite", "pubg", "netflix", "spotify", "robux", "nitro", "giftcard", 
                "gift card", "gift cards", "steam key", "valorant", "free fire", "pubg mobile",
                "clash of clans", "clash royale", "game account", "game accounts", "game keys",
                "netflix", "spotify", "crunchyroll", "hulu", "disney+", "disney plus", "iptv",
                "حسابات فورت", "حسابات ببجي", "شدات ببجي", "شحن العاب", "شحن ألعاب", "حسابات ألعاب",
                "حسابات العاب", "فيزا وهمية", "حسابات نتفليكس", "اشتراكات نتفلكس", "نتفلكس", "نتفليكس",
                "توزيع حسابات", "حسابات مجانية", "حسابات مجانيه", "شراء حسابات", "بيع حسابات",
                "second hand", "used items", "أشياء مستعملة", "اشياء مستعمله", "سيارات مستعملة",
                "عقارات", "شقق للبيع", "شقة للبيع", "أراضي للبيع", "اراضي للبيع", "فلل للبيع",
                "clothes", "ملابس", "أزياء", "ازياء", "أحذية", "احذيه", "مستحضرات تجميل",
                "عطور", "perfume", "shoes", "bags", "شنط", "ساعات مستعملة", "ساعات مستعمله"
            ]
            text_lower = f"{u} {desc} {sample_text}".lower()
            print("Blacklist Hits:")
            for kw in general_marketplace_blacklist:
                cnt = text_lower.count(kw)
                if cnt > 0:
                    print(f"  - '{kw}': {cnt}")
            
except Exception as e:
    print(f"Error: {e}")
