import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_app import sample, app, Presentation, BytesIO, unittest
import base64
from PIL import Image
import charts

class MediaTests(unittest.TestCase):
    def setUp(self):self.client=app.test_client()
    def test_every_chart_native_and_preview(self):
        for kind in charts.KINDS:
            with self.subTest(kind=kind):
                s=sample()['slides'][4];s['chartType']=kind
                s['content']='1 | 10 | 20\n2 | -5 | 30\n3 | 25 | 15'
                if kind in ('pie','donut'):s['content']='A | 10\nB | 25\nC | 0'
                deck={'theme':'midnight','slides':[s]}
                r=self.client.post('/api/preview',json=deck);self.assertEqual(r.status_code,200,r.data)
                r=self.client.post('/api/generate',json=deck);self.assertEqual(r.status_code,200,r.data[:500])
                prs=Presentation(BytesIO(r.data));chart=next(x.chart for x in prs.slides[0].shapes if x.has_chart)
                self.assertEqual(len(chart.series),1 if kind in ('pie','donut') else 2)
                if kind=='combo':self.assertEqual(len(chart.plots),2)
                self.assertTrue(chart.part.chart_workbook.xlsx_part.blob)
    def test_image_embedded_and_invalid(self):
        b=BytesIO();Image.new('RGB',(120,80),'navy').save(b,format='PNG')
        s=sample()['slides'][0];s['image']='data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
        s['imagePosition']='left';s['imageSize']='large'
        deck={'theme':'ocean','slides':[s]}
        r=self.client.post('/api/generate',json=deck);self.assertEqual(r.status_code,200)
        p=Presentation(BytesIO(r.data));pictures=[x for x in p.slides[0].shapes if x.shape_type==13]
        self.assertEqual(len(pictures),1);self.assertAlmostEqual(pictures[0].width/pictures[0].height,1.5,places=4)
        s['image']='data:image/svg+xml;base64,AAAA'
        self.assertEqual(self.client.post('/api/generate',json=deck).status_code,400)
    def test_chart_validation(self):
        for kind,content in [('pie','A | -1'),('donut','A | 0'),('scatter','hello | 1'),('combo','A | 1'),('line','A | 1 | 2\nB | 3'),('line','A | Infinity')]:
            s=sample()['slides'][4];s.update(chartType=kind,content=content)
            self.assertEqual(self.client.post('/api/generate',json={'theme':'ocean','slides':[s]}).status_code,400)
