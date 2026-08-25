import logging
from datetime import datetime

class KeywordFrequencyService:
    def __init__(self, db_helper):
        self.db_helper = db_helper
        self.tracked_keywords = [
            "VIP", "Premium", "اشتراك", "اشتراكات", "باقات", 
            "إدارة حسابات", "نسخ تداول", "نسخ صفقات", 
            "USDT", "Binance", "WhatsApp", "Website",
            "تحليل العملات", "توصيات كريبتو", "بيتكوين", "صفقات سكالبينج", "منصة بينانس", 
            "Whale Alert", "Liquidation", "SMC Crypto", "Binance Futures", "تداول الكريبتو",
            "تحليل SMC", "كورس ICT", "سمارت موني", "اوردر بلوك", "Order Block عربي",
            "سيولة التداول", "Liquidity كريبتو", "تداول SMC", "مفهوم ICT", "هندسة السيولة",
            "Fair Value Gap", "FVG فوركس", "توصيات SMC", "صفقات ICT",
            "فوركس عرب", "عرب فوركس", "تداول العملات مصر", "فوركس الخليج", "عرب تداول",
            "مدرسة التداول", "المتداول العربي", "ديوان التداول", "عالم الفوركس", "ديلي فوركس",
            "توصيات Binance", "مستقبل الكريبتو", "إشارات كريبتو", "حيتان الكريبتو", "Whale Alert عربي",
            "صفقات فيوتشر", "Binance Futures عربي", "توصيات SOL", "تحليل BTC",
            "جروب VIP فوركس", "توصيات VIP مجانية", "Premium Signals كريبتو", "قناة اشتراك فوركس",
            "اشارات ذهب VIP", "توصيات مدفوعة", "VIP Crypto Trading",
            "إدارة حسابات فوركس", "ادارة حسابات تداول", "Copy Trading عربي",
            "حسابات ممولة", "شركات التمويل فوركس", "Funded Accounts عربي", "تحدي شركة تمويل",
            "تداول باير", "دفع USDT بينانس"
        ]

    def analyze_and_update(self, channel_id: str, title: str, description: str, recent_messages: list) -> dict:
        """
        Reads channel title, description, and recent messages, counts frequencies,
        and upserts the counts to the channel_keywords table in the database.
        """
        self.db_helper.check_connection()
        
        # Compile all text
        message_texts = [msg.text for msg in recent_messages if msg.text]
        combined_text = f"{title or ''} {description or ''} " + " ".join(message_texts)
        combined_text_lower = combined_text.lower()
        
        keyword_freqs = {}
        for kw in self.tracked_keywords:
            keyword_freqs[kw] = combined_text_lower.count(kw.lower())
            
        logging.info(f"Keyword Frequency Scan results for channel {channel_id}: {keyword_freqs}")
        
        # Upsert keyword frequencies to DB (Increment count on conflict)
        query = """
        INSERT INTO channel_keywords (channel_id, keyword, frequency, last_updated)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (channel_id, keyword) 
        DO UPDATE SET 
            frequency = channel_keywords.frequency + EXCLUDED.frequency,
            last_updated = CURRENT_TIMESTAMP;
        """
        
        try:
            with self.db_helper.conn.cursor() as cur:
                for kw, freq in keyword_freqs.items():
                    cur.execute(query, (channel_id, kw, freq))
            logging.info(f"Keyword Frequency Engine successfully updated DB records for channel {channel_id}")
        except Exception as e:
            logging.error(f"Error updating keyword frequencies for channel {channel_id}: {e}")
            
        return keyword_freqs
