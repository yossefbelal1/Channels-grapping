# Graph Intelligence Engine

The Arabic Forex Discovery Engine utilizes a Multi-Edge Graph Intelligence Engine (Phase 2) to build a sophisticated network of relationships between Telegram channels.

## Core Concepts

### Nodes
Nodes represent individual Telegram channels or groups (leads).

### Edges
Edges are directed relationships between nodes, categorized by type:
- `recommendation`: Official similar channel recommendations from Telegram.
- `forwarded_from`: Content syndicated or forwarded from another channel.
- `promoted`: Explicitly promoted or sponsored content containing advertising keywords.
- `link`: A standard t.me link found in a message.
- `mention`: An @username mention in a message.

### Edge Confidence Model
Edges are assigned a confidence score based on their relation type:
- `forwarded_from`: 95
- `recommendation`: 90
- `promoted`: 85
- `link`: 75
- `mention`: 70

Repeated occurrences of the same edge increment the `occurrence_count` and slowly boost the confidence up to 100.

## Discovery Pipeline Integration
The Graph Engine (Worker D) traverses validated high-value channels, extracting relationships and discovering new candidates. These candidates are deduped globally using the `ProvenanceManager` and pushed to the `queue:high` shared pipeline.
