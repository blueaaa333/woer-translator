import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from mac_bridge import MacBridge
from mac_native import Gestures


class MacGestureTests(unittest.TestCase):
    def raw(self, kind, x=100, y=100, clicks=1, at=1000):
        return dict(type=kind, x=x, y=y, at=at, clicks=clicks)

    def test_drag_works_in_other_browsers_and_keeps_release_anchor(self):
        for bundle in ('com.apple.Safari', 'company.thebrowser.Browser', 'com.google.Chrome.canary',
                       'com.microsoft.edgemac', 'com.example.pdfreader'):
            tracker = Gestures({10, 11})
            tracker.handle(self.raw('down'), (12, bundle))
            kind, selected = tracker.handle(self.raw('up', x=160), (12, bundle))
            self.assertEqual(kind, 'gesture')
            self.assertEqual((selected['x'], selected['y'], selected['word']), (160, 100, ''))

    def test_single_click_clears_double_click_offers_actions(self):
        tracker = Gestures({10})
        self.assertEqual(tracker.handle(self.raw('up'), (12, 'com.browser'))[0], 'clear')
        self.assertEqual(tracker.handle(self.raw('up', clicks=2), (12, 'com.browser'))[0], 'gesture')

    def test_own_windows_and_app_switch_cannot_reuse_drag(self):
        tracker = Gestures({10, 11})
        tracker.handle(self.raw('down'), (12, 'com.browser'))
        self.assertIsNone(tracker.handle(self.raw('up', x=180), (10, 'our.app')))
        self.assertEqual(tracker.handle(self.raw('up', x=180), (12, 'com.browser'))[0], 'clear')
        self.assertIsNone(tracker.handle(self.raw('up', clicks=2), (12, 'com.apple.finder')))


class MacBridgeTests(unittest.TestCase):
    def test_cache_and_disabled_selection_do_not_call_system_apis(self):
        bridge = MacBridge(queue.Queue(), threading.Event(), threading.Event(), '.')
        bridge.receive(dict(kind='clipboard', sequence=42, text='current'))
        self.assertEqual(bridge.clipboard(), (42, 'current'))
        bridge.receive(dict(kind='gesture', value={'id': 1}))
        self.assertTrue(bridge.events.empty())
        bridge.enabled.set()
        bridge.receive(dict(kind='gesture', value={'id': 2}))
        self.assertEqual(bridge.events.get_nowait(), ('gesture', {'id': 2}))

    def test_query_is_queued_and_backpressure_cannot_block_ui(self):
        bridge = MacBridge(queue.Queue(), threading.Event(), threading.Event(), '.')
        self.assertTrue(bridge.send('query', pid=12, version=3))
        command = bridge.commands.get_nowait()
        self.assertEqual((command['pid'], command['version']), (12, 3))
        self.assertIn('created', command)
        for _ in range(32):
            self.assertTrue(bridge.send('permissions'))
        self.assertFalse(bridge.send('permissions'))
        self.assertEqual(bridge.events.get_nowait()[0], 'status')

    def test_poll_is_rescheduled_after_a_transient_clipboard_error(self):
        from app import App
        fake = Mock()
        with patch('app.clipboard_sequence', side_effect=OSError('temporary clipboard failure')):
            App.poll(fake)
        fake.on_error.assert_called_once()
        fake.root.after.assert_called_once_with(25, fake.poll)

    def test_stale_query_cannot_replace_a_newer_selection(self):
        from app import App
        fake = Mock()
        fake.mac_query = dict(version=3, anchor=None)
        fake.selection_version = 4
        App.finish_mac_query(fake, dict(version=3, word='wrong'))
        fake.lookup.assert_not_called()
        self.assertIsNone(fake.mac_query)


if __name__ == '__main__':
    unittest.main()
