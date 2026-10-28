import unittest
from unittest.mock import Mock
from passive_popup import choose_position,intersects,show_without_activation
class PassivePopupTests(unittest.TestCase):
 def test_does_not_cover_native_selection_toolbar(self):
  own=(100,100,400,150);native=(100,100,420,165);x,y=choose_position(own,[native],(0,0,1200,900))
  self.assertFalse(intersects((x,y,x+300,y+50),native));self.assertGreaterEqual(y,4)
 def test_stays_in_work_area_when_native_toolbar_is_near_bottom(self):
  x,y=choose_position((100,840,400,890),[(100,820,420,890)],(0,0,1200,900))
  self.assertGreaterEqual(y,4);self.assertLessEqual(y+50,896);self.assertFalse(intersects((x,y,x+300,y+50),(100,820,420,890)))
 def test_no_collision_keeps_original_anchor(self):self.assertEqual(choose_position((10,100,310,150),[],(0,0,1200,900)),(10,100))
 def test_disable_before_mapping_and_reenable_after_mapping(self):
  calls=[];window=Mock();window.winfo_id.return_value=2;window.attributes.side_effect=lambda *args:calls.append(args);window.deiconify.side_effect=lambda:calls.append(('map',))
  user=Mock();user.GetParent.return_value=3;user.GetForegroundWindow.return_value=1;user.GetWindowLongW.return_value=0
  self.assertEqual(show_without_activation(window,user),(1,1));self.assertEqual(calls,[('-disabled',True),('map',),('-disabled',False)])
