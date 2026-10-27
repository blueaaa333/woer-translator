import tempfile,unittest,urllib.error,json
from pathlib import Path
from unittest.mock import patch
from scripts.native_notices import collect
class NativeNoticeTests(unittest.TestCase):
 def source(self,url):
  if url.endswith('PCbuild/python.props'):return b'libffi-3.4.4 bzip2-1.0.8 xz-5.2.5'
  if url.endswith('Doc/license.rst'):return b'OpenSSL and incorporated software notices'
  if url.endswith('Mac/BuildScript/build-installer.py'):return b'http://tukaani.org/xz/xz-5.2.3.tar.gz'
  if 'madler/zlib/' in url:
   if url.endswith('/LICENSE'):raise urllib.error.HTTPError(url,404,'not found',{},None)
   return b'/* origin of this software must not be misrepresented */ extra code'
  if 'openssl/openssl' in url:return b'Apache License Version 2.0'
  if 'expat' in url or 'libffi' in url:return b'Permission is hereby granted'
  if 'mpdecimal.c' in url:return b'/* Copyright Stefan Krah. Complete BSD licence here. */ source code'
  if 'bzip2-' in url:return b'Copyright Julian R Seward'
  if 'xz-' in url or 'tukaani' in url:return b'liblzma is in the public domain'
  raise AssertionError(url)
 def test_exact_refs_and_legacy_zlib_header_are_preserved(self):
  with tempfile.TemporaryDirectory() as folder,patch('scripts.native_notices.read',side_effect=self.source):
   data=collect(folder,python_version='3.12.10',openssl_version='3.0.16',zlib_version='1.2.12',target='darwin')
   self.assertEqual(data['xz_source_reference'],'5.2.3')
   self.assertEqual(len(data['notices']),8)
   self.assertNotIn('extra code',(Path(folder)/'zlib-LICENSE.txt').read_text())
   self.assertNotIn('source code',(Path(folder)/'libmpdec-NOTICE.txt').read_text())
 def test_unknown_openssl_major_requires_review(self):
  with tempfile.TemporaryDirectory() as folder:
   with self.assertRaisesRegex(RuntimeError,'Review OpenSSL'):collect(folder,openssl_version='4.0.0')
 def test_wrong_notice_content_stops_collection(self):
  with tempfile.TemporaryDirectory() as folder,patch('scripts.native_notices.read',return_value=b'not a license'):
   with self.assertRaises(RuntimeError):collect(folder,python_version='3.12.10',openssl_version='3.0.16')
