import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from test_app import app, sample, Presentation, BytesIO, unittest
from statistical import analyze, pearson

def stat(kind,content,names=''):
    s=sample()['slides'][4]
    s.update(chartType=kind,content=content,seriesNames=names)
    return s

class StatisticsTests(unittest.TestCase):
    def test_pareto_aggregation_sort_and_threshold(self):
        a=analyze(stat('pareto','B | 20\nA | 30\nA | 30\nC | 20'))
        self.assertEqual(a['labels'],['A','B','C'])
        self.assertEqual(a['values'],[60,20,20])
        self.assertEqual(a['cumulative'],[.6,.8,1.0])
        self.assertEqual(a['cutoff'],2)
    def test_pearson_known_values(self):
        a=pearson([1,2,3],[2,4,6])
        self.assertAlmostEqual(a['r'],1)
        self.assertEqual(a['slope'],2)
        self.assertEqual(a['intercept'],0)
        self.assertAlmostEqual(pearson([1,2,3],[3,2,1])['r'],-1)
        self.assertAlmostEqual(pearson([-1,0,1],[1,0,1])['r'],0)
        self.assertIsNone(pearson([1,1,1],[1,2,3])['r'])
        self.assertIsNone(pearson([1,2,3],[1,1,1])['r'])
    def test_matrix_symmetry_and_constant(self):
        a=analyze(stat('matrix','1 | 3 | 5\n2 | 2 | 5\n3 | 1 | 5'))
        self.assertAlmostEqual(a['matrix'][0][1],-1)
        self.assertEqual(a['matrix'][0][1],a['matrix'][1][0])
        self.assertIsNone(a['matrix'][2][2])
    def test_invalid_data(self):
        for kind,content in [('pareto','A | -1'),('pareto','A | 0'),('correlation','1 | 1\n2 | 2'),('correlation','1 | 2\n2 | NaN\n3 | 4'),('matrix','1 | 2\n2 | \n3 | 4')]:
            with self.assertRaises(ValueError):analyze(stat(kind,content))
    def test_preview_export_all_statistics(self):
        client=app.test_client()
        for theme in ('ocean','forest','midnight'):
            for kind,content in [('pareto','A | 60\nB | 20\nC | 20'),('correlation','1 | 2\n2 | 4\n3 | 6'),('correlation','1 | 2\n1 | 3\n1 | 4'),('matrix','1 | 3 | 5\n2 | 2 | 5\n3 | 1 | 5')]:
                deck={'theme':theme,'slides':[stat(kind,content)]}
                p=client.post('/api/preview',json=deck)
                self.assertEqual(p.status_code,200,p.data)
                self.assertIn('Pearson' if kind=='correlation' else 'Total' if kind=='pareto' else 'correlation',p.json['slides'][0])
                r=client.post('/api/generate',json=deck)
                self.assertEqual(r.status_code,200,r.data[:300])
                prs=Presentation(BytesIO(r.data));self.assertEqual(len(prs.slides),1)
                self.assertTrue(any(s.has_text_frame for s in prs.slides[0].shapes))
    def test_100_observations(self):
        s=stat('correlation','\n'.join(f'{i} | {i*2}' for i in range(100)))
        self.assertAlmostEqual(analyze(s)['r'],1)
        self.assertEqual(app.test_client().post('/api/generate',json={'theme':'ocean','slides':[s]}).status_code,200)
