import tempfile,unittest,time
from unittest.mock import Mock,patch
from online_dictionary import Definitions,OnlineDictionary,fetch,attribution,DictionaryUnavailable,page_source
class OnlineDictionaryTests(unittest.TestCase):
 def test_chinese_definitions_skip_examples_and_etymology(self):
  p=Definitions();p.feed('<h2>英語</h2><h3>語源</h3><ol><li>not a definition</li></ol><h3>名詞</h3><ol><li>電流<dl><dd>example</dd></dl></li><li>水流</li></ol>')
  self.assertEqual([x['text'] for x in p.items],['电流','水流'])
 def test_chinese_revision_and_license(self):
  page=dict(parse=dict(title='ceteris paribus',revid=123,text='<h2>英語</h2><h3>詞組</h3><ol><li>其它條件相同。</li></ol>'))
  with patch('online_dictionary.request',return_value=page):data=fetch('ceteris paribus')
  self.assertEqual(data['entries'][0]['text'],'其它条件相同。');self.assertIn('oldid=123',data['sources'][0]['revision_url'])
 def test_latin_fallback_is_labelled_english(self):
  replies=[dict(error=dict(code='missingtitle')),dict(la=[dict(language='Latin',partOfSpeech='Adjective',definitions=[dict(definition='plural of <i>ceterus</i>')])])]
  with patch('online_dictionary.request',side_effect=replies):data=fetch('ceteris')
  self.assertTrue(data['entries'][0]['english']);self.assertEqual(data['entries'][0]['language'],'Latin')
 def test_network_failure_is_not_missing_word(self):
  with patch('online_dictionary.request',side_effect=DictionaryUnavailable('network')):
   with self.assertRaises(DictionaryUnavailable):fetch('water')
 def test_cache_avoids_second_request(self):
  with tempfile.TemporaryDirectory() as folder:
   data=dict(word='water',entries=[dict(text='水')],sources=[],fetched=time.time())
   with patch('online_dictionary.fetch',return_value=data) as remote:
    c=OnlineDictionary(folder);self.assertEqual(c.get('water'),c.get('water'));remote.assert_called_once()
 def test_attribution(self):
  with tempfile.TemporaryDirectory() as folder:
   text=attribution(dict(sources=[page_source('zh','water',123)]),folder).read_text(encoding='utf-8')
   for term in ('action=history','oldid=123','by-sa/4.0'):self.assertIn(term,text)
 def test_stale_result_does_not_replace_new_query(self):
  from app import App
  fake=Mock();fake.selection_version=2;fake.word='new';fake.preferences={}
  App.finish_dictionary(fake,(1,'old',dict(entries=[dict(text='wrong')]),''));fake.render.assert_not_called()
