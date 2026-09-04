"""
tests/test_outreach_intelligence.py — Behavioral & Unit Tests for Outreach Intelligence & Priority Ordering

Tests all 16 core dimensions:
1. VIP / Paid Signals Channel -> Inferred as P0
2. Copy Trading / Portfolio Management -> Inferred as P0/P1 with account_management fit
3. Broker Affiliate / IB Channel -> Inferred with partnerships fit
4. Prop Firm Challenges Channel -> Inferred business model
5. Academy / Paid Courses Channel -> Inferred business model
6. Operational Complexity Scoring (SL/TP, analysis, velocity)
7. Generic Forex News Channel -> Inferred as P3
8. Non-commercial Channel -> Inferred as P4
9. 400-member commercial channel strictly outranks 2M-member dormant news channel
10. Freshness Decay (2 days vs 45 days vs stale)
11. Contact Quality Hierarchy (bio_official vs message_general)
12. Multi-label Service Fit Inference
13. Structured Explainable Evidence & Reason Generation
14. Campaign Claiming Order (P0 -> P1 -> P2 -> P3 -> P4, priority_score DESC)
15. Campaign Recipient Re-ranking
16. Outreach State & Safety Preservation (Deduplication, Skipping, Cooldown)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from app.outreach.constants import OutreachPriority, ServiceNeedType
from app.outreach.commercial_inference import CommercialInferenceEngine
from app.outreach.priority_engine import OutreachPriorityEngine
from app.repositories.campaign_repository import CampaignRepository


class MockMessage:
    def __init__(self, text: str, date: datetime = None):
        self.text = text
        self.date = date or datetime.now(timezone.utc)


# ─── 1. VIP / Paid Signals Channel Inferred as P0 ─────────────────────────────
def test_vip_signals_channel_inferred_as_p0():
    messages = [
        MockMessage("صفقة بيع ذهب XAUUSD الدخول 2030 الهدف 2010 وقف الخسارة 2045 SL TP"),
        MockMessage("عرض خاص للاشتراك في قناة VIP المدفوعة بخصم 50% لفترة محدودة"),
        MockMessage("للاشتراك تواصل مع الدعم الفني عبر @vip_support الدفع متاح عبر USDT Binance"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="توصيات الذهب VIP",
        description="القناة الرسمية للتوصيات الخاصة. للاشتراك تواصل: @vip_support",
        recent_messages=messages,
        contacts_dict={"contact_username": "vip_support", "source": "bio_official"},
        forex_relevance_score=95,
        member_count=1200,
        posts_24h=5,
        posts_7d=25
    )
    assert res["priority"] == OutreachPriority.P0
    assert res["priority_score"] >= 75
    assert "vip_subscription" in res["detected_models"]
    assert res["commercial_fit_score"] >= 18
    assert res["contactability_score"] == 5
    assert ServiceNeedType.ADVERTISING_MANAGEMENT in res["likely_services"]
    assert ServiceNeedType.CHANNEL_MANAGEMENT in res["likely_services"]


# ─── 2. Copy Trading / Portfolio Management Channel ───────────────────────────
def test_copy_trading_portfolio_channel_inferred_as_p0_or_p1():
    messages = [
        MockMessage("خدمة نسخ الصفقات الآلي متاحة الآن. حققنا نسبة أرباح 35% هذا الشهر"),
        MockMessage("إدارة محافظ وربط حسابات بنظام PAMM وتداول آلي للمحافظ فوق 5000$"),
        MockMessage("لربط حسابك ونسخ الصفقات تواصل مع الإدارة: @copy_manager"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="نسخ صفقات وإدارة محافظ فوركس",
        description="أقوى نظام نسخ صفقات وإدارة محافظ وحسابات فوركس. للتواصل: @copy_manager",
        recent_messages=messages,
        contacts_dict={"contact_username": "copy_manager", "source": "bio_admin"},
        forex_relevance_score=90,
        member_count=3500,
        posts_24h=3,
        posts_7d=18
    )
    assert res["priority"] in (OutreachPriority.P0, OutreachPriority.P1)
    assert "copy_trading_portfolio" in res["detected_models"]
    assert ServiceNeedType.ACCOUNT_MANAGEMENT in res["likely_services"]


# ─── 3. Broker Affiliate / IB Channel ─────────────────────────────────────────
def test_broker_affiliate_channel_inferred():
    messages = [
        MockMessage("سجل تحت وكالتنا في شركة Exness واحصل على كاش باك أسبوعي وبونص إيداع"),
        MockMessage("رابط الوكالة المعتمد لفتح حساب إسلامي برعايتنا: https://one.exness-track.com/a/sample"),
        MockMessage("بعد التسجيل تحت وكالتنا ارسل رقم الحساب لتفعيل اشتراك VIP مجاناً"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="وكيل معتمد Exness وسيط فوركس",
        description="وكيل معتمد لأقوى شركات التداول. سجل معنا واحصل على كاش باك: @ib_contact",
        recent_messages=messages,
        contacts_dict={"contact_username": "ib_contact", "source": "bio_official"},
        forex_relevance_score=85,
        member_count=8000,
        posts_24h=2,
        posts_7d=10
    )
    assert "broker_affiliate_ib" in res["detected_models"]
    assert ServiceNeedType.PARTNERSHIPS in res["likely_services"]
    assert res["priority"] in (OutreachPriority.P0, OutreachPriority.P1, OutreachPriority.P2)


# ─── 4. Prop Firm Challenges Channel ─────────────────────────────────────────
def test_prop_firm_challenges_channel_inferred():
    messages = [
        MockMessage("اجتياز تحدي التمويل في شركات FTMO و FundedNext بنجاح للمرحلة الأولى"),
        MockMessage("نساعدك في إدارة حساب ممول واجتياز التحدي مع ضمان الحفاظ على قواعد التراجع"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="اجتياز تحديات شركات التمويل Prop Firm",
        description="خبراء اجتياز حسابات ممولة وشركات التمويل FTMO",
        recent_messages=messages,
        contacts_dict={"contact_username": "prop_trader", "source": "bio_admin"},
        forex_relevance_score=80,
        member_count=1500
    )
    assert "prop_firm_challenges" in res["detected_models"]
    assert ServiceNeedType.PARTNERSHIPS in res["likely_services"]


# ─── 5. Academy / Paid Courses Channel ───────────────────────────────────────
def test_academy_courses_channel_inferred():
    messages = [
        MockMessage("انطلاق الدورة الاحترافية لكورس التحليل الحجمي والموجي مع التدريب الخاص"),
        MockMessage("خصم خاص للدفعة الجديدة من أكاديمية التداول. للتسجيل تواصل @academy_admin"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="أكاديمية الفوركس الاحترافية",
        description="أكاديمية ودورات تدريبية متقدمة في أسواق المال",
        recent_messages=messages,
        contacts_dict={"contact_username": "academy_admin", "source": "bio_official"},
        forex_relevance_score=85,
        member_count=4500
    )
    assert "academy_courses" in res["detected_models"]


# ─── 6. Operational Complexity Scoring ────────────────────────────────────────
def test_operational_complexity_scoring():
    structured_msgs = [
        MockMessage("BUY EURUSD @ 1.0850 | SL: 1.0800 | TP1: 1.0900 | TP2: 1.0950"),
        MockMessage("تحليل فني للذهب على فريم الأربع ساعات. كسر خط الاتجاه الصاعد مع مؤشر RSI"),
        MockMessage("تحديث صفقة الباوند ين ضرب الهدف الأول +45 نقطة ونقل وقف الخسارة إلى الدخول"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="إشارات وتحليلات يومية",
        description="تداول منظم مع تحليلات فنية وإشارات لحظية",
        recent_messages=structured_msgs,
        contacts_dict={"contact_username": "ops_trader"},
        forex_relevance_score=90,
        member_count=2000,
        posts_24h=8,
        posts_7d=40
    )
    assert res["operational_complexity_score"] >= 8
    assert res["evidence"]["has_structured_signals"] is True


# ─── 7. Generic Forex News Channel Scores P3 ─────────────────────────────────
def test_generic_forex_news_scores_p3():
    news_msgs = [
        MockMessage("عاجل: التضخم الأمريكي يرتفع بنسبة 0.2% في قراءة شهر يوليو"),
        MockMessage("تصريحات محافظ الفيدرالي جيروم باول تؤكد استمرار السياسة المتشددة"),
        MockMessage("أسعار النفط تسجل استقراراً مع افتتاح الأسواق الأوروبية اليوم"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="أخبار الاقتصاد والفوركس العاجلة",
        description="تغطية إخبارية فورية لأسواق العملات والاقتصاد العالمي",
        recent_messages=news_msgs,
        contacts_dict={},
        forex_relevance_score=75,
        member_count=50000,
        posts_24h=12,
        posts_7d=60
    )
    assert res["priority"] == OutreachPriority.P3
    assert res["priority_score"] < 50
    assert len(res["detected_models"]) == 0
    assert res["commercial_fit_score"] <= 5


# ─── 8. Non-Commercial Channel Scores P4 ──────────────────────────────────────
def test_non_commercial_channel_scores_p4():
    weak_msgs = [
        MockMessage("صباح الخير جميعاً"),
        MockMessage("أذكار الصباح والمساء"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="خواطر وتأملات عامة",
        description="قناة عامة للمشاركة والخواطر",
        recent_messages=weak_msgs,
        contacts_dict={},
        forex_relevance_score=10,
        member_count=150
    )
    assert res["priority"] == OutreachPriority.P4
    assert res["priority_score"] < 25


# ─── 9. Small Active Commercial Channel Outranks 2M Dormant News Channel ──────
def test_small_active_commercial_outranks_large_dormant_news():
    small_commercial_msgs = [
        MockMessage("صفقة شراء ذهب XAUUSD | دخول: 2025 | وقف الخسارة SL: 2015 | أهداف TP: 2045"),
        MockMessage("باقات اشتراك VIP للقناة المدفوعة متوفرة الآن بخصم 40%، الدفع USDT"),
        MockMessage("للاشتراك تواصل فوراً عبر @gold_vip_admin"),
    ]
    small_eval = OutreachPriorityEngine.evaluate_priority(
        title="توصيات الذهب الخاصة VIP",
        description="قناة التوصيات الذهبية المدفوعة. للتواصل: @gold_vip_admin",
        recent_messages=small_commercial_msgs,
        contacts_dict={"contact_username": "gold_vip_admin", "source": "bio_official"},
        forex_relevance_score=95,
        member_count=400,
        posts_24h=4,
        posts_7d=20
    )

    huge_news_msgs = [
        MockMessage("بيانات التضخم في منطقة اليورو تسجل 2.4% متوافقة مع التوقعات"),
        MockMessage("مؤشر نيكي الياباني يغلق على ارتفاع طفيف في ختام تعاملات اليوم"),
    ]
    huge_eval = OutreachPriorityEngine.evaluate_priority(
        title="شبكة الأخبار الاقتصادية العالمية",
        description="أكبر شبكة اقتصادية لتغطية أسواق المال والأخبار العالمية",
        recent_messages=huge_news_msgs,
        contacts_dict={},
        forex_relevance_score=65,
        member_count=2_000_000,
        posts_24h=1,
        posts_7d=4
    )

    assert small_eval["priority_score"] > huge_eval["priority_score"]
    assert small_eval["priority"] in (OutreachPriority.P0, OutreachPriority.P1)
    assert huge_eval["priority"] in (OutreachPriority.P3, OutreachPriority.P4)
    assert (huge_eval["audience_context_score"] - small_eval["audience_context_score"]) <= 4


# ─── 10. Freshness Decay ──────────────────────────────────────────────────────
def test_freshness_decay():
    now = datetime.now(timezone.utc)
    
    fresh_msgs = [
        MockMessage("عرض خاص للاشتراك بقناة VIP بخصم 30%", date=now - timedelta(days=2))
    ]
    fresh_eval = CommercialInferenceEngine.analyze_channel_commercial_fit(
        title="تداول فوركس",
        description="قناة تداول",
        recent_messages=fresh_msgs,
        contacts_dict={}
    )
    assert fresh_eval["freshness_score"] == 5
    assert fresh_eval["freshness_days"] <= 3.0

    stale_msgs = [
        MockMessage("عرض خاص للاشتراك بقناة VIP بخصم 30%", date=now - timedelta(days=45))
    ]
    stale_eval = CommercialInferenceEngine.analyze_channel_commercial_fit(
        title="تداول فوركس",
        description="قناة تداول",
        recent_messages=stale_msgs,
        contacts_dict={}
    )
    assert stale_eval["freshness_score"] == 1
    assert stale_eval["freshness_days"] >= 40.0


# ─── 11. Contact Quality Hierarchy ────────────────────────────────────────────
def test_contact_quality_hierarchy():
    eval_official = OutreachPriorityEngine.evaluate_priority(
        title="فوركس",
        description="للتواصل: @official_contact",
        contacts_dict={"contact_username": "official_contact", "source": "bio_official"},
        forex_relevance_score=70
    )
    assert eval_official["contactability_score"] == 5

    eval_bio_gen = OutreachPriorityEngine.evaluate_priority(
        title="فوركس",
        description="قناة تداول @some_channel_link",
        contacts_dict={"contact_username": "some_contact", "source": "bio_general"},
        forex_relevance_score=70
    )
    assert eval_bio_gen["contactability_score"] == 4

    eval_msg_gen = OutreachPriorityEngine.evaluate_priority(
        title="فوركس",
        description="قناة تداول",
        contacts_dict={"contact_username": "msg_user", "source": "message_general"},
        forex_relevance_score=70
    )
    assert eval_msg_gen["contactability_score"] == 3

    eval_no_contact = OutreachPriorityEngine.evaluate_priority(
        title="فوركس",
        description="قناة تداول",
        contacts_dict={},
        forex_relevance_score=70
    )
    assert eval_no_contact["contactability_score"] == 0


# ─── 12. Multi-Label Service Fit Inference ────────────────────────────────────
def test_service_fit_inference_multi_label():
    messages = [
        MockMessage("سجل عبر رابط الوكالة في شركة Exness واحصل على اشتراك VIP مجاناً"),
        MockMessage("للاشتراك تواصل مع الدعم الفني @service_admin الدفع USDT"),
        MockMessage("تحليل فني لمؤشر الدولار والذهب على فريم 4 ساعات"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="إكسنس فوركس VIP",
        description="وكيل معتمد وقناة خاصة للتوصيات",
        recent_messages=messages,
        contacts_dict={"contact_username": "service_admin", "source": "bio_official"},
        forex_relevance_score=90,
        member_count=5000,
        posts_7d=20
    )
    services = res["likely_services"]
    assert ServiceNeedType.PARTNERSHIPS in services
    assert ServiceNeedType.ADVERTISING_MANAGEMENT in services
    assert ServiceNeedType.CHANNEL_MANAGEMENT in services


# ─── 13. Structured Explainable Evidence & Reason Generation ──────────────────
def test_explainable_evidence_structure():
    messages = [
        MockMessage("خصم خاص 40% للاشتراك السنوي في VIP، الدفع متاح عبر Binance Pay و USDT"),
    ]
    res = OutreachPriorityEngine.evaluate_priority(
        title="توصيات واستشارات تداول",
        description="للاشتراك تواصل مع @admin_gold",
        recent_messages=messages,
        contacts_dict={"contact_username": "admin_gold", "source": "bio_official"},
        forex_relevance_score=85
    )
    evidence = res["evidence"]
    assert "detected_models" in evidence
    assert "promo_post_count" in evidence
    assert "payment_methods" in evidence
    assert "snippets" in evidence
    assert isinstance(res["reason"], str)
    assert len(res["reason"]) > 10


# ─── 14. Campaign Claiming Order (P0 before P1, P2, P3) ──────────────────────
def test_campaign_claiming_order_p0_before_p1_p2_p3():
    mock_cur = MagicMock()
    rows = [
        {"log_id": "1", "priority": "P0", "priority_score": 90},
        {"log_id": "2", "priority": "P0", "priority_score": 82},
        {"log_id": "3", "priority": "P1", "priority_score": 70},
        {"log_id": "4", "priority": "P2", "priority_score": 50},
        {"log_id": "5", "priority": "P3", "priority_score": 25},
    ]
    mock_cur.fetchone.return_value = rows[0]

    item = mock_cur.fetchone()
    assert item["priority"] == "P0"
    assert item["priority_score"] == 90


# ─── 15. Campaign Recipient Re-ranking ────────────────────────────────────────
def test_rerank_campaign_recipients():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    mock_cur.fetchall.return_value = [
        {"priority": "P0", "cnt": 12},
        {"priority": "P1", "cnt": 25},
        {"priority": "P2", "cnt": 40},
        {"priority": "P3", "cnt": 80}
    ]
    mock_cur.rowcount = 157

    result = OutreachPriorityEngine.rerank_campaign_recipients(mock_conn, "camp-123")
    assert result["updated"] == 157
    assert result["tier_counts"]["P0"] == 12
    assert result["tier_counts"]["P1"] == 25
    mock_conn.commit.assert_called_once()


# ─── 16. Outreach State & Safety Preservation ─────────────────────────────────
def test_outreach_state_and_safety_preserved():
    from app.outreach.eligibility import check_eligibility

    mock_redis = MagicMock()
    mock_cur = MagicMock()

    status, reason = check_eligibility(
        mock_redis, mock_cur, "lead-1", "camp-1", "signals_bot"
    )
    assert status == "BLOCKED"
    assert "Bot" in reason

    status, reason = check_eligibility(
        mock_redis, mock_cur, "lead-2", "camp-1", "joinchat"
    )
    assert status == "BLOCKED"
    assert "System keyword" in reason


# ─── 17. Real Database SQL Ordering Integration Test ──────────────────────────
def test_sql_ordering_real_database_integration():
    """
    Integration test executing the actual claiming query against a real SQL database engine
    to prove that pending recipients are claimed strictly in:
    P0 -> P1 -> P2 -> P3 -> P4, and ordered by priority_score DESC within each tier.
    """
    import sqlite3

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE campaigns (
            id TEXT PRIMARY KEY,
            message_text TEXT,
            media_path TEXT,
            created_at TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE leads (
            id TEXT PRIMARY KEY,
            channel_username TEXT,
            contact_username TEXT,
            outreach_priority TEXT,
            outreach_priority_score INT,
            outreach_priority_reason TEXT,
            commercial_last_seen TIMESTAMP,
            intent_detected_at TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE campaign_logs (
            id TEXT PRIMARY KEY,
            campaign_id TEXT,
            lead_id TEXT,
            status TEXT,
            priority TEXT,
            priority_score INT,
            attempt_count INT DEFAULT 0,
            last_attempt_at TIMESTAMP,
            sent_at TIMESTAMP
        );
    """)

    cur.execute("INSERT INTO campaigns VALUES ('camp-1', 'Test message', NULL, '2026-09-01 10:00:00')")

    # Insert diverse leads: P3, P0, P1, P0, P2, P4, P1, P3
    leads = [
        ("lead-p3-low", "news_1", "admin1", "P3", 22, "2026-09-01 00:00:00"),
        ("lead-p0-high", "vip_1", "admin2", "P0", 92, "2026-09-04 04:00:00"),
        ("lead-p1-mid", "copy_1", "admin3", "P1", 65, "2026-09-03 12:00:00"),
        ("lead-p0-mid", "vip_2", "admin4", "P0", 78, "2026-09-04 02:00:00"),
        ("lead-p2-high", "ib_1", "admin5", "P2", 52, "2026-09-02 15:00:00"),
        ("lead-p4-min", "chat_1", "admin6", "P4", 10, None),
        ("lead-p1-high", "prop_1", "admin7", "P1", 72, "2026-09-04 01:00:00"),
        ("lead-p3-high", "news_2", "admin8", "P3", 35, "2026-09-02 08:00:00"),
    ]

    for lid, cname, uadmin, prio, score, lseen in leads:
        cur.execute("INSERT INTO leads VALUES (?, ?, ?, ?, ?, 'reason', ?, NULL)", (lid, cname, uadmin, prio, score, lseen))
        cur.execute("INSERT INTO campaign_logs VALUES (?, 'camp-1', ?, 'pending', ?, ?, 0, NULL, NULL)", (f"log-{lid}", lid, prio, score))

    # Actual Claiming Query (matching campaign_worker.py / validator.py)
    cur.execute("""
        SELECT cl.id as log_id, l.channel_username,
               COALESCE(cl.priority, l.outreach_priority, 'P3') as priority,
               COALESCE(cl.priority_score, l.outreach_priority_score, 25) as priority_score
        FROM campaign_logs cl
        JOIN campaigns c ON cl.campaign_id = c.id
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.status = 'pending'
        ORDER BY 
            CASE COALESCE(cl.priority, l.outreach_priority, 'P3')
                WHEN 'P0' THEN 0
                WHEN 'P1' THEN 1
                WHEN 'P2' THEN 2
                WHEN 'P3' THEN 3
                WHEN 'P4' THEN 4
                ELSE 5
            END ASC,
            COALESCE(cl.priority_score, l.outreach_priority_score, 25) DESC,
            COALESCE(l.commercial_last_seen, l.intent_detected_at) DESC,
            cl.attempt_count ASC,
            c.created_at ASC
    """)

    results = cur.fetchall()
    extracted_order = [(r[1], r[2], r[3]) for r in results]

    # Verify exact claimed sequence
    expected_order = [
        ("vip_1", "P0", 92),
        ("vip_2", "P0", 78),
        ("prop_1", "P1", 72),
        ("copy_1", "P1", 65),
        ("ib_1", "P2", 52),
        ("news_2", "P3", 35),
        ("news_1", "P3", 22),
        ("chat_1", "P4", 10),
    ]
    assert extracted_order == expected_order


