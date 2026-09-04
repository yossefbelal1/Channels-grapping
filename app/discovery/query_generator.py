"""
app/discovery/query_generator.py — Extensible Multi-Platform Cross-Lingual Query Generator

Generates high-recall discovery queries targeting Telegram, TikTok, Facebook,
and the public Web across Arabic and English financial/forex domains.
"""

import random
from typing import List, Dict, Set, Optional
from app.discovery.entity_model import Platform


class QueryGenerator:
    """
    Extensible query generator supporting Arabic & English seeds,
    platform-specific search operators, intent modifiers, and dynamic expansion.
    """

    DEFAULT_ARABIC_SEEDS = [
        "فوركس",
        "تداول",
        "تداول العملات",
        "سوق العملات",
        "تحليل فني",
        "تحليل الذهب",
        "تداول الذهب",
        "إشارات فوركس",
        "إشارات تداول",
        "نسخ التداول",
        "حسابات ممولة",
        "شركة فوركس",
        "وسيط فوركس",
        "أكاديمية تداول",
        "دورات تداول",
        "توصيات تداول",
        "VIP تداول"
    ]

    DEFAULT_ENGLISH_SEEDS = [
        "forex",
        "forex arabic",
        "trading arabic",
        "forex trading",
        "gold trading",
        "XAUUSD",
        "EURUSD",
        "forex signals",
        "trading signals",
        "copy trading",
        "prop firm",
        "forex broker",
        "trading academy",
        "trading courses",
        "VIP signals"
    ]

    INTENT_MODIFIERS_AR = [
        "قناة تليجرام",
        "جروب تداول",
        "توصيات vip",
        "حساب حقيقي",
        "تحليلات يومية",
        "سكالبينج ذهب",
        "سمارت موني",
        "إدارة محافظ",
        "بونص إيداع"
    ]

    INTENT_MODIFIERS_EN = [
        "telegram channel",
        "vip group",
        "daily signals",
        "gold scalping",
        "smc ict analysis",
        "funded account challenge",
        "best broker arabic"
    ]

    def __init__(
        self,
        custom_arabic_seeds: Optional[List[str]] = None,
        custom_english_seeds: Optional[List[str]] = None
    ):
        self.arabic_seeds: List[str] = list(custom_arabic_seeds or self.DEFAULT_ARABIC_SEEDS)
        self.english_seeds: List[str] = list(custom_english_seeds or self.DEFAULT_ENGLISH_SEEDS)
        self.dynamic_seeds: Set[str] = set()

    def add_seed(self, keyword: str, language: str = "ar") -> None:
        """Dynamically appends a new seed keyword to the generator."""
        clean = keyword.strip()
        if not clean:
            return
        if language.lower() in ("ar", "arabic"):
            if clean not in self.arabic_seeds:
                self.arabic_seeds.append(clean)
        else:
            if clean not in self.english_seeds:
                self.english_seeds.append(clean)
        self.dynamic_seeds.add(clean)

    def get_all_base_seeds(self) -> List[str]:
        """Returns unified deduplicated list of all base seeds."""
        seen = set()
        result = []
        for s in self.arabic_seeds + self.english_seeds + list(self.dynamic_seeds):
            if s.lower() not in seen:
                seen.add(s.lower())
                result.append(s)
        return result

    def generate_queries_for_platform(
        self,
        platform: str,
        limit: int = 50,
        shuffle: bool = True
    ) -> List[str]:
        """
        Generates platform-tailored discovery search queries.
        """
        plat = platform.lower().strip()
        seeds = self.get_all_base_seeds()
        if shuffle:
            random.shuffle(seeds)

        queries: List[str] = []

        for seed in seeds:
            if plat == Platform.TELEGRAM:
                queries.append(f'"{seed}" site:t.me')
                queries.append(f'{seed} "t.me/"')
                queries.append(f'{seed} telegram channel forex')
            elif plat == Platform.TIKTOK:
                # Queries targeting TikTok creator profiles and videos
                queries.append(f'"{seed}" site:tiktok.com/@')
                queries.append(f'site:tiktok.com/@ {seed} "t.me"')
                queries.append(f'{seed} "tiktok.com/@" trading')
                queries.append(f'site:tiktok.com/tag/{seed.replace(" ", "")}')
            elif plat == Platform.FACEBOOK:
                # Queries targeting Facebook public trading pages and communities
                queries.append(f'site:facebook.com "{seed}" ("t.me" OR "telegram")')
                queries.append(f'site:facebook.com/pages "{seed}" forex')
                queries.append(f'site:facebook.com/groups "{seed}" trading')
            elif plat == Platform.WEB:
                # General web discovery targeting directory, blog and trading platforms
                queries.append(f'"{seed}" ("t.me/" OR "telegram.me/")')
                queries.append(f'"{seed}" "قناة توصيات" (telegram OR t.me)')
                queries.append(f'"{seed}" forex trading community arabic')
            else:
                queries.append(f"{seed} trading forex")

            if len(queries) >= limit:
                break

        return queries[:limit]

    def generate_cross_platform_bridge_queries(self, limit: int = 25) -> List[str]:
        """
        Generates queries specifically designed to find cross-platform bridges:
        e.g. TikTok/Facebook profiles that link directly to Telegram communities.
        """
        seeds = self.arabic_seeds[:10] + self.english_seeds[:10]
        random.shuffle(seeds)
        queries = []
        for s in seeds:
            queries.append(f'site:tiktok.com/@ "{s}" "t.me"')
            queries.append(f'site:facebook.com "{s}" "t.me"')
            queries.append(f'"{s}" "tiktok.com/@" "t.me"')
            if len(queries) >= limit:
                break
        return queries[:limit]
