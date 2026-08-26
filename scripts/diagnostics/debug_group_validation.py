import asyncio
import os
import sys
import logging
import psycopg2
import redis
from dotenv import load_dotenv

sys.path.append('/app')
from tg_manager import TelegramManager
from validator import check_is_forex, calculate_forex_intent_score, classify_forex_category, count_word

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

async def main():
    load_dotenv()
    
    # Connect to Redis
    redis_conn = redis.Redis(host='redis', port=6379, db=0)
    
    # Initialize TG Manager
    tg_manager = TelegramManager(redis_conn, session_name="scavenger_session", worker_type="validator")
    await tg_manager.initialize_clients()
    
    usernames = ['usassnbuysell', 'selling', 'stoned']
    
    for username in usernames:
        print(f"\n==================================================")
        print(f"DEBUGGING Group: @{username}")
        print(f"==================================================")
        
        # 1. Resolve entity
        async def resolve(cl):
            return await cl.get_entity(username)
        
        try:
            entity = await tg_manager.execute_request("scavenger_session", resolve)
            title = entity.title
            description = entity.about or ""
            print(f"Title: {title}")
            print(f"Description: {description}")
            
            # 2. Fetch last 100 messages
            async def fetch_msgs(cl):
                return await cl.get_messages(entity, limit=100)
            
            messages = await tg_manager.execute_request("scavenger_session", fetch_msgs)
            print(f"Fetched {len(messages)} messages.")
            
            # 3. Print messages sample
            sample_texts = [m.text for m in messages if m.text]
            sample_text = " \n ".join(sample_texts)
            print(f"Sample Text Length: {len(sample_text)} characters")
            
            # 4. Check check_is_forex details
            text_lower = f"{title} {description} {sample_text}".lower()
            
            # Check absolute blacklist
            absolute_blacklist = [
                "دعم قنوات", "تبادل نشر", "زيادة متابعين", "زيادة أعضاء", "زيادة اعضاء",
                "تبادل قنوات", "تبادل اشتراكات", "لدعم القنوات", "ارسل رابط القناه",
                "ترويج قنوات", "اضافة اعضاء", "بوت اضافة", "اعضاء مجانا", "اعضاء مجاناً",
            ]
            print("\n--- Absolute Blacklist Hits ---")
            for bl in absolute_blacklist:
                hits = count_word(text_lower, bl)
                if hits > 0:
                    print(f"  - '{bl}': {hits}")
                    
            # Check High Confidence indicators
            high_confidence = [
                "forex", "فوركس", "xauusd", "eurusd", "gbpusd", "usdjpy", "audusd", "usdchf", "usdcad",
                "nzdusd", "gbpjpy", "eurjpy", "xagusd", "توصيات فوركس", "توصيات العملات", "توصيات الذهب",
                "تحليل الذهب", "تحليل فوركس", "تحليل العملات", "صفقات فوركس", "صفقات ذهب",
                "تداول العملات", "تداول الذهب", "تداول الفوركس", "نسخ صفقات", "نسخ تداول", "copy trading",
                "إدارة حسابات", "ادارة حسابات", "إدارة محافظ", "ادارة محافظ", "ادارة حسابات تداول",
                "حساب ممول", "funded account", "تمويل تداول", "حسابات ممولة", "تداول كريبتو", 
                "تداول بيتكوين", "crypto signals", "توصيات كريبتو", "بيتكوين", "صفقات سكالبينج", 
                "منصة بينانس", "whale alert", "liquidation", "smc crypto", "binance futures", 
                "تداول الكريبتو", "بينانس", "فيوتشر", "وسيط فوركس", "شركة تداول", "منصة تداول",
                "smc", "ict", "order block", "fvg", "fair value gap", "اوردر بلوك", "سمارت موني", 
                "سيولة التداول", "هندسة السيولة", "مفهوم ict", "توصيات smc", "صفقات ict",
                "فوركس عرب", "عرب فوركس", "وقف الخسارة", "stop loss", "take profit", "هدف الربح",
                "مناطق دعم ومقاومة", "دعم ومقاومة", "الموجات", "elliott wave"
            ]
            print("\n--- High Confidence Hits ---")
            for hc in high_confidence:
                hits = count_word(text_lower, hc)
                if hits > 0:
                    print(f"  - '{hc}': {hits}")
                    
            # Check General Marketplace Blacklist
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
            print("\n--- General Marketplace Blacklist Hits ---")
            for bl in general_marketplace_blacklist:
                hits = count_word(text_lower, bl)
                if hits > 0:
                    print(f"  - '{bl}': {hits}")

            # Check Medium confidence categories
            medium_groups = {
                'signals': ["توصية", "توصيات", "إشارات", "signals"],
                'price_action': ["شراء", "بيع", "buy", "sell", "long", "short", "سيولة"],
                'analysis': ["تحليل", "تحليلات", "analysis", "chart", "فجوة"],
                'trading': ["تداول", "trade", "trader", "trading"],
                'gold': ["الذهب", "gold", "ذهب"],
                'targets': ["هدف", "أهداف", "اهداف", "target", "tp"],
                'levels': ["نقطة", "نقاط", "مستوى", "مستويات", "level", "بلوك"],
                'orders': ["صفقة", "صفقات", "order", "position", "اوردر"],
                'risk': ["ستوب", "stop", "وقف", "خسارة", "risk"],
                'smc_ict': ["smc", "ict", "fvg", "order block", "سيولة", "اوردر", "بلوك", "فجوة"]
            }
            print("\n--- Medium Confidence Matches ---")
            matched_g = []
            for g_name, keywords in medium_groups.items():
                matched_kws = [kw for kw in keywords if kw in text_lower]
                if matched_kws:
                    print(f"  - Group '{g_name}': matched keywords {matched_kws}")
                    matched_g.append(g_name)
            print(f"Total Matched Groups: {len(matched_g)} (Requires >= 3 to be qualified)")
            
            # Check Niche Blacklist
            from validator import check_is_forex
            is_qualified = check_is_forex(text_lower, is_group=True)
            print(f"\ncheck_is_forex(combined_text, is_group=True) Result: {is_qualified}")
            
            # 5. Forex Intent Scoring breakdown
            print("\n--- Forex Intent Scoring Breakdown ---")
            contacts = {'website': '', 'email': '', 'whatsapp': '', 'contact_username': ''}
            intent_score = calculate_forex_intent_score(title, description, messages, contacts, "telegram_search")
            print(f"Calculated Forex Intent Score: {intent_score}")
            
        except Exception as e:
            print(f"Error checking group @{username}: {e}")
            
    # Disconnect
    for client in tg_manager.clients.values():
        if client.is_connected():
            await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