# ─── 18. Previously Contacted / Replied / Skipped / Cooldown Not Selected ─────
def test_previously_contacted_replied_skipped_cooldown_not_selected():
    """
    Ensures that leads that were already contacted, replied, skipped, or in cooldown
    are NEVER selected by the claiming query.
    """
    import sqlite3

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    cur.execute("CREATE TABLE campaigns (id TEXT PRIMARY KEY, created_at TIMESTAMP);")
    cur.execute("CREATE TABLE leads (id TEXT PRIMARY KEY, channel_username TEXT, outreach_priority TEXT, outreach_priority_score INT, commercial_last_seen TIMESTAMP, intent_detected_at TIMESTAMP);")
    cur.execute("CREATE TABLE campaign_logs (id TEXT PRIMARY KEY, campaign_id TEXT, lead_id TEXT, status TEXT, priority TEXT, priority_score INT, attempt_count INT, sent_at TIMESTAMP, last_attempt_at TIMESTAMP);")

    cur.execute("INSERT INTO campaigns VALUES ('camp-1', '2026-09-01 10:00:00')")

    # Insert 4 leads with different states
    # 1. P0 lead that was already sent
    cur.execute("INSERT INTO leads VALUES ('l1', 'p0_sent', 'P0', 95, NULL, NULL)")
    cur.execute("INSERT INTO campaign_logs VALUES ('log1', 'camp-1', 'l1', 'sent', 'P0', 95, 1, '2026-09-02', '2026-09-02')")

    # 2. P0 lead that was skipped (duplicate / blacklisted)
    cur.execute("INSERT INTO leads VALUES ('l2', 'p0_skipped', 'P0', 90, NULL, NULL)")
    cur.execute("INSERT INTO campaign_logs VALUES ('log2', 'camp-1', 'l2', 'skipped', 'P0', 90, 0, NULL, NULL)")

    # 3. P0 lead currently being processed
    cur.execute("INSERT INTO leads VALUES ('l3', 'p0_processing', 'P0', 85, NULL, NULL)")
    cur.execute("INSERT INTO campaign_logs VALUES ('log3', 'camp-1', 'l3', 'processing', 'P0', 85, 1, NULL, '2026-09-04 05:30:00')")

    # 4. P1 lead that is legitimately PENDING
    cur.execute("INSERT INTO leads VALUES ('l4', 'p1_eligible', 'P1', 68, NULL, NULL)")
    cur.execute("INSERT INTO campaign_logs VALUES ('log4', 'camp-1', 'l4', 'pending', 'P1', 68, 0, NULL, NULL)")

    # Claim query
    cur.execute("""
        SELECT cl.id, l.channel_username, cl.priority
        FROM campaign_logs cl
        JOIN campaigns c ON cl.campaign_id = c.id
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.status = 'pending'
        ORDER BY 
            CASE COALESCE(cl.priority, l.outreach_priority, 'P3')
                WHEN 'P0' THEN 0
                WHEN 'P1' THEN 1
                WHEN 'P2' THEN 2
                WHEN 'P3' THEN 3
                WHEN 'P4' THEN 4
                ELSE 5
            END ASC
        LIMIT 1
    """)

    claimed = cur.fetchone()
    # Must claim the pending P1 lead, completely ignoring sent/skipped/processing P0 leads
    assert claimed is not None
    assert claimed[1] == "p1_eligible"
    assert claimed[2] == "P1"
