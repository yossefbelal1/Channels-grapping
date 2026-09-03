"""
app/scoring/growth_analyzer.py — Observable Member Count Growth Tracking

Computes growth metrics and growth_score strictly based on historical snapshot observations:
- member_count_t0, member_count_t1
- time_delta_days
- growth_absolute
- growth_percentage
- growth_rate_per_day
- growth_score (0-100)
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone


class GrowthAnalyzer:
    @staticmethod
    def calculate_growth_from_snapshots(
        snapshots: List[Dict[str, Any]]
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Calculates observable growth metrics from a list of historical snapshot records.
        Each snapshot dict must contain 'member_count' and 'recorded_at' (or 'created_at').
        Snapshots are expected to be ordered chronologically or will be sorted.

        Returns:
            Tuple of (growth_score: int 0-100, evidence: Dict[str, Any])
        """
        if not snapshots or len(snapshots) < 2:
            return 50, {
                "status": "INSUFFICIENT_DATA",
                "snapshot_count": len(snapshots) if snapshots else 0,
                "growth_score": 50,
                "reason": "Single snapshot or unobserved history; neutral baseline assigned."
            }

        # Sort snapshots by recorded_at
        def get_ts(s):
            dt = s.get("recorded_at") or s.get("created_at")
            if isinstance(dt, datetime):
                return dt.timestamp()
            elif isinstance(dt, (int, float)):
                return float(dt)
            return 0.0

        sorted_snaps = sorted(snapshots, key=get_ts)
        t0_snap = sorted_snaps[0]
        t1_snap = sorted_snaps[-1]

        m_t0 = int(t0_snap.get("member_count") or 0)
        m_t1 = int(t1_snap.get("member_count") or 0)

        dt_t0 = t0_snap.get("recorded_at") or t0_snap.get("created_at")
        dt_t1 = t1_snap.get("recorded_at") or t1_snap.get("created_at")

        if isinstance(dt_t0, datetime) and isinstance(dt_t1, datetime):
            time_delta_seconds = abs((dt_t1 - dt_t0).total_seconds())
        else:
            time_delta_seconds = 86400 # fallback 1 day

        time_delta_days = max(0.01, time_delta_seconds / 86400.0)

        growth_absolute = m_t1 - m_t0
        growth_percentage = (growth_absolute / max(1, m_t0)) * 100.0
        growth_rate_per_day = growth_absolute / time_delta_days

        # Score calculation:
        # Base 50 for stable channel (0% growth)
        # > +5% daily growth -> 80-100
        # > +20% total growth -> 70-90
        # Negative growth (loss of members) -> drops to 10-40
        if growth_percentage >= 50.0 and time_delta_days <= 30:
            growth_score = 95
        elif growth_percentage >= 25.0 and time_delta_days <= 14:
            growth_score = 90
        elif growth_percentage >= 10.0:
            growth_score = 75
        elif growth_percentage >= 0.0:
            # Gentle positive growth
            growth_score = min(70, 50 + int(growth_percentage * 2))
        elif growth_percentage >= -5.0:
            # Minor fluctuation
            growth_score = 45
        else:
            # Sharp decline
            growth_score = max(10, 50 - int(abs(growth_percentage)))

        evidence = {
            "status": "OBSERVED",
            "snapshot_count": len(sorted_snaps),
            "member_count_t0": m_t0,
            "member_count_t1": m_t1,
            "time_delta_days": round(time_delta_days, 2),
            "growth_absolute": growth_absolute,
            "growth_percentage": round(growth_percentage, 2),
            "growth_rate_per_day": round(growth_rate_per_day, 2),
            "growth_score": growth_score
        }

        return growth_score, evidence
