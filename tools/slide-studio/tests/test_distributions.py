import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from test_app import app, sample, Presentation, BytesIO, unittest
from distributions import analyze, summary

def slide(kind,content,**kwargs):
    s=sample()['slides'][4];s.update(chartType=kind,content=content,**kwargs);return s

class DistributionTests(unittest.TestCase):
    def test_summary_known_values(self):
        a=summary([1,2,3,4,5])
        self.assertEqual((a['mean'],a['median'],a['q1'],a['q3']),(3,3,2,4))
        self.assertAlmostEqual(a['sd'],2.5**.5)
        self.assertAlmostEqual(a['p90'],4.6)
        self.assertAlmostEqual(a['p95'],4.8)
        self.assertIsNone(summary([7])['sd'])
    def test_bins_cover_boundaries(self):
        a=analyze(slide('histogram','0\n1\n2\n3\n4',histogramBins=2))
        self.assertEqual(a['edges'],[0,2,4]);self.assertEqual(a['counts'],[2,3])
        a=analyze(slide('histogram','-4\n-3\n-2\n-1\n0',histogramBins=2))
        self.assertEqual(a['counts'],[2,3])
        a=analyze(slide('histogram','7\n7\n7'))
        self.assertEqual(a['counts'],[3]);self.assertLess(a['edges'][0],7);self.assertGreater(a['edges'][-1],7)
    def test_outliers_and_group_sizes(self):
        a=analyze(slide('boxplot','A | 1\nA | 2\nA | 3\nA | 4\nA | 100\nB | 5'))
        self.assertEqual(a['groups'][0]['outliers'],[100]);self.assertEqual(a['groups'][0]['high'],4)
        self.assertEqual(a['groups'][1]['n'],1)
    def test_invalid(self):
        for kind,content,kwargs in [('histogram','1\n2',{'histogramBins':True}),('histogram','1',{'histogramBins':13}),('descriptive','nan',{}),('descriptive','A | 3',{}),('boxplot','A | ',{}),('boxplot','A | 1\nB | 2\nC | 3\nD | 4\nE | 5',{})]:
            with self.assertRaises(ValueError):analyze(slide(kind,content,**kwargs))
    def test_all_exports(self):
        client=app.test_client()
        for theme in ('ocean','forest','midnight'):
            for kind,content in [('descriptive','1\n2\n3\n4\n100'),('histogram','1\n2\n3\n4\n100'),('boxplot','A | 1\nA | 2\nA | 3\nB | 4'),('descriptive','5'),('histogram','5'),('boxplot','A | 5')]:
                deck={'theme':theme,'slides':[slide(kind,content)]}
                response=client.post('/api/preview',json=deck);self.assertEqual(response.status_code,200,response.data)
                r=client.post('/api/generate',json=deck);self.assertEqual(r.status_code,200,r.data[:100])
                p=Presentation(BytesIO(r.data));self.assertEqual(len(p.slides),1)
                self.assertGreater(len(p.slides[0].shapes),10)
