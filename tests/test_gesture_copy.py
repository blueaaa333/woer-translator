import unittest
from gesture_copy import GestureCopy
class GestureCopyTests(unittest.TestCase):
 def source(self):return dict(pid=1,hwnd=2,clipboard_before=3,emitted=1000,x=20,y=30,id=5)
 def test_no_gesture_cannot_prompt(self):self.assertIsNone(GestureCopy().consume(1,2,4,1,1050))
 def test_cancelled_gesture_does_not_probe_clipboard_later(self):
  from app import App
  from unittest.mock import Mock
  fake=Mock();fake.selection_version=3
  App.probe_source_copy(fake,self.source(),2)
  fake.try_explicit_copy.assert_not_called();fake.root.after.assert_not_called()
 def test_format_notifications_do_not_close_existing_selection_toolbar(self):
  from app import App
  from unittest.mock import Mock
  fake=Mock();fake.popup.winfo_exists.return_value=True;fake.pending_source=self.source()
  App.offer_clipboard(fake,'water')
  fake.offer_selection.assert_not_called();fake.close_floating.assert_not_called()
 def test_clipboard_notifications_do_not_replace_pending_gesture(self):
  import ctypes
  from ctypes import wintypes
  from app import App
  from unittest.mock import Mock,patch
  fake=Mock();fake.popup=None;fake.pending_gesture=self.source();fake.auto.get.return_value=True;fake.seq=4;fake.try_explicit_copy.return_value=False
  def pid(window,pointer):ctypes.cast(pointer,ctypes.POINTER(wintypes.DWORD))[0]=1
  with patch('app.u') as user:
   user.GetForegroundWindow.return_value=2;user.GetWindowThreadProcessId.side_effect=pid;user.GetClipboardSequenceNumber.return_value=4
   App.offer_clipboard(fake,'water')
  fake.offer_selection.assert_not_called()
 def test_cancel_prevents_delayed_toolbar(self):
  c=GestureCopy();c.record(self.source());c.cancel(1020);self.assertIsNone(c.consume(1,2,4,1,1050))
 def test_stale_cancel_does_not_discard_new_selection(self):
  c=GestureCopy();c.record(self.source());c.cancel(999);self.assertEqual(c.consume(1,2,4,1,1050),self.source())
 def test_unchanged_clipboard_cannot_confirm_gesture(self):
  c=GestureCopy();c.record(self.source());self.assertIsNone(c.consume(1,2,3,1,1050))
 def test_fresh_source_owned_copy_confirms_original_anchor(self):
  c=GestureCopy();c.record(self.source());self.assertEqual(c.consume(1,2,4,1,1050),self.source());self.assertIsNone(c.consume(1,2,5,1,1100))
 def test_other_clipboard_owner_cannot_confirm_gesture(self):
  c=GestureCopy();c.record(self.source());self.assertIsNone(c.consume(1,2,4,9,1050))
 def test_other_window_or_expired_gesture_cannot_confirm(self):
  c=GestureCopy();c.record(self.source());self.assertIsNone(c.consume(1,20,4,1,1050));self.assertIsNone(c.consume(1,2,4,1,1701))
 def test_app_uses_original_selection_anchor_after_source_copy(self):
  import ctypes
  from ctypes import wintypes
  from app import App
  from unittest.mock import Mock,patch
  fake=Mock();fake.auto.get.return_value=True;fake.selection.get.return_value=True
  copied=dict(pid=1,hwnd=2,copy_sequence=4);original=self.source()
  def owner_pid(window,pointer):ctypes.cast(pointer,ctypes.POINTER(wintypes.DWORD))[0]=1
  with patch('app.u') as user,patch('selection_verifier.source_is_active',return_value=True),patch('copy_intent.recent_copy.consume',return_value=False),patch('gesture_copy.recent_gesture.consume',return_value=original):
   user.GetClipboardSequenceNumber.return_value=4;user.GetClipboardOwner.return_value=3;user.GetWindowThreadProcessId.side_effect=owner_pid
   self.assertTrue(App.try_explicit_copy(fake,copied))
  fake.prompt.assert_called_once_with('',original)
