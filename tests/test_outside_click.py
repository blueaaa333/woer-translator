import unittest
from unittest.mock import Mock,patch
from outside_click import should_hide
class OutsideClickTests(unittest.TestCase):
 def test_new_outside_press_hides(self):self.assertTrue(should_hide(dict(reason='pointer_down',at=101),100))
 def test_old_click_does_not_hide_new_result(self):self.assertFalse(should_hide(dict(reason='pointer_down',at=99),100))
 def test_mouse_release_does_not_hide_just_opened_result(self):self.assertFalse(should_hide(dict(reason='click',at=101),100))
 def test_typing_or_navigation_does_not_hide_result(self):
  for reason in ('typing','navigation','keyboard'):self.assertFalse(should_hide(dict(reason=reason,at=101),100))
 def test_app_hides_root_and_closes_floating_windows(self):
  from app import App
  fake=Mock();fake.pending_gesture=None;fake.pending_source=None;fake.window_shown_at=100
  App.dismiss_from_input(fake,dict(reason='pointer_down',at=101,pid=12))
  fake.root.withdraw.assert_called_once();fake.close_floating.assert_called_once_with('pointer_down')
