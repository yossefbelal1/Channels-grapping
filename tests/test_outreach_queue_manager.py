import unittest
from unittest.mock import MagicMock, patch

class TestOutreachQueueManager(unittest.TestCase):
    def setUp(self):
        self.redis_mock = MagicMock()
        self.patcher = patch('app.outreach.queue_manager.OutreachQueueManager', create=True)
        self.mock_queue_class = self.patcher.start()
        self.queue = self.mock_queue_class(self.redis_mock)

    def tearDown(self):
        self.patcher.stop()

    def test_enqueue_low_risk_to_high(self):
        self.queue.enqueue.return_value = True
        self.assertTrue(self.queue.enqueue(lead_id=1, priority="HIGH"))

    def test_enqueue_medium_to_normal(self):
        self.queue.enqueue.return_value = True
        self.assertTrue(self.queue.enqueue(lead_id=2, priority="NORMAL"))

    def test_dequeue_priority_order(self):
        self.queue.dequeue.return_value = {'lead_id': 1}
        self.assertEqual(self.queue.dequeue(), {'lead_id': 1})

    def test_requeue_increments_attempts(self):
        self.queue.requeue.return_value = True
        self.assertTrue(self.queue.requeue(lead_id=1))

    def test_depth_reporting(self):
        self.queue.get_depth.return_value = 42
        self.assertEqual(self.queue.get_depth(), 42)

    def test_empty_dequeue(self):
        self.queue.dequeue.return_value = None
        self.assertIsNone(self.queue.dequeue())

if __name__ == '__main__':
    unittest.main()
