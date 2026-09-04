"""
Script: generate_top50_ranking.py
Generates a realistic sample dataset of pending Arabic Forex/Trading Telegram channel recipients,
evaluates them with OutreachPriorityEngine, and outputs the top 50 ranked list with all required attributes.
"""

import os
import sys
from datetime import datetime, timezone, timedelta


# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app.outreach.priority_engine import OutreachPriorityEngine


def create_sample_candidates():
    now = datetime.now(timezone.utc)
    
    candidates = [
        # 1. High Commercial Fit - VIP Signals (Small 400 - 800 members)
        {
            "channel_title": "VIP Gold Scalping Signals",
            "about": "توصيات ذهب ونفط VIP يومية بنسبة نجاح 90%، للاشتراك الشهري وتفعيل العضوية راسل @gold_vip_admin",
            "recent_messages": ["صفقة شراء XAUUSD هدف أول محقق +50 نقطة", "تجديد اشتراكات قناة VIP الذهبية مستمر عبر الخاص"],
            "admin_usernames": ["gold_vip_admin"],
            "subscriber_count": 420,
            "last_post_date": now - timedelta(hours=2),
            "lead_score": 85.0
        },
        {
            "channel_title": "أكاديمية الفوركس للمحترفين - VIP",
            "about": "توصيات فوركس خاصة ودروس تطبيقية vip، تواصل مع المشرف @fx_academy_support",
            "recent_messages": ["إغلاق نصف العقود وتأمين الدخول", "للاشتراك السنوي أو الشهري بالقناة الخاصة كلم المشرف"],
            "admin_usernames": ["fx_academy_support"],
            "subscriber_count": 650,
            "last_post_date": now - timedelta(hours=3),
            "lead_score": 82.0
        },
        {
            "channel_title": "قناص الذهب VIP للتحليلات والتوصيات",
            "about": "إشارات حية يومية على الذهب والمؤشرات. للاشتراك وتفاصيل الـ vip كلم @sniper_gold_ceo",
            "recent_messages": ["توصية بيع ناسداك محققة 120 نقطة", "عروض الاشتراك برعاية القناة مستمرة"],
            "admin_usernames": ["sniper_gold_ceo"],
            "subscriber_count": 780,
            "last_post_date": now - timedelta(hours=1),
            "lead_score": 88.0
        },
        
        # 2. Copy Trading / PAMM Accounts
        {
            "channel_title": "نسخ صفقات الفوركس الآلي | Copy Trading",
            "about": "خدمة نسخ الصفقات التلقائية pamm وربط الحسابات مباشرة بدون تدخل منك. تواصل: @copy_trade_manager",
            "recent_messages": ["أرباح الأسبوع الماضي لخدمة النسخ بلغت +14%", "لربط حسابك في خدمة copy trading تواصل معنا"],
            "admin_usernames": ["copy_trade_manager"],
            "subscriber_count": 1200,
            "last_post_date": now - timedelta(hours=4),
            "lead_score": 86.0
        },
        {
            "channel_title": "محفظة النمو - إدارة محافظ واستثمار",
            "about": "إدارة محافظ استثمارية وتداول آلي للمشتركين. حسابات pamm رسمية. استفسارات: @growth_portfolio_admin",
            "recent_messages": ["تقرير أداء المحفظة الاستثمارية لشهر أغسطس", "نظام نسخ الصفقات يعمل بكفاءة مع وسيطنا المعتمد"],
            "admin_usernames": ["growth_portfolio_admin"],
            "subscriber_count": 2100,
            "last_post_date": now - timedelta(hours=6),
            "lead_score": 84.0
        },
        {
            "channel_title": "المضارب العربي - نظام النسخ الذكي",
            "about": "نسخ صفقات وتحليلات فنية للمتداول العربي. كلم الدعم @smart_copy_support",
            "recent_messages": ["افتتاح صفقات جديدة على اليورو دولار", "طريقة الانضمام إلى نظام النسخ المباشر"],
            "admin_usernames": ["smart_copy_support"],
            "subscriber_count": 1500,
            "last_post_date": now - timedelta(hours=5),
            "lead_score": 83.0
        },

        # 3. Prop Firm Passing & EA / Bot Sales
        {
            "channel_title": "اجتياز تحديات شركات التمويل Prop Firm",
            "about": "نساعدك في اجتياز تقييم شركات التمويل FTMO و FundedNext عبر روبوت تداول آلي وخوارزميات مجربة. @prop_pass_expert",
            "recent_messages": ["تم اجتياز تحدي 100k بنجاح لأحد العملاء", "احجز مقعدك لاجتياز اختبار التمويل"],
            "admin_usernames": ["prop_pass_expert"],
            "subscriber_count": 950,
            "last_post_date": now - timedelta(hours=2),
            "lead_score": 89.0
        },
        {
            "channel_title": "Expert Advisor Algo Trading Bot",
            "about": "روبوت تداول آلي إكسبيرت EA ومؤشر سكالبينج للبيع. دعم فني وتركيب مجاني: @algo_ea_seller",
            "recent_messages": ["نتائج باك تست للإكسبيرت لشهر يوليو", "تحديث استراتيجية التداول الآلي على الميتاتريدر"],
            "admin_usernames": ["algo_ea_seller"],
            "subscriber_count": 820,
            "last_post_date": now - timedelta(hours=7),
            "lead_score": 85.0
        },
        {
            "channel_title": "حلول تمويل المتداولين Funded Trading",
            "about": "خدمات تخطي التحديات والتقييمات وحسابات التمويل بروب فيرم. للتواصل: @funded_solutions",
            "recent_messages": ["تسليم حساب ممول 50 ألف دولار اليوم", "شروط الاشتراك في خدمة التمرير الآمن"],
            "admin_usernames": ["funded_solutions"],
            "subscriber_count": 1400,
            "last_post_date": now - timedelta(hours=4),
            "lead_score": 87.0
        },

        # 4. Broker Affiliates & IB Networks
        {
            "channel_title": "نادي المتداولين - وكالة إكسنس الرسمية",
            "about": "افتح حسابك تحت وكالتنا وسجل تحت رابط الإحالة الخاص بنا واحصل على توصيات مجانية وكاش باك أسبوعي. @ib_exness_club",
            "recent_messages": ["رابط التسجيل في الشركة تحت الوكالة", "تحويل عمولات الكاش باك لجميع الأعضاء المسجلين"],
            "admin_usernames": ["ib_exness_club"],
            "subscriber_count": 3400,
            "last_post_date": now - timedelta(hours=3),
            "lead_score": 79.0
        },
        {
            "channel_title": "مجتمع البورصة وكاش باك التداول",
            "about": "استرداد عمولات التداول وكاش باك على كل لوت تتداوله برابط الوكالة. انضمام واستفسار: @cashback_trader",
            "recent_messages": ["أفضل سبريد متوفر في السوق لعملائنا", "أرسل رقم حسابك لتفعيله في قائمة الكاش باك"],
            "admin_usernames": ["cashback_trader"],
            "subscriber_count": 2800,
            "last_post_date": now - timedelta(hours=6),
            "lead_score": 77.0
        },
        {
            "channel_title": "سفراء الفوركس | وسيط معتمد",
            "about": "قناة الشركاء والوكلاء المعتمدين. افتح حساب برابط الشراكة وادخل غرفة التوصيات. المشرف: @broker_ambassador",
            "recent_messages": ["تحليل فرص تداول الذهب اليومية", "خطوات فتح وتوثيق الحساب بخصم على العمولات"],
            "admin_usernames": ["broker_ambassador"],
            "subscriber_count": 1900,
            "last_post_date": now - timedelta(hours=8),
            "lead_score": 75.0
        },

        # 5. Forex Academy & Mentorship
        {
            "channel_title": "أكاديمية موجات إليوت والتحليل التوافقي",
            "about": "دورات تدريبية مكثفة وكورس احتراف التحليل الموجي مع جلسات لايف أسبوعية. للتسجيل: @elliott_academy",
            "recent_messages": ["موعد انطلاق الويبنار التدريبي القادم", "فتح باب التسجيل لدفعة دورة سبتمبر الاحترافية"],
            "admin_usernames": ["elliott_academy"],
            "subscriber_count": 3100,
            "last_post_date": now - timedelta(hours=5),
            "lead_score": 80.0
        },
        {
            "channel_title": "كورس السلوك السعري Price Action Mastery",
            "about": "تدريب عملي ومتابعة فردية ومنتورينج خاص على حركة الأسعار. للاشتراك في الكورس: @priceaction_mentor",
            "recent_messages": ["شرح نموذج السيولة الذكية SMC بالفيديو", "تفاصيل الدورة التدريبية والمقاعد المتبقية"],
            "admin_usernames": ["priceaction_mentor"],
            "subscriber_count": 1600,
            "last_post_date": now - timedelta(hours=3),
            "lead_score": 81.0
        },
        {
            "channel_title": "مدرسة التداول الذكي SMC Trading",
            "about": "تعليم الفوركس للمبتدئين والمحترفين، ورش عمل ودورات مباشرة. التواصل: @smart_money_edu",
            "recent_messages": ["درس تحليل الهيكل وسيولة القيعان", "احجز جلستك التدريبية الفردية اليوم"],
            "admin_usernames": ["smart_money_edu"],
            "subscriber_count": 2200,
            "last_post_date": now - timedelta(hours=9),
            "lead_score": 78.0
        },

        # 6. More VIP / Trading Services (Mid Sizes 1k - 10k)
        {
            "channel_title": "الصقر لتوصيات العملات والسلع VIP",
            "about": "توصيات حصرية VIP ومتابعة فورية لحظة بلحظة. اشتراك شهري وسنوي: @falcon_vip_trader",
            "recent_messages": ["صفقة الباوند ين حققت الهدف الثاني 80 نقطة", "للحصول على العضوية الخاصة راسلنا"],
            "admin_usernames": ["falcon_vip_trader"],
            "subscriber_count": 4500,
            "last_post_date": now - timedelta(hours=1),
            "lead_score": 86.0
        },
        {
            "channel_title": "ديوانية المتداول العربي VIP",
            "about": "مجتمع تداول وإشارات خاصة وغرفة صفقات حية. مسؤول الاشتراكات: @dewan_fx_owner",
            "recent_messages": ["إغلاق جميع عقود الداوجونز بربح 200 نقطة", "تجديد اشتراكك السنوي بعرض خاص"],
            "admin_usernames": ["dewan_fx_owner"],
            "subscriber_count": 3800,
            "last_post_date": now - timedelta(hours=2),
            "lead_score": 84.0
        },
        {
            "channel_title": "إشارات النفط والطاقة VIP Signals",
            "about": "تخصص تداول برنت والنفط الخام الأمريكي مع توصيات خاصة وإدارة محافظ. الدعم: @oil_vip_signals",
            "recent_messages": ["تحليل مخزونات النفط الأمريكية وفرصة بيع", "انضم للقناة الخاصة للاستفادة من تقلبات الطاقة"],
            "admin_usernames": ["oil_vip_signals"],
            "subscriber_count": 2900,
            "last_post_date": now - timedelta(hours=4),
            "lead_score": 83.0
        },
        {
            "channel_title": "الرائد لتوصيات العملات الرقمية والفوركس",
            "about": "إشارات كريبتو وفوركس يومية VIP مع روبوت تداول آلي. تواصل: @pioneer_crypto_fx",
            "recent_messages": ["صفقة البيتكوين حققت جميع الأهداف", "باقات الاشتراك الشهرية المتوفرة حاليا"],
            "admin_usernames": ["pioneer_crypto_fx"],
            "subscriber_count": 5200,
            "last_post_date": now - timedelta(hours=5),
            "lead_score": 82.0
        },
        {
            "channel_title": "مملكة الذهب للمضاربة اللحظية VIP",
            "about": "توصيات سكالبينج يومية سريعة. تواصل مع المدير المباشر: @gold_kingdom_vip",
            "recent_messages": ["دخول شراء سريع لوت صغير وقف 20 نقطة", "للانضمام إلى باقة الـ VIP كلمنا عبر الخاص"],
            "admin_usernames": ["gold_kingdom_vip"],
            "subscriber_count": 4100,
            "last_post_date": now - timedelta(hours=2),
            "lead_score": 85.0
        },
        {
            "channel_title": "مكتب استشارات الأسواق والعملات",
            "about": "استشارات استثمارية وإدارة حسابات تداول وتوصيات VIP للمستثمرين. المدير: @markets_consultant",
            "recent_messages": ["توجيهات المحافظ المالية للأسبوع الجاري", "خطط الاشتراك والخدمات المقدمة لرجال الأعمال"],
            "admin_usernames": ["markets_consultant"],
            "subscriber_count": 1800,
            "last_post_date": now - timedelta(hours=6),
            "lead_score": 80.0
        },
        {
            "channel_title": "المحترف للمضاربة الآلية والنسخ",
            "about": "خدمة نسخ وإشارات فوركس واكسبيرت روبوت. للاشتراك تواصل مع: @pro_algo_trader",
            "recent_messages": ["تحديث نتائج النسخ لشهر أغسطس على ماي اف اكس بوك", "أفضل الإعدادات لروبوت التداول"],
            "admin_usernames": ["pro_algo_trader"],
            "subscriber_count": 2400,
            "last_post_date": now - timedelta(hours=7),
            "lead_score": 81.0
        },
        {
            "channel_title": "شبكة إشارات الداو جونز والنازداك",
            "about": "توصيات مؤشرات أمريكية حصرية VIP مع تحليل فني وموجي. المشرف: @us_indices_vip",
            "recent_messages": ["افتتاح وول ستريت وفرصة شراء على الداو", "العضوية المميزة تشمل صفقات لايف وصوتية"],
            "admin_usernames": ["us_indices_vip"],
            "subscriber_count": 3300,
            "last_post_date": now - timedelta(hours=3),
            "lead_score": 82.0
        },
        {
            "channel_title": "مركز النخبة للتدريب المالي",
            "about": "دورات متقدمة في الأسواق المالية وتأهيل لاختبارات التمويل. تواصل: @elite_finance_edu",
            "recent_messages": ["محاضرة مجانية تمهيدية للدورة القادمة", "سجل الآن في دبلومة المتداول المحترف"],
            "admin_usernames": ["elite_finance_edu"],
            "subscriber_count": 1750,
            "last_post_date": now - timedelta(hours=10),
            "lead_score": 79.0
        },
        {
            "channel_title": "رواد التداول والتوصيات الخاصة",
            "about": "إشارات فوركس وذهب VIP بنسب نجاح عالية. تفاصيل الاشتراك: @forex_pioneers_admin",
            "recent_messages": ["الذهب يحقق الهدف الأول بنجاح", "عرض اشتراك 3 أشهر بخصم 30%"],
            "admin_usernames": ["forex_pioneers_admin"],
            "subscriber_count": 2600,
            "last_post_date": now - timedelta(hours=4),
            "lead_score": 83.0
        },

        # 7. Intermediate Commercial / Semi-Commercial (P1 - P2)
        {
            "channel_title": "بوصلة الأسواق للتحليل الفني",
            "about": "تحليلات فنية يومية للعملات والسلع، للمشاركة في القناة الخاصة والاستفسارات: @markets_compass_admin",
            "recent_messages": ["نظرة فنية على زوج اليورو دولار والفرص المتاحة", "تحديث مستويات الدعم والمقاومة للذهب"],
            "admin_usernames": ["markets_compass_admin"],
            "subscriber_count": 5600,
            "last_post_date": now - timedelta(hours=8),
            "lead_score": 72.0
        },
        {
            "channel_title": "رؤية اقتصادية وتحليلات فوركس",
            "about": "متابعة الأسواق وتغطية البيانات الاقتصادية، للتواصل والتعاون: @eco_vision_support",
            "recent_messages": ["بيانات التضخم الأمريكية وتأثيرها على الدولار", "تحليل حركة الفيدرالي في الاجتماع القادم"],
            "admin_usernames": ["eco_vision_support"],
            "subscriber_count": 7800,
            "last_post_date": now - timedelta(hours=12),
            "lead_score": 68.0
        },
        {
            "channel_title": "ميدان التداول العربي",
            "about": "قناة عامة لمشاركة الفرص ومناقشة صفقات السوق، للتواصل مع الإدارة: @fx_midan_contact",
            "recent_messages": ["فرصة بيع سريعة على الاسترليني ين", "ما رأيكم في اتجاه الذهب بعد كسر الدعم؟"],
            "admin_usernames": ["fx_midan_contact"],
            "subscriber_count": 4200,
            "last_post_date": now - timedelta(hours=15),
            "lead_score": 65.0
        },
        {
            "channel_title": "أسرار الشموع اليابانية",
            "about": "تعليم ونماذج الشموع اليابانية، استفسارات المتابعين: @japanese_candles_bot",
            "recent_messages": ["شرح نموذج الابتلاع الشرائي بالتفصيل", "تطبيقات على نماذج الشموع من شارت اليوم"],
            "admin_usernames": ["japanese_candles_bot"],
            "subscriber_count": 6400,
            "last_post_date": now - timedelta(hours=9),
            "lead_score": 60.0
        },
        {
            "channel_title": "مرآة العملات والسلع العالمية",
            "about": "تغطية حركة العملات الأجنبية وأسعار السلع لحظياً. للتواصل معنا: @fx_mirror_desk",
            "recent_messages": ["تقرير أسعار النفط وبرنت عند الإغلاق", "حركة مؤشر الدولار DXY اليوم"],
            "admin_usernames": ["fx_mirror_desk"],
            "subscriber_count": 8500,
            "last_post_date": now - timedelta(hours=18),
            "lead_score": 62.0
        },
        {
            "channel_title": "محطة التداول اليومي Daily Trade",
            "about": "أفكار تداول يومية وتحليل الاتجاه العام. تواصل: @daily_trade_hq",
            "recent_messages": ["مستويات البيع والشراء لزوج الدولار ين", "جلسة تداول لندن وفرص افتتاح السوق"],
            "admin_usernames": ["daily_trade_hq"],
            "subscriber_count": 4900,
            "last_post_date": now - timedelta(hours=14),
            "lead_score": 66.0
        },
        {
            "channel_title": "نبض الأسواق المالية",
            "about": "متابعة لحظية لأخبار وتحركات البورصات العالمية. تواصل: @pulse_markets",
            "recent_messages": ["عاجل: تصريحات رئيس البنك المركزي الأوروبي", "صعود عوائد السندات الأمريكية لأعلى مستوى"],
            "admin_usernames": ["pulse_markets"],
            "subscriber_count": 9200,
            "last_post_date": now - timedelta(hours=6),
            "lead_score": 58.0
        },
        {
            "channel_title": "ديلي فوركس العربي DailyFX Arabic",
            "about": "تحليلات فنية يومية ورسوم بيانية مجانية للجميع.",
            "recent_messages": ["الشارت اليومي لزوج الدولار كندي", "مؤشر القوة النسبية RSI يظهر تشبع بيعي"],
            "admin_usernames": ["dailyfx_arabic_bot"],
            "subscriber_count": 14000,
            "last_post_date": now - timedelta(hours=11),
            "lead_score": 54.0
        },
        {
            "channel_title": "حوارات وتحليلات المستثمرين",
            "about": "منصة مفتوحة لتبادل وجهات النظر في تداول الأسهم والعملات. المشرف: @investors_chat_admin",
            "recent_messages": ["مناقشة حول نتائج أرباح شركات التكنولوجيا", "ما هي أفضل أزواج العملات للمضاربة هذا الشهر؟"],
            "admin_usernames": ["investors_chat_admin"],
            "subscriber_count": 3900,
            "last_post_date": now - timedelta(hours=20),
            "lead_score": 52.0
        },
        {
            "channel_title": "ملتقى محللي الفوركس العرب",
            "about": "تجميع لتحليلات مختلف المحللين والخبراء في الوطن العربي. إدارة القناة: @fx_analysts_admin",
            "recent_messages": ["تحليل فني مشترك للذهب من عدة محللين", "نظرة على أهم أحداث الأسبوع الاقتصادي"],
            "admin_usernames": ["fx_analysts_admin"],
            "subscriber_count": 6100,
            "last_post_date": now - timedelta(hours=16),
            "lead_score": 55.0
        },

        # 8. Large Generic News / Broadcast Channels (Low commercial fit, P3)
        {
            "channel_title": "أخبار الأسواق والمال العالمية (2.2M)",
            "about": "أكبر شبكة إخبارية عربية لتغطية أسواق المال والأسهم والسلع والاقتصاد العالمي على مدار الساعة.",
            "recent_messages": ["عاجل: مؤشرات الأسهم العالمية تغلق على تباين", "ارتفاع أسعار النفط بسبب التوترات الجيوسياسية"],
            "admin_usernames": [],
            "subscriber_count": 2200000,
            "last_post_date": now - timedelta(minutes=15),
            "lead_score": 35.0
        },
        {
            "channel_title": "نبض البورصة الإخباري العاجل (1.5M)",
            "about": "القناة الإخبارية الأولى لمتابعة البيانات الاقتصادية العاجلة وأسعار الفائدة وقرارات البنوك المركزية.",
            "recent_messages": ["عاجل: مؤشر أسعار المستهلكين يسجل تباطؤاً", "الفيدرالي يبقي أسعار الفائدة دون تغيير"],
            "admin_usernames": ["news_bot"],
            "subscriber_count": 1500000,
            "last_post_date": now - timedelta(minutes=30),
            "lead_score": 32.0
        },
        {
            "channel_title": "اقتصاد الشرق وعالم المال (850k)",
            "about": "متابعة اقتصادية شاملة لحركة الأسواق العربية والعالمية والنفط والغاز.",
            "recent_messages": ["تقرير: تحولات أسواق الطاقة في الشرق الأوسط", "افتتاح البورصات الخليجية على مكاسب طفيفة"],
            "admin_usernames": [],
            "subscriber_count": 850000,
            "last_post_date": now - timedelta(hours=1),
            "lead_score": 30.0
        },
        {
            "channel_title": "أخبار الذهب والعملات مباشر (500k)",
            "about": "نشرة أسعار الذهب والعملات الأجنبية في البنوك والأسواق الرسمية لحظة بلحظة.",
            "recent_messages": ["سعر جرام الذهب عيار 21 اليوم في السوق المحلي", "استقرار سعر الدولار مقابل الجنيه"],
            "admin_usernames": [],
            "subscriber_count": 500000,
            "last_post_date": now - timedelta(hours=2),
            "lead_score": 28.0
        },
        {
            "channel_title": "المفكرة الاقتصادية العالمية (350k)",
            "about": "جدول مواعيد البيانات الاقتصادية اليومية ومؤشرات مديري المشتريات ومعدلات البطالة.",
            "recent_messages": ["بيان نتائج مؤشر ثقة المستهلك الأمريكي", "مبيعات التجزئة البريطانية تسجل نمواً طفيفاً"],
            "admin_usernames": ["calendar_bot"],
            "subscriber_count": 350000,
            "last_post_date": now - timedelta(hours=3),
            "lead_score": 25.0
        },
        {
            "channel_title": "أسواق العملات والأوراق المالية (200k)",
            "about": "قناة إخبارية ترصد تحركات السندات والأسهم والسلع الاستراتيجية حول العالم.",
            "recent_messages": ["هبوط جماعي لأسهم شركات التعدين الأوروبية", "تقرير صندوق النقد الدولي حول النمو العالمي"],
            "admin_usernames": [],
            "subscriber_count": 200000,
            "last_post_date": now - timedelta(hours=4),
            "lead_score": 24.0
        },
        {
            "channel_title": "بورصة السلع والذهب اليومية (120k)",
            "about": "متابعة حركة أسعار المعادن الثمينة والفضة والبلاتين والنفط في البورصات العالمية.",
            "recent_messages": ["تداولات الفضة تشهد استقراراً أعلى 28 دولار", "النحاس يرتفع بفعل زيادة الطلب الصناعي"],
            "admin_usernames": [],
            "subscriber_count": 120000,
            "last_post_date": now - timedelta(hours=5),
            "lead_score": 22.0
        },
        {
            "channel_title": "صدى الاقتصاد العربي (80k)",
            "about": "مقالات اقتصادية وتحليلات للأوضاع المالية في الشرق الأوسط وشمال أفريقيا.",
            "recent_messages": ["مقال الأسبوع: مستقبل التجارة البينية العربية", "تقرير حول احتياطيات النقد الأجنبي"],
            "admin_usernames": [],
            "subscriber_count": 80000,
            "last_post_date": now - timedelta(hours=7),
            "lead_score": 20.0
        },

        # 9. Non-Commercial / Personal Journals / Dormant (P4)
        {
            "channel_title": "يوميات متداول مبتدئ",
            "about": "قناتي الشخصية لتوثيق صفقاتي وأخطائي في التداول، ليست توصيات وليست نصيحة مالية.",
            "recent_messages": ["اليوم ارتكبت خطأ الدخول بعقد كبير في الذهب", "الحمد لله خرجت بربح بسيط وسأكتفي لليوم"],
            "admin_usernames": ["trader_diary"],
            "subscriber_count": 180,
            "last_post_date": now - timedelta(days=2),
            "lead_score": 15.0
        },
        {
            "channel_title": "أرشيف مؤشرات وكتب الفوركس",
            "about": "مكتبة مجانية لتحميل كتب واستراتيجيات التحليل الفني والكتب المترجمة بدون أي مقابل.",
            "recent_messages": ["كتاب المرجع الشامل في الشموع اليابانية pdf", "تحميل مؤشر الموفينج المزدوج للميتاتريدر"],
            "admin_usernames": [],
            "subscriber_count": 720,
            "last_post_date": now - timedelta(days=5),
            "lead_score": 12.0
        },
        {
            "channel_title": "خواطر وتحليلات تداول شخصية",
            "about": "مجرد شارتات وأفكار خاصة بي غير ملزمة لأحد.",
            "recent_messages": ["شارت الذهب للإغلاق الأسبوعي للمراجعة لاحقاً"],
            "admin_usernames": [],
            "subscriber_count": 95,
            "last_post_date": now - timedelta(days=12),
            "lead_score": 10.0
        },
        {
            "channel_title": "قناة قديمة متوقفة - فوركس العرب",
            "about": "قناة فوركس توقفت عن النشر في 2024. شكراً للجميع.",
            "recent_messages": ["نعتذر عن توقف القناة بشكل نهائي بالتوفيق للجميع"],
            "admin_usernames": [],
            "subscriber_count": 2500,
            "last_post_date": now - timedelta(days=120),
            "lead_score": 8.0
        },
        {
            "channel_title": "مقتطفات وحكم أسواق المال",
            "about": "أقوال وحكم وارن بافيت وجيم روجرز في الاستثمار وإدارة المخاطر.",
            "recent_messages": ["السوق ينقل المال من غير الصبورين إلى الصبورين", "لا تضع كل البيض في سلة واحدة"],
            "admin_usernames": [],
            "subscriber_count": 310,
            "last_post_date": now - timedelta(days=4),
            "lead_score": 14.0
        },
        {
            "channel_title": "شارتات ورسومات بيانية مجردة",
            "about": "قناة غير تجارية لمشاركة رسومات بيانية بدون أي تعليق أو خدمات.",
            "recent_messages": ["شارت الداو جونز إطار 4 ساعات", "شارت الفضة إطار يومي"],
            "admin_usernames": [],
            "subscriber_count": 140,
            "last_post_date": now - timedelta(days=8),
            "lead_score": 9.0
        },
        {
            "channel_title": "تجارب مضاربة عشوائية",
            "about": "حساب شخصي وتجارب غير منتظمة.",
            "recent_messages": ["تجربة استراتيجية جديدة على حساب ديمو"],
            "admin_usernames": [],
            "subscriber_count": 60,
            "last_post_date": now - timedelta(days=25),
            "lead_score": 7.0
        }
    ]
    return candidates


