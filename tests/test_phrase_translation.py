import unittest
from unittest.mock import patch
import io,json
from phrase_translation import translate,TranslationUnavailable,accept_result

class Response(io.BytesIO):
    url='http://127.0.0.1:5000/translate'
class PhraseTests(unittest.TestCase):
    def test_translation(self):
        response=Response(json.dumps({'translatedText':'購買行為'}).encode())
        with patch('urllib.request.urlopen',return_value=response) as request:
            self.assertEqual(translate('buying behaviour'),'购买行为')
            body=json.loads(request.call_args.args[0].data)
            self.assertEqual(body['q'],'buying behaviour')
            self.assertEqual(body['target'],'zh')
    def test_unavailable(self):
        with patch('urllib.request.urlopen',side_effect=OSError()):
            with self.assertRaises(TranslationUnavailable):translate('a phrase')
    def test_bad_response(self):
        with patch('urllib.request.urlopen',return_value=Response(b'{"translatedText":null}')):
            with self.assertRaises(TranslationUnavailable):translate('a phrase')
    def test_stale_result(self):
        self.assertFalse(accept_result(2,'new phrase',(1,'old phrase','translation',False)))
        self.assertFalse(accept_result(2,'new phrase',(2,'old phrase','translation',False)))
        self.assertTrue(accept_result(2,'new phrase',(2,'new phrase','translation',False)))
    def test_no_insecure_remote(self):
        with self.assertRaises(TranslationUnavailable):translate('hello','http://example.com')
