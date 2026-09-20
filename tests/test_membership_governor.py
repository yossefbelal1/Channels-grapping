"""
tests/test_membership_governor.py — Unit tests for MembershipGovernor
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from app.core.membership_governor import MembershipGovernor


class DummyEntity:
    def __init__(self, username="test_chan", ent_id=1001, is_creator=False, admin_rights=None, left=False, kicked=False):
        self.id = ent_id
        self.username = username
        self.creator = is_creator
        self.admin_rights = admin_rights
        self.left = left
        self.kicked = kicked


class DummyDialog:
    def __init__(self, entity, is_channel=True, is_group=False, days_ago=20):
        self.entity = entity
        self.is_channel = is_channel
        self.is_group = is_group
        self.date = datetime.now(timezone.utc) - timedelta(days=days_ago)


class TestMembershipGovernor:

    def test_admin_creator_100_percent_immunity(self):
        # 1. Creator channel
        creator_entity = DummyEntity(is_creator=True)
        assert MembershipGovernor.is_admin_or_creator(creator_entity) is True

        # 2. Admin rights channel
        admin_entity = DummyEntity(admin_rights=MagicMock(post_messages=True))
        assert MembershipGovernor.is_admin_or_creator(admin_entity) is True

        # 3. Regular member (no admin rights)
        regular_entity = DummyEntity(is_creator=False, admin_rights=None)
        assert MembershipGovernor.is_admin_or_creator(regular_entity) is False

        # 4. Already left
        left_admin = DummyEntity(is_creator=True, left=True)
        assert MembershipGovernor.is_admin_or_creator(left_admin) is False

    @pytest.mark.asyncio
    async def test_scan_account_capacity_separates_admin_channels(self):
        client = AsyncMock()
        admin_d = DummyDialog(DummyEntity("my_admin_channel", ent_id=1, is_creator=True))
        regular_d = DummyDialog(DummyEntity("forex_signals", ent_id=2, is_creator=False))
        client.get_dialogs.side_effect = lambda limit=None, folder=None: [admin_d, regular_d] if folder is None else []

        gov = MembershipGovernor()
        admin_dialogs, non_admin_dialogs = await gov.scan_account_capacity(client)

        assert len(admin_dialogs) == 1
        assert admin_dialogs[0].entity.username == "my_admin_channel"
        assert len(non_admin_dialogs) == 1
        assert non_admin_dialogs[0].entity.username == "forex_signals"

    @pytest.mark.asyncio
    async def test_retention_of_pending_new_leads(self):
        """Channels with status='new' (pending validation) must NEVER be evicted."""
        gov = MembershipGovernor()
        gov.check_db_lead_status = MagicMock(return_value="new")

        client = AsyncMock()
        pending_d = DummyDialog(DummyEntity("pending_lead", ent_id=10, is_creator=False), days_ago=20)
        client.get_dialogs.side_effect = lambda limit=None, folder=None: [pending_d] if folder is None else []

        with patch("asyncio.sleep", new_callable=AsyncMock):
            stats = await gov.execute_governance_on_account("test_session", client)

        assert stats["leaves_executed"] == 0
        client.assert_not_called()

    @pytest.mark.asyncio
    async def test_eviction_of_value_completed_leads(self):
        """Channels already validated, rejected, or sent in DB are safely pruned."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "0"
        mock_redis.pipeline.return_value.execute.return_value = [1]

        gov = MembershipGovernor(redis_conn=mock_redis)
        gov.check_db_lead_status = MagicMock(return_value="validated")

        client = AsyncMock()
        completed_d = DummyDialog(DummyEntity("completed_lead", ent_id=20, is_creator=False), days_ago=10)
        client.get_dialogs.side_effect = lambda limit=None, folder=None: [completed_d] if folder is None else []

        with patch("asyncio.sleep", new_callable=AsyncMock):
            stats = await gov.execute_governance_on_account("test_session", client)

        assert stats["leaves_executed"] == 1

    @pytest.mark.asyncio
    async def test_daily_leaves_limit_enforcement(self):
        """When an account reaches 30 leaves in 24 hours, halt leaves."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "30"  # Already at MAX_LEAVES_PER_DAY

        gov = MembershipGovernor(redis_conn=mock_redis)
        client = AsyncMock()

        stats = await gov.execute_governance_on_account("capped_session", client)
        assert stats["status"] == "DAILY_LIMIT_REACHED"
        assert stats["leaves_executed"] == 0
        client.get_dialogs.assert_not_called()
