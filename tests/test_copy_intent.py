import unittest
from copy_intent import CopyIntent
class CopyIntentTests(unittest.TestCase):
 def test_cancel_discards_pending_copy(self):
  c=CopyIntent();c.record(1,2,3,1000);c.cancel(1020);self.assertFalse(c.consume(1,2,4,1050))
 def test_background_clipboard_change_is_not_copy(self):self.assertFalse(CopyIntent().consume(1,2,4,1000))
 def test_copy_requires_changed_clipboard(self):
  c=CopyIntent();c.record(1,2,3,1000);self.assertFalse(c.consume(1,2,3,1050));self.assertTrue(c.consume(1,2,4,1050))
 def test_cannot_reuse_copy_intent(self):
  c=CopyIntent();c.record(1,2,3,1000);self.assertTrue(c.consume(1,2,4,1050));self.assertFalse(c.consume(1,2,5,1100))
 def test_other_window_cannot_use_intent(self):
  c=CopyIntent();c.record(1,2,3,1000);self.assertFalse(c.consume(1,20,4,1050));self.assertFalse(c.consume(10,2,4,1050))
 def test_expired_or_future_copy_is_rejected(self):
  for now in (999,2501):
   c=CopyIntent();c.record(1,2,3,1000);self.assertFalse(c.consume(1,2,4,now))
 def test_app_prompts_after_explicit_copy_without_pdf_text_provider(self):
  from app import App
  from unittest.mock import Mock,patch
  fake=Mock();fake.auto.get.return_value=True;source=dict(pid=1,hwnd=2,copy_sequence=4)
  with patch('app.u') as user,patch('selection_verifier.source_is_active',return_value=True),patch('copy_intent.recent_copy.consume',return_value=True):
   user.GetClipboardSequenceNumber.return_value=4
   self.assertTrue(App.try_explicit_copy(fake,source))
  fake.prompt.assert_called_once_with('',source)
 def test_app_does_not_prompt_after_window_or_clipboard_changes(self):
  from app import App
  from unittest.mock import Mock,patch
  fake=Mock();fake.auto.get.return_value=True;source=dict(pid=1,hwnd=2,copy_sequence=4)
  with patch('app.u') as user,patch('selection_verifier.source_is_active',return_value=True):
   user.GetClipboardSequenceNumber.return_value=5
   self.assertFalse(App.try_explicit_copy(fake,source))
  fake.prompt.assert_not_called()
