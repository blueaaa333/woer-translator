import unittest
from mac_selection import verify
class API:
 kAXValueCFRangeType=4;kAXValueCGRectType=3
 def __init__(self):self.length=5;self.role='AXTextArea';self.pid=12
 def AXUIElementCreateSystemWide(self):return 'system'
 def AXUIElementSetMessagingTimeout(self,*args):pass
 def AXUIElementCreateApplication(self,pid):return 'app'
 def AXUIElementGetPid(self,e,out):return 0,self.pid
 def AXUIElementCopyElementAtPosition(self,*args):return 0,'text'
 def AXUIElementCopyAttributeValue(self,e,name,out):
  return 0,{'AXFocusedApplication':'app','AXFocusedUIElement':'text','AXRole':self.role,'AXSelectedTextRange':'range','AXSelectedText':'water','AXParent':None}.get(name)
 def AXValueGetValue(self,value,kind,out):return (True,(0,self.length)) if value=='range' else (True,((100,100),(50,20)))
 def AXUIElementCopyParameterizedAttributeValue(self,*args):return 0,'bounds'
class MacSelectionTests(unittest.TestCase):
 def test_nonempty_range_near_release(self):self.assertTrue(verify(API(),12,130,110))
 def test_collapsed_range(self):
  api=API();api.length=0;self.assertFalse(verify(api,12,130,110))
 def test_stale_unrelated_bounds(self):self.assertFalse(verify(API(),12,400,400))
 def test_scroll_and_image_are_rejected(self):
  for role in ('AXScrollBar','AXImage','AXButton','AXSecureTextField'):
   api=API();api.role=role;self.assertFalse(verify(api,12,130,110))
 def test_changed_front_application(self):self.assertFalse(verify(API(),99,130,110))
 def test_copy_requires_matching_current_text(self):
  self.assertTrue(verify(API(),12,400,400,'water'));self.assertFalse(verify(API(),12,400,400,'table'))
