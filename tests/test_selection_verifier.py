import queue,subprocess,unittest
from unittest.mock import Mock,patch
from selection_verifier import check_selection
class SelectionVerifierTests(unittest.TestCase):
 def test_prepare_only_queues_a_readonly_warmup(self):
  from selection_verifier import SelectionVerifier
  verifier=SelectionVerifier('.',queue.Queue());verifier.submit=Mock()
  verifier.prepare(self.source());verifier.submit.assert_called_once_with(None,dict(self.source(),_warm=True))
 def test_unavailable_uia_does_not_cancel_scheduled_pdf_copy_probe(self):
  from app import App
  source=dict(self.source(),clipboard_before=3)
  fake=Mock();fake.selection_version=1;fake.pending_gesture=source;fake.selection.get.return_value=True
  App.finish_selection(fake,(1,source,False))
  self.assertEqual(fake.pending_gesture,source);fake.prompt.assert_not_called()
 def test_pdf_provider_first_response_can_take_more_than_half_a_second(self):
  import threading
  from selection_verifier import SelectionVerifier
  verifier=SelectionVerifier('.',queue.Queue());verifier.server=Mock();verifier.server.poll.return_value=None;verifier.lines=queue.Queue()
  timer=threading.Timer(.6,lambda:verifier.lines.put(b'SELECTED'));timer.start()
  try:self.assertTrue(verifier.windows_check(self.source()))
  finally:timer.join();verifier.close()
 def test_late_provider_must_still_confirm_real_selection(self):
  from selection_verifier import SelectionVerifier
  verifier=SelectionVerifier('.',queue.Queue());verifier.server=Mock();verifier.server.poll.return_value=None;verifier.lines=queue.Queue();verifier.lines.put(b'EMPTY')
  try:self.assertFalse(verifier.windows_check(self.source()))
  finally:verifier.close()
 def source(self):return dict(pid=12,hwnd=23,x=100,y=100,id=1,emitted=1000)
 def test_no_selection_is_rejected(self):
  proc=Mock();proc.returncode=0;proc.communicate.return_value=(b'EMPTY\n',b'');proc.poll.return_value=0
  with patch('selection_verifier.subprocess.Popen',return_value=proc):self.assertFalse(check_selection('.',self.source()))
 def test_confirmed_selection(self):
  proc=Mock();proc.returncode=0;proc.communicate.return_value=(b'SELECTED\n',b'');proc.poll.return_value=0
  with patch('selection_verifier.subprocess.Popen',return_value=proc):self.assertTrue(check_selection('.',self.source()))
 def test_timeout_kills_only_verifier_process(self):
  proc=Mock();proc.poll.return_value=None;proc.communicate.side_effect=[subprocess.TimeoutExpired('helper',.65),(b'',b'')]
  with patch('selection_verifier.subprocess.Popen',return_value=proc):self.assertFalse(check_selection('.',self.source()))
  proc.kill.assert_called_once()
 def test_cancelled_or_replaced_gesture_cannot_show_toolbar(self):
  from app import App
  fake=Mock();fake.selection_version=2;fake.pending_gesture=dict(id=2)
  App.finish_selection(fake,(1,self.source(),True));fake.prompt.assert_not_called()
 def test_false_result_does_not_show_toolbar(self):
  from app import App
  fake=Mock();fake.selection_version=1;fake.pending_gesture=dict(id=1)
  App.finish_selection(fake,(1,self.source(),False));fake.prompt.assert_not_called()
 def test_confirmed_current_result_shows_toolbar(self):
  from app import App
  fake=Mock();fake.selection_version=1;fake.pending_gesture=dict(id=1)
  with patch('selection_verifier.source_is_active',return_value=True):App.finish_selection(fake,(1,self.source(),True))
  fake.prompt.assert_called_once_with('',self.source())

 def test_focus_change_cancels_pending_verification(self):
  from app import App
  fake=Mock();fake.pending_gesture=dict(id=1);fake.selection_version=2
  App.cancel_pending_verification(fake)
  self.assertEqual(fake.selection_version,3);self.assertIsNone(fake.pending_gesture)

 def test_front_application_changed_after_confirmation(self):
  from app import App
  fake=Mock();fake.selection_version=1;fake.pending_gesture=dict(id=1)
  with patch('selection_verifier.source_is_active',return_value=False):App.finish_selection(fake,(1,self.source(),True))
  fake.prompt.assert_not_called()
