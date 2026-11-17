import os
import sys
import re
import psycopg2
from psycopg2.extras import RealDictCursor
import json

# Compile Regex Patterns for High-Precision Detection
RE_VIP = re.compile(
    r'\b(vip|v\.i\.p|vip\s*signals?|vip\s*channel)\b|قناة\s*(vip|خاصة|الخاصة|مدفوعة)|القناة\s*الخاصة|جروب\s*vip|اشتراك\s*vip|عضوية\s*خاصة|قناة\s*vip\s*المجانية|قناتنا\s*الخاصة',
    re.IGNORECASE
)

RE_ACCT_MGMT = re.compile(
    r'(إدارة|ادارة)\s*(حسابات|محافظ|المحافظ|الحسابات)|portfolio\s*management|ربط\s*حساب(ك|ات)?|نسخ\s*صفقات|نسخ\s*الصفقات|copy\s*trad(e|ing)|تداول\s*آلي|بوت\s*نسخ',
    re.IGNORECASE
)

RE_SUBSCRIPTION = re.compile(
    r'اشتراك|اشتراكات|رسوم\s*اشتراك|باقة\s*(شهرية|سنوية)|باقات|اشتراك\s*(شهري|سنوي)|مدفوع(ة)?|سعر\s*رمزي|عرض\s*خاص|خصم\s*خاص|انضمام\s*للقناة\s*الخاصة',
    re.IGNORECASE
)

RE_FOREX_SIGNALS = re.compile(
    r'\b(xauusd|gold|ذهب|الذهب|دهب|فوركس|forex|تداول|توصيات|صفقات|تحليل\s*فني|ستوب|وقف\s*الخسارة|take\s*profit|stop\s*loss|eurusd|gbpusd|us30|nasdaq|ناسداك)\b',
    re.IGNORECASE
)

# Non-Forex / Noise Patterns to Demote or Disqualify
RE_NON_FOREX = re.compile(
    r'ملابس|فساتين|أحذية|عطور|بضاعة|متجر|شوب|تسوق|سوق\s*الاسهم\s*السعودي|تاسي|tasi|بورس|سهام|ایران|بورس\s*ایران|نرم\s*افزار|فیلم|مسلسل|اغاني|طبخ|مكياج|عناية|كازينو|رهان|1xbet',
    re.IGNORECASE
)

JUNK_HANDLES = {
    'https', 'http', 'none', 'null', 'admin', 'support', 'bot', 'channel',
    'group', 'chat', 'contact', 'info', 'username', 'telegram', 'spambot',
    'joinchat', 'addlist', 'share', 'test'
}

def clean_contact(raw_contact: str, channel_username: str) -> str:
    if not raw_contact:
        return ""
    c = str(raw_contact).strip().lstrip('@').lower()
    ch = str(channel_username).strip().lstrip('@').lower()
    if not c or c == ch or c in JUNK_HANDLES:
        return ""
    if c.isdigit() or len(c) < 4 or len(c) > 32:
        return ""
    if not re.match(r'^[a-zA-Z0-9_]+$', c):
        return ""
    return c

def extract_contact_from_text(text: str, channel_username: str) -> str:
    if not text:
        return ""
    # Find all mentions
    mentions = re.findall(r'@([a-zA-Z0-9_]{4,32})', text)
    ch = str(channel_username).strip().lstrip('@').lower()
    
    # Priority keywords in line
    lines = text.split('\n')
    for line in lines:
        l_lower = line.lower()
        if any(k in l_lower for k in ["تواصل", "للاشتراك", "للحجز", "راسل", "إدارة", "ادارة", "الدعم", "خدمة العملاء", "admin", "owner", "contact"]):
            line_mentions = re.findall(r'@([a-zA-Z0-9_]{4,32})', line)
            for m in line_mentions:
                cleaned = clean_contact(m, ch)
                if cleaned and not cleaned.endswith('bot'):
                    return cleaned

    for m in mentions:
        cleaned = clean_contact(m, ch)
        if cleaned and not cleaned.endswith('bot'):
            return cleaned
    return ""

