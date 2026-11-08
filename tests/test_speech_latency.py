import tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from pronunciation import SpeechEngine
class LatencyTests(unittest.TestCase):
 def test_local_cache_skips_network(self):
  with tempfile.TemporaryDirectory() as d:
   e=SpeechEngine(d,d)
   try:
    with patch.object(e.recordings,'cached',return_value=None),patch.object(e,'cached_synthesis',return_value=Path('hit.wav')),patch.object(e.recordings,'get',side_effect=AssertionError('network')):
     self.assertEqual(e.render('water',1),Path('hit.wav'))
   finally:e.close()
 def test_slow_recording_is_bounded_and_not_queued(self):
  with tempfile.TemporaryDirectory() as d:
   e=SpeechEngine(d,d);release=threading.Event();started=threading.Event()
   def slow(*args):started.set();release.wait(2)
   try:
    with patch('pronunciation.voice_files',return_value=(None,)*5),patch('pronunciation.Recordings.get',side_effect=slow) as get:
     t=time.monotonic();self.assertIsNone(e.quick_recording('water',1));self.assertLess(time.monotonic()-t,.6)
     self.assertTrue(started.is_set());self.assertIsNone(e.quick_recording('hello',2));self.assertEqual(get.call_count,1)
     release.set()
   finally:release.set();e.close()
if __name__=='__main__':unittest.main()
