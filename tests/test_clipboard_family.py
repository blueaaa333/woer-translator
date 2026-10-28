import unittest
from unittest.mock import patch
from clipboard_family import matches,related_owner
class ClipboardFamilyTests(unittest.TestCase):
 def paths(self):return {1:r'C:\Office\wps.exe',2:r'C:\Office\wpp.exe'}
 def test_wps_direct_child_with_same_installation_is_accepted(self):self.assertTrue(matches(1,2,{2:1},self.paths()))
 def test_parent_owner_with_same_installation_is_accepted(self):self.assertTrue(matches(2,1,{2:1},self.paths()))
 def test_unrelated_process_same_folder_is_rejected(self):self.assertFalse(matches(1,2,{2:9},self.paths()))
 def test_child_from_other_folder_is_rejected(self):self.assertFalse(matches(1,2,{2:1},{1:r'C:\Office\wps.exe',2:r'C:\Other\wpp.exe'}))
 def test_missing_process_identity_is_rejected(self):self.assertFalse(matches(1,2,{2:1},{}));self.assertFalse(related_owner(1,0))
 def test_metadata_read_failure_does_not_accept_foreign_clipboard(self):
  with patch('clipboard_family.metadata',side_effect=OSError):self.assertFalse(related_owner(1,2))
