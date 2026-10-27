import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from scripts.distribution_audit import audit,REQUIRED,NATIVE
class DistributionTests(unittest.TestCase):
 def fixture(self,root):
  license=root/'licenses';runtime=license/'runtime';runtime.mkdir(parents=True)
  for name in REQUIRED:(license/name).write_text('notice',encoding='utf-8')
  for name in NATIVE:(runtime/name).write_text('notice',encoding='utf-8')
  evidence=dict(notices=[dict(file=NATIVE[0],sha256=hashlib.sha256(b'notice').hexdigest())])
  (runtime/'native-components.json').write_text(json.dumps(evidence))
  con=sqlite3.connect(root/'words.db');con.execute('create table words(word text)');con.commit();con.close()
 def test_complete_distribution(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);self.fixture(root);self.assertEqual(audit(root)['native_notice_hashes'],'matched')
 def test_missing_openssl_notice_blocks_build(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);self.fixture(root);(root/'licenses/runtime/OpenSSL-LICENSE.txt').unlink()
   with self.assertRaisesRegex(RuntimeError,'Missing distribution notices'):audit(root)
 def test_model_weights_block_build(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);self.fixture(root);(root/'voice.onnx').write_bytes(b'weights')
   with self.assertRaisesRegex(RuntimeError,'Unreviewed/private'):audit(root)
 def test_private_dictionary_blocks_build(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);self.fixture(root);con=sqlite3.connect(root/'words.db');con.execute("insert into words values ('private')");con.commit();con.close()
   with self.assertRaisesRegex(RuntimeError,'Private dictionary'):audit(root)
 def test_changed_notices_block_build(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);self.fixture(root);(root/'licenses/runtime/Python-LICENSE.txt').write_text('changed')
   with self.assertRaisesRegex(RuntimeError,'Notice changed'):audit(root)
