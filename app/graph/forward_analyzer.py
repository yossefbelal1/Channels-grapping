"""
app/graph/forward_analyzer.py — Production-Hardened Forward Origin Detection & Edge Evidence

Hardened Features:
- Extracts channel ID, peer ID, message ID, and public username from message.fwd_from
- Does NOT require a public username if channel ID or peer ID is present
- Preserves forward relationships even when from_name is missing
- Never invents a forward relationship
- Generates structured, explainable edge evidence:
  {source_message_id, original_channel_id, original_message_id, observed_at}
"""

import logging
from datetime import datetime, timezone
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
        Extracts the strongest available origin identity from a Telethon Message object
        or a mock message dictionary.

        Returns structured origin dict or None if not a forward.
        """
        if not message:
            return None

        # Check Telethon Message or dict
        fwd = getattr(message, 'fwd_from', None)
        msg_id = getattr(message, 'id', None)

        if fwd is None and isinstance(message, dict):
            fwd = message.get('fwd_from')
            msg_id = message.get('id')

        if not fwd:
            return None

        origin: Dict[str, Any] = {
            "is_forward": True,
            "channel_id": None,
            "peer_id": None,
            "channel_post_id": None,
            "from_name": None,
            "from_username": None,
            "source_message_id": msg_id,
            "date": None,
            "evidence": {}
        }

        # 1. Extract date
        origin["date"] = getattr(fwd, 'date', None) if not isinstance(fwd, dict) else fwd.get('date')

        # 2. Extract channel_post / message_id in origin channel
        origin["channel_post_id"] = getattr(fwd, 'channel_post', None) if not isinstance(fwd, dict) else fwd.get('channel_post')
        if not origin["channel_post_id"]:
            saved_msg_id = getattr(fwd, 'saved_from_msg_id', None) if not isinstance(fwd, dict) else fwd.get('saved_from_msg_id')
            if saved_msg_id:
                origin["channel_post_id"] = saved_msg_id

        # 3. Extract from_name
        origin["from_name"] = getattr(fwd, 'from_name', None) if not isinstance(fwd, dict) else fwd.get('from_name')

        # 4. Extract Peer ID / Channel ID from from_id
        from_id = getattr(fwd, 'from_id', None) if not isinstance(fwd, dict) else fwd.get('from_id')
        if from_id is not None:
            ch_id = getattr(from_id, 'channel_id', None)
            if isinstance(ch_id, (int, str)):
                origin["channel_id"] = str(ch_id)
                origin["peer_id"] = str(ch_id)
            elif isinstance(from_id, (int, str)):
                origin["channel_id"] = str(from_id)
                origin["peer_id"] = str(from_id)
            elif hasattr(from_id, 'user_id') and isinstance(getattr(from_id, 'user_id', None), (int, str)):
                origin["peer_id"] = str(from_id.user_id)
            elif hasattr(from_id, 'chat_id') and isinstance(getattr(from_id, 'chat_id', None), (int, str)):
                origin["peer_id"] = str(from_id.chat_id)
            elif isinstance(from_id, dict):
                c_id = from_id.get('channel_id') or from_id.get('peer_id')
                if c_id:
                    origin["channel_id"] = str(c_id)
                    origin["peer_id"] = str(c_id)

        # 5. Fallback to saved_from_peer if from_id is absent
        saved_peer = getattr(fwd, 'saved_from_peer', None) if not isinstance(fwd, dict) else fwd.get('saved_from_peer')
        if not origin["channel_id"] and saved_peer is not None:
            sp_ch_id = getattr(saved_peer, 'channel_id', None)
            if isinstance(sp_ch_id, (int, str)):
                origin["channel_id"] = str(sp_ch_id)
                origin["peer_id"] = str(sp_ch_id)
            elif isinstance(saved_peer, (int, str)):
                origin["channel_id"] = str(saved_peer)
                origin["peer_id"] = str(saved_peer)

        # 6. Extract from_username (Telethon forward object, fwd attributes, or from_name)
        fwd_obj = getattr(message, 'forward', None)
        if fwd_obj:
            chat_obj = getattr(fwd_obj, 'chat', None)
            if chat_obj and getattr(chat_obj, 'username', None):
                origin["from_username"] = chat_obj.username
            sender_obj = getattr(fwd_obj, 'sender', None)
            if not origin["from_username"] and sender_obj and getattr(sender_obj, 'username', None):
                origin["from_username"] = sender_obj.username

        if not origin["from_username"]:
            direct_user = getattr(fwd, 'from_username', None) if not isinstance(fwd, dict) else fwd.get('from_username')
            if direct_user:
                origin["from_username"] = str(direct_user).lstrip('@')

        if not origin["from_username"] and origin.get("from_name"):
            import re
            name = str(origin["from_name"]).strip()
            if name.startswith("@") and len(name) > 1:
                origin["from_username"] = name[1:]
            elif "t.me/" in name:
                m = re.search(r't\.me/([a-zA-Z0-9_]{5,32})', name)
                if m:
                    origin["from_username"] = m.group(1)

        # 7. Structured Explainable Edge Evidence (PART L)
        observed_time = origin["date"]
        if observed_time is None:
            observed_time = datetime.now(timezone.utc).isoformat()
        elif hasattr(observed_time, 'isoformat'):
            observed_time = observed_time.isoformat()

        origin["evidence"] = {
            "relation_type": "forwarded_from",
            "source_message_id": msg_id,
            "original_channel_id": origin["channel_id"],
            "original_message_id": origin["channel_post_id"],
            "origin_name": origin["from_name"],
            "origin_username": origin["from_username"],
            "observed_at": observed_time
        }

        return origin

    @staticmethod
    def summarize_forwards(messages: List[Any]) -> Dict[str, Any]:
        """
        Analyzes a batch of sampled messages to compute forward metrics.
        """
        if not messages:
            return {"total_messages": 0, "forwarded_count": 0, "forward_ratio": 0.0, "top_origins": []}

        origin_counts: Dict[str, int] = {}
        forwarded_count = 0

        for msg in messages:
            origin = ForwardAnalyzer.extract_forward_origin(msg)
            if origin:
                forwarded_count += 1
                # Prefer human-readable name, then channel ID or peer ID
                key = str(origin.get("from_name") or origin.get("channel_id") or origin.get("peer_id") or "unknown")
                origin_counts[key] = origin_counts.get(key, 0) + 1

        ratio = round(forwarded_count / len(messages), 3) if messages else 0.0
        sorted_origins = sorted(origin_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_messages": len(messages),
            "forwarded_count": forwarded_count,
            "forward_ratio": ratio,
            "top_origins": [{"origin_identifier": k, "count": v} for k, v in sorted_origins[:5]]
        }
