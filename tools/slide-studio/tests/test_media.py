import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_app import sample, app, Presentation, BytesIO, unittest
import base64
import zipfile
from PIL import Image
import charts
import engine

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
    def test_company_logo_and_native_transition(self):
        image=BytesIO();Image.new('RGBA',(180,60),(0,120,140,255)).save(image,format='PNG')
        logo='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
        slide=sample()['slides'][1];slide['transition']='wipe'
        deck={'theme':'ocean','slides':[slide],'logo':logo,'logoPosition':'top-right','logoSize':'medium',
              'hideLogoOnTitle':False,'transition':{'type':'fade','speed':'fast'}}
        preview=self.client.post('/api/preview',json=deck)
        self.assertEqual(preview.status_code,200,preview.data)
        self.assertIn('<image',preview.json['slides'][0])
        generated=self.client.post('/api/generate',json=deck)
        self.assertEqual(generated.status_code,200,generated.data[:400])
        presentation=Presentation(BytesIO(generated.data))
        self.assertTrue(any(shape.shape_type==13 for shape in presentation.slides[0].shapes))
        with zipfile.ZipFile(BytesIO(generated.data)) as archive:
            xml=archive.read('ppt/slides/slide1.xml').decode()
        self.assertIn('<p:transition spd="fast" advClick="1"><p:wipe dir="r"/></p:transition>',xml)
    def test_title_page_images_are_stable_embedded_and_limited(self):
        uris=[]
        for color in ('navy','orange'):
            image=BytesIO();Image.new('RGB',(180,120),color).save(image,format='PNG')
            uris.append('data:image/png;base64,'+base64.b64encode(image.getvalue()).decode())
        slide=sample()['slides'][0]
        deck={'name':'Title image test','theme':'ocean','slides':[slide],'titleImages':uris}
        first=engine.scene(slide,engine.THEMES['ocean'],1,deck)
        second=engine.scene(slide,engine.THEMES['ocean'],1,deck)
        first_image=next(item for item in first if item.get('role')=='title-image')
        second_image=next(item for item in second if item.get('role')=='title-image')
        self.assertEqual(first_image['raw'],second_image['raw'])
        self.assertEqual((first_image['x'],first_image['y'],first_image['w'],first_image['h']),(760,0,440,675))
        preview=self.client.post('/api/preview',json=deck)
        self.assertEqual(preview.status_code,200,preview.data)
        self.assertIn('<image',preview.json['slides'][0])
        generated=self.client.post('/api/generate',json=deck)
        self.assertEqual(generated.status_code,200,generated.data[:400])
        presentation=Presentation(BytesIO(generated.data))
        pictures=[shape for shape in presentation.slides[0].shapes if shape.shape_type==13]
        self.assertEqual(len(pictures),1)
        deck['titleImages']=uris*3
        self.assertEqual(self.client.post('/api/generate',json=deck).status_code,400)
    def test_title_page_images_rotate_before_repeating(self):
        uris=[]
        for color in ('red','green','blue','orange','purple'):
            image=BytesIO();Image.new('RGB',(90,60),color).save(image,format='PNG')
            uris.append('data:image/png;base64,'+base64.b64encode(image.getvalue()).decode())
        title=sample()['slides'][0]
        slides=[{**title,'title':f'Title {index}'} for index in range(6)]
        deck={'name':'Rotation test','theme':'ocean','slides':slides,'titleImages':uris}
        raws=[]
        for number,slide in enumerate(slides,1):
            objects=engine.scene(slide,engine.THEMES['ocean'],number,deck)
            raws.append(next(item['raw'] for item in objects if item.get('role')=='title-image'))
        self.assertEqual(len(set(raws[:5])),5)
        self.assertEqual(raws[0],raws[5])
        preview_raws=[]
        for ordinal,slide in enumerate(slides[:5]):
            preview_deck={**deck,'slides':[slide],'previewTitleOrdinal':ordinal,'previewSlideNumber':ordinal+1}
            objects=engine.scene(slide,engine.THEMES['ocean'],ordinal+1,preview_deck)
            preview_raws.append(next(item['raw'] for item in objects if item.get('role')=='title-image'))
        self.assertEqual(len(set(preview_raws)),5)
    def test_cover_footer_has_logo_and_prepared_time(self):
        image=BytesIO();Image.new('RGBA',(160,50),(0,120,140,255)).save(image,format='PNG')
        logo='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
        slide=sample()['slides'][0]
        deck={'theme':'ocean','slides':[slide],'logo':logo,'hideLogoOnTitle':True,
              'preparedAt':'Sep 27, 2026, 4:15 PM'}
        objects=engine.scene(slide,engine.THEMES['ocean'],1,deck)
        self.assertEqual(len([item for item in objects if item.get('role')=='cover-logo']),1)
        footer=' '.join(' '.join(item.get('lines',[])) for item in objects if item.get('kind')=='text')
        self.assertIn('Deck prepared · Sep 27, 2026, 4:15 PM',footer)
        generated=self.client.post('/api/generate',json=deck)
        self.assertEqual(generated.status_code,200,generated.data[:400])
        presentation=Presentation(BytesIO(generated.data))
        self.assertTrue(any('Deck prepared' in shape.text for shape in presentation.slides[0].shapes if shape.has_text_frame))
    def test_visual_image_layouts_and_content_footer(self):
        image=BytesIO();Image.new('RGB',(320,180),'teal').save(image,format='PNG')
        uri='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
        catalog=sample()['slides']
        for slide_type in ('image-focus','image-caption'):
            with self.subTest(slide_type=slide_type):
                slide=next(item for item in catalog if item['type']==slide_type);slide['image']=uri
                deck={'name':'RAG Deep Dive','theme':'ocean','slides':[slide]}
                generated=self.client.post('/api/generate',json=deck)
                self.assertEqual(generated.status_code,200,generated.data[:300])
                presentation=Presentation(BytesIO(generated.data))
                self.assertEqual(len([shape for shape in presentation.slides[0].shapes if shape.shape_type==13]),1)
        content=next(item for item in catalog if item['type']=='summary')
        deck={'name':'RAG Deep Dive','theme':'ocean','slides':[catalog[0],content]}
        objects=engine.scene(content,engine.THEMES['ocean'],2,deck)
        footer=' '.join(' '.join(item.get('lines',[])) for item in objects if item.get('kind')=='text')
        self.assertIn('RAG Deep Dive',footer);self.assertIn('02 / 02',footer)
