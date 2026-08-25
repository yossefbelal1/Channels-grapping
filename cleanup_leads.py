import psycopg2
import re
from datetime import datetime, timezone
import sys

# Add current path to import validator
sys.path.append('/app')
from validator import check_is_forex, calculate_forex_intent_score, LeadValidator, classify_forex_category

class MockMessage:
    def __init__(self, text):
        self.text = text

def cleanup():
    conn = psycopg2.connect("postgresql://postgres:leadhunter_pass@postgres/leadhunter_db")
    cur = conn.cursor()
    
    # Reset status for genuine channels that were falsely rejected by early blacklist match
    cur.execute("""
        UPDATE leads 
        SET status = 'new' 
        WHERE channel_username IN ('ITradly', 'alskndry', 'ForexBreakingNews')
    """)
    conn.commit()
    print("Reset status of genuine channels back to 'new'.")
    
    # Fetch all non-rejected scanned leads
    cur.execute("""
        SELECT 
            id, channel_username, member_count, description, website, email, whatsapp, 
            contact_username, is_group, vip, premium, subscription, monthly_plans, 
            yearly_plans, account_management, copy_trading, funded_accounts, usdt_payments, 
            binance_payments, discovery_method, arabic_ratio, status, discovery_source,
            arabic_score, region_score
        FROM leads 
        WHERE status != 'rejected' AND last_scan IS NOT NULL
    """)
    rows = cur.fetchall()
    print(f"Total leads to process: {len(rows)}")
    
    rejected_count = 0
    updated_count = 0
    
    for row in rows:
        lead_id, username, member_count, description, website, email, whatsapp, \
        contact_username, is_group, vip, premium, subscription, monthly_plans, \
        yearly_plans, account_management, copy_trading, funded_accounts, usdt_payments, \
        binance_payments, discovery_method, arabic_ratio, current_status, discovery_source, \
        arabic_score, region_score = row
        
        description = description or ""
        
        # 1. Fetch messages from database to compile sample text
        cur.execute("""
            SELECT message_text 
            FROM channel_posts 
            WHERE channel_username = %s 
            ORDER BY timestamp DESC 
            LIMIT 50
        """, (username,))
        posts = cur.fetchall()
        
        messages = [MockMessage(p[0]) for p in posts if p[0]]
        sample_text = " \n ".join([m.text for m in messages])
        combined_text = f"{username} {description} {sample_text}".lower()
        
        # 2. Check if it passes check_is_forex niche check
        is_forex_qualified = check_is_forex(combined_text, is_group=is_group)
        
        # 3. Calculate forex intent score
        contacts = {
            'website': website,
            'email': email,
            'whatsapp': whatsapp,
            'contact_username': contact_username
        }
        forex_intent_score = calculate_forex_intent_score(
            username, description, messages, contacts, discovery_method
        )
        
        # 4. Check gate qualification
        passes = False
        new_score = 0
        new_tier = 'Tier_D'
        
        if is_group:
            # Group Gate: hits check AND forex intent >= 35 AND arabic_score >= 50
            is_group_forex = is_forex_qualified and forex_intent_score >= 35 and arabic_score >= 50
            if is_group_forex:
                passes = True
                # Fetch group metrics to compute mkt_score
                cur.execute("SELECT messages_scanned, mentions_count, telegram_links_count, advertisements_count, marketplace_score FROM group_metrics WHERE group_id = %s", (lead_id,))
                metric_row = cur.fetchone()
                if metric_row:
                    new_score = metric_row[4] # marketplace_score
                else:
                    new_score = 50 # Default fallback score
                new_tier = LeadValidator.classify_tier(None, new_score)
        else:
            # Broadcast Channel Gate
            if is_forex_qualified:
                # Fetch keyword frequencies
                cur.execute("SELECT keyword, frequency FROM channel_keywords WHERE channel_id = %s", (lead_id,))
                kw_rows = cur.fetchall()
                kw_freqs = {r[0]: r[1] for r in kw_rows}
                
                # Fetch incoming links (in_degree)
                cur.execute("SELECT COUNT(*) FROM channel_graph WHERE target_channel_id = %s", (lead_id,))
                in_degree = cur.fetchone()[0]
                
                # Build metadata dict
                arabic_regex = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
                title_has_arabic = bool(arabic_regex.search(username))
                desc_has_arabic = bool(arabic_regex.search(description))
                high_arabic_ratio = (arabic_ratio > 80)
                whatsapp_num = whatsapp or ''
                is_gulf_whatsapp = any(whatsapp_num.startswith(prefix) for prefix in ["+966", "+971", "+965", "+968", "+973", "+962"])
                
                metadata = {
                    'member_count': member_count,
                    'website': website,
                    'contact_username': contact_username,
                    'whatsapp': whatsapp,
                    'is_arabic': (arabic_ratio > 60),
                    'arabic_ratio': arabic_ratio,
                    'recent_activity': True,
                    'active_posting': True,
                    'vip': vip,
                    'premium': premium,
                    'subscription': subscription,
                    'monthly_plans': monthly_plans,
                    'yearly_plans': yearly_plans,
                    'account_management': account_management,
                    'copy_trading': copy_trading,
                    'funded_accounts': funded_accounts,
                    'usdt_payments': usdt_payments,
                    'binance_payments': binance_payments,
                    'title_has_arabic': title_has_arabic,
                    'desc_has_arabic': desc_has_arabic,
                    'high_arabic_ratio': high_arabic_ratio,
                    'is_gulf_whatsapp': is_gulf_whatsapp,
                    'forex_intent_score': forex_intent_score
                }
                
                new_score = LeadValidator.calculate_weighted_score(None, metadata, kw_freqs, in_degree)
                new_tier = LeadValidator.classify_tier(None, new_score)
                
                passes = (new_score >= 50 and forex_intent_score >= 40)
        
        if not passes:
            # Reject lead
            print(f"[-] Rejecting @{username} (Group: {is_group}) | New Score: {new_score} | Forex Score: {forex_intent_score}")
            cur.execute("""
                UPDATE leads 
                SET status = 'rejected', lead_score = 0, tier = 'Tier_D', forex_intent_score = %s 
                WHERE id = %s
            """, (forex_intent_score, lead_id))
            rejected_count += 1
        else:
            # Keep and update lead
            print(f"[+] Keeping @{username} (Group: {is_group}) | New Score: {new_score} | Forex Score: {forex_intent_score}")
            cur.execute("""
                UPDATE leads 
                SET lead_score = %s, tier = %s, forex_intent_score = %s 
                WHERE id = %s
            """, (new_score, new_tier, forex_intent_score, lead_id))
            updated_count += 1
            
    conn.commit()
    cur.close()
    conn.close()
    
    print("="*60)
    print(f"Cleanup finished! Rejected: {rejected_count} | Updated: {updated_count}")

if __name__ == '__main__':
    cleanup()
