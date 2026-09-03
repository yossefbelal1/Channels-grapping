"""
app/graph/forward_analyzer.py — Forward Origin Detection & Signal Provider Mapper
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ForwardAnalyzer:
    """
    Analyzes forwarded messages to identify parent signal providers,
    master broadcast channels, and cross-channel content syndication.
    """

    @staticmethod
    def extract_forward_origin(message) -> Optional[Dict[str, Any]]:
        """
        Extracts origin channel metadata from a Telethon Message object.
        Returns dict with origin details or None if not forwarded.
        """
        if not getattr(message, 'fwd_from', None):
            return None

        fwd = message.fwd_from
        origin = {
            "is_forward": True,
            "channel_id": None,
            "channel_post_id": getattr(fwd, 'channel_post', None),
            "from_name": getattr(fwd, 'from_name', None),
            "date": getattr(fwd, 'date', None)
        }

        # Extract channel peer ID if available
        if getattr(fwd, 'from_id', None):
            from telethon.tl.types import PeerChannel
            if isinstance(fwd.from_id, PeerChannel):
                origin["channel_id"] = str(fwd.from_id.channel_id)
            elif isinstance(getattr(fwd.from_id, 'channel_id', None), (int, str)):
                origin["channel_id"] = str(fwd.from_id.channel_id)

        return origin

    @staticmethod
    def summarize_forwards(messages: List[Any]) -> Dict[str, Any]:
        """
        Analyzes a batch of sampled messages to compute forward metrics.
        Returns:
            {
                "total_messages": int,
                "forwarded_count": int,
                "forward_ratio": float,
                "top_origins": List[Dict[str, Any]]
            }
        """
        if not messages:
            return {"total_messages": 0, "forwarded_count": 0, "forward_ratio": 0.0, "top_origins": []}

        origin_counts: Dict[str, int] = {}
        forwarded_count = 0

        for msg in messages:
            origin = ForwardAnalyzer.extract_forward_origin(msg)
            if origin:
                forwarded_count += 1
                key = str(origin.get("channel_id") or origin.get("from_name") or "unknown")
                origin_counts[key] = origin_counts.get(key, 0) + 1

        ratio = round(forwarded_count / len(messages), 3) if messages else 0.0
        sorted_origins = sorted(origin_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_messages": len(messages),
            "forwarded_count": forwarded_count,
            "forward_ratio": ratio,
            "top_origins": [{"origin_identifier": k, "count": v} for k, v in sorted_origins[:5]]
        }
