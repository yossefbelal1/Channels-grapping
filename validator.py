import os
import sys
import json
import re
import random
import asyncio
import signal
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, errors
from telethon.tl.types import Chat, Channel
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest
from tg_manager import TelegramManager, get_session_path
from keyword_frequency_service import KeywordFrequencyService

# Outreach Engine imports
from app.outreach.emergency import is_outreach_enabled, is_account_enabled
from app.outreach.dry_run import is_dry_run, log_dry_run_decision
from app.outreach.risk_scorer import calculate_risk_score, classify_risk_level
from app.outreach.eligibility import check_eligibility
from app.outreach.account_health import AccountHealthManager
from app.outreach.adaptive_throttle import AdaptiveThrottle
from app.outreach.circuit_breaker import CircuitBreaker
from app.outreach.message_validator import validate_message
from app.outreach.metrics import OutreachMetrics
from app.outreach.reconciliation import ReconciliationManager
from app.outreach.backpressure import BackpressureManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Regex to broadly match Telegram links (t.me/... or telegram.me/...)
TELEGRAM_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/)?\+?[a-zA-Z0-9_.-]+',
    re.IGNORECASE
)

# Regex to match mentions/usernames (e.g. @username)
USERNAME_REGEX = re.compile(r'@([a-zA-Z0-9_]{5,32})')

# ── Ad Exchange Detection: Arabic cross-promotion keywords ────────────────────
# Signals that a post is promoting/mentioning another channel via ad exchange
ad_exchange_kws = [
    "تبادل", "إعلان مدفوع", "دعم", "قناتنا الثانية", "تابعوا", "اشتركوا",
    "توصيات مدفوعة", "اشتراك مجاني", "لمدة محدودة", "العرض ساري",
    "باقي أيام وينتهي", "الاشتراك السنوي", "لفترة محدودة",
    "اشتركو معانا", "انضموا قبل الحذف", "القناة الخاصة",
    "الجروب الخاص", "جروب الـ VIP", "دخول مجاني",
    "أقوى قناة توصيات", "تعويض الخسارة", "تحقيق أرباح",
    "مجانا لأول", "خصم خاص"
]

# ── Forex Ad-Copywriting Patterns: high-value urgency/CTA phrases ─────────────
# Signals an active, profit-driven Forex/Crypto promotional post
forex_ad_patterns = [
    # Urgency / Time-bound
    "لمدة محدودة", "العرض ساري", "باقي أيام وينتهي",
    "الاشتراك السنوي", "لفترة محدودة",
    # Direct CTA / Group Type
    "اشتركو معانا", "انضموا قبل الحذف", "القناة الخاصة",
    "الجروب الخاص", "جروب الـ VIP", "دخول مجاني",
    # Hype / Profit-driven
    "أقوى قناة توصيات", "تعويض الخسارة", "تحقيق أرباح",
    "مجانا لأول", "خصم خاص",
]

def parse_telegram_link(link: str):
    """
    Parses a Telegram link and returns a tuple (link_type, identifier).
    link_type can be 'public' or 'private'.
    For 'public', identifier is the username.
    For 'private', identifier is the invite hash.
    Returns (None, None) if parsing fails.
    """
    link = link.strip()
    
    # Check for private invite links with '+' prefix (e.g. t.me/+hash)
    if '(?:t.me|telegram.me)/+' in link or '/+' in link:
        parts = link.split('/+')
        if len(parts) > 1:
            return 'private', parts[1].split('/')[0]
            
    # Check for private invite links with 'joinchat' prefix
    private_joinchat_match = re.search(r'(?:t\.me|telegram\.me)/joinchat/([a-zA-Z0-9_-]+)', link, re.IGNORECASE)
    if private_joinchat_match:
        return 'private', private_joinchat_match.group(1)
        
    # Public link: t.me/username
    public_match = re.search(r'(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,32})', link, re.IGNORECASE)
    if public_match:
        username = public_match.group(1)
        username_lower = username.lower()
        
        # Avoid matching common Telegram subpaths, email domains, reserved words, and bots
        junk_usernames = {
            'joinchat', 'share', 'addstickers', 'addlist', 'gmail', 'hotmail', 'yahoo', 'outlook',
            'icloud', 'mail', 'yandex', 'protonmail', 'proton', 'telegram', 'spambot', 'sticker',
            'gif', 'bot', 'username', 'ads', 'advertise', 'channel', 'group', 'chat', 'support',
            'help', 'admin', 'contact', 'info', 'service', 'feedback', 'terms', 'privacy'
        }
        
        if username_lower not in junk_usernames:
            # Skip usernames ending in "bot" or "_bot" to avoid resolving bots
            if not (username_lower.endswith('bot') or username_lower.endswith('_bot')):
                return 'public', username
            
    return None, None

def normalize_telegram_link(link: str) -> str:
    """
    Normalizes different Telegram link variations into a standard https://t.me/... format.
    """
    clean_link = link.strip()
    # Remove protocol prefix
    if clean_link.lower().startswith("https://"):
        clean_link = clean_link[8:]
    elif clean_link.lower().startswith("http://"):
        clean_link = clean_link[7:]
        
    # Standardize domain
    if clean_link.lower().startswith("telegram.me/"):
        clean_link = "t.me/" + clean_link[12:]
        
    # Re-prep protocol
    if not clean_link.lower().startswith("t.me/"):
        return f"https://t.me/{clean_link}"
    
    return f"https://{clean_link}"

def extract_contacts(text: str, description: str, channel_username: str) -> dict:
    """
    Extracts contact info (website, email, whatsapp, support usernames) from text & description.
    """
    contacts = {
        'website': None,
        'email': None,
        'whatsapp': None,
        'contact_username': None
    }
    
    combined_text = f"{text} {description}"
    
    # 1. Website: Matches HTTP/HTTPS URLs excluding telegram links
    web_match = re.search(
        r'https?://(?:www\.)?(?!(?:t\.me|telegram\.(?:me|dog|org|space)))([a-zA-Z0-9-]+\.[a-zA-Z]{2,6})[^\s]*',
        combined_text,
        re.IGNORECASE
    )
    if web_match:
        contacts['website'] = web_match.group(0).rstrip('.,;)!}"\'')
        
    # 2. Email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', combined_text)
    if email_match:
        contacts['email'] = email_match.group(0)
        
    # 3. WhatsApp
    # Match links like wa.me or standard phone patterns
    wa_link_match = re.search(
        r'(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp:)\+?([0-9]{9,15})',
        combined_text,
        re.IGNORECASE
    )
    if wa_link_match:
        contacts['whatsapp'] = f"+{wa_link_match.group(1)}"
    else:
        # Match standard phone formats with international codes
        phone_match = re.search(
            r'\+?(966|971|965|968|973|962|961|963|967|964|20|90|44|1)[0-9\s-]{7,15}',
            combined_text
        )
        if phone_match:
            num = re.sub(r'[\s-]', '', phone_match.group(0))
            if not num.startswith('+'):
                num = f"+{num}"
            contacts['whatsapp'] = num

    # 4. Telegram support/admin username
    contact_username = None
    
    # Define contact keywords list (Arabic + English) - Massive list covering all possible variations
    keywords_pattern = (
        r'للتواصل|تواصل|تواصلوا|راسل|راسلونا|راسلني|راسلنا|مراسلة|للمراسلة|'
        r'للاشتراك|اشتراك|للانضمام|انضمام|الادارة|الاداره|ادارة|اداره|'
        r'المشرف|مشرف|المشرفين|الدعم|دعم|المسؤول|المسئول|مسؤول|مسئول|'
        r'للاستفسار|استفسار|استفسارات|للاستفسارات|حسابي|خاص|الخاص|'
        r'تواصل معي|تواصل معنا|للتواصل معي|للتواصل معنا|راسلني على|راسلنا على|'
        r'ارسل لي|ارسل لنا|ارسل رسالة|كلمني|كلمني على|تواصل عبر|تواصلوا عبر|'
        r'سجل|التسجيل|للتشراك|للتحدث|تحدث|مطور|المطور|مطورين|'
        r'صاحب القناة|صاحب القناه|مالك القناة|مالك القناه|صاحب|مالك|المالك|الصاحب|'
        r'admin|administrator|support|contact|help|owner|manager|ceo|founder|creator|'
        r'inquiry|inquiries|subscribe|subscription|pm|dm|chat|personal|me|contactme|contactus|'
        r'messageme|reachme|reachus|writeme|writeus|askme|tg|tele|telegram'
    )
    
    # Usernames list to skip during fallback extraction (bots, channels, channels terms)
    skip_usernames = {
        'vip', 'premium', 'joinchat', 'channel', 'bot', 'ads', 'link', 'group', 'telegram', 
        'robot', 'signals', 'crypto', 'forex', 'arabic', 'trade', 'trading', 'chart', 'charts', 
        'alerts', 'alert', 'course', 'courses', 'education', 'academy', 'hub', 'capital', 'fund', 
        'fx', 'gold', 'signal', 'goldfx', 'team', 'club', 'official', 'news', 'fxsignals', 'system',
        'user', 'adminbot', 'helper', 'supportbot', 'channelbot', 'addstickers', 'share',
        'addlist', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i'
    }

    def _clean_cand(u_str):
        if not u_str:
            return ""
        c = u_str.strip().lstrip('@').lstrip('/').rstrip('.,;:)!?*~`"\'')
        for glued in ['whatsup', 'whatsapp', 'telegram', 'tele', 'vipsignal', 'channel', 'group']:
            if c.lower().endswith(glued) and len(c) > len(glued) + 3:
                c = c[:-len(glued)]
                break
        while c.endswith('_') and len(c) > 3:
            c = c[:-1]
        while c.startswith('_') and len(c) > 3:
            c = c[1:]
        return c.strip()
    
    # A. Search description first (official channel biography) - Check both @ and t.me/ formats
    match_desc_fwd = re.search(r'(?:' + keywords_pattern + r')\s*[:\-\x20]{1,10}(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})', description or '', re.IGNORECASE)
    if match_desc_fwd:
        cand = _clean_cand(match_desc_fwd.group(1))
        if cand.lower() != channel_username.lower() and cand.lower() not in skip_usernames:
            contact_username = cand
            
    if not contact_username:
        match_desc_bwd = re.search(r'(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})\s*[:\-\x20]{1,10}(?:' + keywords_pattern + r')', description or '', re.IGNORECASE)
        if match_desc_bwd:
            cand = _clean_cand(match_desc_bwd.group(1))
            if cand.lower() != channel_username.lower() and cand.lower() not in skip_usernames:
                contact_username = cand
                
    if not contact_username and description:
        # Fallback 1: any t.me link in description
        all_desc_tme = re.findall(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{3,35})', description, re.IGNORECASE)
        for raw in all_desc_tme:
            cand = _clean_cand(raw)
            if cand.lower() != channel_username.lower() and cand.lower() not in skip_usernames and not cand.startswith('+'):
                contact_username = cand
                break
                
    if not contact_username and description:
        # Fallback 2: any username in description
        all_desc = re.findall(r'@([a-zA-Z0-9_]{3,35})', description)
        for raw in all_desc:
            cand = _clean_cand(raw)
            if cand.lower() != channel_username.lower() and cand.lower() not in skip_usernames:
                contact_username = cand
                break
                    
    # B. If not found in description, search in the message logs text
    if not contact_username:
        match_txt_fwd = re.search(r'(?:' + keywords_pattern + r')\s*[:\-\x20]{1,10}(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})', text or '', re.IGNORECASE)
        if match_txt_fwd:
            cand = _clean_cand(match_txt_fwd.group(1))
            if cand.lower() != channel_username.lower() and cand.lower() not in skip_usernames:
                contact_username = cand
                
    if not contact_username:
        match_txt_bwd = re.search(r'(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})\s*[:\-\x20]{1,10}(?:' + keywords_pattern + r')', text or '', re.IGNORECASE)
        if match_txt_bwd:
            cand = _clean_cand(match_txt_bwd.group(1))
            if cand.lower() != channel_username.lower() and cand.lower() not in skip_usernames:
                contact_username = cand

    if not contact_username and text:
        # Fallback: any t.me link in text
        all_txt_tme = re.findall(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{3,35})', text, re.IGNORECASE)
        for raw in all_txt_tme:
            cand = _clean_cand(raw)
            if cand.lower() != channel_username.lower() and cand.lower() not in skip_usernames and not cand.startswith('+'):
                contact_username = cand
                break

    if not contact_username and text:
        # Fallback: any @username in text
        all_text_usernames = re.findall(r'@([a-zA-Z0-9_]{3,35})', text)
        for raw in all_text_usernames:
            cand = _clean_cand(raw)
            if cand.lower() != channel_username.lower() and cand.lower() not in skip_usernames:
                contact_username = cand
                break
                        
    if contact_username:
        contacts['contact_username'] = contact_username
        
    return contacts


def calculate_arabic_metrics(text: str, messages: list) -> tuple:
    """
    Calculates rules-based Arabic language metrics without AI.
    Returns (char_pct, word_pct, msg_ratio, final_avg_ratio).
    """
    # Regex for Arabic Unicode script ranges
    arabic_regex = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    
    # 1. Arabic Character Percentage
    # Exclude spaces and punctuation, count total letters/digits vs Arabic script
    total_letters = len(re.findall(r'[a-zA-Z0-9\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', text))
    arabic_letters = len(arabic_regex.findall(text))
    char_pct = (arabic_letters / total_letters * 100) if total_letters > 0 else 0.0
    
    # 2. Arabic Word Percentage
    words = text.split()
    arabic_words = sum(1 for w in words if arabic_regex.search(w))
    word_pct = (arabic_words / len(words) * 100) if words else 0.0
    
    # 3. Recent Message Arabic Ratio
    msg_count = len(messages)
    arabic_msgs = 0
    for msg in messages:
        if msg.text and arabic_regex.search(msg.text):
            arabic_msgs += 1
    msg_ratio = (arabic_msgs / msg_count * 100) if msg_count > 0 else 0.0
    
    # Final combined ratio (simple average of the three percentages)
    final_ratio = (char_pct + word_pct + msg_ratio) / 3.0
    
    return int(char_pct), int(word_pct), int(msg_ratio), int(final_ratio)


def calculate_arabic_score(title: str, description: str, sample_text: str, messages: list, contacts: dict) -> int:
    """
    Calculates 0-100 score:
    - Arabic Title: +20
    - Arabic Description: +20
    - Arabic Messages: +40
    - Arabic Contact Info: +20
    """
    arabic_regex = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    
    # 1. Arabic Title (+20)
    title_score = 20 if (title and arabic_regex.search(title)) else 0
    
    # 2. Arabic Description (+20)
    desc_score = 20 if (description and arabic_regex.search(description)) else 0
    
    # 3. Arabic Messages (+40)
    msg_count = len(messages)
    arabic_msgs = 0
    for msg in messages:
        if msg.text and arabic_regex.search(msg.text):
            arabic_msgs += 1
    msg_ratio = (arabic_msgs / msg_count) if msg_count > 0 else 0.0
    msg_score = int(msg_ratio * 40)
    
    # 4. Arabic Contacts (+20)
    contact_score = 0
    whatsapp_num = contacts.get('whatsapp') or ''
    # GCC/Egypt: +966, +971, +965, +968, +973, +20, +974
    is_gulf_or_egypt = any(whatsapp_num.startswith(prefix) for prefix in ["+966", "+971", "+965", "+968", "+973", "+20", "+974"])
    
    contact_username = contacts.get('contact_username') or ''
    support_keywords_found = bool(re.search(r'(للتواصل|الدعم|الادارة|تواصل|توصيات|قروب)', f"{sample_text} {description}"))
    
    if is_gulf_or_egypt:
        contact_score = 20
    elif support_keywords_found or (contact_username and (title_score > 0 or desc_score > 0)):
        contact_score = 20
    elif contact_username or whatsapp_num or contacts.get('website'):
        if title_score > 0 or desc_score > 0:
            contact_score = 20
            
    return min(100, title_score + desc_score + msg_score + contact_score)


def calculate_region_score(title: str, description: str, sample_text: str, contacts: dict) -> int:
    """
    GCC / Egypt Market Boost:
    Saudi Arabia, UAE, Kuwait, Qatar, Bahrain, Oman, Egypt.
    """
    score = 0
    combined_text = f"{title} {description} {sample_text}".lower()
    
    countries = {
        'saudi': ["السعودية", "سعودي", "سعودية", "ksa", "+966"],
        'uae': ["الإمارات", "اماراتي", "اماراتية", "دبي", "أبوظبي", "uae", "+971"],
        'kuwait': ["الكويت", "كويتي", "كويتية", "kuwait", "+965"],
        'qatar': ["قطر", "قطري", "قطرية", "qatar", "+974"],
        'bahrain': ["البحرين", "بحريني", "بحرينية", "bahrain", "+973"],
        'oman': ["عمان", "عماني", "عمانية", "oman", "+968"],
        'egypt': ["مصر", "مصري", "مصرية", "egypt", "+20"]
    }
    
    whatsapp_num = contacts.get('whatsapp') or ''
    
    matched_countries = set()
    for country, keywords in countries.items():
        for kw in keywords:
            if kw.startswith("+"):
                if whatsapp_num.startswith(kw):
                    matched_countries.add(country)
                    score += 40
            else:
                if kw in combined_text:
                    matched_countries.add(country)
                    
    score += len(matched_countries) * 20
    return min(100, score)


def calculate_forex_intent_score(
    title: str,
    description: str,
    messages: list,
    contacts: dict,
    discovery_method: str = ""
) -> int:
    """
    STRICT Points-Based Forex Intent Score Engine (0-100).
    Guarantees that a qualified lead is genuinely a Forex/Gold/Indices
    Arabic recommendation, analysis, or account management channel.
    
    1. Forex Core: Max 40 points. (0 if no core forex keywords found).
    2. Arabic Signals & Analysis: Max 30 points. (0 if no Arabic signal/analysis keywords found).
    3. Ecosystem & Business: Max 20 points.
    4. Contacts & Legitimacy: Max 10 points.
    """
    combined = f"{title} {description}".lower()
    msgs_text = " ".join(m.text for m in messages if m.text).lower()
    full_text = f"{combined} {msgs_text}"

    # 1. Forex Core (Max 40 points)
    forex_core_kws = [
        "forex", "فوركس", "xauusd", "eurusd", "gbpusd", "usdjpy", "audusd",
        "usdchf", "usdcad", "nzdusd", "gbpjpy", "eurjpy", "xagusd",
        "ذهب", "الذهب", "gold", "دهب", "الدهب", "ناسداك", "nasdaq",
        "us30", "داو جونز", "dow jones", "توصيات الذهب", "توصيات فوركس",
        "تحليل الذهب", "تحليل فوركس", "صفقات فوركس", "صفقات ذهب",
        "تداول العملات", "تداول الذهب", "تداول الفوركس"
    ]
    unique_forex_hits = sum(1 for kw in forex_core_kws if count_word(full_text, kw) > 0)
    forex_score = min(40, unique_forex_hits * 10)
    
    # If a channel has no Forex/Gold/Indices keyword, it gets a Forex intent score of 0
    if forex_score == 0:
        return 0

    # 2. Arabic Signals & Analysis (Max 30 points)
    arabic_signals_kws = [
        "توصية", "توصيات", "توصيه", "صفقة", "صفقات", "شراء", "بيع", "دخول",
        "الهدف", "الاهداف", "أهداف", "اهداف", "وقف الخسارة", "ضربت هدف", "ضربت استوب",
        "تحليل", "تحليلات", "تحليل فني", "مستويات", "شارت", "منزل التحليل",
        "إدارة حسابات", "ادارة حسابات", "إدارة محافظ", "ادارة محافظ", "نسخ صفقات", "نسخ تداول"
    ]
    unique_signal_hits = sum(1 for kw in arabic_signals_kws if count_word(full_text, kw) > 0)
    signals_score = min(30, unique_signal_hits * 5)

    # Must contain at least some recommendation/signal/analysis terms to pass
    if signals_score == 0:
        return 0

    # 3. Ecosystem & Business Models (Max 20 points)
    biz_score = 0
    has_vip = any(kw in full_text for kw in ["vip", "premium", "اشتراك", "باقات", "قناة خاصة"])
    has_ac_mgmt = any(kw in full_text for kw in ["إدارة حسابات", "ادارة حسابات", "إدارة محافظ", "ادارة محافظ", "نسخ صفقات", "نسخ تداول", "copy trading", "حساب ممول", "funded"])
    if has_vip:
        biz_score += 10
    if has_ac_mgmt:
        biz_score += 10

    # 4. Contacts & Trust (Max 10 points)
    trust_score = 0
    if contacts.get('whatsapp'):
        trust_score += 4
    if contacts.get('contact_username'):
        trust_score += 3
    if contacts.get('website'):
        trust_score += 3

    # Add discovery-method bonuses
    bonus = 0
    if discovery_method == "ad_exchange_feedback":
        bonus = 5
    elif discovery_method == "ad_copywriting_pattern":
        bonus = 10

    total_score = forex_score + signals_score + biz_score + trust_score + bonus
    return min(100, max(0, total_score))


def classify_forex_category(title: str, description: str, sample_text: str) -> str:
    """
    PHASE 6 — Forex Category Classifier.
    Classifies channels into predefined Forex business categories.
    """
    combined = f"{title} {description} {sample_text}".lower()

    # Priority order: most specific first
    if any(k in combined for k in ["حسابات ممولة", "شركات التمويل", "تحدي شركة تمويل", "funded accounts", "prop firms", "prop firm", "حساب ممول", "funded account", "funded trader", "تمويل تداول"]):
        return "prop_firms_arabic"

    if any(k in combined for k in ["صفقات سكالبينج", "سكالبينج", "scalping", "صفقات فيوتشر", "فيوتشر", "binance futures", "futures"]):
        return "crypto_scalping"

    if any(k in combined for k in ["توصيات كريبتو", "توصيات binance", "إشارات كريبتو", "crypto signals", "تحليل البيتكوين", "عملات رقمية", "حيتان الكريبتو", "تحليل btc", "توصيات sol", "whale alert", "بيتكوين", "بينانس", "منصة بينانس", "تداول الكريبتو", "تداول كريبتو", "liquidation", "smc crypto"]):
        return "crypto_signals"

    if any(k in combined for k in ["إدارة حسابات", "ادارة حسابات", "إدارة محافظ", "ادارة محافظ", "account management", "managed account"]):
        return "account_management"

    if any(k in combined for k in ["نسخ تداول", "نسخ صفقات", "copy trading", "copy trade", "copytrade"]):
        return "copy_trading"

    if any(k in combined for k in ["vip", "premium", "اشتراك", "باقات", "قناة مدفوعة", "اشترك"]):
        return "vip_services"

    if any(k in combined for k in ["الذهب", "ذهب", "gold", "xauusd", "xagusd", "توصيات ذهب", "تحليل الذهب", "صفقات ذهب"]):
        return "gold_signals"

    if any(k in combined for k in ["فوركس", "forex", "eurusd", "gbpusd", "usdjpy", "توصيات فوركس", "تداول العملات"]):
        return "forex_signals"

    if any(k in combined for k in ["تداول", "توصيات", "trading", "signals", "صفقات"]):
        return "forex_signals"

    if any(k in combined for k in ["تعليم", "تعليم تداول", "كورس", "دورة", "education", "course", "tutorial", "شرح"]):
        return "trading_education"

    return "unknown"

def count_word(text: str, word: str) -> int:
    """
    Counts occurrences of word as a whole word in text,
    ensuring it is not bordered by alphanumeric characters (English or Arabic).
    """
    pattern = r'(?<![a-zA-Z0-9_\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF])' + re.escape(word) + r'(?![a-zA-Z0-9_\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF])'
    return len(re.findall(pattern, text))