def main():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "leadhunter_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "leadhunter_pass")
    )
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Get active campaign
        cur.execute("SELECT id FROM campaigns ORDER BY created_at DESC LIMIT 1;")
        camp = cur.fetchone()
        if not camp:
            print("No active campaign found!")
            return
        camp_id = camp['id']
        print(f"Target Campaign ID: {camp_id}")
        
        # Fetch all pending campaign logs
        cur.execute("""
            SELECT cl.id as log_id, cl.lead_id, cl.priority as current_priority,
                   l.channel_username, l.title, l.contact_username, l.description,
                   l.forex_category, l.member_count
            FROM campaign_logs cl
            JOIN leads l ON l.id = cl.lead_id
            WHERE cl.campaign_id = %s
              AND cl.status IN ('pending', 'pending_review', 'approved')
        """, (camp_id,))
        rows = cur.fetchall()
        print(f"Total rows fetched for evaluation: {len(rows)}")

    # Step 1: Detect multi-channel spam contacts (> 5 channels)
    contact_counts = {}
    for r in rows:
        c = clean_contact(r['contact_username'], r['channel_username'])
        if c:
            contact_counts[c] = contact_counts.get(c, 0) + 1

    spam_contacts = {c for c, count in contact_counts.items() if count > 5}
    print(f"Detected {len(spam_contacts)} multi-channel repeated contacts (e.g., @FFILSVIP82 count={contact_counts.get('ffilsvip82', 0)})")

    # Step 2: Evaluate and categorize every lead
    updates = []
    stats = {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "skipped": 0}
    seen_contacts = set()

    for r in rows:
        log_id = r['log_id']
        lead_id = r['lead_id']
        ch_user = r['channel_username'] or ''
        title = r['title'] or ''
        desc = r['description'] or ''
        full_text = f"{title} {desc}"
        
        # Resolve contact
        contact = clean_contact(r['contact_username'], ch_user)
        if not contact:
            # Try to extract from description
            contact = extract_contact_from_text(desc, ch_user)

        # Check spam network
        is_spam_network = (contact.lower() in spam_contacts) if contact else False
        
        # Check non-forex noise
        is_non_forex = bool(RE_NON_FOREX.search(full_text))

        # Check forex and commercial signals
        has_vip = bool(RE_VIP.search(full_text))
        has_acct_mgmt = bool(RE_ACCT_MGMT.search(full_text))
        has_sub = bool(RE_SUBSCRIPTION.search(full_text))
        has_forex = bool(RE_FOREX_SIGNALS.search(full_text))

        # Decision Logic
        if not contact or is_spam_network or is_non_forex or contact.isdigit():
            # Skip junk, spam networks, or channels without any valid contact
            status = 'skipped'
            priority = 'P4'
            score = 10
            if not contact:
                reason = "Not eligible: Empty or invalid contact username"
            elif is_spam_network:
                reason = f"Skipped: Multi-channel spam network contact (@{contact})"
            else:
                reason = "Skipped: Non-Forex / E-commerce / Persian / Noise channel"
            stats["skipped"] += 1

        elif contact.lower() in seen_contacts:
            # Duplicate contact in the same campaign batch
            status = 'skipped'
            priority = 'P4'
            score = 15
            reason = f"Skipped (Dup): Contact @{contact} already enqueued in higher priority lead"
            stats["skipped"] += 1

        else:
            seen_contacts.add(contact.lower())

            # Tier P0: Hardcore Commercial Forex (VIP Private Channel / Account Management / Paid Subscription)
            if has_forex and (has_vip or has_acct_mgmt or has_sub):
                status = 'approved'
                priority = 'P0'
                score = 98 if (has_acct_mgmt or has_vip) else 95
                reasons = []
                if has_vip: reasons.append("VIP Private Channel")
                if has_acct_mgmt: reasons.append("Account Management (إدارة حسابات)")
                if has_sub: reasons.append("Paid Subscription (اشتراك)")
                reason = f"Prime Target [P0]: Explicit {' + '.join(reasons)} with verified owner contact (@{contact})."
                stats["P0"] += 1

            # Tier P1: Active Forex & Gold Signals / Trade Setups
            elif has_forex:
                status = 'approved'
                priority = 'P1'
                score = 88
                reason = f"High-Value Forex [P1]: Active Forex/Gold signals & analysis setup with verified contact (@{contact})."
                stats["P1"] += 1

            # Tier P2: Standard / General Trading Community
            elif any(k in full_text.lower() for k in ["تداول", "عملات", "كريبتو", "crypto", "trading", "أسواق"]):
                status = 'pending_review'
                priority = 'P2'
                score = 70
                reason = f"Standard Trading [P2]: General trading / crypto community with verified contact (@{contact})."
                stats["P2"] += 1

            else:
                status = 'pending_review'
                priority = 'P3'
                score = 40
                reason = f"Low Intent [P3]: Minimal trading indicators."
                stats["P3"] += 1

        updates.append({
            "log_id": log_id,
            "lead_id": lead_id,
            "contact_username": contact,
            "status": status,
            "priority": priority,
            "priority_score": score,
            "priority_reason": reason,
            "forex_category": "vip_services" if has_vip else ("account_management" if has_acct_mgmt else ("forex_signals" if has_forex else r['forex_category']))
        })

    print("\n" + "=" * 60)
    print("SIMULATION / RE-RANKING SUMMARY")
    print("=" * 60)
    print(f"Total Evaluated: {len(updates)}")
    print(f"  P0 (Prime VIP / Acct Mgmt / Subscription): {stats['P0']} (Marked APPROVED)")
    print(f"  P1 (Active Forex Signals & Setups):        {stats['P1']} (Marked APPROVED)")
    print(f"  P2 (Standard Trading Community):           {stats['P2']} (Marked PENDING_REVIEW)")
    print(f"  P3 (Low Intent / Informational):           {stats['P3']} (Marked PENDING_REVIEW)")
    print(f"  Skipped (Spam Networks, Non-Forex, Dups):  {stats['skipped']} (Marked SKIPPED)")

    # Execute DB Updates in Batches
    print("\nApplying updates to PostgreSQL database...")
    with conn.cursor() as cur:
        for u in updates:
            # Update leads contact if newly resolved
            if u["contact_username"]:
                cur.execute("""
                    UPDATE leads SET
                        contact_username = COALESCE(NULLIF(contact_username, ''), %s),
                        outreach_priority = %s,
                        outreach_priority_score = %s,
                        outreach_priority_reason = %s,
                        forex_category = COALESCE(%s, forex_category),
                        outreach_priority_updated_at = NOW()
                    WHERE id = %s;
                """, (u["contact_username"], u["priority"], u["priority_score"], u["priority_reason"], u["forex_category"], u["lead_id"]))
            else:
                cur.execute("""
                    UPDATE leads SET
                        outreach_priority = %s,
                        outreach_priority_score = %s,
                        outreach_priority_reason = %s,
                        outreach_priority_updated_at = NOW()
                    WHERE id = %s;
                """, (u["priority"], u["priority_score"], u["priority_reason"], u["lead_id"]))

            # Update campaign_logs status and priority
            cur.execute("""
                UPDATE campaign_logs SET
                    status = %s,
                    priority = %s,
                    priority_score = %s,
                    priority_reason = %s,
                    error_message = CASE WHEN %s = 'skipped' THEN %s ELSE error_message END
                WHERE id = %s;
            """, (u["status"], u["priority"], u["priority_score"], u["priority_reason"], u["status"], u["priority_reason"], u["log_id"]))

        conn.commit()
    print("All campaign_logs and leads updated successfully!")
    conn.close()

if __name__ == '__main__':
    main()
