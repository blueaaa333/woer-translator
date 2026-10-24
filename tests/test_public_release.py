import importlib.util,json,re,sqlite3,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lexicon import Lexicon,normalize_query,definition_sections,examples_text
from word_forms import form_rows
from pronunciation import phonetic_labels

class PublicReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.lexicon=Lexicon(ROOT)
    @classmethod
    def tearDownClass(cls):
        for name in ('db','extra','community','exam'):
            connection=getattr(cls.lexicon,name)
            if connection:connection.close()
    def test_private_data_excluded(self):
        self.assertEqual(self.lexicon.db.execute('select count(*) from words').fetchone()[0],0)
        self.assertIsNone(self.lexicon.exam)
        self.assertFalse((ROOT/'exam_core.db').exists())
    def test_open_data_integrity(self):
        for db in (self.lexicon.db,self.lexicon.extra,self.lexicon.community):
            self.assertEqual(db.execute('pragma integrity_check').fetchone()[0],'ok')
        self.assertEqual(self.lexicon.extra.execute('select count(*) from senses').fetchone()[0],117659)
        for url, in self.lexicon.community.execute('select distinct url from entries'):
            self.assertRegex(url,r'^https://(zh|simple|en)\.wiktionary\.org/wiki/')
        self.assertFalse(self.lexicon.extra.execute("select 1 from forms where form='i' and lemma='positioning'").fetchone())
    def test_compound_and_primary_chinese(self):
        for text in ('well-researched','well‑researched','well–researched','well-\nresearched'):
            result=self.lexicon.lookup(text)
            self.assertEqual(result['word'],'well-researched')
            self.assertIn('经过充分研究',definition_sections(result)['primary'][0]['text'])
            self.assertIn('城市交通',examples_text(result))
        current=definition_sections(self.lexicon.lookup('current'))
        self.assertTrue(any(re.search('[\u4e00-\u9fff]',s['text']) for s in current['primary']))
        self.assertNotIn('维基词典',current['primary'][0]['text'])
    def test_structured_forms(self):
        rows=form_rows(self.lexicon,self.lexicon.lookup('positioning'))
        self.assertTrue(any(row['form']=='positioning' and 'i' in row['kinds'] for row in rows))
        self.assertFalse(any(row['form']=='i' or row['label']=='变形' for row in rows))
        self.assertTrue(any(re.search('[\u4e00-\u9fff]',row['meaning']) and '暂未' not in row['meaning'] for row in rows))
        self.assertTrue(all(row['usage'] for row in rows if row['kinds']!=['0']))
        went=form_rows(self.lexicon,self.lexicon.lookup('went'))
        self.assertTrue(any(row['form']=='went' and row['kinds']==['p'] for row in went))
        self.assertFalse(any(row['form']=='went' and 's' in row['kinds'] for row in went))
    def test_independent_accent_metadata(self):
        ipa=phonetic_labels(self.lexicon.lookup('better'))
        self.assertTrue(ipa['uk'] and ipa['us'])
        self.assertNotEqual(ipa['uk'],ipa['us'])
        empty=phonetic_labels(dict(word='missing-inflection',entries=[dict(word='missing',phonetic='x')],community=[]))
        self.assertEqual(empty['uk'],'');self.assertEqual(empty['us'],'')
    def test_no_active_private_endpoint_or_generic_ipa_label(self):
        text=(ROOT/'app.py').read_text(encoding='utf-8')
        self.assertNotIn('youdao',text.lower())
        self.assertNotIn('common_ipa',text)
        self.assertNotIn('https://github.com/skywind3000',text)
        self.assertNotIn('m.destroy();self.menu()',text)

if __name__=='__main__':unittest.main()
