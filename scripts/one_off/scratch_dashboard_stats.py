import json
from dashboard import get_quality_stats

try:
    stats = get_quality_stats()
    print(stats)
except Exception as e:
    print(f"Error: {e}")