def check_is_forex(combined_text: str, is_group: bool = False) -> bool:
    """
    STRICT Forex and Trading niche filter.
    Requires explicit Forex/Trading indicators and Arabic recommendation/analysis terms.
    Always runs the absolute blacklist to eliminate false positives.
    """
    text_lower = combined_text.lower()
    
    # 1. Absolute Blacklist (always blocks for ALL channels - directory spam, member boost, gaming, quotes)
    absolute_blacklist = [
        # Directory/Boost spam
        "دعم قنوات", "تبادل نشر", "زيادة متابعين", "زيادة أعضاء", "زيادة اعضاء",
        "تبادل قنوات", "تبادل اشتراكات", "لدعم القنوات", "ارسل رابط القناه",
        "ترويج قنوات", "اضافة اعضاء", "بوت اضافة", "اعضاء مجانا", "اعضاء مجاناً",
        # Gaming / Gaming Accounts / Gaming Shop
        "fortnite", "pubg", "robux", "nitro", "giftcard", 
        "gift card", "gift cards", "steam key", "valorant", "free fire", "pubg mobile",
        "clash of clans", "clash royale", "game account", "game accounts", "game keys",
        "حسابات فورت", "حسابات ببجي", "شدات ببجي", "شحن العاب", "شحن ألعاب", "حسابات ألعاب",
        "حسابات العاب", "فيزا وهمية", "حسابات نتفليكس", "اشتراكات نتفلكس", "نتفلكس", "نتفليكس",
        "توزيع حسابات", "حسابات مجانية", "حسابات مجانيه", "شراء حسابات", "بيع حسابات",
        "فري فاير", "ببجي", "فورتنايت", "كلاش", "جواهر فري", "شدات ببجي", "شحن العاب",
        # Non-Forex Accounts/IPTV Shops
        "crunchyroll", "iptv",
        # Generic Underground Marketplace Terms (never used by legit Forex signal channels)
        "wtb", "wts", "wtt", "middleman", "middlemen", "escrow", 
        "ssn", "passport", "id card", "identity", "logs", "accs", "underground", "leaks", "leaked", "marketplace",
        "selling accounts", "buying accounts", "buy sell trade", "buy/sell/trade"
    ]
    if any(count_word(text_lower, bl) > 0 for bl in absolute_blacklist):
        return False

    # 2. Require presence of at least ONE core Forex/Gold/Indices keyword
    forex_core_kws = [
        "forex", "فوركس", "xauusd", "eurusd", "gbpusd", "usdjpy", "audusd", "usdchf", "usdcad",
        "nzdusd", "gbpjpy", "eurjpy", "xagusd", "ذهب", "الذهب", "gold", "دهب", "الدهب",
        "ناسداك", "nasdaq", "us30", "داو جونز", "dow jones", "توصيات الذهب", "توصيات فوركس",
        "تحليل الذهب", "تحليل فوركس", "صفقات فوركس", "صفقات ذهب", "تداول العملات", "تداول الذهب", "تداول لعملات", "تداول الفوركس"
    ]
    has_core_forex = any(count_word(text_lower, kw) > 0 for kw in forex_core_kws)
    if not has_core_forex:
        return False

    # 3. Require presence of at least TWO Arabic signals/recommendation/analysis keywords
    arabic_signals_kws = [
        "توصية", "توصيات", "توصيه", "صفقة", "صفقات", "شراء", "بيع", "دخول",
        "الهدف", "الاهداف", "أهداف", "اهداف", "وقف الخسارة", "ضربت هدف", "ضربت استوب",
        "تحليل", "تحليلات", "تحليل فني", "مستويات", "شارت", "منزل التحليل",
        "إدارة حسابات", "ادارة حسابات", "إدارة محافظ", "ادارة محافظ", "نسخ صفقات", "نسخ تداول"
    ]
    signal_hits_count = sum(count_word(text_lower, kw) for kw in arabic_signals_kws)
    required_hits = 5 if is_group else 3
    return signal_hits_count >= required_hits



class DatabaseHelper:
    """
    Manages connections and queries to the PostgreSQL CRM database.
    """
    def __init__(self, host, port, dbname, user, password):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.conn = None
        self.connect()

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                cursor_factory=RealDictCursor
            )
            self.conn.autocommit = True
            with self.conn.cursor() as cur:
                # Self-healing schema migrations — safe to run repeatedly
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS high_risk_fraud BOOLEAN DEFAULT FALSE;")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS discovery_source VARCHAR(255);")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS discovery_method VARCHAR(100);")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS arabic_score INT DEFAULT 0;")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS region_score INT DEFAULT 0;")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS forex_intent_score INT DEFAULT 0;")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS forex_category VARCHAR(50) DEFAULT 'unknown';")
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS depth INT DEFAULT 0;")
                # Fix the missing discovery_sources table (referenced in upsert_discovery_source)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS discovery_sources (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    source_type VARCHAR(50) NOT NULL,
                    source_name VARCHAR(255) UNIQUE NOT NULL,
                    keyword VARCHAR(255),
                    discovered_channels INT DEFAULT 0,
                    high_quality_leads INT DEFAULT 0,
                    last_discovery TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    quality_score INT DEFAULT 0
                );
                """)
            logging.info("Connected to PostgreSQL database successfully.")
        except Exception as e:
            logging.error(f"Failed to connect to PostgreSQL database: {e}")
            raise e

    def check_connection(self):
        if self.conn is None or self.conn.closed:
            logging.warning("Database connection is closed or missing. Reconnecting...")
            self.connect()

    def close(self):
        if self.conn:
            self.conn.close()
            logging.info("PostgreSQL database connection closed.")

    def add_to_blacklist(self, entity_username_or_link: str, reason: str):
        self.check_connection()
        query = """
        INSERT INTO blacklist (entity_username_or_link, reason, blacklisted_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (entity_username_or_link) 
        DO UPDATE SET reason = EXCLUDED.reason, blacklisted_at = CURRENT_TIMESTAMP;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (entity_username_or_link, reason))
            
            # Mark the blacklisted entity as rejected in the leads table instead of deleting it
            username = entity_username_or_link
            if '/' in username:
                username = username.split('/')[-1].strip()
            if username:
                cur.execute("UPDATE leads SET status = 'rejected' WHERE LOWER(channel_username) = LOWER(%s)", (username,))
                
        logging.info(f"Entity blacklisted: '{entity_username_or_link}' (Reason: {reason})")

    def is_blacklisted(self, entity_username_or_link: str) -> bool:
        self.check_connection()
        username = entity_username_or_link
        if '/' in username:
            username = username.split('/')[-1].strip()
            
        query = """
        SELECT EXISTS (
            SELECT 1 FROM blacklist 
            WHERE LOWER(entity_username_or_link) = LOWER(%s)
               OR LOWER(entity_username_or_link) = LOWER(%s)
               OR LOWER(entity_username_or_link) LIKE %s
        ) as is_blacklisted;
        """
        like_pattern = f"%/{username.lower()}"
        with self.conn.cursor() as cur:
            cur.execute(query, (entity_username_or_link, username, like_pattern))
            res = cur.fetchone()
            return res['is_blacklisted'] if res else False

    def is_verified_tier_a(self, channel_username: str) -> bool:
        self.check_connection()
        username = channel_username
        if '/' in username:
            username = username.split('/')[-1].strip()
            
        query = """
        SELECT EXISTS (
            SELECT 1 FROM leads 
            WHERE LOWER(channel_username) = LOWER(%s) 
              AND status IN ('new', 'contacted', 'closed') 
              AND tier = 'Tier_A'
        ) as is_verified;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (username,))
            res = cur.fetchone()
            return res['is_verified'] if res else False

    def upsert_lead(self, channel_username: str, member_count: int, description: str, language: str,
                    arabic_ratio: int, website: str, email: str, whatsapp: str, contact_username: str,
                    is_group: bool, marketplace_score: int, vip: bool, premium: bool, subscription: bool,
                    monthly_plans: bool, yearly_plans: bool, account_management: bool, copy_trading: bool,
                    funded_accounts: bool, usdt_payments: bool, binance_payments: bool,
                    lead_score: int, tier: str, ai_confidence: int, last_activity,
                    discovery_source: str = None, discovery_method: str = None,
                    arabic_score: int = 0, region_score: int = 0, status: str = 'new',
                    forex_intent_score: int = 0, forex_category: str = 'unknown',
                    high_risk_fraud: bool = False, depth: int = 0):
        self.check_connection()
        query = """
        INSERT INTO leads (
            channel_username, member_count, description, language, arabic_ratio, website, email, whatsapp, 
            contact_username, is_group, marketplace_score, vip, premium, subscription, monthly_plans,
            yearly_plans, account_management, copy_trading, funded_accounts, usdt_payments, binance_payments,
            lead_score, tier, ai_confidence, status, last_scan, last_activity, discovery_source, discovery_method,
            arabic_score, region_score, forex_intent_score, forex_category, high_risk_fraud, depth
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (channel_username) 
        DO UPDATE SET 
            member_count = EXCLUDED.member_count,
            description = EXCLUDED.description,
            language = EXCLUDED.language,
            arabic_ratio = EXCLUDED.arabic_ratio,
            website = EXCLUDED.website,
            email = EXCLUDED.email,
            whatsapp = EXCLUDED.whatsapp,
            contact_username = EXCLUDED.contact_username,
            is_group = EXCLUDED.is_group,
            marketplace_score = EXCLUDED.marketplace_score,
            vip = EXCLUDED.vip,
            premium = EXCLUDED.premium,
            subscription = EXCLUDED.subscription,
            monthly_plans = EXCLUDED.monthly_plans,
            yearly_plans = EXCLUDED.yearly_plans,
            account_management = EXCLUDED.account_management,
            copy_trading = EXCLUDED.copy_trading,
            funded_accounts = EXCLUDED.funded_accounts,
            usdt_payments = EXCLUDED.usdt_payments,
            binance_payments = EXCLUDED.binance_payments,
            lead_score = EXCLUDED.lead_score,
            tier = EXCLUDED.tier,
            ai_confidence = EXCLUDED.ai_confidence,
            status = EXCLUDED.status,
            last_scan = CURRENT_TIMESTAMP,
            last_activity = EXCLUDED.last_activity,
            discovery_source = COALESCE(EXCLUDED.discovery_source, leads.discovery_source),
            discovery_method = COALESCE(EXCLUDED.discovery_method, leads.discovery_method),
            arabic_score = EXCLUDED.arabic_score,
            region_score = EXCLUDED.region_score,
            forex_intent_score = EXCLUDED.forex_intent_score,
            forex_category = EXCLUDED.forex_category,
            high_risk_fraud = EXCLUDED.high_risk_fraud;
            -- Note: depth is intentionally NOT updated on conflict to preserve original discovery depth
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (
                channel_username, member_count, description, language, arabic_ratio, website, email, whatsapp,
                contact_username, is_group, marketplace_score, vip, premium, subscription, monthly_plans,
                yearly_plans, account_management, copy_trading, funded_accounts, usdt_payments, binance_payments,
                lead_score, tier, ai_confidence, status, last_activity, discovery_source, discovery_method,
                arabic_score, region_score, forex_intent_score, forex_category, high_risk_fraud, depth
            ))
        logging.info(f"Lead upserted: @{channel_username} | Score:{lead_score} Forex:{forex_intent_score} Arabic:{arabic_score} Cat:{forex_category} Tier:{tier} Fraud:{high_risk_fraud} Depth:{depth}")

    def upsert_group_stats(self, group_username: str, marketplace_score: int):
        self.check_connection()
        query = """
        INSERT INTO leads (channel_username, is_group, marketplace_score, status, discovered_at, last_scan)
        VALUES (%s, TRUE, %s, 'new', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (channel_username) 
        DO UPDATE SET is_group = TRUE, marketplace_score = EXCLUDED.marketplace_score, last_scan = CURRENT_TIMESTAMP;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (group_username, marketplace_score))
        logging.info(f"Group stats upserted: @{group_username} (Marketplace Score: {marketplace_score}%)")

    def upsert_group_metrics(self, group_id: str, messages_scanned: int, mentions_count: int, telegram_links_count: int, advertisements_count: int, marketplace_score: int):
        self.check_connection()
        with self.conn.cursor() as cur:
            cur.execute("UPDATE leads SET is_group = TRUE, marketplace_score = %s WHERE id = %s", (marketplace_score, group_id))
            
        query = """
        INSERT INTO group_metrics (group_id, messages_scanned, mentions_count, telegram_links_count, advertisements_count, marketplace_score, last_scan)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (group_id) 
        DO UPDATE SET 
            messages_scanned = EXCLUDED.messages_scanned,
            mentions_count = EXCLUDED.mentions_count,
            telegram_links_count = EXCLUDED.telegram_links_count,
            advertisements_count = EXCLUDED.advertisements_count,
            marketplace_score = EXCLUDED.marketplace_score,
            last_scan = CURRENT_TIMESTAMP;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (group_id, messages_scanned, mentions_count, telegram_links_count, advertisements_count, marketplace_score))
        logging.info(f"Group metrics upserted for group ID {group_id}: (Score: {marketplace_score}%)")

    def upsert_channel_keywords(self, channel_id: str, keyword_freqs: dict):
        self.check_connection()
        query = """
        INSERT INTO channel_keywords (channel_id, keyword, frequency, last_updated)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (channel_id, keyword) 
        DO UPDATE SET 
            frequency = channel_keywords.frequency + EXCLUDED.frequency,
            last_updated = CURRENT_TIMESTAMP;
        """
        with self.conn.cursor() as cur:
            for kw, freq in keyword_freqs.items():
                cur.execute(query, (channel_id, kw, freq))

    def get_incoming_graph_count(self, channel_id: str) -> int:
        self.check_connection()
        query = "SELECT COUNT(*) as count FROM channel_graph WHERE target_channel_id = %s"
        with self.conn.cursor() as cur:
            cur.execute(query, (channel_id,))
            res = cur.fetchone()
            if res:
                return res['count']
        return 0

    def insert_post(self, channel_username: str, message_id: int, message_text: str, timestamp):
        self.check_connection()
        query = """
        INSERT INTO channel_posts (channel_username, message_id, message_text, timestamp)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (channel_username, message_id, timestamp) DO NOTHING;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (channel_username, message_id, message_text, timestamp))

    def get_lead_id_by_username(self, channel_username: str):
        self.check_connection()
        query = "SELECT id FROM leads WHERE channel_username = %s"
        with self.conn.cursor() as cur:
            cur.execute(query, (channel_username,))
            res = cur.fetchone()
            if res:
                return res['id']
        return None

    def insert_stub_lead(self, channel_username: str, depth: int = 0, discovery_source: str = None):
        self.check_connection()
        # Returns the UUID of the newly created or existing stub lead.
        # depth and discovery_source are only set on INSERT (not updated on conflict
        # to preserve the original discovery context).
        query = """
        INSERT INTO leads (channel_username, status, discovered_at, last_scan, depth, discovery_source)
        VALUES (%s, 'new', CURRENT_TIMESTAMP, NULL, %s, %s)
        ON CONFLICT (channel_username) 
        DO UPDATE SET channel_username = EXCLUDED.channel_username
        RETURNING id;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (channel_username, depth, discovery_source))
            res = cur.fetchone()
            if res:
                return res['id']
        return None

    def get_channels_for_graph_expansion(self, batch_size: int = 15, max_depth: int = 5) -> list:
        """
        Returns channels and groups ready for deep graph expansion by graph_expander.py.
        Exposed here so graph_expander can use the same DatabaseHelper instance.
        """
        self.check_connection()
        query = """
        SELECT
            channel_username,
            COALESCE(lead_score, 0) AS score,
            COALESCE(depth, 0) AS depth,
            is_group,
            last_scan,
            COALESCE(marketplace_score, 0) AS marketplace_score
        FROM leads
        WHERE
            status NOT IN ('rejected')
            AND COALESCE(depth, 0) < %(max_depth)s
            AND (
                last_scan IS NULL
                OR (
                    is_group = FALSE AND (
                        CASE
                            WHEN COALESCE(lead_score, 0) > 80 THEN last_scan < NOW() - INTERVAL '3 days'
                            WHEN COALESCE(lead_score, 0) > 60 THEN last_scan < NOW() - INTERVAL '7 days'
                            ELSE last_scan < NOW() - INTERVAL '14 days'
                        END
                    )
                )
                OR (
                    is_group = TRUE AND (
                        CASE
                            WHEN COALESCE(marketplace_score, 0) > 60 THEN last_scan < NOW() - INTERVAL '1 day'
                            WHEN COALESCE(marketplace_score, 0) > 30 THEN last_scan < NOW() - INTERVAL '3 days'
                            ELSE last_scan < NOW() - INTERVAL '7 days'
                        END
                    )
                )
            )
        ORDER BY
            CASE WHEN is_group = FALSE THEN COALESCE(lead_score, 0) ELSE COALESCE(marketplace_score, 0) END DESC,
            COALESCE(last_scan, '2000-01-01') ASC
        LIMIT %(batch_size)s;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, {"max_depth": max_depth, "batch_size": batch_size})
                return cur.fetchall()
        except Exception as e:
            logging.error(f"Error querying channels for graph expansion: {e}", exc_info=True)
            return []

    def insert_relationship(self, source_id: str, target_id: str, relation_type: str):
        self.check_connection()
        query = """
        INSERT INTO channel_graph (source_channel_id, target_channel_id, relation_type, created_at)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (source_channel_id, target_channel_id) 
        DO UPDATE SET relation_type = EXCLUDED.relation_type;
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (source_id, target_id, relation_type))

    def upsert_discovery_source(self, source_type: str, source_name: str, keyword: str, is_high_quality: bool):
        self.check_connection()
        query = """
        INSERT INTO discovery_sources (source_type, source_name, keyword, discovered_channels, high_quality_leads, last_discovery, quality_score)
        VALUES (%s, %s, %s, 1, %s, CURRENT_TIMESTAMP, %s)
        ON CONFLICT (source_name)
        DO UPDATE SET
            discovered_channels = discovery_sources.discovered_channels + 1,
            high_quality_leads = discovery_sources.high_quality_leads + EXCLUDED.high_quality_leads,
            last_discovery = CURRENT_TIMESTAMP,
            quality_score = CASE 
                WHEN (discovery_sources.discovered_channels + 1) > 0 THEN
                    CAST(((discovery_sources.high_quality_leads + EXCLUDED.high_quality_leads) * 100.0 / (discovery_sources.discovered_channels + 1)) AS INT)
                ELSE 0
            END;
        """
        hq_val = 1 if is_high_quality else 0
        quality_score_init = 100 if is_high_quality else 0
        with self.conn.cursor() as cur:
            cur.execute(query, (source_type, source_name, keyword, hq_val, quality_score_init))
            
            # Boost the source itself if it yields high-quality Arabic Forex channels (Phase 8 Learning)
            if is_high_quality:
                if source_type == 'group':
                    cur.execute("UPDATE leads SET marketplace_score = LEAST(100, COALESCE(marketplace_score, 0) + 10) WHERE channel_username = %s AND is_group = TRUE", (source_name,))
                elif source_type == 'channel':
                    cur.execute("UPDATE leads SET lead_score = LEAST(100, COALESCE(lead_score, 0) + 10) WHERE channel_username = %s AND is_group = FALSE", (source_name,))


