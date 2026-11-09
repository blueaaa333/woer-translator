import hashlib,json,shutil,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from lexicon import Lexicon,clean_definition,definition_sections,definition_text,normalize_pos,simplified
from scripts.build_ecdict import SOURCE_SHA256,SOURCE_BYTES,build_database
from scripts.prepare_data import ecdict_bundle,install_ecdict,prepare

class ECDICTTests(unittest.TestCase):
    def test_source_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='woer-ecdict-bad-source-') as folder:
            source=Path(folder)/'wrong.csv';source.write_bytes(b'x');output=Path(folder)/'words.db'
            with patch('scripts.build_ecdict.SOURCE_BYTES',1),patch('scripts.build_ecdict.SOURCE_SHA256','0'*64):
                with self.assertRaisesRegex(ValueError,'ECDICT source SHA-256 mismatch'):
                    build_database(source,output)
            self.assertFalse(output.exists())

    def test_unknown_existing_database_is_not_overwritten(self):
        info,_,archive=ecdict_bundle(ROOT)
        item=next(x for x in json.loads((ROOT/'data'/'checksums.json').read_text(encoding='utf-8')) if x['target']=='words.db')
        marker=b'user-owned fixture bytes; no private database is read'
        with tempfile.TemporaryDirectory(prefix='woer-ecdict-unknown-db-') as folder:
            root=Path(folder);(root/'data').mkdir();shutil.copy2(ROOT/'data'/item['archive'],root/'data'/item['archive'])
            target=root/item['target'];target.write_bytes(marker)
            with self.assertRaisesRegex(FileExistsError,'Refusing to overwrite a different local dictionary'):
                install_ecdict(root,item,info,archive)
            self.assertEqual(target.read_bytes(),marker)

    def test_clean_public_only_prepare_and_tk_text_show_complete_meanings(self):
        item_files=('checksums.json','words.db.gz','extended.db.gz','community.db.gz')
        with tempfile.TemporaryDirectory(prefix='woer-public-only-') as folder:
            root=Path(folder);(root/'data').mkdir()
            for name in item_files:shutil.copy2(ROOT/'data'/name,root/'data'/name)
            prepare(root,bundle_dir=ROOT/'build'/'ecdict')
            info=json.loads((ROOT/'build'/'ecdict'/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(hashlib.sha256((root/'words.db').read_bytes()).hexdigest(),info['database_sha256'])
            self.assertFalse((root/'exam_core.db').exists())
            lexicon=Lexicon(root)
            try:
                for word in ('optimum','current','bank'):
                    result=lexicon.lookup(word)
                    entry=next(e for e in result['entries'] if e['word']==word and e['translation'])
                    expected=simplified(clean_definition(normalize_pos(entry['translation'])))
                    primary='\n'.join(s['text'] for s in definition_sections(result)['primary'])
                    tk_text=definition_text(result)
                    self.assertIn(expected,primary)
                    self.assertIn(expected,tk_text)
                optimum=lexicon.lookup('optimum')
                value=next(e['translation'] for e in optimum['entries'] if e['word']=='optimum')
                displayed=simplified(clean_definition(normalize_pos(value)))
                self.assertRegex(displayed,r'(?m)^adj\.')
                self.assertEqual(lexicon.exam,None)
            finally:
                for name in ('db','extra','community','exam'):
                    connection=getattr(lexicon,name)
                    if connection:connection.close()

if __name__=='__main__':unittest.main()
