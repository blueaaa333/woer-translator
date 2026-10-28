import ctypes,unittest
from ctypes import wintypes
from unittest.mock import Mock
from edge_pdf_copy import request_copy,fresh_copy
class EdgePdfCopyTests(unittest.TestCase):
 def test_all_apps_mode_supports_wps_word_and_other_browsers(self):
  for name in ('wps','wpspdf','winword','chrome','firefox','wechat'):
   user=self.user('Document');source=dict(self.source(),app=name)
   self.assertEqual(request_copy(source,user,all_apps=True),8,name);self.assertEqual(user.keybd_event.call_count,4)
 def test_all_apps_mode_excludes_terminal_password_and_lock_apps(self):
  for name in ('windowsterminal','cmd','powershell','pwsh','keepass','1password','bitwarden','lockapp','woertranslator'):
   user=self.user();self.assertIsNone(request_copy(dict(self.source(),app=name),user,all_apps=True),name);user.keybd_event.assert_not_called()
 def test_all_apps_mode_rejects_native_password_fields(self):
  from edge_pdf_copy import GuiThreadInfo
  user=self.user()
  def info(thread,pointer):ctypes.cast(pointer,ctypes.POINTER(GuiThreadInfo)).contents.hwndFocus=7;return 1
  def name(window,buffer,length):buffer.value='Edit'
  user.GetGUIThreadInfo.side_effect=info;user.GetClassNameW.side_effect=name;user.GetWindowLongW.return_value=0x20
  self.assertIsNone(request_copy(dict(self.source(),app='wps'),user,all_apps=True));user.keybd_event.assert_not_called()
 def test_clipboard_owner_in_source_child_window_is_accepted(self):
  self.assertTrue(fresh_copy(self.source(),8,9,5,2))
  self.assertFalse(fresh_copy(self.source(),8,9,5,7))
 def source(self):return dict(app='msedge',pid=1,hwnd=2)
 def user(self,title='lesson.pdf - Microsoft Edge'):
  user=Mock();user.GetForegroundWindow.return_value=2;user.GetClipboardSequenceNumber.return_value=8;user.GetAsyncKeyState.return_value=0
  def pid(window,pointer):ctypes.cast(pointer,ctypes.POINTER(wintypes.DWORD))[0]=1
  def text(window,buffer,length):buffer.value=title
  user.GetWindowThreadProcessId.side_effect=pid;user.GetWindowTextW.side_effect=text
  return user
 def test_only_active_edge_pdf_can_request_copy(self):
  user=self.user();self.assertEqual(request_copy(self.source(),user),8);self.assertEqual(user.keybd_event.call_count,4)
 def test_normal_webpage_and_other_apps_are_not_probed(self):
  user=self.user('Home - Microsoft Edge');self.assertIsNone(request_copy(self.source(),user));user.keybd_event.assert_not_called()
  user=self.user();source=self.source();source['app']='notepad';self.assertIsNone(request_copy(source,user));user.keybd_event.assert_not_called()
 def test_no_copy_after_foreground_or_modifier_changes(self):
  user=self.user();user.GetForegroundWindow.return_value=9;self.assertIsNone(request_copy(self.source(),user));user.keybd_event.assert_not_called()
  user=self.user();user.GetAsyncKeyState.return_value=0x8000;self.assertIsNone(request_copy(self.source(),user));user.keybd_event.assert_not_called()
 def test_unchanged_clipboard_does_not_confirm_selection(self):self.assertFalse(fresh_copy(self.source(),8,8,1))
 def test_other_owner_does_not_confirm_selection(self):self.assertFalse(fresh_copy(self.source(),8,9,4))
 def test_fresh_source_owned_copy_is_required(self):self.assertTrue(fresh_copy(self.source(),8,9,1))
 def test_releases_keys_even_if_copy_injection_fails(self):
  user=self.user();user.keybd_event.side_effect=[None,OSError('failure'),None,None]
  with self.assertRaises(OSError):request_copy(self.source(),user)
  self.assertEqual(user.keybd_event.call_args_list[-1].args,(17,0,2,0))