class LeadValidator:
    """
    Worker B (The Validator) implementation with AI analysis and feedback crawls.
    """
    def __init__(self):
        load_dotenv()
        
        # Redis
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_db = int(os.getenv("REDIS_DB", 0))
        self.redis_password = os.getenv("REDIS_PASSWORD", None)
        
        # PostgreSQL
        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = int(os.getenv("DB_PORT", 5432))
        self.db_name = os.getenv("DB_NAME", "leadhunter_db")
        self.db_user = os.getenv("DB_USER", "postgres")
        self.db_password = os.getenv("DB_PASSWORD", "")
        
        # AI/Gemini integration is completely removed to operate autonomously and cost-free.
        self.ai_enabled = False
            
        self.redis_conn = None
        self.db_helper = None
        self.tg_manager = None
        self.session_name = os.getenv("SESSION_VALIDATOR", "validator_session")
        self.shutdown_event = asyncio.Event()

        # Outreach engine modules (initialized in start() after Redis/DB connection)
        self.outreach_metrics = None
        self.account_health_mgr = None
        self.adaptive_throttle = None
        self.circuit_breaker = None
        self.backpressure_mgr = None
        self.reconciliation_mgr = None

    def is_all_sessions_rate_limited(self) -> bool:
        """Check if ALL Telegram sessions are currently rate-limited."""
        import time
        if not self.redis_conn or not self.tg_manager or not hasattr(self.tg_manager, 'accounts'):
            return False
        for acc in self.tg_manager.accounts:
            name = acc.get("session_name")
            if not name:
                continue
            until_ts = self.redis_conn.get(f"health:{name}:rate_limited_until")
            if not until_ts:
                return False  # This session is available
            try:
                if time.time() >= float(until_ts):
                    return False  # Rate limit expired
            except ValueError:
                return False
        return True  # All sessions are blocked

    def check_rescan_cooldown(self, username: str) -> bool:
        """
        Checks if the channel or group has been scanned recently.
        Returns True if the entity is still in cooldown and should NOT be rescanned.
        """
        self.db_helper.check_connection()
        query = "SELECT last_scan, lead_score, marketplace_score, is_group FROM leads WHERE channel_username = %s"
        try:
            with self.db_helper.conn.cursor() as cur:
                cur.execute(query, (username,))
                res = cur.fetchone()
                if not res:
                    return False # No prior record, scan immediately
                
                last_scan = res['last_scan']
                is_group = res['is_group']
                
                # Determine score to use for cooldown calculation
                score = None
                if is_group:
                    score = res['marketplace_score']
                else:
                    score = res['lead_score']
                    
                if not last_scan:
                    return False
                    
                # Calculate required cooldown based on scan priority engine
                if score is None:
                    cooldown = timedelta(hours=1)  # stubs retry in 1 hour
                elif score > 80:
                    cooldown = timedelta(days=1)   # scan every 24h
                elif score > 60:
                    cooldown = timedelta(days=3)   # scan every 3 days
                elif score > 40:
                    cooldown = timedelta(days=7)   # scan every 7 days
                else:
                    cooldown = timedelta(days=30)  # scan every 30 days
                    
                now = datetime.now(timezone.utc)
                if last_scan.tzinfo is None:
                    last_scan = last_scan.replace(tzinfo=timezone.utc)
                    
                if (now - last_scan) < cooldown:
                    logging.info(f"Entity @{username} is in cooldown (Score/Marketplace: {score}, Last Scan: {last_scan}). Skipping rescan.")
                    return True
        except Exception as e:
            logging.error(f"Error checking rescan cooldown for {username}: {e}")
            
        return False

    @staticmethod
    def parse_views_value(val_text: str) -> int:
        val_text = val_text.strip().upper()
        if not val_text:
            return 0
        try:
            val_text = val_text.replace(",", "")
            if val_text.endswith("K"):
                return int(float(val_text[:-1]) * 1000)
            elif val_text.endswith("M"):
                return int(float(val_text[:-1]) * 1000000)
            else:
                return int(float(val_text))
        except Exception:
            return 0

    def check_username_via_http(self, username: str) -> dict:
        """
        Checks username via public HTTP web preview to get basic channel metadata.
        Does not use Telegram API.
        """
        url = f"https://t.me/s/{username}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        result = {
            "exists": False,
            "is_channel": False,
            "is_group": False,
            "title": "",
            "description": "",
            "member_count": 0,
            "avg_views": 0,
            "status_code": 0
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            result["status_code"] = resp.status_code
            if resp.status_code != 200:
                return result
                
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Extract og:title and og:description
            title_tag = soup.find("meta", property="og:title")
            title = title_tag["content"] if title_tag else ""
            
            desc_tag = soup.find("meta", property="og:description")
            desc = desc_tag["content"] if desc_tag else ""
            
            # If title is placeholder/missing or non-existent
            if not title or title == f"Telegram: Contact @{username}":
                if not desc:
                    return result
                    
            result["exists"] = True
            result["title"] = title
            result["description"] = desc
            
            # Check if it is a public channel/group preview (contains tgme_channel_info or tgme_page_extra)
            info_div = soup.find("div", class_="tgme_channel_info")
            extra_div = soup.find("div", class_="tgme_page_extra")
            if info_div or extra_div:
                result["is_channel"] = True
                
                # Parse member/subscriber count from info counters
                counters = soup.find_all("div", class_="tgme_channel_info_counter")
                for counter in counters:
                    val_tag = counter.find("span", class_="counter_value")
                    type_tag = counter.find("span", class_="counter_type")
                    if val_tag and type_tag:
                        type_text = type_tag.get_text().strip().lower()
                        if "subscriber" in type_text or "member" in type_text:
                            val_text = val_tag.get_text().strip().upper()
                            try:
                                if val_text.endswith("K"):
                                    result["member_count"] = int(float(val_text[:-1]) * 1000)
                                elif val_text.endswith("M"):
                                    result["member_count"] = int(float(val_text[:-1]) * 1000000)
                                else:
                                    result["member_count"] = int(val_text.replace(",", ""))
                            except Exception:
                                pass
                                
                # Parse member/subscriber count from extra div (common in public groups or mobile previews)
                if extra_div:
                    extra_text = extra_div.get_text().strip().lower()
                    if "members" in extra_text:
                        result["is_group"] = True
                    for term in ["members", "subscribers"]:
                        if term in extra_text:
                            parts = extra_text.split(term)
                            num_part = parts[0].strip()
                            num_str = "".join([c for c in num_part if c.isdigit()])
                            if num_str:
                                try:
                                    result["member_count"] = int(num_str)
                                except Exception:
                                    pass
                
                # Parse post views
                view_tags = soup.find_all("span", class_="tgme_widget_message_views")
                views_list = []
                for tag in view_tags:
                    txt = tag.get_text().strip()
                    parsed = self.parse_views_value(txt)
                    if parsed > 0:
                        views_list.append(parsed)
                result["avg_views"] = int(sum(views_list) / len(views_list)) if views_list else 0
        except Exception as e:
            logging.error(f"Error in check_username_via_http for @{username}: {e}")
            
        return result

    
    async def process_http_fallback(self, actual_link, username, http_info, discovery_source, discovery_method, keyword):
        try:
            title = http_info.get("title", "")
            description = http_info.get("description", "")
            member_count = http_info.get("member_count", 0)
            is_group = http_info.get("is_group", False)
            
            # Hard rejection for low members
            if member_count < 100:
                logging.info(f"HTTP fallback: Channel @{username} rejected (HARD): low member count ({member_count} < 100).")
                self.db_helper.add_to_blacklist(actual_link, 'low_members')
                self.db_helper.upsert_lead(
                    channel_username=username, member_count=member_count, description=description,
                    language='English/Other', arabic_ratio=0, website='', email='', whatsapp='', contact_username='',
                    is_group=is_group, marketplace_score=0, vip=False, premium=False,
                    subscription=False, monthly_plans=False, yearly_plans=False,
                    account_management=False, copy_trading=False, funded_accounts=False,
                    usdt_payments=False, binance_payments=False, lead_score=0,
                    tier='Tier_D', ai_confidence=100, last_activity=None,
                    discovery_source=discovery_source, discovery_method=discovery_method,
                    arabic_score=0, region_score=0, status='rejected',
                    forex_intent_score=0, forex_category='unknown', high_risk_fraud=False
                )
                return True

            # Scrape messages from web preview
            url = f"https://t.me/s/{username}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            
            if resp.status_code != 200 or "tgme_widget_message_text" not in resp.text:
                logging.warning(f"HTTP fallback: Failed to fetch messages for @{username} (status: {resp.status_code})")
                return False
                
            soup = BeautifulSoup(resp.text, "html.parser")
            message_blocks = soup.find_all("div", class_="tgme_widget_message")
            
            messages = []
            for block in message_blocks:
                try:
                    msg_id = 0
                    if block.has_attr("data-post"):
                        msg_id = int(block["data-post"].split("/")[-1])
                        
                    text_div = block.find("div", class_="tgme_widget_message_text")
                    text = text_div.get_text().strip() if text_div else ""
                    
                    date_obj = None
                    time_tag = block.find("time")
                    if time_tag and time_tag.has_attr("datetime"):
                        date_obj = datetime.fromisoformat(time_tag["datetime"])
                        
                    views = 0
                    views_span = block.find("span", class_="tgme_widget_message_views")
                    if views_span:
                        views = self.parse_views_value(views_span.get_text().strip())
                        
                    if msg_id and date_obj:
                        class MockMessage:
                            def __init__(self, id, text, date, views):
                                self.id = id
                                self.text = text
                                self.date = date
                                self.views = views
                        messages.append(MockMessage(msg_id, text, date_obj, views))
                except Exception:
                    pass
            
            messages.sort(key=lambda x: x.date)
            
            # Parse average views for HTTP fallback
            channel_views = [msg.views for msg in messages if getattr(msg, 'views', 0) > 0]
            avg_views = int(sum(channel_views) / len(channel_views)) if channel_views else 0
            
            is_low_views = False
            is_medium_views_penalty = False
            if not is_group and member_count < 1000:
                if avg_views < 50:
                    is_low_views = True
                elif avg_views < 100:
                    is_medium_views_penalty = True

            if is_low_views:
                logging.info(f"HTTP fallback: Channel {actual_link} has low views ({avg_views}<50) for small channel. Saving as rejected.")
                self.db_helper.upsert_lead(
                    channel_username=username, member_count=member_count, description=description,
                    language='Other', arabic_ratio=0, website=None, email=None, whatsapp=None, contact_username=None,
                    is_group=is_group, marketplace_score=0, vip=False, premium=False,
                    subscription=False, monthly_plans=False, yearly_plans=False,
                    account_management=False, copy_trading=False, funded_accounts=False,
                    usdt_payments=False, binance_payments=False, lead_score=0,
                    tier='Tier_D', ai_confidence=100, last_activity=None,
                    discovery_source=discovery_source, discovery_method=discovery_method,
                    arabic_score=0, region_score=0,
                    status='rejected', forex_intent_score=0, forex_category='Unclassified',
                    high_risk_fraud=False
                )
                return True
            
            # Activity check
            is_inactive = False
            inactive_reason = ""
            if not messages:
                is_inactive = True
                inactive_reason = "No valid messages found in web preview"
            else:
                now = datetime.now(timezone.utc)
                msgs_72h = 0
                msgs_7d = 0
                for msg in messages:
                    msg_date = msg.date
                    if msg_date.tzinfo is None:
                        msg_date = msg_date.replace(tzinfo=timezone.utc)
                    age = now - msg_date
                    if age <= timedelta(hours=72):
                        msgs_72h += 1
                    if age <= timedelta(days=7):
                        msgs_7d += 1
                        
                if msgs_72h < 3:
                    is_inactive = True
                    inactive_reason = f"Only {msgs_72h} messages posted in the last 72 hours (minimum 3 required)"
                elif msgs_7d < 5:
                    is_inactive = True
                    inactive_reason = f"Only {msgs_7d} messages posted in the last 7 days (minimum 5 required)"
            
            if is_inactive:
                sample_text_list = [msg.text for msg in messages if msg.text]
                sample_text = " \n ".join(sample_text_list)
                combined_desc_text = f"{title} {description} {sample_text}"
                
                # Check forbidden keywords
                neg_regex = re.compile(r'(ارباح\s+مضمونة|أرباح\s+مضمونة|ربح\s+مضمون|استثمار\s+مضمون|ضمان\s+الربح|تعويض\s+الخسائر|تداول\s+بدون\s+مخاطرة)', re.IGNORECASE)
                has_forbidden = bool(neg_regex.search(combined_desc_text))
                
                # Check Arabic
                arabic_score = calculate_arabic_score(title, description, sample_text, messages, {})
                
                # Check Forex
                forex_intent_score = calculate_forex_intent_score(title, description, messages, {}, discovery_method)
                is_forex = check_is_forex(combined_desc_text) or forex_intent_score >= 30
                
                passes_inactive_gate = (is_forex and arabic_score >= 50 and not has_forbidden)
                
                if passes_inactive_gate:
                    logging.info(f"HTTP fallback: Inactive channel {actual_link} passed niche filters. Saving as low-tier qualified.")
                    self.db_helper.upsert_lead(
                        channel_username=username, member_count=member_count, description=f"Inactive channel: {inactive_reason}",
                        language='Arabic', arabic_ratio=100, website='', email='',
                        whatsapp='', contact_username='', is_group=is_group,
                        marketplace_score=0, vip=False, premium=False, subscription=False, monthly_plans=False,
                        yearly_plans=False, account_management=False, copy_trading=False, funded_accounts=False,
                        usdt_payments=False, binance_payments=False, lead_score=10, tier='Tier_D', ai_confidence=100,
                        last_activity=messages[-1].date.astimezone(timezone.utc) if messages else None,
                        discovery_source=discovery_source, discovery_method=discovery_method, arabic_score=arabic_score,
                        region_score=0, status='new', forex_intent_score=forex_intent_score, forex_category='unknown', high_risk_fraud=False
                    )
                else:
                    logging.info(f"HTTP fallback: Inactive channel {actual_link} failed niche filters (is_forex={is_forex}, arabic_score={arabic_score}, forbidden={has_forbidden}). Rejecting.")
                    self.db_helper.upsert_lead(
                        channel_username=username, member_count=member_count, description=f"Inactive non-forex channel: {inactive_reason}",
                        language='Other', arabic_ratio=0, website='', email='',
                        whatsapp='', contact_username='', is_group=is_group,
                        marketplace_score=0, vip=False, premium=False, subscription=False, monthly_plans=False,
                        yearly_plans=False, account_management=False, copy_trading=False, funded_accounts=False,
                        usdt_payments=False, binance_payments=False, lead_score=0, tier='Tier_D', ai_confidence=100,
                        last_activity=messages[-1].date.astimezone(timezone.utc) if messages else None,
                        discovery_source=discovery_source, discovery_method=discovery_method, arabic_score=arabic_score,
                        region_score=0, status='rejected', forex_intent_score=forex_intent_score, forex_category='unknown', high_risk_fraud=False
                    )
                return True
                
            sample_text_list = [msg.text for msg in messages if msg.text]
            sample_text = " \n ".join(sample_text_list)
            
            contacts = extract_contacts(sample_text, description, username)
            source_id = self.db_helper.insert_stub_lead(username)
            in_degree = self.db_helper.get_incoming_graph_count(source_id) if source_id else 0
            
            arabic_score = calculate_arabic_score(title, description, sample_text, messages, contacts)
            region_score = calculate_region_score(title, description, sample_text, contacts)
            forex_intent_score = calculate_forex_intent_score(title, description, messages, contacts, discovery_method)
            forex_category = classify_forex_category(title, description, sample_text)
            
            if arabic_score < 50:
                logging.info(f"HTTP fallback: Channel {actual_link} has low Arabic score ({arabic_score}<50). Saving as rejected.")
                self.db_helper.upsert_lead(
                    channel_username=username, member_count=member_count, description=description,
                    language='Other', arabic_ratio=0, website=None, email=None, whatsapp=None, contact_username=None,
                    is_group=is_group, marketplace_score=0, vip=False, premium=False,
                    subscription=False, monthly_plans=False, yearly_plans=False,
                    account_management=False, copy_trading=False, funded_accounts=False,
                    usdt_payments=False, binance_payments=False, lead_score=0,
                    tier='Tier_D', ai_confidence=100, last_activity=None,
                    discovery_source=discovery_source, discovery_method=discovery_method,
                    arabic_score=arabic_score, region_score=region_score,
                    status='rejected', forex_intent_score=forex_intent_score, forex_category=forex_category,
                    high_risk_fraud=False
                )
                return True

            is_scam = False
            signals_count = 0
            risk_mgmt_count = 0
            signal_keywords = ["buy", "sell", "شراء", "بيع", "entry", "tp", "target", "هدف", "أهداف", "xauusd", "توصية", "توصيات"]
            risk_keywords = ["وقف الخسارة", "إدارة المخاطر", "sl", "stop loss"]
            
            for msg in messages:
                if not msg.text:
                    continue
                msg_text_lower = msg.text.lower()
                if any(kw in msg_text_lower for kw in signal_keywords):
                    signals_count += 1
                if any(kw in msg_text_lower for kw in risk_keywords):
                    risk_mgmt_count += 1
                    
            combined_desc_text = f"{title} {description} {sample_text}"
            has_doubling_hype = "مضاعفة رأس المال" in combined_desc_text
            
            is_forex = check_is_forex(combined_desc_text) or forex_intent_score >= 35
            
            if is_forex and ((signals_count > 5 and risk_mgmt_count == 0) or has_doubling_hype):
                is_scam = True
                
            arabic_regex = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
            title_has_arabic = bool(arabic_regex.search(title))
            desc_has_arabic = bool(arabic_regex.search(description))
            
            arabic_chars = len(arabic_regex.findall(combined_desc_text))
            total_chars = len(combined_desc_text) if combined_desc_text else 1
            arabic_ratio = int((arabic_chars * 100.0) / total_chars)
            
            whatsapp_num = contacts['whatsapp'] or ''
            is_gulf_whatsapp = any(whatsapp_num.startswith(prefix) for prefix in ["+966", "+971", "+965", "+968", "+973", "+962"])
            
            has_vip_feature = any(kw in combined_desc_text.lower() for kw in ["vip", "premium", "اشتراك", "باقات", "عضوية"])
            has_ac_mgmt = any(kw in combined_desc_text.lower() for kw in ["إدارة حسابات", "ادارة حسابات", "إدارة محافظ", "ادارة محافظ", "نسخ صفقات", "copy trading", "نسخ تداول", "funded"])
            
            metadata = {
                'title_has_arabic': title_has_arabic,
                'desc_has_arabic': desc_has_arabic,
                'high_arabic_ratio': (arabic_ratio > 80),
                'is_gulf_whatsapp': is_gulf_whatsapp,
                'arabic_ratio': arabic_ratio,
                'confidence': 100,
                'vip': has_vip_feature,
                'premium': has_vip_feature,
                'subscription': has_vip_feature,
                'monthly_plans': has_vip_feature,
                'yearly_plans': has_vip_feature,
                'account_management': has_ac_mgmt,
                'copy_trading': has_ac_mgmt,
                'funded_accounts': has_ac_mgmt,
                'usdt_payments': any(kw in combined_desc_text.lower() for kw in ["usdt", "pay", "دفع"]),
                'binance_payments': any(kw in combined_desc_text.lower() for kw in ["binance", "بينانس"]),
                'is_private': (parse_telegram_link(actual_link)[0] == 'private')
            }
            
            keyword_freqs = {}
            for kw in ['VIP', 'Premium', 'اشتراك', 'اشتراكات', 'باقات', 'إدارة حسابات', 'نسخ تداول', 'نسخ صفقات', 'USDT', 'Binance']:
                keyword_freqs[kw] = combined_desc_text.lower().count(kw.lower())
                
            score = self.calculate_weighted_score(metadata, keyword_freqs, in_degree)
            if is_medium_views_penalty:
                score = min(10, score)
            if is_scam:
                score = max(0, score - 50)
                logging.warning(f"HTTP fallback: 🚨 SCAM / FRAUD DETECTED for @{username}. Dropping score by 50. New score: {score}")
                
            tier = self.classify_tier(score)
            
            passes_gate = (score >= 10 and forex_intent_score >= 30 and not is_scam)
            if not passes_gate:
                status_val = 'rejected'
                logging.info(f"HTTP fallback: Channel @{username} below gate (score={score}<10 or forex_intent={forex_intent_score}<30 or is_scam={is_scam}). Saving as rejected.")
            else:
                status_val = 'new'
                logging.info(f"HTTP fallback: Channel @{username} PASSED gate 🎉 Real CRM Lead! (score={score} forex_intent={forex_intent_score})")
                try:
                    payload = json.dumps({"link": actual_link})
                    self.redis_conn.rpush("user_join_queue", payload)
                    logging.info(f"User Joiner: Queued verified Forex channel {actual_link} from HTTP fallback for auto-join.")
                except Exception as q_err:
                    logging.warning(f"Failed to queue user join from HTTP fallback: {q_err}")
                
            last_activity_ts = messages[-1].date.astimezone(timezone.utc) if messages else None
            
            self.db_helper.upsert_lead(
                channel_username=username, member_count=member_count, description=description,
                language='Arabic', arabic_ratio=arabic_ratio,
                website=contacts['website'], email=contacts['email'], whatsapp=contacts['whatsapp'], contact_username=contacts['contact_username'],
                is_group=is_group, marketplace_score=0,
                vip=metadata['vip'], premium=metadata['premium'], subscription=metadata['subscription'],
                monthly_plans=metadata['monthly_plans'], yearly_plans=metadata['yearly_plans'],
                account_management=metadata['account_management'], copy_trading=metadata['copy_trading'],
                funded_accounts=metadata['funded_accounts'], usdt_payments=metadata['usdt_payments'],
                binance_payments=metadata['binance_payments'],
                lead_score=score, tier=tier, ai_confidence=100, last_activity=last_activity_ts,
                discovery_source=discovery_source, discovery_method=discovery_method,
                arabic_score=arabic_score, region_score=region_score,
                status=status_val, forex_intent_score=forex_intent_score, forex_category=forex_category,
                high_risk_fraud=is_scam
            )
            
            for msg in messages:
                self.db_helper.insert_post(username, msg.id, msg.text or "", msg.date.astimezone(timezone.utc))
                
            group_link = f"https://t.me/{username}"
            self.redis_conn.sadd("scavenged_groups_set", group_link)
            return True
            
        except Exception as e:
            logging.error(f"Error in process_http_fallback for @{username}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    async def get_entity_safe(self, link: str):
        """
        Resolves a link using GetEntity through Centralized Request Manager.
        """
        async def resolve(cl):
            logging.info(f"Resolving entity for: {link}")
            return await cl.get_entity(link)
        return await self.tg_manager.execute_request(self.session_name, resolve, shutdown_event=self.shutdown_event)

    async def join_or_get_private_entity(self, hash_code: str, raw_link: str):
        """
        Allows worker accounts (scavenger, radar, validator) to join private channels via ImportChatInviteRequest
        so they can resolve private entities, extract contact handles, and feed the Spider Graph Expander network.
        """
        try:
            entity = await self.get_entity_safe(raw_link)
            if entity:
                return entity
        except Exception:
            pass

        if self.redis_conn.sismember("invalid_private_hashes", hash_code):
            return None

        async def do_join(cl):
            from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
            from telethon.errors import UserAlreadyParticipantError, InviteHashExpiredError, InviteHashInvalidError, FloodWaitError
            try:
                logging.info(f"🕷️ Worker Spider Joiner: Attempting to join private chat invite hash '{hash_code}'...")
                res = await cl(ImportChatInviteRequest(hash_code))
                if hasattr(res, 'chats') and res.chats:
                    return res.chats[0]
            except UserAlreadyParticipantError:
                logging.info(f"🕷️ Worker Spider Joiner: Already participant in private hash '{hash_code}'. Resolving entity...")
                try:
                    check_res = await cl(CheckChatInviteRequest(hash_code))
                    if hasattr(check_res, 'chat'):
                        return check_res.chat
                except Exception:
                    pass
                return await cl.get_entity(raw_link)
            except (InviteHashExpiredError, InviteHashInvalidError) as inv_err:
                logging.warning(f"🕷️ Worker Spider Joiner: Invalid/Expired invite link '{hash_code}': {inv_err}")
                self.redis_conn.sadd("invalid_private_hashes", hash_code)
                return None
            except FloodWaitError as fw:
                logging.warning(f"🕷️ Worker Spider Joiner: FloodWait {fw.seconds}s on joining private hash '{hash_code}'.")
                raise fw
            except Exception as e:
                logging.warning(f"🕷️ Worker Spider Joiner: Note on joining private hash '{hash_code}': {e}")
                try:
                    return await cl.get_entity(raw_link)
                except Exception:
                    return None

        try:
            return await self.tg_manager.execute_request(self.session_name, do_join, shutdown_event=self.shutdown_event)
        except Exception as err:
            logging.warning(f"Failed to join or resolve private entity '{hash_code}': {err}")
            return None

    async def fetch_messages_safe(self, entity, limit=50):
        """
        Fetches the last 50 messages of a channel through Centralized Request Manager.
        """
        async def fetch(cl):
            logging.info(f"Fetching last {limit} messages for channel: {entity.id}")
            return await cl.get_messages(entity, limit=limit)
        return await self.tg_manager.execute_request(self.session_name, fetch, shutdown_event=self.shutdown_event)

    async def get_member_count_safe(self, entity):
        """
        Retrieves member count, falling back to GetFullChannelRequest if not present.
        """
        member_count = getattr(entity, 'participants_count', None)
        if member_count is not None:
            return member_count
            
        async def fetch_full(cl):
            logging.info(f"Fetching full channel details to get member count for {entity.id}")
            full_info = await cl(GetFullChannelRequest(entity))
            return full_info.full_chat.participants_count
            
        return await self.tg_manager.execute_request(self.session_name, fetch_full, shutdown_event=self.shutdown_event)

    def calculate_weighted_score(self, metadata: dict, kw_freqs: dict, in_degree: int) -> int:
        """
        Weighted Smart Lead Scoring Engine V4 (Business Signal Boost & High Arabic Forex Priority).
        """
        score = 0
        
        # 1. Keyword Frequency Score (up to 15 points)
        freq_sum = sum(kw_freqs.values())
        score += min(15, freq_sum)
        
        # 2. Member Count (up to 10 points)
        members = metadata.get('member_count', 0)
        if members > 50000:
            score += 10
        elif members > 20000:
            score += 7
        elif members > 5000:
            score += 4
            
        # 3. Posting Frequency (5 points)
        if metadata.get('active_posting'):
            score += 5
            
        # 4. Recent Activity (5 points)
        if metadata.get('recent_activity'):
            score += 5
            
        # 5. Website Presence (15 points - Phase 6 Boost)
        if metadata.get('website'):
            score += 15
            
        # 6. WhatsApp Presence (15 points - Phase 6 Boost)
        if metadata.get('whatsapp'):
            score += 15
            
        # 7. Telegram Contact (15 points - Phase 6 Boost)
        if metadata.get('contact_username'):
            score += 15
            
        # 8. VIP Indicators (15 points - Phase 6 Boost)
        if metadata.get('vip'):
            score += 15
            
        # 9. Subscription Indicators (15 points - Phase 6 Boost)
        if metadata.get('subscription') or metadata.get('monthly_plans') or metadata.get('yearly_plans'):
            score += 15
            
        # 10. Account Management (30 points - Phase 6 Boost)
        if metadata.get('account_management'):
            score += 30
            
        # 13. Private Channel Boost (+25 points)
        if metadata.get('is_private'):
            score += 25
            
        # 11. Copy Trading (20 points - Phase 6 Boost)
        if metadata.get('copy_trading'):
            score += 20
            
        # 11b. Funded Accounts (20 points - Phase 6 Boost)
        if metadata.get('funded_accounts'):
            score += 20
            
        # 12. Marketplace Exposure (up to 10 points)
        score += min(10, in_degree * 2)
        
        # Apply Arabic ranking boost (+15 points, capped at 100)
        if metadata.get('is_arabic'):
            score += 15
            
        # Additional Granular Arabic and Gulf Boosts (up to +25 additional points, capped at 100)
        if metadata.get('title_has_arabic'):
            score += 5
        if metadata.get('desc_has_arabic'):
            score += 5
        if metadata.get('high_arabic_ratio'):
            score += 10
        if metadata.get('is_gulf_whatsapp'):
            score += 5
            
        return min(100, max(0, score))

    def classify_tier(self, score: int) -> str:
        """
        Classifies leads into Tier_A, Tier_B, Tier_C, or Tier_D.
        """
        if score >= 75:
            return 'Tier_A'
        elif score >= 50:
            return 'Tier_B'
        elif score >= 25:
            return 'Tier_C'
        else:
            return 'Tier_D'

    async def process_link(self, link: str):
        """
        Resolves, scores, parses contacts, runs keyword frequencies, and updates CRM DB.
        All analysis is completely rules-based; AI dependencies are bypassed.
        """
        actual_link = link
        discovery_source = "unknown"
        discovery_method = "unknown"
        keyword = ""
        http_info = None
        try:
            # Unpack JSON payload if applicable
            if isinstance(link, str) and link.startswith("{") and link.endswith("}"):
                try:
                    data = json.loads(link)
                    actual_link = data.get("link", link)
                    discovery_source = data.get("source", "unknown")
                    discovery_method = data.get("method", "unknown")
                    keyword = data.get("keyword", "")
                except Exception:
                    pass
            
            # First extract name to run database caching check and get identifier/username
            link_type, identifier = parse_telegram_link(actual_link)
            if not link_type or not identifier:
                logging.info(f"Link {actual_link} failed parsing (invalid format or junk/email domain/bot). Skipping.")
                self.db_helper.add_to_blacklist(actual_link, 'invalid_link_format')
                return

            username = identifier
            is_gp = (link_type == 'private')

            # Fast check: is this link or username already blacklisted?
            if self.db_helper.is_blacklisted(actual_link):
                logging.info(f"Skipping validation for {actual_link} because it is already blacklisted. Updating database...")
                self.db_helper.upsert_lead(
                    channel_username=username,
                    member_count=0,
                    description="Blacklisted entity",
                    language="Non-Arabic",
                    arabic_ratio=0,
                    website='', email='', whatsapp='', contact_username='',
                    is_group=is_gp, marketplace_score=0, vip=False, premium=False,
                    subscription=False, monthly_plans=False, yearly_plans=False,
                    account_management=False, copy_trading=False, funded_accounts=False,
                    usdt_payments=False, binance_payments=False, lead_score=0,
                    tier='Tier_D', ai_confidence=100, last_activity=None,
                    discovery_source=discovery_source, discovery_method=discovery_method,
                    arabic_score=0, region_score=0, status='rejected',
                    forex_intent_score=0, forex_category='unknown', high_risk_fraud=False
                )
                return
            
            # Fast short-circuit: if the source is a rejected group, skip validation immediately to save API limits
            if discovery_source and discovery_source.lower() != "unknown":
                if self.redis_conn.sismember("rejected_groups_set", discovery_source.lower()):
                    logging.info(f"Skipping validation for {actual_link} because its source group @{discovery_source} is rejected. Updating database...")
                    self.db_helper.add_to_blacklist(actual_link, 'source_rejected')
                    self.db_helper.upsert_lead(
                        channel_username=username,
                        member_count=0,
                        description="Source group rejected",
                        language="Non-Arabic",
                        arabic_ratio=0,
                        website='', email='', whatsapp='', contact_username='',
                        is_group=is_gp, marketplace_score=0, vip=False, premium=False,
                        subscription=False, monthly_plans=False, yearly_plans=False,
                        account_management=False, copy_trading=False, funded_accounts=False,
                        usdt_payments=False, binance_payments=False, lead_score=0,
                        tier='Tier_D', ai_confidence=100, last_activity=None,
                        discovery_source=discovery_source, discovery_method=discovery_method,
                        arabic_score=0, region_score=0, status='rejected',
                        forex_intent_score=0, forex_category='unknown', high_risk_fraud=False
                    )
                    return
                    
            if link_type == 'public' and identifier:
                if self.check_rescan_cooldown(identifier):
                    # Cooldown hit, skip network API requests to protect account
                    return
                
                # Perform fast HTTP pre-filtering check
                logging.info(f"Performing HTTP pre-filter check for @{identifier}...")
                http_info = await asyncio.to_thread(self.check_username_via_http, identifier)
                
                # Check for HTTP rate limits (429) or failures, and bypass pre-filter to fall back to Telethon API
                status_code = http_info.get("status_code", 0)
                if status_code != 200:
                    logging.warning(f"HTTP pre-filter failed or rate-limited (status code: {status_code}) for @{identifier}. Bypassing HTTP pre-filter and falling back directly to Telethon API.")
                    http_info = {
                        "exists": True,
                        "is_channel": False,
                        "title": "",
                        "description": "",
                        "member_count": 999999,
                        "avg_views": 999999,
                        "status_code": status_code
                    }
                
                if not http_info["exists"]:
                    logging.info(f"HTTP filter: Username @{identifier} does not exist or is invalid. Rejecting immediately.")
                    self.db_helper.add_to_blacklist(actual_link, 'non_existent')
                    self.db_helper.upsert_lead(
                        channel_username=identifier,
                        member_count=0,
                        description="Entity does not exist (HTTP checked)",
                        language="Non-Arabic",
                        arabic_ratio=0,
                        website='', email='', whatsapp='', contact_username='',
                        is_group=is_gp, marketplace_score=0, vip=False, premium=False,
                        subscription=False, monthly_plans=False, yearly_plans=False,
                        account_management=False, copy_trading=False, funded_accounts=False,
                        usdt_payments=False, binance_payments=False, lead_score=0,
                        tier='Tier_D', ai_confidence=100, last_activity=None,
                        discovery_source=discovery_source, discovery_method=discovery_method,
                        arabic_score=0, region_score=0, status='rejected',
                        forex_intent_score=0, forex_category='unknown', high_risk_fraud=False
                    )
                    return
                    
                if http_info["is_channel"]:
                    # 1. Member count check (< 100) - HARD REJECTION
                    if http_info["member_count"] < 100:
                        logging.info(f"HTTP filter: Channel @{identifier} rejected (HARD): low member count ({http_info['member_count']} < 100).")
                        self.db_helper.add_to_blacklist(actual_link, 'low_members')
                        self.db_helper.upsert_lead(
                            channel_username=identifier,
                            member_count=http_info["member_count"],
                            description=http_info["description"],
                            language='English/Other',
                            arabic_ratio=0,
                            website='', email='', whatsapp='', contact_username='',
                            is_group=False, marketplace_score=0, vip=False, premium=False,
                            subscription=False, monthly_plans=False, yearly_plans=False,
                            account_management=False, copy_trading=False, funded_accounts=False,
                            usdt_payments=False, binance_payments=False, lead_score=0,
                            tier='Tier_D', ai_confidence=100, last_activity=None,
                            discovery_source=discovery_source, discovery_method=discovery_method,
                            arabic_score=0, region_score=0, status='rejected',
                            forex_intent_score=0, forex_category='unknown', high_risk_fraud=False
                        )
                        return

                    # 2. Evaluate Soft Rejection Criteria
                    failed_rules = []

                    # Soft check A: Low views for small channels
                    if http_info["member_count"] < 1000 and 0 < http_info["avg_views"] < 100:
                        failed_rules.append("low_views")

                    # Soft check B: Arabic Language Check
                    arabic_regex = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
                    has_arabic = bool(arabic_regex.search(http_info["title"]) or arabic_regex.search(http_info["description"]))
                    if not has_arabic:
                        failed_rules.append("non_arabic")

                    # Soft check C: Forex Intent Check
                    combined_text = (http_info["title"] + " " + http_info["description"]).lower()
                    forex_keywords = [
                        'forex', 'signals', 'xauusd', 'gold', 'ذهب', 'توصيات', 'تداول', 'عملات', 'فوركس',
                        'smc', 'ict', 'منزل التحليل', 'الصفقة', 'الربح', 'الخسارة', 'تحدي', 'تمويل'
                    ]
                    has_forex = any(kw in combined_text for kw in forex_keywords)
                    if not has_forex:
                        failed_rules.append("non_forex")

                    failed_count = len(failed_rules)
                    if failed_count >= 2:
                        failed_reason = f"failed_multiple_filters:{','.join(failed_rules)}"
                        logging.info(f"HTTP filter: Channel @{identifier} rejected (SOFT): failed rules {failed_rules} (failed_count={failed_count} >= 2).")
                        self.db_helper.add_to_blacklist(actual_link, failed_reason)
                        self.db_helper.upsert_lead(
                            channel_username=identifier,
                            member_count=http_info["member_count"],
                            description=http_info["description"],
                            language='English/Other' if 'non_arabic' in failed_rules else 'Arabic',
                            arabic_ratio=0 if 'non_arabic' in failed_rules else 100,
                            website='', email='', whatsapp='', contact_username='',
                            is_group=False, marketplace_score=0, vip=False, premium=False,
                            subscription=False, monthly_plans=False, yearly_plans=False,
                            account_management=False, copy_trading=False, funded_accounts=False,
                            usdt_payments=False, binance_payments=False, lead_score=0,
                            tier='Tier_D', ai_confidence=100, last_activity=None,
                            discovery_source=discovery_source, discovery_method=discovery_method,
                            arabic_score=0 if 'non_arabic' in failed_rules else 15, region_score=0, status='rejected',
                            forex_intent_score=0, forex_category='unknown', high_risk_fraud=False
                        )
                        return
                    else:
                        if failed_count > 0:
                            logging.info(f"HTTP filter: Channel @{identifier} passed with soft failures: {failed_rules} (failed_count={failed_count} < 2). Proceeding.")
                        else:
                            logging.info(f"HTTP filter: Channel @{identifier} passed all HTTP pre-filter checks. Proceeding.")
                    
                    logging.info(f"HTTP filter: Channel @{identifier} passed HTTP pre-filter checks. Proceeding to Telegram API validation.")
                    
            # ALWAYS attempt HTTP-only validation first for public channels to preserve Telethon session quotas
            if http_info and http_info.get("is_channel"):
                logging.info(f"Running HTTP primary validation for @{identifier} to bypass Telethon quotas.")
                http_ok = await self.process_http_fallback(actual_link, identifier, http_info, discovery_source, discovery_method, keyword)
                if http_ok:
                    logging.info(f"HTTP primary validation successful for @{identifier}. Preserving Telethon API limit.")
                    return
                else:
                    logging.warning(f"HTTP primary validation failed or returned no posts for @{identifier}. Falling back to Telethon API.")

            if self.is_all_sessions_rate_limited():
                logging.warning(f"All sessions rate-limited. Skipping Telegram API validation for @{identifier}.")
                return
                
            # Resolve channel/group entity using get_entity_safe or worker spider joiner for private links
            if link_type == 'private' and identifier:
                entity = await self.join_or_get_private_entity(identifier, actual_link)
            else:
                entity = await self.get_entity_safe(actual_link)
            if not entity:
                logging.warning(f"Failed to resolve entity for {actual_link}")
                return

            is_group = False
            is_channel = False
            if isinstance(entity, Chat):
                is_group = True
            elif isinstance(entity, Channel) and entity.megagroup:
                is_group = True
            else:
                is_channel = isinstance(entity, Channel) and getattr(entity, 'broadcast', False)

            if not is_group and not is_channel:
                logging.info(f"Target {actual_link} is neither a Group nor a broadcast Channel (resolved as {type(entity).__name__}). Blacklisting...")
                self.db_helper.add_to_blacklist(actual_link, 'invalid_entity_type')
                return

            full_chat_info = None
            description = ""
            member_count = 0

            try:
                async def fetch_full_details(cl):
                    return await cl(GetFullChannelRequest(entity))
                full_chat_info = await self.tg_manager.execute_request(
                    self.session_name, fetch_full_details, shutdown_event=self.shutdown_event
                )
                if full_chat_info and hasattr(full_chat_info, 'full_chat'):
                    description = full_chat_info.full_chat.about or ''
                    member_count = full_chat_info.full_chat.participants_count or 0
            except Exception as ex:
                logging.warning(f"Could not fetch full details for {actual_link}: {ex}")
                if hasattr(entity, 'participants_count') and entity.participants_count is not None:
                    member_count = entity.participants_count

            title = getattr(entity, 'title', '') or ''
            title = title or ""
            description = description or ""
            username = getattr(entity, 'username', None) or identifier

            # ── Early-Rejection Filtering for Broadcast Channels ──
            if is_channel:
                # 1. Member count check (< 100) - HARD REJECTION
                if member_count < 100:
                    logging.info(f"Channel @{username} rejected (HARD): low member count ({member_count} < 100).")
                    self.db_helper.add_to_blacklist(actual_link, 'low_members')
                    self.db_helper.upsert_lead(
                        channel_username=username,
                        member_count=member_count,
                        description=description,
                        language='English/Other',
                        arabic_ratio=0,
                        website='', email='', whatsapp='', contact_username='',
                        is_group=False, marketplace_score=0, vip=False, premium=False,
                        subscription=False, monthly_plans=False, yearly_plans=False,
                        account_management=False, copy_trading=False, funded_accounts=False,
                        usdt_payments=False, binance_payments=False, lead_score=0,
                        tier='Tier_D', ai_confidence=100, last_activity=None,
                        discovery_source=discovery_source, discovery_method=discovery_method,
                        arabic_score=0, region_score=0, status='rejected',
                        forex_intent_score=0, forex_category='unknown', high_risk_fraud=False
                    )
                    return

                # 2. Evaluate Early Soft Rejection Criteria
                early_failed_rules = []

                # Soft check A: Arabic Language Check
                arabic_regex = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
                has_arabic = bool(arabic_regex.search(title) or arabic_regex.search(description))
                if not has_arabic:
                    early_failed_rules.append("non_arabic")

                # Soft check B: Core Forex Keywords Check
                core_forex_kws = [
                    "forex", "signals", "xauusd", "gold", "ذهب", "دهب", "توصيات", 
                    "تداول", "عملات", "تحليل", "فوركس", "smc", "ict", "fvg",
                    "nasdaq", "ناسداك", "us30", "داو جونز"
                ]
                combined_meta_text = f"{title} {description}".lower()
                has_core_kw = any(kw in combined_meta_text for kw in core_forex_kws)
                if not has_core_kw:
                    early_failed_rules.append("no_forex_intent")

                # If both soft rules failed early, we can reject immediately (failed_count = 2)
                if len(early_failed_rules) == 2:
                    failed_reason = f"failed_multiple_filters:{','.join(early_failed_rules)}"
                    logging.info(f"Channel @{username} rejected (SOFT - Early): failed rules {early_failed_rules} (failed_count=2).")
                    self.db_helper.add_to_blacklist(actual_link, failed_reason)
                    self.db_helper.upsert_lead(
                        channel_username=username,
                        member_count=member_count,
                        description=description,
                        language='English/Other',
                        arabic_ratio=0,
                        website='', email='', whatsapp='', contact_username='',
                        is_group=False, marketplace_score=0, vip=False, premium=False,
                        subscription=False, monthly_plans=False, yearly_plans=False,
                        account_management=False, copy_trading=False, funded_accounts=False,
                        usdt_payments=False, binance_payments=False, lead_score=0,
                        tier='Tier_D', ai_confidence=100, last_activity=None,
                        discovery_source=discovery_source, discovery_method=discovery_method,
                        arabic_score=0, region_score=0, status='rejected',
                        forex_intent_score=0, forex_category='unknown', high_risk_fraud=False
                    )
                    return
                else:
                    if early_failed_rules:
                        logging.info(f"Channel @{username} passed early Telethon soft check with rules failed: {early_failed_rules}. Proceeding to fetch messages.")
                    else:
                        logging.info(f"Channel @{username} passed all early Telethon soft checks. Proceeding to fetch messages.")

            # Fetch messages: 100 messages for both channels & groups to scrape maximum contact information
            msg_limit = 100
            messages = await self.fetch_messages_safe(entity, limit=msg_limit)
            
            # Fetch pinned message if any exists
            pinned_text = ""
            if full_chat_info and hasattr(full_chat_info.full_chat, 'pinned_msg_id') and full_chat_info.full_chat.pinned_msg_id:
                try:
                    async def fetch_pinned(cl):
                        return await cl.get_messages(entity, ids=full_chat_info.full_chat.pinned_msg_id)
                    pinned_msg = await self.tg_manager.execute_request(
                        self.session_name, fetch_pinned, shutdown_event=self.shutdown_event
                    )
                    if pinned_msg and pinned_msg.message:
                        pinned_text = pinned_msg.message
                        logging.info(f"Successfully fetched pinned message for @{username} (ID: {full_chat_info.full_chat.pinned_msg_id})")
                except Exception as p_err:
                    logging.warning(f"Could not fetch pinned message for @{username}: {p_err}")

            
            # Enforce refined activity check: Must have at least 3 messages in the last 72h AND at least 5 messages in the last 7 days
            is_inactive = False
            inactive_reason = ""
            if not messages:
                is_inactive = True
                inactive_reason = "No messages retrieved"
            else:
                now = datetime.now(timezone.utc)
                msgs_72h = 0
                msgs_7d = 0
                for msg in messages:
                    msg_date = msg.date
                    if msg_date.tzinfo is None:
                        msg_date = msg_date.replace(tzinfo=timezone.utc)
                    age = now - msg_date
                    if age <= timedelta(hours=72):
                        msgs_72h += 1
                    if age <= timedelta(days=7):
                        msgs_7d += 1
                        
                if msgs_72h < 3:
                    is_inactive = True
                    inactive_reason = f"Only {msgs_72h} messages posted in the last 72 hours (minimum 3 required)"
                elif msgs_7d < 5:
                    is_inactive = True
                    inactive_reason = f"Only {msgs_7d} messages posted in the last 7 days (minimum 5 required)"

            # Views validation for channels with < 1000 members (must be >= 50 average views)
            is_low_views = False
            is_medium_views_penalty = False
            if not is_inactive and is_channel and member_count < 1000:
                channel_views = [msg.views for msg in messages if getattr(msg, 'views', None) is not None]
                avg_views = int(sum(channel_views) / len(channel_views)) if channel_views else 0
                if avg_views < 50:
                    is_low_views = True
                    logging.info(f"Channel @{username} has very low average views ({avg_views} < 50) for small channel ({member_count} members). (Flagged as soft failure)")
                elif avg_views < 100:
                    is_medium_views_penalty = True
                    logging.info(f"Channel @{username} has medium average views ({avg_views} in [50, 99]) for small channel. Penalty will be applied.")
            
            if is_inactive:
                sample_text_list = []
                for msg in messages:
                    if msg.text:
                        sample_text_list.append(msg.text)
                if pinned_text:
                    sample_text_list.append(pinned_text)
                sample_text = " \n ".join(sample_text_list)
                combined_desc_text = f"{title} {description} {sample_text}"
                
                # Check forbidden keywords
                neg_regex = re.compile(r'(ارباح\s+مضمونة|أرباح\s+مضمونة|ربح\s+مضمون|استثمار\s+مضمون|ضمان\s+الربح|تعويض\s+الخسائر|تداول\s+بدون\s+مخاطرة)', re.IGNORECASE)
                has_forbidden = bool(neg_regex.search(combined_desc_text))
                
                # Check Arabic
                arabic_score = calculate_arabic_score(title, description, sample_text, messages, {})
                
                # Check Forex
                forex_intent_score = calculate_forex_intent_score(title, description, messages, {}, discovery_method)
                is_forex = check_is_forex(combined_desc_text) or forex_intent_score >= 30
                
                passes_inactive_gate = (is_forex and arabic_score >= 50 and not has_forbidden)
                
                if passes_inactive_gate:
                    logging.info(f"Inactive channel {actual_link} passed niche filters. Saving as low-tier qualified.")
                    try:
                        payload = json.dumps({"link": actual_link})
                        self.redis_conn.rpush("user_join_queue", payload)
                        logging.info(f"User Joiner: Queued verified Forex inactive channel {actual_link} for auto-join.")
                    except Exception as q_err:
                        logging.warning(f"Failed to queue user join for inactive channel: {q_err}")
                        
                    self.db_helper.upsert_lead(
                        channel_username=username, member_count=member_count, description=f"Inactive channel: {inactive_reason}",
                        language='Arabic', arabic_ratio=100, website='', email='',
                        whatsapp='', contact_username='', is_group=is_group,
                        marketplace_score=0, vip=False, premium=False, subscription=False, monthly_plans=False,
                        yearly_plans=False, account_management=False, copy_trading=False, funded_accounts=False,
                        usdt_payments=False, binance_payments=False, lead_score=10, tier='Tier_D', ai_confidence=100,
                        last_activity=messages[-1].date.astimezone(timezone.utc) if messages else None,
                        discovery_source=discovery_source, discovery_method=discovery_method, arabic_score=arabic_score,
                        region_score=0, status='new', forex_intent_score=forex_intent_score, forex_category='unknown', high_risk_fraud=False
                    )
                else:
                    logging.info(f"Inactive channel {actual_link} failed niche filters (is_forex={is_forex}, arabic_score={arabic_score}, forbidden={has_forbidden}). Rejecting.")
                    self.db_helper.upsert_lead(
                        channel_username=username, member_count=member_count, description=f"Inactive non-forex channel: {inactive_reason}",
                        language='Other', arabic_ratio=0, website='', email='',
                        whatsapp='', contact_username='', is_group=is_group,
                        marketplace_score=0, vip=False, premium=False, subscription=False, monthly_plans=False,
                        yearly_plans=False, account_management=False, copy_trading=False, funded_accounts=False,
                        usdt_payments=False, binance_payments=False, lead_score=0, tier='Tier_D', ai_confidence=100,
                        last_activity=messages[-1].date.astimezone(timezone.utc) if messages else None,
                        discovery_source=discovery_source, discovery_method=discovery_method, arabic_score=arabic_score,
                        region_score=0, status='rejected', forex_intent_score=forex_intent_score, forex_category='unknown', high_risk_fraud=False
                    )
                return
                
            # Compile messages sample text
            sample_text_list = []
            for msg in messages:
                if msg.text:
                    sample_text_list.append(msg.text)
            if pinned_text:
                sample_text_list.append(pinned_text)
            sample_text = " \n ".join(sample_text_list)
            
            contacts = extract_contacts(sample_text, description, username)
            
            # Pre-register lead to get its UUID and count incoming mentions
            source_id = self.db_helper.insert_stub_lead(username)
            
            if is_group:
                logging.info(f"Target {link} is a Group/Megagroup. Updating group_metrics and scoring...")
                
                total_msgs = len(messages)
                mentions_count = 0
                links_count = 0
                ad_count = 0
                unique_promoters = set()
                
                high_value_kws = ["vip", "premium", "اشتراك", "ادارة", "نسخ", "funded"]
                discovered_in_msg = {} # target_username_lower -> (target_username, normalized_link, rel_type)
                
                for msg in messages:
                    if not msg.text:
                        continue
                        
                    raw_mentions = USERNAME_REGEX.findall(msg.text)
                    mentions_in_msg = sum(1 for m in raw_mentions if m.lower() not in ('joinchat', 'share', 'addstickers', 'addlist'))
                    mentions_count += mentions_in_msg
                    
                    links_in_msg = len(TELEGRAM_LINK_REGEX.findall(msg.text))
                    links_count += links_in_msg
                    
                    is_promo = any(kw in msg.text.lower() for kw in high_value_kws)
                    if is_promo:
                        ad_count += 1
                        
                    sender_id = getattr(msg, 'sender_id', None)
                    if sender_id and (mentions_in_msg > 0 or links_in_msg > 0 or is_promo):
                        unique_promoters.add(str(sender_id))
                        
                    is_high_priority = is_promo
                    links_found = TELEGRAM_LINK_REGEX.findall(msg.text)
                    for link_found in links_found:
                        clean_link = link_found.rstrip('.,;)!"\'')
                        if clean_link:
                            normalized = normalize_telegram_link(clean_link)
                            target_type, target_username = parse_telegram_link(normalized)
                            if target_username:
                                rel_type = 'advertisement' if is_high_priority else 'link'
                                discovered_in_msg[target_username.lower()] = (target_username, normalized, rel_type)
                                
                    for mention in raw_mentions:
                        if mention.lower() not in ('joinchat', 'share', 'addstickers', 'addlist'):
                            normalized = f"https://t.me/{mention}"
                            rel_type = 'advertisement' if is_high_priority else 'mention'
                            if mention.lower() not in discovered_in_msg:
                                discovered_in_msg[mention.lower()] = (mention, normalized, rel_type)
                                
                # member_count already pre-fetched in phase 1
                
                score = 0
                if total_msgs > 0:
                    promo_ratio = (mentions_count * 1.0 + links_count * 1.5 + ad_count * 2.0) / total_msgs
                    promoter_ratio = len(unique_promoters) / total_msgs
                    score = int(promo_ratio * 70 + promoter_ratio * 20)
                    
                if member_count > 50000:
                    score += 10
                elif member_count > 20000:
                    score += 7
                elif member_count > 5000:
                    score += 4
                    
                mkt_score = min(100, max(0, score))
                
                # Calculate Arabic, Region, and Forex Intent Scores for group
                arabic_score = calculate_arabic_score(title, description, sample_text, messages, contacts)
                region_score = calculate_region_score(title, description, sample_text, contacts)
                forex_intent_score = calculate_forex_intent_score(title, description, messages, contacts, discovery_method)
                forex_category = classify_forex_category(title, description, sample_text)

                # Check if group is a Forex group (fails niche check or has low Forex score)
                combined_group_text = f"{title} {description} {sample_text}"
                is_group_forex = check_is_forex(combined_group_text) or forex_intent_score >= 40
                group_status = 'new' if is_group_forex else 'rejected'
                
                if group_status == 'new':
                    try:
                        payload = json.dumps({"link": actual_link})
                        self.redis_conn.rpush("user_join_queue", payload)
                        logging.info(f"User Joiner: Queued verified Forex group {actual_link} for auto-join.")
                    except Exception as q_err:
                        logging.warning(f"Failed to queue user join for group: {q_err}")

                # Update group metadata in database
                self.db_helper.upsert_lead(
                    channel_username=username,
                    member_count=member_count,
                    description=description,
                    language='Arabic',
                    arabic_ratio=100,
                    website=contacts['website'],
                    email=contacts['email'],
                    whatsapp=contacts['whatsapp'],
                    contact_username=contacts['contact_username'],
                    is_group=True,
                    marketplace_score=mkt_score,
                    vip=False,
                    premium=False,
                    subscription=False,
                    monthly_plans=False,
                    yearly_plans=False,
                    account_management=False,
                    copy_trading=False,
                    funded_accounts=False,
                    usdt_payments=False,
                    binance_payments=False,
                    lead_score=0,
                    tier='Tier_D',
                    ai_confidence=100,
                    last_activity=None,
                    discovery_source=discovery_source,
                    discovery_method=discovery_method,
                    arabic_score=arabic_score,
                    region_score=region_score,
                    status=group_status,
                    forex_intent_score=forex_intent_score,
                    forex_category=forex_category,
                    high_risk_fraud=False
                )
                
                # Update group metrics in database
                self.db_helper.upsert_group_metrics(source_id, total_msgs, mentions_count, links_count, ad_count, mkt_score)

                if not is_group_forex:
                    logging.info(f"Group @{username} is NOT a Forex group (Forex score: {forex_intent_score}). Rejecting, adding to rejected_groups_set, and skipping link extraction.")
                    self.redis_conn.sadd("rejected_groups_set", username.lower())
                    return

                # Track discovery source analytics for group
                is_high_quality = (mkt_score >= 50)
                source_type_val = "keyword" if discovery_method == "telegram_search" else "group"
                source_name_val = keyword if (discovery_method == "telegram_search" and keyword) else discovery_source
                if source_name_val and source_name_val != "unknown":
                    self.db_helper.upsert_discovery_source(source_type_val, source_name_val, keyword, is_high_quality)
                
                # Populate graph edges & queue discovered links (Phase 5: Higher crawl priority for group-discovered links)
                for target_username_lower, (target_username, normalized, rel_type) in discovered_in_msg.items():
                    is_seen = self.redis_conn.sismember("seen_channels", normalized)
                    if not is_seen:
                        queue_target = "queue:critical" if (rel_type == 'advertisement') else "queue:high"
                        self.redis_conn.sadd("seen_channels", normalized)
                        
                        method_val = "advertisement" if rel_type == 'advertisement' else "marketplace_group"
                        payload = json.dumps({
                            "link": normalized,
                            "source": username,
                            "method": method_val,
                            "keyword": ""
                        })
                        self.redis_conn.rpush(queue_target, payload)
                        logging.info(f"Recursive scanner discovered link from group: {normalized} (Queued to: {queue_target})")
                        
                    target_id = self.db_helper.insert_stub_lead(target_username)
                    if target_id and source_id:
                        self.db_helper.insert_relationship(source_id, target_id, rel_type)
                        logging.info(f"Graph edge added recursively from group scan: @{username} -> @{target_username} ({rel_type})")
                        
                return
                
            in_degree = 0
            if source_id:
                in_degree = self.db_helper.get_incoming_graph_count(source_id)
                
            # ── Graph Database edge insertion & Ad Exchange Deep Scraper ────────────
            # Runs on every scanned channel BEFORE early filter returns.
            # Detects ad-exchange posts, high-value copywriting patterns, and
            # immediately routes discovered target channels to queue:critical.
            if source_id:
                source_is_tier_a = self.db_helper.is_verified_tier_a(username)
                high_value_kws = ["vip", "premium", "اشتراك", "ادارة", "نسخ", "funded"]

                for msg in messages:
                    if not msg.text:
                        continue

                    msg_text_lower = msg.text.lower()

                    # ── Classify message signal level ─────────────────────────
                    is_high_priority       = any(kw in msg_text_lower for kw in high_value_kws)
                    is_ad_exchange         = any(kw in msg.text for kw in ad_exchange_kws)
                    is_ad_copywriting      = any(kw in msg.text for kw in forex_ad_patterns)
                    lists_ad_exchange_phrases = ["لمدة محدودة", "العرض ساري", "باقي أيام وينتهي", "الاشتراك السنوي", "انضموا قبل الحذف", "القناة الخاصة", "الجروب الخاص", "جروب الـ VIP", "دخول مجاني", "أقوى قناة توصيات", "تعويض الخسارة"]
                    is_lists_ad_exchange   = any(kw in msg.text for kw in lists_ad_exchange_phrases)

                    links_found   = TELEGRAM_LINK_REGEX.findall(msg.text)
                    mentions_found = USERNAME_REGEX.findall(msg.text)
                    discovered_in_msg = {}

                    for link_found in links_found:
                        clean_link = link_found.rstrip('.,;)!"\'')
                        if not clean_link:
                            continue
                        normalized = normalize_telegram_link(clean_link)
                        target_type, target_username = parse_telegram_link(normalized)
                        if target_type == 'public' and target_username:
                            rel_type = 'advertisement' if (is_high_priority or is_ad_exchange or is_ad_copywriting or is_lists_ad_exchange) else 'link'
                            discovered_in_msg[target_username.lower()] = (target_username, normalized, rel_type)

                    for mention in mentions_found:
                        if mention.lower() not in ('joinchat', 'share', 'addstickers', 'addlist'):
                            normalized = f"https://t.me/{mention}"
                            rel_type = 'advertisement' if (is_high_priority or is_ad_exchange or is_ad_copywriting or is_lists_ad_exchange) else 'mention'
                            if mention.lower() not in discovered_in_msg:
                                discovered_in_msg[mention.lower()] = (mention, normalized, rel_type)

                    for target_username_lower, (target_username, normalized, rel_type) in discovered_in_msg.items():
                        is_seen = self.redis_conn.sismember("seen_channels", normalized)
                        if not is_seen:
                            self.redis_conn.sadd("seen_channels", normalized)

                            # ── Routing decision (priority order) ────────────────
                            if is_lists_ad_exchange and (links_found or mentions_found):
                                # Closed-Loop Recursive Lists / Ad-Exchange detection
                                queue_target = "queue:critical"
                                payload_dict = {
                                    "link": normalized,
                                    "source": username,
                                    "method": "ad_exchange_feedback",
                                    "keyword": "",
                                    "priority_weight": 30,
                                    "discovery_source": "ad_exchange_feedback"
                                }
                                logging.info(
                                    f"[RECURSIVE LISTS/AD-EXCHANGE] Discovered target channel {normalized} in @{username}. "
                                    f"Routing to queue:critical (priority_weight=30)"
                                )

                            elif is_ad_copywriting and (links_found or mentions_found):
                                # Highest signal: urgency/CTA copywriting + link → queue:critical
                                queue_target = "queue:critical"
                                payload_dict = {
                                    "link": normalized,
                                    "source": username,
                                    "method": "ad_copywriting_pattern",
                                    "keyword": "",
                                    "priority_weight": 25,
                                    "discovery_source": "ad_copywriting_pattern"
                                }
                                logging.info(
                                    f"[AD_COPY] High-Value copywriting pattern detected in @{username}. "
                                    f"Routing {normalized} → queue:critical (priority_weight=25)"
                                )

                            elif is_ad_exchange and (links_found or mentions_found):
                                # Ad Exchange cross-promotion: push discovered channel immediately
                                queue_target = "queue:critical"
                                payload_dict = {
                                    "link": normalized,
                                    "source": username,
                                    "method": "ad_exchange_feedback",
                                    "keyword": "",
                                    "priority_weight": 30,
                                    "discovery_source": "ad_exchange_feedback"
                                }
                                logging.info(
                                    f"[AD_EXCHANGE] Cross-promo post detected in @{username}. "
                                    f"Routing {normalized} → queue:critical"
                                )

                            elif source_is_tier_a:
                                # Verified Tier_A source: all discovered links are critical
                                queue_target = "queue:critical"
                                payload_dict = {
                                    "link": normalized,
                                    "source": username,
                                    "method": "verified_partner",
                                    "keyword": "",
                                    "priority": "high"
                                }

                            else:
                                # Standard routing based on high-priority keywords
                                queue_target = "queue:high" if (is_high_priority or rel_type == 'advertisement') else "queue:normal"
                                payload_dict = {
                                    "link": normalized,
                                    "source": username,
                                    "method": "advertisement" if rel_type == 'advertisement' else "channel_mention",
                                    "keyword": ""
                                }

                            payload = json.dumps(payload_dict)
                            self.redis_conn.rpush(queue_target, payload)
                            logging.info(
                                f"Recursive scanner → {normalized} queued to {queue_target} "
                                f"(tier_a={source_is_tier_a}, ad_exchange={is_ad_exchange}, ad_copy={is_ad_copywriting})"
                            )

                        target_id = self.db_helper.insert_stub_lead(target_username)
                        if target_id:
                            self.db_helper.insert_relationship(source_id, target_id, rel_type)
                            logging.info(f"Graph edge added recursively: @{username} -> @{target_username} ({rel_type})")
            
            # Local Rules Regex checks
            pos_regex = re.compile(r'(vip|premium|اشتراك|ادارة\s+محافظ|نسخ|توصية|توصيات|إشارة|إشارات|اشارات|اشارة|signal|signals)', re.IGNORECASE)
            neg_regex = re.compile(r'(ارباح\s+مضمونة|أرباح\s+مضمونة|ربح\s+مضمون|استثمار\s+مضمون|ضمان\s+الربح|تعويض\s+الخسائر|تداول\s+بدون\s+مخاطرة)', re.IGNORECASE)
            
            payment_detected = bool(re.search(r'(usdt|binance|payeer|crypto|تحويل|دفع|سداد)', f"{sample_text} {description}", re.IGNORECASE))
            
            # Calculate Arabic Language Metrics strictly rules-based
            char_pct, word_pct, msg_ratio, arabic_ratio = calculate_arabic_metrics(sample_text, messages)
            is_arabic = (arabic_ratio > 60)
            logging.info(f"Rules-based Arabic Detection for @{username}: Chars: {char_pct}%, Words: {word_pct}%, Msg Ratio: {msg_ratio}%, Final Avg: {arabic_ratio}% (Is Arabic: {is_arabic})")
            
            # Check for negative (blacklist) keywords
            has_forbidden_keywords = bool(neg_regex.search(sample_text))
            
            # Keyword Frequency Engine (Track specific keywords)
            tracked_keywords = [
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
            keyword_freqs = {}
            combined_desc_text = f"{title} {description} {sample_text}".lower()
            for kw in tracked_keywords:
                keyword_freqs[kw] = combined_desc_text.count(kw.lower())
                
            # Dynamic rule-based Business Detection Engine
            vip = bool(pos_regex.search(combined_desc_text))
            premium = "premium" in title.lower() or "premium" in description.lower() or "مميز" in combined_desc_text or "بريميوم" in combined_desc_text
            subscription = bool(re.search(r'(اشتراك|اشتراكات|باقة|باقات|عضوية|توصية|توصيات|إشارة|إشارات|اشارات|اشارة|signal|signals)', combined_desc_text, re.IGNORECASE))
            monthly_plans = bool(re.search(r'(شهري|شهرية|monthly)', combined_desc_text, re.IGNORECASE))
            yearly_plans = bool(re.search(r'(سنوي|سنوية|yearly|annual)', combined_desc_text, re.IGNORECASE))
            account_management = bool(re.search(r'(إدارة حسابات|ادارة حسابات|محفظة استثمارية|استثمار|ادارة محافظ|إدارة محافظ)', combined_desc_text, re.IGNORECASE))
            copy_trading = bool(re.search(r'(نسخ تداول|نسخ صفقات|copy trading|النسخ|نسخ)', combined_desc_text, re.IGNORECASE))
            funded_accounts = bool(re.search(r'(حساب ممول|funded)', combined_desc_text, re.IGNORECASE))
            usdt_payments = "usdt" in combined_desc_text or "يو اس دي تي" in combined_desc_text
            binance_payments = "binance" in combined_desc_text or "بينانس" in combined_desc_text
            
            # Pure rules-based is_forex check
            is_forex = check_is_forex(f"{title} {description} {sample_text}")
            
            recent_activity = False
            active_posting = False
            last_activity_date = None
            
            if messages:
                last_msg_date = messages[0].date
                last_activity_date = last_msg_date
                now = datetime.now(timezone.utc)
                
                # Dynamic post counting to align with 72h / 7d rules
                msgs_72h = sum(1 for m in messages if (now - (m.date.replace(tzinfo=timezone.utc) if m.date.tzinfo is None else m.date)) <= timedelta(hours=72))
                msgs_7d = sum(1 for m in messages if (now - (m.date.replace(tzinfo=timezone.utc) if m.date.tzinfo is None else m.date)) <= timedelta(days=7))
                
                if msgs_72h >= 3:
                    recent_activity = True
                if msgs_7d >= 5:
                    active_posting = True
                    
            # member_count already pre-fetched in phase 1
            
            metadata = {
                'member_count': member_count,
                'website': contacts['website'],
                'contact_username': contacts['contact_username'],
                'whatsapp': contacts['whatsapp'],
                'payment_detected': payment_detected or usdt_payments or binance_payments,
                'is_arabic': is_arabic,
                'arabic_ratio': arabic_ratio,
                'recent_activity': recent_activity,
                'active_posting': active_posting,
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
                'is_forex': is_forex,
                'confidence': 100,
                'is_private': (parse_telegram_link(link)[0] == 'private')
            }
            
            # Evaluate final soft failure rules
            final_failed_rules = []
            if not metadata['is_arabic']:
                final_failed_rules.append("non_arabic")
            if not metadata['is_forex']:
                final_failed_rules.append("non_forex")
            if is_low_views:
                final_failed_rules.append("low_views")

            failed_count = len(final_failed_rules)
            if failed_count >= 2:
                failed_reason = f"failed_multiple_filters:{','.join(final_failed_rules)}"
                logging.info(f"Channel {actual_link} rejected (SOFT - Final): failed rules {final_failed_rules} (failed_count={failed_count} >= 2). Blacklisting...")
                self.db_helper.add_to_blacklist(actual_link, failed_reason)
                self.db_helper.upsert_lead(
                    channel_username=username,
                    member_count=member_count,
                    description=description,
                    language='English/Other' if 'non_arabic' in final_failed_rules else 'Arabic',
                    arabic_ratio=metadata['arabic_ratio'],
                    website=contacts['website'],
                    email=contacts['email'],
                    whatsapp=contacts['whatsapp'],
                    contact_username=contacts['contact_username'],
                    is_group=False,
                    marketplace_score=0,
                    vip=metadata['vip'],
                    premium=metadata['premium'],
                    subscription=metadata['subscription'],
                    monthly_plans=metadata['monthly_plans'],
                    yearly_plans=metadata['yearly_plans'],
                    account_management=metadata['account_management'],
                    copy_trading=metadata['copy_trading'],
                    funded_accounts=metadata['funded_accounts'],
                    usdt_payments=metadata['usdt_payments'],
                    binance_payments=metadata['binance_payments'],
                    lead_score=0,
                    tier='Tier_D',
                    ai_confidence=metadata['confidence'],
                    last_activity=None,
                    discovery_source=discovery_source,
                    discovery_method=discovery_method,
                    arabic_score=0 if 'non_arabic' in final_failed_rules else 15,
                    region_score=0,
                    status='rejected',
                    forex_intent_score=0,
                    forex_category='unknown',
                    high_risk_fraud=False
                )
                return
            else:
                if failed_count > 0:
                    logging.info(f"Channel {actual_link} passed final validation with soft failures: {final_failed_rules} (failed_count={failed_count} < 2).")

            # Calculate all scores
            arabic_score = calculate_arabic_score(title, description, sample_text, messages, contacts)
            region_score = calculate_region_score(title, description, sample_text, contacts)
            forex_intent_score = calculate_forex_intent_score(title, description, messages, contacts, discovery_method)
            forex_category = classify_forex_category(title, description, sample_text)

            logging.info(f"Scores for @{username}: arabic={arabic_score} forex_intent={forex_intent_score} region={region_score} category={forex_category}")

            # ── PHASE 3: Arabic Gate (raised to 50) ───────────────────────────────
            if arabic_score < 50:
                logging.info(f"Channel {actual_link} has low Arabic score ({arabic_score}<50). Saving as rejected.")
                self.db_helper.upsert_lead(
                    channel_username=username, member_count=0, description=description,
                    language='Other', arabic_ratio=metadata['arabic_ratio'],
                    website=None, email=None, whatsapp=None, contact_username=None,
                    is_group=False, marketplace_score=0,
                    vip=False, premium=False, subscription=False, monthly_plans=False,
                    yearly_plans=False, account_management=False, copy_trading=False,
                    funded_accounts=False, usdt_payments=False, binance_payments=False,
                    lead_score=0, tier='Tier_D', ai_confidence=100, last_activity=None,
                    discovery_source=discovery_source, discovery_method=discovery_method,
                    arabic_score=arabic_score, region_score=region_score,
                    status='rejected', forex_intent_score=forex_intent_score, forex_category=forex_category,
                    high_risk_fraud=False
                )
                return

            # ── Forbidden keywords check ──────────────────────────────────────────
            if has_forbidden_keywords:
                logging.info(f"Channel {actual_link} contains forbidden keywords. Blacklisting...")
                self.db_helper.add_to_blacklist(actual_link, 'forbidden_keywords')
                return

            # ── Build scored metadata ─────────────────────────────────────────────
            arabic_regex = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
            title_has_arabic = bool(arabic_regex.search(title))
            desc_has_arabic = bool(arabic_regex.search(description))
            high_arabic_ratio = (metadata['arabic_ratio'] > 80)
            whatsapp_num = contacts['whatsapp'] or ''
            is_gulf_whatsapp = any(whatsapp_num.startswith(prefix) for prefix in ["+966", "+971", "+965", "+968", "+973", "+962"])
            metadata.update({
                'title_has_arabic': title_has_arabic,
                'desc_has_arabic': desc_has_arabic,
                'high_arabic_ratio': high_arabic_ratio,
                'is_gulf_whatsapp': is_gulf_whatsapp
            })

            # ── Scam Score Check (Quality Gate) ──
            is_scam = False
            signals_count = 0
            risk_mgmt_count = 0
            
            signal_keywords = ["buy", "sell", "شراء", "بيع", "entry", "tp", "target", "هدف", "دخول", "xauusd", "توصية", "إشارة"]
            risk_keywords = ["إيقاف الخسارة", "أمر وقف الخسارة", "sl", "stop loss"]
            
            for msg in messages:
                if not msg.text:
                    continue
                msg_text_lower = msg.text.lower()
                is_sig = any(kw in msg_text_lower for kw in signal_keywords)
                if is_sig:
                    signals_count += 1
                    if any(kw in msg_text_lower for kw in risk_keywords):
                        risk_mgmt_count += 1
                        
            has_doubling_hype = "مضاعفة رأس المال" in combined_desc_text
            
            # If a verified trading channel posts >5 signals and 0 mention risk management, OR has doubling hype
            if is_forex and ((signals_count > 5 and risk_mgmt_count == 0) or has_doubling_hype):
                is_scam = True
                
            metadata['high_risk_fraud'] = is_scam

            score = self.calculate_weighted_score(metadata, keyword_freqs, in_degree)
            if is_medium_views_penalty:
                score = min(10, score)
            
            # If flagged as scam, drop score by 50 points
            if is_scam:
                score = max(0, score - 50)
                logging.warning(f"🚨 SCAM / FRAUD DETECTED for @{username} (signals: {signals_count}, risk_mgmt: {risk_mgmt_count}, doubling_hype: {has_doubling_hype}). Dropping score by 50 points. New score: {score}")

            tier = self.classify_tier(score)
            lang_str = "Arabic"

            # ── PHASE 4: DUAL LEAD GATE ───────────────────────────────────────────
            # A channel MUST pass BOTH gates and NOT be flagged as high risk fraud to become a real CRM lead
            passes_gate = (score >= 10 and forex_intent_score >= 30 and not is_scam)
            if not passes_gate:
                status_val = 'rejected'
                logging.info(f"Channel @{username} below gate (score={score}<10 or forex_intent={forex_intent_score}<30 or is_scam={is_scam}). Saving as rejected.")
            else:
                status_val = 'new'
                logging.info(f"Channel @{username} PASSED gate → Real CRM Lead! (score={score} forex_intent={forex_intent_score})")
                try:
                    payload = json.dumps({"link": actual_link})
                    self.redis_conn.rpush("user_join_queue", payload)
                    logging.info(f"User Joiner: Queued verified Forex active channel {actual_link} for auto-join.")
                except Exception as q_err:
                    logging.warning(f"Failed to queue user join for active channel: {q_err}")
                
            last_activity_ts = last_activity_date.astimezone(timezone.utc) if last_activity_date else None
            
            # Save to database (status is 'rejected' if arabic_score is low)
            self.db_helper.upsert_lead(
                channel_username=username,
                member_count=member_count,
                description=description,
                language=lang_str,
                arabic_ratio=metadata['arabic_ratio'],
                website=contacts['website'],
                email=contacts['email'],
                whatsapp=contacts['whatsapp'],
                contact_username=contacts['contact_username'],
                is_group=False,
                marketplace_score=0,
                vip=metadata['vip'],
                premium=metadata['premium'],
                subscription=metadata['subscription'],
                monthly_plans=metadata['monthly_plans'],
                yearly_plans=metadata['yearly_plans'],
                account_management=metadata['account_management'],
                copy_trading=metadata['copy_trading'],
                funded_accounts=metadata['funded_accounts'],
                usdt_payments=metadata['usdt_payments'],
                binance_payments=metadata['binance_payments'],
                lead_score=score,
                tier=tier,
                ai_confidence=metadata['confidence'],
                last_activity=last_activity_ts,
                discovery_source=discovery_source,
                discovery_method=discovery_method,
                arabic_score=arabic_score,
                region_score=region_score,
                status=status_val,
                forex_intent_score=forex_intent_score,
                forex_category=forex_category,
                high_risk_fraud=metadata.get('high_risk_fraud', False)
            )
            
            # ── Auto Outreach Enqueue for Newly Discovered Qualified Lead ──────────
            contact_user_str = contacts.get('contact_username')
            if status_val == 'new' and contact_user_str:
                try:
                    self.db_helper.check_connection()
                    conn = self.db_helper.conn
                    with conn.cursor(cursor_factory=RealDictCursor) as cur_enqueue:
                        cur_enqueue.execute("SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1")
                        active_camp_row = cur_enqueue.fetchone()
                        if active_camp_row:
                            active_camp_id = active_camp_row['id']
                            cur_enqueue.execute("SELECT id FROM leads WHERE channel_username = %s", (username,))
                            lead_db_row = cur_enqueue.fetchone()
                            if lead_db_row:
                                cur_enqueue.execute("""
                                    INSERT INTO campaign_logs (id, campaign_id, lead_id, status, sent_at)
                                    SELECT gen_random_uuid(), %s, %s, 'pending', NULL
                                    WHERE NOT EXISTS (
                                        SELECT 1 FROM campaign_logs cl2
                                        JOIN leads l2 ON cl2.lead_id = l2.id
                                        WHERE LOWER(l2.contact_username) = LOWER(%s)
                                    )
                                """, (active_camp_id, lead_db_row['id'], contact_user_str))
                                conn.commit()
                                if cur_enqueue.rowcount > 0:
                                    logging.info(f"🚀 Auto Outreach Enqueue: Added NEW validated lead @{username} (contact @{contact_user_str}) to active campaign {active_camp_id}!")
                except Exception as enqueue_err:
                    logging.warning(f"Auto Outreach Enqueue note for @{username}: {enqueue_err}")

            # Track discovery source analytics
            is_high_quality = (status_val == 'new' and score >= 70 and forex_intent_score >= 60)
            source_type_val = "keyword" if discovery_method == "telegram_search" else "channel"
            source_name_val = keyword if (discovery_method == "telegram_search" and keyword) else discovery_source
            if source_name_val and source_name_val != "unknown":
                self.db_helper.upsert_discovery_source(source_type_val, source_name_val, keyword, is_high_quality)
                
                # Closed-loop learning for search keywords (Phase 8: zadd/zincrby keyword priority in Redis)
                if source_type_val == "keyword":
                    delta = 5.0 if is_high_quality else -1.0
                    try:
                        self.redis_conn.zincrby("priority:keywords", delta, source_name_val)
                        logging.info(f"Phase 8 Learning: Updated keyword '{source_name_val}' weight by {delta} in Redis.")
                    except Exception as redis_err:
                        logging.warning(f"Failed to update keyword weight in Redis: {redis_err}")
                
                # Store keyword frequencies via KeywordFrequencyService
                if source_id and self.keyword_service:
                    self.keyword_service.analyze_and_update(source_id, title, description, messages)
                
                # Save message logs
                for msg in messages:
                    msg_text = msg.text or ""
                    msg_ts = msg.date.astimezone(timezone.utc)
                    self.db_helper.insert_post(username, msg.id, msg_text, msg_ts)
                    
                # Push back valid channel to radar join queue slowly
                group_link = f"https://t.me/{username}"
                is_new = self.redis_conn.sadd("scavenged_groups_set", group_link)
                if is_new:
                    payload = json.dumps({
                        "link": group_link,
                        "source": username,
                        "method": "channel_mention",
                        "keyword": keyword
                    })
                    self.redis_conn.rpush("discovered_groups", payload)
                    logging.info(f"Recursive discovery feedback loop: Added {group_link} back to radar queue.")
                    
        except Exception as e:
            logging.error(f"Error processing link {link}: {e}", exc_info=True)
            try:
                # Extract username to mark as rejected in DB to prevent clogging
                link_type, identifier = parse_telegram_link(actual_link)
                if identifier:
                    # Check if the error is a Telethon FloodWaitError or similar rate limit
                    is_rate_limit = isinstance(e, errors.FloodWaitError) or "wait" in str(e).lower() or "flood" in str(e).lower() or "limit" in str(e).lower()
                    if is_rate_limit:
                        logging.info(f"Rate limit / FloodWait error hit for @{identifier} during Telethon request. Updating last_scan to cool down.")
                        self.db_helper.check_connection()
                        with self.db_helper.conn.cursor() as cur:
                            cur.execute("UPDATE leads SET last_scan = CURRENT_TIMESTAMP WHERE channel_username = %s", (identifier,))
                        self.db_helper.conn.commit()
                    else:
                        logging.info(f"Marking failed link @{identifier} as rejected in DB to prevent queue clog. Reason: {e}")
                        self.db_helper.upsert_lead(
                        channel_username=identifier,
                        member_count=0,
                        description=f"Error during validation: {str(e)[:200]}",
                        language="Non-Arabic",
                        arabic_ratio=0,
                        website='', email='', whatsapp='', contact_username='',
                        is_group=(link_type == 'private'), marketplace_score=0, vip=False, premium=False,
                        subscription=False, monthly_plans=False, yearly_plans=False,
                        account_management=False, copy_trading=False, funded_accounts=False,
                        usdt_payments=False, binance_payments=False, lead_score=0,
                        tier='Tier_D', ai_confidence=100, last_activity=None,
                        discovery_source=discovery_source, discovery_method=discovery_method,
                        arabic_score=0, region_score=0, status='rejected',
                        forex_intent_score=0, forex_category='unknown', high_risk_fraud=False
                    )
            except Exception as db_err:
                logging.error(f"Failed to mark failed link as rejected in DB: {db_err}")

    async def rescan_scheduler_loop(self):
        """
        Runs periodically every 1 hour, finds leads past their cooldown, and queues them with appropriate priority.
        (Phase 5: marketplace groups receive higher scan frequency and direct validation queues).
        """
        logging.info("Rescan Scheduler loop initialized.")
        while not self.shutdown_event.is_set():
            try:


                # Query leads past their scan cooldown
                self.db_helper.check_connection()
                query = """
                SELECT channel_username, is_group, marketplace_score, lead_score,
                       CASE 
                           WHEN is_group = TRUE THEN COALESCE(marketplace_score, 0)
                           ELSE COALESCE(lead_score, 0)
                       END as score
                FROM leads
                WHERE status != 'rejected' AND (last_scan IS NULL OR 
                       (CASE 
                           WHEN is_group = TRUE THEN
                               CASE 
                                   WHEN COALESCE(marketplace_score, 0) > 50 THEN last_scan < NOW() - INTERVAL '6 hours'
                                   WHEN COALESCE(marketplace_score, 0) > 20 THEN last_scan < NOW() - INTERVAL '12 hours'
                                   ELSE last_scan < NOW() - INTERVAL '24 hours'
                               END
                           ELSE
                               CASE
                                    WHEN lead_score IS NULL THEN last_scan < NOW() - INTERVAL '1 hour'
                                    WHEN lead_score > 80 THEN last_scan < NOW() - INTERVAL '1 day'
                                   WHEN COALESCE(lead_score, 0) > 60 THEN last_scan < NOW() - INTERVAL '3 days'
                                   WHEN COALESCE(lead_score, 0) > 40 THEN last_scan < NOW() - INTERVAL '7 days'
                                   ELSE last_scan < NOW() - INTERVAL '30 days'
                               END
                        END))
                LIMIT 50;
                """
                with self.db_helper.conn.cursor() as cur:
                    cur.execute(query)
                    leads_to_scan = cur.fetchall()
                
                if leads_to_scan:
                    logging.info(f"Rescan Scheduler found {len(leads_to_scan)} leads past cooldown. Queueing...")
                    for lead in leads_to_scan:
                        username = lead['channel_username']
                        is_gp = lead['is_group']
                        score = lead['score']
                        
                        # Target link
                        target_link = f"https://t.me/{username}"
                        
                        # Decide priority queue
                        queue_name = "queue:normal"
                        if score > 80:
                            queue_name = "queue:critical"
                        elif score > 60:
                            queue_name = "queue:high"
                        elif score > 40:
                            queue_name = "queue:normal"
                        else:
                            queue_name = "queue:low"
                            
                        # Queue
                        if is_gp:
                            # Direct queue to validation (critical or high) to bypass 12-hour joiner delay
                            queue_target = "queue:critical" if score > 50 else "queue:high"
                            payload = json.dumps({
                                "link": target_link,
                                "source": "rescan_scheduler",
                                "method": "marketplace_group",
                                "keyword": ""
                            })
                            self.redis_conn.rpush(queue_target, payload)
                            logging.info(f"Rescan scheduler directly queued group {target_link} to {queue_target}")
                        else:
                            payload = json.dumps({
                                "link": target_link,
                                "source": "rescan_scheduler",
                                "method": "channel_mention",
                                "keyword": ""
                            })
                            self.redis_conn.rpush(queue_name, payload)
                
            except Exception as e:
                logging.error(f"Error in rescan scheduler loop: {e}", exc_info=True)
                
            # Sleep dynamically: check queue sizes to keep validator saturated
            try:
                total_len = 0
                for q in ["queue:critical", "queue:high", "queue:normal", "queue:low"]:
                    try:
                        total_len += self.redis_conn.llen(q) or 0
                    except Exception:
                        pass
                
                # If queues are empty/low, sleep only 30 seconds to fetch more stubs.
                # Otherwise, sleep 5 minutes (300 seconds).
                sleep_seconds = 30 if total_len < 20 else 300
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=sleep_seconds)
            except asyncio.TimeoutError:
                pass

    async def user_joiner_loop(self):
        """
        Monitors 'user_join_queue' in Redis and slowly, safely joins the user's account
        to newly verified Forex public/private links. Capped at 10 joins per day, with
        30-45 minutes interval between joins to prevent bans on a new account.
        """
        logging.info("User Auto-Joiner background task started.")
        
        async def add_to_folder(client, peer):
            from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
            from telethon.tl.types import DialogFilter, TextWithEntities
            
            try:
                # 1. Get existing filters
                res = await client(GetDialogFiltersRequest())
                filters = res.filters if hasattr(res, 'filters') else []
                
                # 2. Find filter with title "Bot_Channels"
                target_filter = None
                for f in filters:
                    title_str = ""
                    if hasattr(f, 'title'):
                        if isinstance(f.title, str):
                            title_str = f.title
                        elif hasattr(f.title, 'text'):
                            title_str = f.title.text
                            
                    if title_str == "Bot_Channels":
                        target_filter = f
                        break
                        
                if target_filter:
                    # Check if already in include_peers to avoid duplicates
                    peer_id = getattr(peer, 'channel_id', None) or getattr(peer, 'chat_id', None) or getattr(peer, 'user_id', None)
                    
                    exists = False
                    for p in target_filter.include_peers:
                        p_id = getattr(p, 'channel_id', None) or getattr(p, 'chat_id', None) or getattr(p, 'user_id', None)
                        if p_id == peer_id:
                            exists = True
                            break
                            
                    if not exists:
                        target_filter.include_peers.append(peer)
                        await client(UpdateDialogFilterRequest(
                            id=target_filter.id,
                            filter=target_filter
                        ))
                        logging.info(f"User Joiner: Added channel/group to existing folder 'Bot_Channels'")
                    else:
                        logging.info(f"User Joiner: Channel/group already exists in folder 'Bot_Channels'")
                else:
                    # Create a new filter
                    existing_ids = [f.id for f in filters if hasattr(f, 'id')]
                    new_id = max(existing_ids) + 1 if existing_ids else 2
                    if new_id < 2:
                        new_id = 2
                        
                    new_filter = DialogFilter(
                        id=new_id,
                        title=TextWithEntities(text="Bot_Channels", entities=[]),
                        pinned_peers=[],
                        include_peers=[peer],
                        exclude_peers=[],
                        contacts=False,
                        non_contacts=False,
                        groups=False,
                        broadcasts=False,
                        bots=False
                    )
                    await client(UpdateDialogFilterRequest(
                        id=new_id,
                        filter=new_filter
                    ))
                    logging.info(f"User Joiner: Created new folder 'Bot_Channels' and added the channel/group to it")
            except Exception as folder_err:
                logging.error(f"User Joiner: Failed to add channel to folder: {folder_err}")

        # Use shared user_client connection
        user_client = getattr(self, 'user_client', None)
        if not user_client:
            logging.warning("User Joiner: Shared user client not initialized. Auto-joiner is disabled.")
            return
            
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            from telethon.tl.functions.messages import ImportChatInviteRequest
            from telethon.errors import FloodWaitError, ChannelsTooMuchError, InviteHashExpiredError, InviteHashInvalidError
            
            while not self.shutdown_event.is_set():
                try:
                    # 1. Enforce Daily Cap (max 10 joins per 24 hours / calendar day)
                    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    joins_today_key = f"user_joins_today:{today_str}"
                    joins_today = int(self.redis_conn.get(joins_today_key) or 0)
                    
                    if joins_today >= 30:
                        logging.info(f"User Joiner: Daily join limit reached (30/30) for {today_str}. Sleeping for 30 minutes...")
                        await asyncio.wait_for(self.shutdown_event.wait(), timeout=1800)
                        continue
                        
                    # 2. Pop link from user_join_queue
                    # Run blpop in executor to avoid blocking event loop
                    loop = asyncio.get_running_loop()
                    res = await loop.run_in_executor(
                        None,
                        self.redis_conn.blpop,
                        "user_join_queue",
                        5
                    )
                    
                    if not res:
                        continue
                        
                    _, raw_payload = res
                    try:
                        payload = json.loads(raw_payload)
                    except Exception:
                        payload = {"link": raw_payload}
                        
                    link = payload.get("link")
                    if not link:
                        continue
                        
                    # 3. Check if already joined
                    is_joined = self.redis_conn.sismember("user_joined_links", link)
                    if is_joined:
                        logging.info(f"User Joiner: Already joined {link} previously. Skipping.")
                        continue
                        
                    logging.info(f"User Joiner: Attempting to join {link}... (Joins today: {joins_today}/30)")
                    
                    # 4. Resolve link type and perform join
                    link_type, identifier = parse_telegram_link(link)
                    
                    try:
                        updates = None
                        if link_type == 'public':
                            # Public channel/group join
                            updates = await user_client(JoinChannelRequest(identifier))
                            logging.info(f"User Joiner: Successfully joined public channel/group: @{identifier}")
                        elif link_type == 'private':
                            # Private invite link join
                            updates = await user_client(ImportChatInviteRequest(identifier))
                            logging.info(f"User Joiner: Successfully joined private invite link: {identifier}")
                        else:
                            logging.warning(f"User Joiner: Invalid link type '{link_type}' for {link}. Skipping.")
                            continue
                            
                        # Resolve input peer and add to folder
                        try:
                            target_entity = None
                            if updates and hasattr(updates, 'chats') and updates.chats:
                                target_entity = updates.chats[0]
                            else:
                                target_entity = await user_client.get_input_entity(identifier if link_type == 'public' else link)
                                
                            input_peer = await user_client.get_input_entity(target_entity)
                            await add_to_folder(user_client, input_peer)
                        except Exception as folder_err:
                            logging.warning(f"User Joiner: Failed to add chat to folder 'Bot_Channels': {folder_err}")

                        # Save success state
                        self.redis_conn.sadd("user_joined_links", link)
                        self.redis_conn.incr(joins_today_key)
                        self.redis_conn.expire(joins_today_key, 86400) # Expire in 24 hours
                        
                        # 5. Cooldown: Sleep 5 to 10 minutes (300 to 600 seconds) between joins
                        cooldown_sec = random.randint(300, 600)
                        logging.info(f"User Joiner: Safe cooldown initiated. Sleeping for {cooldown_sec // 60} minutes and {cooldown_sec % 60} seconds before next join...")
                        await asyncio.wait_for(self.shutdown_event.wait(), timeout=cooldown_sec)
                        
                    except FloodWaitError as flood_err:
                        # Wait the requested duration plus 60 seconds
                        wait_sec = flood_err.seconds + 60
                        logging.warning(f"User Joiner: Telegram FloodWaitError! Must sleep for {wait_sec} seconds...")
                        # Put link back to head of queue
                        self.redis_conn.lpush("user_join_queue", raw_payload)
                        await asyncio.wait_for(self.shutdown_event.wait(), timeout=wait_sec)
                        
                    except ChannelsTooMuchError:
                        logging.error("User Joiner: Account limit reached! You are already in 500 channels/groups. Auto-joiner is paused.")
                        # Put link back to queue
                        self.redis_conn.lpush("user_join_queue", raw_payload)
                        # Sleep 1 hour and try again
                        await asyncio.wait_for(self.shutdown_event.wait(), timeout=3600)
                        
                    except (InviteHashExpiredError, InviteHashInvalidError) as invite_err:
                        logging.warning(f"User Joiner: Invite link expired or invalid for {link}: {invite_err}")
                        
                    except Exception as join_err:
                        logging.error(f"User Joiner: Failed to join {link}: {join_err}")
                        
                except asyncio.TimeoutError:
                    pass
                except Exception as loop_err:
                    logging.error(f"User Joiner loop error: {loop_err}")
                    await asyncio.sleep(10)
        finally:
            logging.info("User Auto-Joiner background task stopped.")

    async def init_user_client(self):
        user_config = None
        try:
            with open("accounts.json", "r") as f:
                accounts = json.load(f)
                for acc in accounts:
                    if acc.get("role") == "user_joiner" or acc.get("session_name") == "user_session":
                        user_config = acc
                        break
        except Exception as e:
            logging.error(f"User Client: Failed to read accounts.json: {e}")
            return False
            
        if not user_config:
            logging.info("User Client: No 'user_joiner' config found in accounts.json. User client disabled.")
            return False
            
        session_name = user_config["session_name"]
        api_id = user_config["api_id"]
        api_hash = user_config["api_hash"]
        session_path = get_session_path(session_name)
        
        logging.info(f"Initializing Telethon client for user session '{session_name}'...")
        self.user_client = TelegramClient(session_path, api_id, api_hash)
        
        try:
            await self.user_client.connect()
            if not await self.user_client.is_user_authorized():
                logging.error("User Client: User session is not authorized! Please run create_user_session.py.")
                await self.user_client.disconnect()
                self.user_client = None
                return False
            me = await self.user_client.get_me()
            logging.info(f"User Client: Connected successfully as @{me.username or me.first_name}")
            return True
        except Exception as conn_err:
            logging.error(f"User Client: Failed to connect or authenticate client: {conn_err}")
            self.user_client = None
            return False

    async def auto_scan_user_dialogs_loop(self):
        """
        Every 5 minutes, scan all channels/groups that the user_session (Tamer Ads) account
        is currently joined to. For each new channel not already in the DB, scrape its
        description + recent posts, extract the owner contact username, and insert it as
        a lead ready for the campaign dispatcher.
        """
        logging.info("Auto Dialog Scanner: Background task started. Will scan Tamer's channels every 5 minutes.")
        if not hasattr(self, 'user_client') or not self.user_client:
            logging.warning("Auto Dialog Scanner: Shared user client not initialized. Exiting task.")
            return

        KEYWORDS_PATTERN = (
            r'للتواصل|تواصل|تواصلوا|راسل|راسلونا|راسلني|راسلنا|مراسلة|للمراسلة|'
            r'للاشتراك|اشتراك|للانضمام|انضمام|الادارة|الاداره|ادارة|اداره|'
            r'المشرف|مشرف|المشرفين|الدعم|دعم|المسؤول|المسئول|مسؤول|مسئول|'
            r'للاستفسار|استفسار|استفسارات|للاستفسارات|حسابي|خاص|الخاص|'
            r'تواصل معي|تواصل معنا|للتواصل معي|للتواصل معنا|راسلني على|راسلنا على|'
            r'ارسل لي|ارسل لنا|ارسل رسالة|كلمني|كلمني على|تواصل عبر|تواصلوا عبر|'
            r'سجل|التسجيل|للتشراك|للتحدث|تحدث|مطور|المطور|مطورين|'
            r'صاحب القناة|صاحب القناه|مالك القناة|مالك القناه|صاحب|مالك|المالك|الصاحب|'
            r'admin|administrator|support|contact|help|owner|manager|ceo|founder|creator|'
            r'inquiry|inquiries|subscribe|subscription|pm|dm|chat|personal|me|contactme|contactus|'
            r'messageme|reachme|reachus|writeme|writeus|askme|tg|tele|telegram'
        )

        def _extract_contact(text: str, description: str, ch_username: str):
            skip = {
                'vip', 'premium', 'joinchat', 'channel', 'bot', 'ads', 'link', 'group', 'telegram', 
                'robot', 'signals', 'crypto', 'forex', 'arabic', 'trade', 'trading', 'chart', 'charts', 
                'alerts', 'alert', 'course', 'courses', 'education', 'academy', 'hub', 'capital', 'fund', 
                'fx', 'gold', 'signal', 'goldfx', 'team', 'club', 'official', 'news', 'fxsignals', 'system',
                'user', 'adminbot', 'helper', 'supportbot', 'channelbot', 'addstickers', 'share',
                'addlist', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i'
            }

            def _clean(u_str):
                if not u_str:
                    return ""
                c = u_str.strip().lstrip('@').lstrip('/').rstrip('.,;:)!?*~`"\'')
                c = re.sub(r'^https?://(?:www\.)?(?:t\.me|telegram\.me)/', '', c, flags=re.IGNORECASE).strip().lstrip('@').rstrip('/')
                for glued in ['whatsup', 'whatsapp', 'telegram', 'tele', 'vipsignal', 'channel', 'group']:
                    if c.lower().endswith(glued) and len(c) > len(glued) + 3:
                        c = c[:-len(glued)]
                        break
                while c.endswith('_') and len(c) > 3:
                    c = c[:-1]
                while c.startswith('_') and len(c) > 3:
                    c = c[1:]
                return c.strip()

            contact_username = None
            for src in [description or '', text or '']:
                # 1. Keyword -> @username or t.me/username
                m = re.search(r'(?:' + KEYWORDS_PATTERN + r')\s*[:\-\x20]{1,10}(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})', src, re.IGNORECASE)
                if m:
                    cand = _clean(m.group(1))
                    if cand.lower() not in skip and cand.lower() != ch_username.lower() and not cand.startswith('+'):
                        contact_username = cand
                        break
                # 2. @username or t.me/username -> Keyword
                m2 = re.search(r'(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})\s*[:\-\x20]{1,10}(?:' + KEYWORDS_PATTERN + r')', src, re.IGNORECASE)
                if m2:
                    cand = _clean(m2.group(1))
                    if cand.lower() not in skip and cand.lower() != ch_username.lower() and not cand.startswith('+'):
                        contact_username = cand
                        break
                # 3. Any t.me link
                tme_all = re.findall(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{3,35})', src, re.IGNORECASE)
                for raw in tme_all:
                    cand = _clean(raw)
                    if cand.lower() not in skip and cand.lower() != ch_username.lower() and not cand.startswith('+'):
                        contact_username = cand
                        break
                if contact_username:
                    break
                # 4. Fallback: any @mention
                all_mentions = re.findall(r'@([a-zA-Z0-9_]{3,35})', src)
                for raw in all_mentions:
                    cand = _clean(raw)
                    if cand.lower() not in skip and cand.lower() != ch_username.lower() and not cand.startswith('+'):
                        contact_username = cand
                        break
                if contact_username:
                    break
            return contact_username

        while not self.shutdown_event.is_set():
            try:
                logging.info("Auto Dialog Scanner: Starting scan of Tamer Ads account dialogs (including archive)...")
                # Fetch active dialogs
                dialogs_active = await self.user_client.get_dialogs(limit=None)
                
                # Fetch archived dialogs (folder=1 is Telegram's archive folder)
                dialogs_archived = []
                try:
                    dialogs_archived = await self.user_client.get_dialogs(limit=None, folder=1)
                except Exception as arch_err:
                    logging.warning(f"Auto Dialog Scanner: Could not retrieve archived dialogs: {arch_err}")
                
                dialogs = dialogs_active + dialogs_archived
                channels = [d for d in dialogs if d.is_channel or d.is_group]
                logging.info(f"Auto Dialog Scanner: Found {len(channels)} channels/groups (Active: {len(dialogs_active)}, Archived: {len(dialogs_archived)}).")

                self.db_helper.check_connection()
                conn = self.db_helper.conn

                # Fetch current dialog filters (folders) once per scan to avoid rate limits
                all_filters = []
                try:
                    from telethon.tl.functions.messages import GetDialogFiltersRequest
                    res_filters = await self.user_client(GetDialogFiltersRequest())
                    all_filters = res_filters.filters if hasattr(res_filters, 'filters') else []
                except Exception as filter_err:
                    logging.warning(f"Auto Dialog Scanner: Could not fetch dialog filters: {filter_err}")

                # Load active auto campaign ID (from file or DB)
                auto_campaign_id = None
                try:
                    campaign_id_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'auto_campaign_id.txt')
                    if os.path.exists(campaign_id_file):
                        with open(campaign_id_file, 'r') as f:
                            auto_campaign_id = f.read().strip()
                    if not auto_campaign_id:
                        with conn.cursor(cursor_factory=RealDictCursor) as cur_c:
                            cur_c.execute("SELECT id FROM campaigns ORDER BY created_at DESC LIMIT 1")
                            crow = cur_c.fetchone()
                            if crow:
                                auto_campaign_id = str(crow['id'])
                except Exception as c_err:
                    logging.warning(f"Auto Dialog Scanner: Error loading campaign ID: {c_err}")

                # ----------------------------------------------------
                # Folder Management & Sorting
                # ----------------------------------------------------
                admin_channel_ids = set()
                admin_peers_map = {}
                admin_names_list = []
                
                for d in channels:
                    entity = d.entity
                    is_admin = False
                    # Exclude channels that the account has left or been kicked/deactivated from
                    if not getattr(entity, 'left', False) and not getattr(entity, 'kicked', False) and not getattr(entity, 'deactivated', False):
                        if hasattr(entity, 'creator') and entity.creator:
                            is_admin = True
                        elif hasattr(entity, 'admin_rights') and entity.admin_rights is not None:
                            is_admin = True
                    
                    if is_admin:
                        p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'user_id', None) or getattr(d.input_entity, 'id', None)
                        if p_id:
                            admin_channel_ids.add(p_id)
                            admin_peers_map[p_id] = d.input_entity
                            admin_names_list.append(f"{d.name} (@{getattr(entity, 'username', 'N/A')}) [creator={getattr(entity, 'creator', False)}]")
                
                logging.info(f"Auto Dialog Scanner: Detected {len(admin_channel_ids)} active admin channels/groups.")

                TARGET_FOLDERS = {"My_Channels", "حملات", "No_Post", "Banned", "Only_Post"}
                
                from telethon.tl.functions.messages import UpdateDialogFilterRequest
                import telethon.tl.functions.chatlists as chatlists_fn
                from telethon.tl.types import DialogFilter, TextWithEntities, InputPeerSelf, InputChatlistDialogFilter

                target_admin_peers = list(admin_peers_map.values()) if admin_peers_map else [InputPeerSelf()]
                
                def is_channel_or_chat_peer(peer):
                    classname = peer.__class__.__name__
                    return "Channel" in classname or "Chat" in classname

                for f in all_filters:
                    t_str = ""
                    if hasattr(f, 'title') and f.title:
                        t_str = f.title.text if hasattr(f.title, 'text') else str(f.title)
                    
                    if t_str in TARGET_FOLDERS:
                        cleaned_peers = []
                        changed = False
                        
                        if t_str == "My_Channels":
                            # My_Channels should strictly and exclusively contain all active admin channels/groups
                            # Also reset default category flags (groups/broadcasts) to avoid non-admin channels appearing
                            old_ids = set(getattr(p, 'channel_id', None) or getattr(p, 'chat_id', None) or getattr(p, 'id', None) for p in getattr(f, 'include_peers', []))
                            new_ids = set(getattr(p, 'channel_id', None) or getattr(p, 'chat_id', None) or getattr(p, 'id', None) for p in target_admin_peers)
                            
                            has_flag_issue = (getattr(f, 'groups', False) or getattr(f, 'broadcasts', False) or getattr(f, 'contacts', False) or getattr(f, 'non_contacts', False))
                            
                            if old_ids != new_ids or has_flag_issue:
                                f.include_peers = target_admin_peers
                                f.exclude_peers = []
                                f.contacts = False
                                f.non_contacts = False
                                f.groups = False
                                f.broadcasts = False
                                f.bots = False
                                changed = True
                                logging.info(f"Auto Dialog Scanner: Syncing folder 'My_Channels' count from {len(old_ids)} to {len(new_ids)} active admin channels.")
                        else:
                            for peer in getattr(f, 'include_peers', []):
                                if is_channel_or_chat_peer(peer):
                                    p_id = getattr(peer, 'channel_id', None) or getattr(peer, 'chat_id', None) or getattr(peer, 'id', None)
                                    if p_id in admin_channel_ids:
                                        cleaned_peers.append(peer)
                                    else:
                                        changed = True
                                        logging.info(f"Auto Dialog Scanner: Removing non-admin peer {peer.__class__.__name__}(id={p_id}) from folder '{t_str}'")
                                else:
                                    cleaned_peers.append(peer)
                            if changed:
                                f.include_peers = cleaned_peers if cleaned_peers else [InputPeerSelf()]
                        
                        if changed:
                            try:
                                await self.user_client(UpdateDialogFilterRequest(id=f.id, filter=f))
                                logging.info(f"Auto Dialog Scanner: Successfully updated folder '{t_str}' on Telegram server.")
                            except Exception as update_err:
                                logging.error(f"Auto Dialog Scanner: Failed to update folder '{t_str}': {update_err}")

                        # Automatically update Share Link for My_Channels
                        if t_str == "My_Channels":
                            try:
                                folder_input = InputChatlistDialogFilter(filter_id=f.id)
                                exp_res = await self.user_client(chatlists_fn.GetExportedInvitesRequest(chatlist=folder_input))
                                invites = getattr(exp_res, 'invites', [])
                                if invites:
                                    for inv in invites:
                                        url = getattr(inv, 'url', '')
                                        slug = url.split('/')[-1] if '/' in url else url
                                        await self.user_client(chatlists_fn.EditExportedInviteRequest(
                                            chatlist=folder_input,
                                            slug=slug,
                                            title="My_Channels",
                                            peers=target_admin_peers
                                        ))
                                        logging.info(f"Auto Dialog Scanner: Successfully updated Chatlist Share Link ({url}) with {len(target_admin_peers)} admin channels.")
                                else:
                                    export_res = await self.user_client(chatlists_fn.ExportChatlistInviteRequest(
                                        chatlist=folder_input,
                                        title="My_Channels",
                                        peers=target_admin_peers
                                    ))
                                    new_url = getattr(export_res, 'url', None) or getattr(getattr(export_res, 'invite', None), 'url', None)
                                    logging.info(f"Auto Dialog Scanner: Created new Chatlist Share Link: {new_url}")
                            except Exception as share_err:
                                logging.warning(f"Auto Dialog Scanner: Share link sync note: {share_err}")

                from telethon.tl.types import InputPeerSelf
                
                existing_folder_titles = set()
                for f in all_filters:
                    if hasattr(f, 'title'):
                        t_str = f.title.text if hasattr(f.title, 'text') else str(f.title)
                        existing_folder_titles.add(t_str)
                
                for target_title in TARGET_FOLDERS:
                    if target_title not in existing_folder_titles:
                        # Determine include_peers
                        if target_title == "My_Channels":
                            inc_peers = list(admin_peers_map.values()) if admin_peers_map else [InputPeerSelf()]
                        else:
                            inc_peers = [InputPeerSelf()]
                            
                        try:
                            existing_ids = [f.id for f in all_filters if hasattr(f, 'id')]
                            new_f_id = max(existing_ids) + 1 if existing_ids else 2
                            if new_f_id < 2:
                                new_f_id = 2
                            
                            new_filter = DialogFilter(
                                id=new_f_id,
                                title=TextWithEntities(text=target_title, entities=[]),
                                pinned_peers=[],
                                include_peers=inc_peers,
                                exclude_peers=[],
                                contacts=False,
                                non_contacts=False,
                                groups=False,
                                broadcasts=False,
                                bots=False
                            )
                            await self.user_client(UpdateDialogFilterRequest(id=new_f_id, filter=new_filter))
                            all_filters.append(new_filter)
                            existing_folder_titles.add(target_title)
                            logging.info(f"Auto Dialog Scanner: Automatically created missing folder '{target_title}' with Saved Messages placeholder.")
                        except Exception as create_err:
                            logging.error(f"Auto Dialog Scanner: Failed to create missing folder '{target_title}': {create_err}")
                # ----------------------------------------------------

                new_added = 0
                updated_contact = 0

                for d in channels:
                    if self.shutdown_event.is_set():
                        break
                    try:
                        entity = d.entity

                        has_username = getattr(entity, 'username', None)
                        ch_username = entity.username if has_username else f"private_{entity.id}"
                        member_count = getattr(entity, 'participants_count', 0) or 0

                        # Check if already in leads with a contact_username resolved
                        with conn.cursor(cursor_factory=RealDictCursor) as cur:
                            cur.execute(
                                "SELECT id, contact_username FROM leads WHERE channel_username = %s",
                                (ch_username,)
                            )
                            existing = cur.fetchone()

                        # Skip if already has contact resolved
                        if existing and existing.get('contact_username'):
                            continue

                        # Fetch description, pinned message, and recent posts
                        about = ''
                        posts_text_list = []
                        member_count = getattr(entity, 'participants_count', 0) or 0
                        try:
                            from telethon.tl.functions.channels import GetFullChannelRequest
                            full = await self.user_client(GetFullChannelRequest(entity))
                            about = full.full_chat.about or ''
                            member_count = full.full_chat.participants_count or member_count
                            
                            # Check and fetch pinned message content
                            if getattr(full.full_chat, 'pinned_msg_id', None):
                                try:
                                    pinned_msg = await self.user_client.get_messages(entity, ids=full.full_chat.pinned_msg_id)
                                    if pinned_msg and pinned_msg.message:
                                        posts_text_list.append(pinned_msg.message)
                                        logging.info(f"Auto Dialog Scanner: Fetched pinned message for @{ch_username}")
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        try:
                            msgs = await self.user_client.get_messages(entity, limit=100)
                            for m in msgs:
                                if m.message:
                                    posts_text_list.append(m.message)
                        except Exception:
                            pass
                            
                        posts_text = ' \n '.join(posts_text_list)
                        contact_username = _extract_contact(posts_text, about, ch_username)

                        with conn.cursor() as cur:
                            if existing:
                                # Update existing lead with resolved contact
                                if contact_username:
                                    cur.execute("""
                                        UPDATE leads SET
                                            contact_username = %s,
                                            description = COALESCE(NULLIF(description,''), %s),
                                            member_count = GREATEST(member_count, %s),
                                            language = COALESCE(NULLIF(language,''), 'Arabic'),
                                            last_scan = COALESCE(last_scan, NOW()),
                                            last_activity = NOW()
                                        WHERE channel_username = %s
                                    """, (contact_username, about, member_count, ch_username))
                                    conn.commit()
                                    updated_contact += 1
                                    logging.info(f"Auto Dialog Scanner: Updated contact @{contact_username} for existing lead @{ch_username}")
                                    
                                    # Auto-enqueue updated lead into campaign
                                    if auto_campaign_id:
                                        with conn.cursor(cursor_factory=RealDictCursor) as cur2:
                                            cur2.execute("SELECT id FROM leads WHERE channel_username = %s", (ch_username,))
                                            lead_row = cur2.fetchone()
                                        if lead_row:
                                            with conn.cursor() as cur2:
                                                cur2.execute("""
                                                    INSERT INTO campaign_logs (id, campaign_id, lead_id, status, sent_at)
                                                    SELECT gen_random_uuid(), %s, %s, 'pending', NULL
                                                    WHERE NOT EXISTS (
                                                        SELECT 1 FROM campaign_logs
                                                        WHERE campaign_id = %s AND lead_id = %s
                                                    )
                                                """, (auto_campaign_id, lead_row['id'], auto_campaign_id, lead_row['id']))
                                                conn.commit()
                                                if cur2.rowcount > 0:
                                                    logging.info(f"Auto Dialog Scanner: Auto-enqueued UPDATED lead @{ch_username} -> @{contact_username} for outreach!")
                            else:
                                # Insert as a new lead
                                cur.execute("""
                                    INSERT INTO leads (
                                        channel_username, member_count, contact_username,
                                        status, forex_category, forex_intent_score, lead_score,
                                        tier, is_group, description, language, last_scan, last_activity
                                    ) VALUES (
                                        %s, %s, %s,
                                        'new', 'unknown', 80, 50,
                                        'Tier_D', %s, %s, 'Arabic', NOW(), NOW()
                                    ) ON CONFLICT (channel_username) DO UPDATE SET
                                        contact_username = COALESCE(NULLIF(leads.contact_username,''), EXCLUDED.contact_username),
                                        member_count = GREATEST(leads.member_count, EXCLUDED.member_count),
                                        language = COALESCE(NULLIF(leads.language,''), 'Arabic'),
                                        last_scan = COALESCE(leads.last_scan, NOW()),
                                        last_activity = NOW()
                                """, (
                                    ch_username, member_count, contact_username,
                                    d.is_group, about
                                ))
                                conn.commit()
                                new_added += 1
                                if contact_username:
                                    logging.info(f"Auto Dialog Scanner: Added new lead @{ch_username} with contact @{contact_username}")
                                    # Auto-enqueue into campaign
                                    if auto_campaign_id:
                                        with conn.cursor(cursor_factory=RealDictCursor) as cur2:
                                            cur2.execute("SELECT id FROM leads WHERE channel_username = %s", (ch_username,))
                                            lead_row = cur2.fetchone()
                                        if lead_row:
                                            with conn.cursor() as cur2:
                                                cur2.execute("""
                                                    INSERT INTO campaign_logs (id, campaign_id, lead_id, status, sent_at)
                                                    SELECT gen_random_uuid(), %s, %s, 'pending', NULL
                                                    WHERE NOT EXISTS (
                                                        SELECT 1 FROM campaign_logs
                                                        WHERE campaign_id = %s AND lead_id = %s
                                                    )
                                                """, (auto_campaign_id, lead_row['id'], auto_campaign_id, lead_row['id']))
                                                conn.commit()
                                                if cur2.rowcount > 0:
                                                    logging.info(f"Auto Dialog Scanner: Auto-enqueued NEW lead @{ch_username} -> @{contact_username} for outreach!")
                                else:
                                    logging.info(f"Auto Dialog Scanner: Added new lead @{ch_username} (no contact found yet)")

                        await asyncio.sleep(1)  # small delay between channels to avoid rate limits

                    except Exception as ch_err:
                        logging.warning(f"Auto Dialog Scanner: Error processing channel {d.name}: {ch_err}")
                        await asyncio.sleep(2)
                        continue

                logging.info(
                    f"Auto Dialog Scanner: Scan complete. "
                    f"New leads added: {new_added}, Contacts updated: {updated_contact}. "
                    f"Sleeping 5 minutes before next scan..."
                )

            except Exception as scan_err:
                logging.error(f"Auto Dialog Scanner: Unexpected error during scan: {scan_err}", exc_info=True)

            # Sleep 5 minutes before next scan
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=300)
            except asyncio.TimeoutError:
                pass

    def _resolve_media_list(self, m_path):
        if not m_path:
            return []
        if m_path.startswith('[') and m_path.endswith(']'):
            try:
                return [f for f in json.loads(m_path) if os.path.exists(f)]
            except Exception:
                pass
        if ',' in m_path:
            return [f.strip() for f in m_path.split(',') if f.strip() and os.path.exists(f.strip())]
        if os.path.isdir(m_path):
            return [os.path.join(m_path, f) for f in sorted(os.listdir(m_path)) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        if os.path.exists(m_path):
            return [m_path]
        return []

    async def campaign_dispatcher_loop(self):
        logging.info("Outreach Campaign Dispatcher background task started.")
        if not hasattr(self, 'user_client') or not self.user_client:
            logging.warning("Campaign Dispatcher: Shared user client not initialized. Exiting task.")
            return
            
        user_client = self.user_client
        import time
        import random
        
        while not self.shutdown_event.is_set():
            # ── Outreach Engine: Emergency & Circuit Breaker Check ──────────
            if not is_outreach_enabled(self.redis_conn):
                logging.info("Campaign Dispatcher: Outreach globally disabled. Sleeping 60s.")
                await asyncio.sleep(60)
                continue
            if self.circuit_breaker and self.circuit_breaker.check_account_circuit('user_session')[0]:
                reason = self.circuit_breaker.check_account_circuit('user_session')[1]
                logging.warning(f"Campaign Dispatcher: Account circuit breaker OPEN: {reason}. Sleeping 120s.")
                await asyncio.sleep(120)
                continue
            try:
                self.db_helper.check_connection()
                conn = self.db_helper.conn
                
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT cl.id as log_id, cl.campaign_id, cl.lead_id, c.message_text, c.media_path,
                               l.contact_username, l.channel_username
                        FROM campaign_logs cl
                        JOIN campaigns c ON cl.campaign_id = c.id
                        JOIN leads l ON cl.lead_id = l.id
                        WHERE cl.status = 'pending'
                        ORDER BY c.created_at ASC, cl.sent_at ASC NULLS FIRST
                        LIMIT 1
                        FOR UPDATE OF cl SKIP LOCKED
                    """)
                    pending_item = cur.fetchone()
                    
                    if not pending_item:
                        conn.commit()
                        await asyncio.sleep(10)
                        continue
                        
                    log_id = pending_item['log_id']
                    campaign_id = pending_item['campaign_id']
                    lead_id = pending_item['lead_id']
                    message_text = pending_item['message_text']
                    media_path = pending_item['media_path']
                    contact_username = pending_item['contact_username']
                    channel_username = pending_item['channel_username']
                    
                    # Mark processing state in DB to claim row
                    cur.execute("UPDATE campaign_logs SET status = 'processing' WHERE id = %s", (log_id,))
                    conn.commit()

                    # Idempotency check in Redis
                    idempotency_key = f"campaign:delivered:{campaign_id}:{lead_id}"
                    if self.redis_conn.exists(idempotency_key):
                        logging.info(f"Campaign Dispatcher: Idempotency hit: message for lead {lead_id} already delivered. Marking sent.")
                        cur.execute("UPDATE campaign_logs SET status = 'sent', sent_at = %s WHERE id = %s", (datetime.now(), log_id))
                        conn.commit()
                        continue
                    
                    # ── Outreach Engine: Eligibility Check ──────────────────
                    if self.outreach_metrics:
                        self.outreach_metrics.record_attempt('user_session', str(campaign_id))
                    
                    elig_status, elig_reason = check_eligibility(
                        self.redis_conn, conn.cursor(), str(lead_id), str(campaign_id),
                        contact_username or ''
                    )
                    if elig_status != 'ELIGIBLE':
                        logging.info(f"Campaign Dispatcher: Lead {lead_id} not eligible: {elig_status} - {elig_reason}")
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'skipped', error_message = %s, sent_at = %s, eligibility = %s WHERE id = %s",
                            (f"Not eligible: {elig_reason}", datetime.now(), elig_status, log_id)
                        )
                        conn.commit()
                        if self.outreach_metrics:
                            self.outreach_metrics.record_skip(elig_status)
                            self.outreach_metrics.record_eligibility_check(elig_status)
                        continue
                    
                    # ── Outreach Engine: Risk Scoring ──────────────────────
                    risk_score, risk_level = calculate_risk_score(
                        self.redis_conn, conn.cursor(), str(lead_id), 'user_session', str(campaign_id)
                    )
                    if risk_level in ('HIGH', 'CRITICAL'):
                        logging.warning(f"Campaign Dispatcher: Lead {lead_id} risk too high: {risk_level} (score={risk_score}). Skipping.")
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'skipped', error_message = %s, sent_at = %s, risk_level = %s WHERE id = %s",
                            (f"Risk too high: {risk_level} (score={risk_score})", datetime.now(), risk_level, log_id)
                        )
                        conn.commit()
                        if self.outreach_metrics:
                            self.outreach_metrics.record_skip('HIGH_RISK')
                            self.outreach_metrics.record_risk_level(risk_level)
                        continue
                    
                    # Record risk level and eligibility on the log row
                    cur.execute(
                        "UPDATE campaign_logs SET risk_level = %s, eligibility = %s, attempt_count = COALESCE(attempt_count, 0) + 1, last_attempt_at = %s WHERE id = %s",
                        (risk_level, 'ELIGIBLE', datetime.now(), log_id)
                    )
                    conn.commit()
                    
                    # ── Outreach Engine: Message Validation ────────────────
                    msg_valid, msg_errors = validate_message(message_text, self._resolve_media_list(media_path) if media_path else None)
                    if not msg_valid:
                        logging.warning(f"Campaign Dispatcher: Message validation failed for lead {lead_id}: {msg_errors}")
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'skipped', error_message = %s, sent_at = %s WHERE id = %s",
                            (f"Message validation failed: {'; '.join(msg_errors)}", datetime.now(), log_id)
                        )
                        conn.commit()
                        continue
                    
                    # ── Outreach Engine: Dry Run Check ─────────────────────
                    if is_dry_run():
                        decision = log_dry_run_decision(
                            str(lead_id), str(campaign_id), contact_username or '',
                            'user_session', risk_level, 'ELIGIBLE',
                            message_text[:100] if message_text else ''
                        )
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'skipped', error_message = 'DRY_RUN: Message not sent', sent_at = %s WHERE id = %s",
                            (datetime.now(), log_id)
                        )
                        conn.commit()
                        if self.outreach_metrics:
                            self.outreach_metrics.record_dry_run_decision()
                        continue
                    
                    # 1. Enforce configurable daily cap
                    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    campaign_sent_key = f"campaign_sent_today:{today_str}"
                    sent_today = int(self.redis_conn.get(campaign_sent_key) or 0)
                    daily_limit = int(os.getenv("CAMPAIGN_DAILY_LIMIT", 60))
                    jitter_min = int(os.getenv("CAMPAIGN_JITTER_MIN", 90))
                    jitter_max = int(os.getenv("CAMPAIGN_JITTER_MAX", 210))
                    burst_size = int(os.getenv("CAMPAIGN_BURST_SIZE", 5))

                    if sent_today >= daily_limit:
                        logging.info(f"Campaign Dispatcher: Daily outreach limit reached ({sent_today}/{daily_limit}) for {today_str}. Sleeping for 60 minutes...")
                        await asyncio.wait_for(self.shutdown_event.wait(), timeout=3600)
                        continue

                    # 1b. Human micro-break: every burst_size messages, take a 10-20 min pause
                    if sent_today > 0 and sent_today % burst_size == 0:
                        break_key = f"campaign_break_taken:{today_str}:{sent_today}"
                        if not self.redis_conn.get(break_key):
                            break_duration = random.randint(600, 1200)
                            logging.info(f"Campaign Dispatcher: Short pause of {break_duration//60} minutes after sending {sent_today} messages...")
                            self.redis_conn.set(break_key, "1", ex=break_duration + 1800)
                            await asyncio.wait_for(self.shutdown_event.wait(), timeout=break_duration)
                            continue

                    # 2. Check if account is globally rate limited for DMs
                    until_ts = self.redis_conn.get("health:user_session:dm_rate_limited_until")
                    if until_ts:
                        try:
                            diff = float(until_ts) - time.time()
                            if diff > 0:
                                logging.info(f"Campaign Dispatcher: Account DM cooling cooldown active. Sleeping for {int(diff)} seconds...")
                                await asyncio.wait_for(self.shutdown_event.wait(), timeout=diff)
                                continue
                        except ValueError:
                            pass

                    # Strictly require valid contact_username
                    target_username = contact_username.strip().lstrip('@') if contact_username else None
                    if not target_username:
                        logging.info(f"Campaign Dispatcher: No direct contact username for lead {lead_id} (@{channel_username}). Marking as skipped.")
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'skipped', error_message = 'No contact username', sent_at = %s WHERE id = %s",
                            (datetime.now(), log_id)
                        )
                        conn.commit()
                        continue

                    # Skip bot accounts or system keywords
                    target_lower = target_username.lower()
                    if target_lower.endswith('bot') or target_lower.endswith('_bot') or target_lower in ('addlist', 'everyone', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i', '4030'):
                        logging.info(f"Campaign Dispatcher: @{target_username} is a bot or system keyword. Skipping log ID {log_id}.")
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'skipped', error_message = 'Invalid contact: bot or system keyword', sent_at = %s WHERE id = %s",
                            (datetime.now(), log_id)
                        )
                        conn.commit()
                        continue

                    # 2b. Strict contact deduplication check: Skip if target_username was ALREADY sent a message
                    cur.execute("""
                        SELECT COUNT(*) as count
                        FROM campaign_logs cl2
                        JOIN leads l2 ON cl2.lead_id = l2.id
                        WHERE LOWER(l2.contact_username) = LOWER(%s)
                          AND cl2.status = 'sent'
                    """, (target_username,))
                    already_sent_res = cur.fetchone()
                    already_sent_count = already_sent_res['count'] if already_sent_res else 0

                    if already_sent_count > 0:
                        logging.info(f"Campaign Dispatcher: Contact @{target_username} was ALREADY messaged previously. Skipping duplicate log ID {log_id} (channel @{channel_username}).")
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'skipped', error_message = %s, sent_at = %s WHERE id = %s",
                            ("Skipped: Contact username already messaged via another channel/campaign", datetime.now(), log_id)
                        )
                        # Also skip any remaining duplicate pending logs for this contact
                        cur.execute("""
                            UPDATE campaign_logs cl_sub
                            SET status = 'skipped', error_message = 'Skipped: Contact username already messaged', sent_at = %s
                            FROM leads l_sub
                            WHERE cl_sub.lead_id = l_sub.id AND LOWER(l_sub.contact_username) = LOWER(%s) AND cl_sub.status = 'pending'
                        """, (datetime.now(), target_username))
                        conn.commit()
                        continue
                        
                    # 3. Message sending with multi-tier fallback (Album -> Single Photo -> Text Pitch)
                    logging.info(f"Campaign Dispatcher: Attempting outreach message delivery to @{target_username} (associated with channel @{channel_username})...")
                    
                    success = False
                    error_message = None
                    
                    try:
                        peer = await user_client.get_input_entity(target_username)
                        media_files = self._resolve_media_list(media_path)
                        if media_files:
                            try:
                                if len(media_files) == 1:
                                    logging.info(f"Campaign Dispatcher: Sending message with single media: {media_files[0]}")
                                    await user_client.send_message(peer, message_text, file=media_files[0])
                                else:
                                    logging.info(f"Campaign Dispatcher: Sending message with album of {len(media_files)} images...")
                                    await user_client.send_file(peer, media_files, caption=message_text)
                            except Exception as media_err:
                                logging.warning(f"Campaign Dispatcher: Media send failed for @{target_username} ({media_err}). Falling back to text-only pitch...")
                                await user_client.send_message(peer, message_text)
                        else:
                            await user_client.send_message(peer, message_text)
                        success = True
                    except errors.FloodWaitError as flood_err:
                        wait_seconds = flood_err.seconds + 60
                        error_message = f"Telegram rate limit: FloodWaitError ({flood_err.seconds}s)"
                        logging.warning(f"Campaign Dispatcher: Rate limit triggered for @{target_username}: {error_message}. Cooling down for {wait_seconds}s...")
                        self.redis_conn.set("health:user_session:dm_rate_limited_until", time.time() + wait_seconds, ex=wait_seconds + 3600)
                        # ── Outreach Engine: Record FloodWait ──────────────
                        if self.account_health_mgr:
                            self.account_health_mgr.record_flood_wait('user_session', 'send_message', flood_err.seconds)
                        if self.circuit_breaker:
                            self.circuit_breaker.record_flood_wait('user_session')
                        if self.adaptive_throttle:
                            self.adaptive_throttle.record_flood_wait(flood_err.seconds)
                        if self.outreach_metrics:
                            self.outreach_metrics.record_flood_wait('user_session', flood_err.seconds)
                            self.outreach_metrics.record_failure('user_session', str(campaign_id), 'FloodWait')
                        # Keep lead as pending so it will be retried safely after cooldown
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'pending', error_message = NULL, sent_at = NULL WHERE id = %s",
                            (log_id,)
                        )
                        conn.commit()
                        await asyncio.sleep(min(wait_seconds, 1800))
                        continue
                    except errors.PeerFloodError as peer_flood:
                        error_message = "Telegram PeerFloodError: Account is in temporary spam cooldown."
                        logging.warning(f"Campaign Dispatcher: PeerFloodError hit on @{target_username}! Pausing outreach for 2 hours to protect account.")
                        self.redis_conn.set("health:user_session:dm_rate_limited_until", time.time() + 7200, ex=8000)
                        # ── Outreach Engine: Record PeerFlood ──────────────
                        if self.account_health_mgr:
                            self.account_health_mgr.record_error('user_session', 'PeerFloodError', str(peer_flood))
                        if self.circuit_breaker:
                            self.circuit_breaker.record_flood_wait('user_session')
                        if self.outreach_metrics:
                            self.outreach_metrics.record_failure('user_session', str(campaign_id), 'PeerFlood')
                        # Keep lead as pending
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'pending', error_message = NULL, sent_at = NULL WHERE id = %s",
                            (log_id,)
                        )
                        conn.commit()
                        await asyncio.sleep(3600)
                        continue
                    except Exception as dispatch_err:
                        error_message = str(dispatch_err)
                        err_lower = error_message.lower()
                        
                        # Check if error is a temporary rate limit or connection issue
                        is_temporary = (
                            "too many requests" in err_lower or
                            "flood" in err_lower or
                            "wait" in err_lower or
                            "timeout" in err_lower or
                            "connection" in err_lower or
                            "network" in err_lower or
                            "rpc" in err_lower
                        )
                        
                        if is_temporary:
                            logging.warning(f"Campaign Dispatcher: Temporary issue detected for @{target_username}: {error_message}. Will retry after cooldown.")
                            self.redis_conn.set("health:user_session:dm_rate_limited_until", time.time() + 300, ex=600)
                            cur.execute(
                                "UPDATE campaign_logs SET status = 'pending', error_message = NULL, sent_at = NULL WHERE id = %s",
                                (log_id,)
                            )
                            conn.commit()
                            await asyncio.sleep(300)
                            continue
                        else:
                            # Permanent error: privacy settings, deleted account, blocked DMs
                            logging.warning(f"Campaign Dispatcher: Permanent delivery failure for @{target_username}: {error_message}")
                        
                    if success:
                        logging.info(f"Campaign Dispatcher: Successfully sent message to @{target_username}!")
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'sent', sent_at = %s WHERE id = %s",
                            (datetime.now(), log_id)
                        )
                        cur.execute(
                            "UPDATE leads SET status = 'contacted', last_activity = %s WHERE id = %s",
                            (datetime.now(), lead_id)
                        )
                        
                        # Mark all other pending campaign logs for the SAME contact_username as skipped to prevent duplicate DMs
                        cur.execute("""
                            UPDATE campaign_logs cl_sub
                            SET status = 'skipped', error_message = %s, sent_at = %s
                            FROM leads l_sub
                            WHERE cl_sub.lead_id = l_sub.id AND LOWER(l_sub.contact_username) = LOWER(%s) AND cl_sub.status = 'pending' AND cl_sub.id != %s
                        """, (f"Skipped: Contact username messaged via channel @{channel_username}", datetime.now(), target_username, log_id))

                        # Increment daily sent count in Redis
                        self.redis_conn.incr(campaign_sent_key)
                        self.redis_conn.expire(campaign_sent_key, 86400)
                        
                        # ── Outreach Engine: Record Success ────────────────
                        if self.account_health_mgr:
                            self.account_health_mgr.record_success('user_session')
                        if self.adaptive_throttle:
                            self.adaptive_throttle.record_success()
                        if self.outreach_metrics:
                            self.outreach_metrics.record_success('user_session', str(campaign_id))
                            self.outreach_metrics.record_eligibility_check('ELIGIBLE')
                            self.outreach_metrics.record_risk_level(risk_level)
                        # Update per-lead cooldown
                        try:
                            cur.execute(
                                "UPDATE leads SET last_contact_at = %s, next_eligible_at = %s WHERE id = %s",
                                (datetime.now(), datetime.now() + timedelta(days=30), lead_id)
                            )
                            conn.commit()
                        except Exception:
                            pass
                    else:
                        cur.execute(
                            "UPDATE campaign_logs SET status = 'failed', error_message = %s, sent_at = %s WHERE id = %s",
                            (error_message, datetime.now(), log_id)
                        )
                        # ── Outreach Engine: Record Failure ────────────────
                        if self.account_health_mgr:
                            self.account_health_mgr.record_error('user_session', 'permanent', error_message or '')
                        if self.adaptive_throttle:
                            self.adaptive_throttle.record_failure()
                        if self.outreach_metrics:
                            self.outreach_metrics.record_failure('user_session', str(campaign_id), 'permanent')
                        if self.circuit_breaker:
                            self.circuit_breaker.record_rejection(str(campaign_id))
                        
                    conn.commit()
                    
                # 4. Safe human-like random jitter between sends (90 to 210 seconds)
                if self.adaptive_throttle:
                    jitter_profile = int(self.adaptive_throttle.get_next_delay())
                else:
                    jitter_profile = random.randint(jitter_min, jitter_max)
                logging.info(f"Campaign Dispatcher: Pacing sleep: {jitter_profile}s (~{jitter_profile//60}m {jitter_profile%60}s). Daily sent: {sent_today}/{daily_limit}.")
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=jitter_profile)
                
            except asyncio.TimeoutError:
                pass
            except Exception as loop_err:
                logging.error(f"Campaign Dispatcher error in main loop: {loop_err}")
                await asyncio.sleep(10)

    async def followup_dispatcher_loop(self):
        """
        Outreach Follow-up Campaign Dispatcher:
        Safely sends follow-up messages (up to 8 per day) to leads who were messaged
        previously but have not replied after X days (default: 4 days).
        Automatically skips any contact that has already replied in chat!
        """
        logging.info("Follow-up Campaign Dispatcher background task started.")
        if not hasattr(self, 'user_client') or not self.user_client:
            logging.warning("Follow-up Dispatcher: Shared user client not initialized. Exiting task.")
            return

        user_client = self.user_client
        import time
        import random

        while not self.shutdown_event.is_set():
            try:
                self.db_helper.check_connection()
                conn = self.db_helper.conn

                today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                followup_sent_key = f"campaign_followup_sent_today:{today_str}"
                sent_today = int(self.redis_conn.get(followup_sent_key) or 0)

                if sent_today >= 8:
                    logging.info(f"Follow-up Dispatcher: Daily follow-up limit reached ({sent_today}/8) for {today_str}. Sleeping for 60 minutes...")
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=3600)
                    continue

                until_ts = self.redis_conn.get("health:user_session:followup_rate_limited_until")
                if until_ts:
                    try:
                        diff = float(until_ts) - time.time()
                        if diff > 0:
                            logging.info(f"Follow-up Dispatcher: Account follow-up cooling cooldown active. Sleeping for {int(diff)}s...")
                            await asyncio.wait_for(self.shutdown_event.wait(), timeout=diff)
                            continue
                    except ValueError:
                        pass

                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT cl.id as log_id, cl.campaign_id, cl.lead_id, cl.sent_at,
                               c.followup_message_text, c.followup_media_path, c.followup_delay_days,
                               l.contact_username, l.channel_username
                        FROM campaign_logs cl
                        JOIN campaigns c ON cl.campaign_id = c.id
                        JOIN leads l ON cl.lead_id = l.id
                        WHERE c.followup_enabled = TRUE
                          AND c.followup_message_text IS NOT NULL
                          AND cl.status = 'sent'
                          AND (cl.followup_status IS NULL OR cl.followup_status = 'pending')
                          AND cl.user_replied = FALSE
                          AND cl.sent_at < NOW() - (COALESCE(c.followup_delay_days, 4) || ' days')::INTERVAL
                        ORDER BY cl.sent_at ASC NULLS FIRST
                        LIMIT 1
                        FOR UPDATE OF cl SKIP LOCKED
                    """)
                    pending_followup = cur.fetchone()

                    if not pending_followup:
                        conn.commit()
                        await asyncio.sleep(30)
                        continue

                    log_id = pending_followup['log_id']
                    campaign_id = pending_followup['campaign_id']
                    lead_id = pending_followup['lead_id']
                    target_username = pending_followup['contact_username']
                    channel_username = pending_followup['channel_username']
                    followup_text = pending_followup['followup_message_text']
                    followup_media = pending_followup['followup_media_path']

                    # Mark followup_status as processing
                    cur.execute("UPDATE campaign_logs SET followup_status = 'processing' WHERE id = %s", (log_id,))
                    conn.commit()

                    # Idempotency check for follow-up
                    followup_idempotency_key = f"campaign:followup_delivered:{campaign_id}:{lead_id}"
                    if self.redis_conn.exists(followup_idempotency_key):
                        logging.info(f"Follow-up Dispatcher: Idempotency hit: follow-up for lead {lead_id} already delivered. Marking sent.")
                        cur.execute("UPDATE campaign_logs SET followup_status = 'sent', followup_sent_at = %s WHERE id = %s", (datetime.now(), log_id))
                        conn.commit()
                        continue

                    if not target_username:
                        cur.execute("UPDATE campaign_logs SET followup_status = 'skipped', followup_error_message = 'No contact username' WHERE id = %s", (log_id,))
                        conn.commit()
                        continue

                    # 3. Check chat history: strictly verify that the other party never replied and no back-and-forth conversation occurred!
                    try:
                        peer = await user_client.get_input_entity(target_username)
                        msgs = await user_client.get_messages(peer, limit=25)
                        if msgs:
                            has_incoming = any(not getattr(m, 'out', True) for m in msgs)
                            total_msg_count = len(msgs)
                            
                            # If the contact sent ANY message (has_incoming is True), or if there are more than 2 messages in chat (meaning prior discussion)
                            if has_incoming or total_msg_count > 2:
                                reason = "User replied in chat" if has_incoming else f"Existing conversation ({total_msg_count} messages)"
                                logging.info(f"Follow-up Dispatcher: @{target_username} (channel @{channel_username}) SKIPPED: {reason}. Marking as replied.")
                                cur.execute("UPDATE campaign_logs SET user_replied = TRUE, followup_status = 'skipped', followup_error_message = %s WHERE id = %s", (reason, log_id))
                                conn.commit()
                                continue
                    except Exception as peer_err:
                        logging.warning(f"Follow-up Dispatcher: Could not inspect chat with @{target_username}: {peer_err}")

                    # 4. Send follow-up message
                    logging.info(f"Follow-up Dispatcher: Sending follow-up message to @{target_username} (associated with @{channel_username})...")
                    success = False
                    error_message = None

                    try:
                        media_files = self._resolve_media_list(followup_media)
                        if media_files:
                            if len(media_files) == 1:
                                logging.info(f"Follow-up Dispatcher: Sending with single media: {media_files[0]}")
                                await user_client.send_message(peer, followup_text, file=media_files[0])
                            else:
                                logging.info(f"Follow-up Dispatcher: Sending with album of {len(media_files)} images...")
                                await user_client.send_file(peer, media_files, caption=followup_text)
                        else:
                            await user_client.send_message(peer, followup_text)
                        success = True
                    except errors.FloodWaitError as flood_err:
                        wait_seconds = flood_err.seconds + 60
                        logging.warning(f"Follow-up Dispatcher: FloodWait ({flood_err.seconds}s). Cooling down...")
                        self.redis_conn.set("health:user_session:followup_rate_limited_until", time.time() + wait_seconds, ex=wait_seconds + 3600)
                        await asyncio.sleep(min(wait_seconds, 1800))
                        continue
                    except Exception as send_err:
                        error_message = str(send_err)
                        logging.error(f"Follow-up Dispatcher: Send error for @{target_username}: {error_message}")

                    if success:
                        logging.info(f"Follow-up Dispatcher: Successfully sent follow-up to @{target_username}!")
                        cur.execute("UPDATE campaign_logs SET followup_status = 'sent', followup_sent_at = %s WHERE id = %s", (datetime.now(), log_id))
                        self.redis_conn.incr(followup_sent_key)
                        self.redis_conn.expire(followup_sent_key, 86400)
                    else:
                        cur.execute("UPDATE campaign_logs SET followup_status = 'failed', followup_error_message = %s WHERE id = %s", (error_message, log_id))

                    conn.commit()

                # Jitter: 25 to 45 minutes between follow-up messages
                jitter = random.randint(1500, 2700)
                logging.info(f"Follow-up Dispatcher: Sleeping {jitter}s (~{jitter//60} min). Today sent: {sent_today}/8.")
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=jitter)

            except asyncio.TimeoutError:
                pass
            except Exception as loop_err:
                logging.error(f"Follow-up Dispatcher error in loop: {loop_err}")
                await asyncio.sleep(15)

    async def start(self):
        """
        Initializes connections and runs the main validation queue loop.
        """
        # Connect to Redis
        logging.info(f"Connecting to Redis at {self.redis_host}:{self.redis_port}...")
        try:
            self.redis_conn = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=True
            )
            self.redis_conn.ping()
            logging.info("Redis connected successfully.")
        except Exception as e:
            logging.error(f"Redis connection failed: {e}")
            sys.exit(1)
            
        # Connect to PostgreSQL
        logging.info(f"Connecting to PostgreSQL at {self.db_host}:{self.db_port}...")
        try:
            self.db_helper = DatabaseHelper(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            self.keyword_service = KeywordFrequencyService(self.db_helper)
        except Exception as e:
            logging.error(f"PostgreSQL connection failed: {e}")
            sys.exit(1)
            
        # Initialize Central Telegram Manager
        logging.info("Initializing Telegram Manager...")
        self.tg_manager = TelegramManager(self.redis_conn, session_name=self.session_name, worker_type="validator")
        await self.tg_manager.start_all()

        # Initialize rejected_groups_set in Redis from PostgreSQL
        try:
            logging.info("Initializing rejected_groups_set in Redis from database...")
            self.db_helper.check_connection()
            query = "SELECT channel_username FROM leads WHERE is_group = TRUE AND (status = 'rejected' OR COALESCE(forex_intent_score, 0) < 40);"
            with self.db_helper.conn.cursor() as cur:
                cur.execute(query)
                rejected_groups = cur.fetchall()
            
            if rejected_groups:
                pipe = self.redis_conn.pipeline()
                for rg in rejected_groups:
                    username = rg['channel_username']
                    if username:
                        pipe.sadd("rejected_groups_set", username.lower())
                pipe.execute()
                logging.info(f"Successfully populated {len(rejected_groups)} rejected groups into Redis 'rejected_groups_set'.")
            else:
                logging.info("No rejected groups found in database to populate.")
        except Exception as init_err:
            logging.error(f"Failed to initialize rejected_groups_set in Redis: {init_err}")
        
        # ── Initialize Outreach Engine ─────────────────────────────────────
        try:
            self.outreach_metrics = OutreachMetrics(self.redis_conn, self.db_helper.conn)
            self.account_health_mgr = AccountHealthManager(self.redis_conn, self.db_helper.conn)
            self.adaptive_throttle = AdaptiveThrottle(self.redis_conn, 'user_session')
            self.circuit_breaker = CircuitBreaker(self.redis_conn)
            self.backpressure_mgr = BackpressureManager(self.redis_conn)
            self.reconciliation_mgr = ReconciliationManager(
                self.redis_conn, self.db_helper.conn
            )
            # Run outreach schema migration
            try:
                migration_path = os.path.join(os.path.dirname(__file__), 'migrate_outreach_engine.sql')
                if os.path.exists(migration_path):
                    with open(migration_path, 'r') as f:
                        migration_sql = f.read()
                    self.db_helper.conn.cursor().execute(migration_sql)
                    self.db_helper.conn.commit()
                    logging.info("Outreach engine schema migration applied successfully.")
            except Exception as mig_err:
                logging.warning(f"Outreach migration warning (may already be applied): {mig_err}")
                try:
                    self.db_helper.conn.rollback()
                except Exception:
                    pass
            logging.info("Outreach engine modules initialized.")
        except Exception as oe_err:
            logging.error(f"Outreach engine initialization error (non-fatal): {oe_err}")

        # Start the periodic rescan scheduler
        asyncio.create_task(self.rescan_scheduler_loop())
        
        # Initialize the shared user client for auto-joiner and campaign dispatcher
        has_user_client = await self.init_user_client()
        
        if has_user_client:
            # Start the user auto-joiner background loop
            self.user_joiner_task = asyncio.create_task(self.user_joiner_loop())
            # Start the outreach campaign dispatcher background loop (12 new leads/day)
            self.campaign_dispatcher_task = asyncio.create_task(self.campaign_dispatcher_loop())
            # Start the follow-up dispatcher background loop (8 follow-ups/day)
            self.followup_dispatcher_task = asyncio.create_task(self.followup_dispatcher_loop())
            # Start the auto dialog scanner: watches Tamer's joined channels and extracts owners
            self.auto_scan_task = asyncio.create_task(self.auto_scan_user_dialogs_loop())
        else:
            logging.warning("User client not initialized. Auto-joiner, Campaign dispatcher, Follow-up dispatcher and Auto Dialog Scanner are disabled.")
        
        try:
            # Setup graceful signal handlers
            def trigger_shutdown():
                logging.info("Shutdown signal received. Graceful exit initiated...")
                self.shutdown_event.set()
                
            loop = asyncio.get_running_loop()
            try:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, trigger_shutdown)
            except NotImplementedError:
                pass
                
            # Queue Loop (Pops from multiple Redis lists based on Priority Queue order)
            logging.info("Validator queue listener is active. Monitoring priority queues...")
            while not self.shutdown_event.is_set():
                try:
                    res = await loop.run_in_executor(
                        None, 
                        self.redis_conn.blpop, 
                        ["queue:critical", "queue:high", "queue:normal", "queue:low"], 
                        5  # Check shutdown event every 5 seconds
                    )
                    
                    if res:
                        # res is a tuple: (list_name_where_popped, value)
                        list_name, link = res
                        logging.info(f"Popped link for validation from '{list_name}': {link}")
                        await self.process_link(link)
                        await asyncio.sleep(1.5)  # Anti-ban sleep for HTTP preview requests
                        
                except redis.exceptions.TimeoutError:
                    # Ignore normal socket timeouts during empty-queue blpop
                    pass
                except Exception as loop_err:
                    logging.error(f"Error in main Validator loop iteration: {loop_err}", exc_info=True)
                    await asyncio.sleep(5)
                    
        except (KeyboardInterrupt, asyncio.CancelledError):
            logging.info("Validator interrupted.")
        finally:
            if hasattr(self, 'user_joiner_task'):
                self.user_joiner_task.cancel()
                try:
                    await self.user_joiner_task
                except asyncio.CancelledError:
                    pass
            if hasattr(self, 'campaign_dispatcher_task'):
                self.campaign_dispatcher_task.cancel()
                try:
                    await self.campaign_dispatcher_task
                except asyncio.CancelledError:
                    pass
            if hasattr(self, 'followup_dispatcher_task'):
                self.followup_dispatcher_task.cancel()
                try:
                    await self.followup_dispatcher_task
                except asyncio.CancelledError:
                    pass
            if hasattr(self, 'auto_scan_task'):
                self.auto_scan_task.cancel()
                try:
                    await self.auto_scan_task
                except asyncio.CancelledError:
                    pass
            if hasattr(self, 'user_client') and self.user_client:
                try:
                    await self.user_client.disconnect()
                    logging.info("Shared user client disconnected.")
                except Exception as dc_err:
                    logging.warning(f"Error disconnecting shared user client: {dc_err}")
            await self.tg_manager.disconnect_all()
            self.db_helper.close()
            self.redis_conn.close()
            logging.info("Worker B (The Validator) has stopped.")

if __name__ == "__main__":
    validator = LeadValidator()
    try:
        asyncio.run(validator.start())
    except KeyboardInterrupt:
        logging.info("Process terminated. Exiting.")
    except Exception as e:
        logging.critical(f"FATAL WORKER ERROR: {e}", exc_info=True)
        sys.exit(1)