class MockMessage:
    def __init__(self, text: str, date: datetime = None):
        self.text = text
        self.date = date or datetime.now(timezone.utc)


def main():
    candidates = create_sample_candidates()
    print(f"Total sample candidates loaded: {len(candidates)}")
    
    evaluated = []
    for c in candidates:
        msgs = [MockMessage(m, date=c["last_post_date"]) for m in c["recent_messages"]]
        contact_user = c["admin_usernames"][0] if c["admin_usernames"] else None
        contact_src = "bio_official" if contact_user and not contact_user.endswith("bot") else ("bio_bot" if contact_user else "none")
        contacts = {"contact_username": contact_user, "source": contact_src} if contact_user else {}

        ev = OutreachPriorityEngine.evaluate_priority(
            title=c["channel_title"],
            description=c["about"],
            recent_messages=msgs,
            contacts_dict=contacts,
            forex_relevance_score=int(c["lead_score"]),
            member_count=c["subscriber_count"],
            posts_24h=3 if c["subscriber_count"] < 10000 else 10,
            posts_7d=15 if c["subscriber_count"] < 10000 else 45
        )
        
        # Calculate freshness
        now = datetime.now(timezone.utc)
        diff = now - c["last_post_date"]
        if diff.total_seconds() < 86400:
            freshness_str = f"{int(diff.total_seconds() // 3600)}h ago (Fresh)"
        else:
            freshness_str = f"{diff.days}d ago (Aged)"
            
        detected_model_str = ", ".join(ev["detected_models"]) if ev["detected_models"] else "None"
        service_needs_str = ", ".join(ev["likely_services"]) if ev["likely_services"] else "None"
        contact_quality_str = "Direct Admin" if contact_src == "bio_official" else ("Bot Contact" if contact_src == "bio_bot" else "No Contact")
            
        evaluated.append({
            "channel_title": c["channel_title"],
            "subscribers": c["subscriber_count"],
            "priority": ev["priority"],
            "priority_score": ev["priority_score"],
            "commercial_fit": ev["commercial_fit_score"],
            "business_model": detected_model_str,
            "service_needs": service_needs_str,
            "reason": ev["reason"],
            "freshness": freshness_str,
            "contact_quality": contact_quality_str
        })
        
    # Sort strictly according to claiming order: P0 -> P1 -> P2 -> P3 -> P4, then priority_score DESC
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
    evaluated.sort(key=lambda x: (priority_order.get(x["priority"], 99), -x["priority_score"]))
    
    top50 = evaluated[:50]
    
    print("\n" + "=" * 120)
    print("TOP 50 RANKED PENDING OUTREACH RECIPIENTS (ORDERED BY CLAIMING PRIORITY & COMMERCIAL FIT)")
    print("=" * 120 + "\n")
    
    print(f"{'#':<4} | {'Priority':<8} | {'Score':<6} | {'CommFit':<8} | {'Business Model':<22} | {'Subs':<8} | {'Contact':<12} | {'Freshness':<14} | {'Channel Title':<30}")
    print("-" * 135)
    for idx, row in enumerate(top50, 1):
        print(f"{idx:<4} | {row['priority']:<8} | {row['priority_score']:<6.1f} | {row['commercial_fit']:<8.1f} | {row['business_model']:<22} | {row['subscribers']:<8} | {row['contact_quality']:<12} | {row['freshness']:<14} | {row['channel_title']:<30}")
    
    print("\n" + "=" * 120)
    print("DETAILED SAMPLES WITH EXPLAINABLE REASON (TOP 5 HIGHEST AND BOTTOM 3 LOWEST):")
    print("=" * 120)
    for idx, row in enumerate(top50[:5], 1):
        print(f"\n[Rank #{idx}] {row['channel_title']} ({row['subscribers']} subs)")
        print(f"  • Priority: {row['priority']} | Priority Score: {row['priority_score']:.1f} | Commercial Fit: {row['commercial_fit']:.1f}")
        print(f"  • Business Model: {row['business_model']} | Needs: {row['service_needs']}")
        print(f"  • Contact Quality: {row['contact_quality']} | Freshness: {row['freshness']}")
        print(f"  • Inferred Reason: {row['reason']}")
        
    print("\n" + "-" * 80)
    print("LOW PRIORITY EXAMPLES (GENERIC NEWS / 2M SUBS / PERSONAL DIARIES):")
    print("-" * 80)
    for row in top50[-3:]:
        print(f"\n[Rank #{top50.index(row)+1}] {row['channel_title']} ({row['subscribers']} subs)")
        print(f"  • Priority: {row['priority']} | Priority Score: {row['priority_score']:.1f} | Commercial Fit: {row['commercial_fit']:.1f}")
        print(f"  • Business Model: {row['business_model']} | Needs: {row['service_needs']}")
        print(f"  • Contact Quality: {row['contact_quality']} | Freshness: {row['freshness']}")
        print(f"  • Inferred Reason: {row['reason']}")

if __name__ == "__main__":
    main()
