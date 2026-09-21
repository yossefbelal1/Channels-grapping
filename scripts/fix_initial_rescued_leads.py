import psycopg2
from psycopg2.extras import RealDictCursor

import os

DB_PARAMS = {
    'dbname': os.getenv('DB_NAME', 'leadhunter_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'leadhunter_pass'),
    'host': os.getenv('DB_HOST', 'postgres'),
    'port': int(os.getenv('DB_PORT', '5432'))
}

RESCUED = [
    {
        'channel': 'lilyforex11',
        'title': '⚜KING SNIPER FX⚜',
        'contact': 'KING_1FUTUR1',
        'members': 5483,
        'tier': 'Tier_B',
        'priority': 'P1',
        'score': 95,
        'desc': 'قناة توصيات فيوتشر وفوركس ومتابعة خاصة'
    },
    {
        'channel': 'MissGold21',
        'title': '👑𝑺𝑼𝑳𝑻𝑨𝑵𝑨_𝑭𝑿🥇',
        'contact': 'SULTANA_1_FX',
        'members': 3913,
        'tier': 'Tier_B',
        'priority': 'P1',
        'score': 95,
        'desc': 'قناة توصيات الذهب والعملات - الخاص @SULTANA_1_FX'
    },
    {
        'channel': 'private_2337975166',
        'title': 'MBA Gold Forex🏦💵🥇❤️‍🔥',
        'contact': 'Sultan1gold',
        'members': 15553,
        'tier': 'Tier_A',
        'priority': 'P0',
        'score': 99,
        'desc': 'A very strong Forex signals channel specializing in gold, metals, and currencies'
    },
    {
        'channel': 'GorillaSignals0',
        'title': 'Gorilla Trading',
        'contact': 'masrawystrategiess',
        'members': 13875,
        'tier': 'Tier_A',
        'priority': 'P0',
        'score': 99,
        'desc': 'توصيات مجانية ومنشورات تعليمية حول التداول في سوق الفوركس'
    },
    {
        'channel': 'gorillatrading0',
        'title': 'Gorilla Trading',
        'contact': 'masrawystrategiess',
        'members': 13875,
        'tier': 'Tier_A',
        'priority': 'P0',
        'score': 99,
        'desc': 'توصيات مجانية ومنشورات تعليمية حول التداول في سوق الفوركس'
    },
    {
        'channel': 'CryptoArabs1',
        'title': 'إشارات تداول كريبتو وفوركس | Crypto Arabs',
        'contact': 'KING_MISHAL10',
        'members': 2983,
        'tier': 'Tier_B',
        'priority': 'P1',
        'score': 95,
        'desc': 'إشارات فوركس مجانية يومية وتحليلات كريبتو وعملات رقمية'
    },
    {
        'channel': 'tqcharts',
        'title': 'أ. مصطفى عبدالقوي (القناة العامة للتوصيات)',
        'contact': 'mustafaabdulqawi',
        'members': 8079,
        'tier': 'Tier_B',
        'priority': 'P1',
        'score': 95,
        'desc': 'القناة العامة للتوصيات والتحليل الفني للداو جونز والذهب'
    },
    {
        'channel': 'forexomni',
        'title': 'Forexomni',
        'contact': 'forexomniadmin',
        'members': 15503,
        'tier': 'Tier_A',
        'priority': 'P0',
        'score': 99,
        'desc': 'Vip signals and Analysis on Major and Minor currency, Stocks and Commodities'
    }
]

def main():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print(f"=== Applying Hotfix for {len(RESCUED)} Verified Forex Leads ===")
    for item in RESCUED:
        ch = item['channel']
        contact = item['contact']
        title = item['title']
        members = item['members']
        tier = item['tier']
        priority = item['priority']
        score = item['score']
        desc = item['desc']
        
        # 1. Update leads table
        cur.execute("""
            UPDATE leads
            SET title = %s,
                contact_username = %s,
                admin_username = %s,
                member_count = GREATEST(member_count, %s),
                tier = %s,
                outreach_priority = %s,
                outreach_priority_score = %s,
                outreach_priority_reason = %s,
                forex_intent_score = 95,
                lead_score = 95,
                status = 'new',
                description = CASE WHEN description LIKE 'Inactive%%' OR description IS NULL OR description = '' THEN %s ELSE description END,
                last_scan = NOW()
            WHERE channel_username ILIKE %s
            RETURNING id, channel_username;
        """, (title, contact, contact, members, tier, priority, score, f"Deep Scan Verified: @{contact}", desc, ch))
        
        updated_leads = cur.fetchall()
        print(f"[{ch}] Updated {len(updated_leads)} lead rows -> Contact: @{contact}")
        
        for lead in updated_leads:
            lead_id = lead['id']
            # 2. Update campaign_logs to approved
            cur.execute("""
                UPDATE campaign_logs
                SET status = 'approved',
                    priority = %s,
                    priority_score = %s,
                    priority_reason = %s,
                    eligibility = 'ELIGIBLE',
                    error_message = NULL,
                    last_error = NULL,
                    account_used = NULL,
                    sent_at = NULL
                WHERE lead_id = %s;
            """, (priority, score, f"Deep Scan Verified: @{contact}", lead_id))
            print(f"  -> campaign_logs updated to 'approved' ({priority}) for lead {lead_id}")
            
    conn.commit()
    cur.close()
    conn.close()
    print("=== Hotfix Completed Successfully! ===")

if __name__ == '__main__':
    main()
