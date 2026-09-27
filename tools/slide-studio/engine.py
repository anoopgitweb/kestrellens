"""Config-driven layouts shared by SVG preview and editable PowerPoint export."""
import json
import math
import textwrap
import base64
import hashlib
from urllib.parse import urlparse
import charts
import images
import statistical
from pathlib import Path
from html import escape
from io import BytesIO
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.xmlchemy import OxmlElement

ROOT = Path(__file__).parent
CATALOG = json.loads((ROOT / 'config/templates.json').read_text(encoding='utf-8'))
THEMES = json.loads((ROOT / 'config/themes.json').read_text(encoding='utf-8'))
TEMPLATES = {t['id']: t for t in CATALOG}
TRANSITIONS = {'none', 'fade', 'push', 'wipe', 'cut'}
TRANSITION_SPEEDS = {'slow', 'medium', 'fast'}

def validate(deck):
    if not isinstance(deck, dict) or deck.get('theme') not in THEMES:
        raise ValueError('Choose a valid theme.')
    slides = deck.get('slides')
    logo = deck.get('logo')
    if logo:
        images.decode(logo)
    if deck.get('logoPosition', 'top-right') not in ('top-left', 'top-right', 'bottom-left', 'bottom-right'):
        raise ValueError('Choose a valid logo position.')
    if deck.get('logoSize', 'medium') not in ('small', 'medium', 'large'):
        raise ValueError('Choose a valid logo size.')
    if not isinstance(deck.get('hideLogoOnTitle', True), bool):
        raise ValueError('Choose whether the logo appears on title slides.')
    if not isinstance(deck.get('pptImageZoom', True), bool):
        raise ValueError('Choose whether PowerPoint images open detail slides.')
    if not isinstance(deck.get('preparedAt', ''), str) or len(deck.get('preparedAt', '')) > 80:
        raise ValueError('Deck prepared date and time must be short text.')
    if 'previewTitleOrdinal' in deck and (not isinstance(deck['previewTitleOrdinal'], int) or deck['previewTitleOrdinal'] < 0):
        raise ValueError('Choose a valid title page preview position.')
    if 'previewSlideNumber' in deck and (not isinstance(deck['previewSlideNumber'], int) or deck['previewSlideNumber'] < 1):
        raise ValueError('Choose a valid slide preview position.')
    if 'previewTotalSlides' in deck and (not isinstance(deck['previewTotalSlides'], int) or deck['previewTotalSlides'] < 1):
        raise ValueError('Choose a valid total slide count.')
    title_images = deck.get('titleImages', [])
    if not isinstance(title_images, list) or len(title_images) > 5:
        raise ValueError('Choose up to 5 title page images.')
    for title_image in title_images:
        images.decode(title_image)
    transition = deck.get('transition') or {}
    if transition.get('type', 'none') not in TRANSITIONS or transition.get('speed', 'medium') not in TRANSITION_SPEEDS:
        raise ValueError('Choose a valid slide transition and speed.')
    if not isinstance(slides, list) or not 1 <= len(slides) <= 60:
        raise ValueError('A presentation must have 1–60 slides.')
    for i, s in enumerate(slides):
        prefix = f'Slide {i + 1}: '
        if not isinstance(s, dict) or s.get('type') not in TEMPLATES:
            raise ValueError(prefix + 'unknown template.')
        for key, limit in [('title', 100), ('subtitle', 160), ('content', 20000 if s.get('chartType') in statistical.KINDS else 2400)]:
            value = s.get(key)
            if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
                raise ValueError(prefix + f'{key} must be text, at most {limit} characters.')
        if 'eyebrow' in s and (not isinstance(s['eyebrow'], str) or len(s['eyebrow']) > 60):
            raise ValueError(prefix + 'title label must be text, at most 60 characters.')
        if not s['title'].strip():
            raise ValueError(prefix + 'add a title.')
        t = TEMPLATES[s['type']]
        if s.get('transition', 'inherit') not in TRANSITIONS | {'inherit'}:
            raise ValueError(prefix + 'choose a valid transition override.')
        layout = t['layout']
        source_url = s.get('sourceUrl', '')
        local_video = s.get('localVideoReference', '')
        if not isinstance(source_url, str) or len(source_url) > 2000:
            raise ValueError(prefix + 'video URL is too long.')
        if source_url and urlparse(source_url).scheme not in ('http', 'https'):
            raise ValueError(prefix + 'video URL must start with http:// or https://.')
        if not isinstance(local_video, str) or len(local_video) > 260:
            raise ValueError(prefix + 'local video reference is too long.')
        rows = parse(s)
        if layout == 'notebook':
            if len(s['content']) > 2400:
                raise ValueError(prefix + 'page details must be at most 2400 characters.')
        elif layout in ('image-focus','image-caption','quote'):
            if len(s['content']) > 600:
                raise ValueError(prefix + 'content must be at most 600 characters.')
        elif layout == 'chart':
            charts.data(s)
        elif t['fields']:
            maximum = 1 if layout=='big-number' else 8 if layout in ('chart', 'table', 'summary') else 6
            if not 1 <= len(rows) <= maximum:
                raise ValueError(prefix + f'enter 1–{maximum} rows.')
            for row in rows:
                if len(row) != len(t['fields']) or any(not cell for cell in row):
                    raise ValueError(prefix + 'each row needs: ' + ' | '.join(t['fields']))
                if any(len(cell) > (180 if t['layout'] == 'summary' else 100) for cell in row):
                    raise ValueError(prefix + 'shorten each cell to fit the slide.')
            if t['layout'] == 'chart':
                try:
                    values = [float(r[1]) for r in rows]
                    if any(not math.isfinite(v) or abs(v) > 1e12 for v in values):
                        raise ValueError()
                except ValueError:
                    raise ValueError(prefix + 'chart values must be finite numbers between -1e12 and 1e12.')
        elif len(s['content']) > 250:
            raise ValueError(prefix + 'closing text must be at most 250 characters.')
        scene(s, THEMES[deck['theme']], i + 1, deck)  # Fail before export on text overflow.
    return deck

def parse(s):
    return [[cell.strip() for cell in line.split('|')] for line in s['content'].splitlines() if line.strip()]

def scene(s, theme, number, deck=None):
    objects = []
    def box(x, y, w, h, color):
        objects.append(dict(kind='rect', x=x, y=y, w=w, h=h, color=theme.get(color, color)))
    def line(x, y, w, color, width=1):
        objects.append(dict(kind='line', x=x, y=y, w=w, h=0, color=theme.get(color, color), width=width, role='background-motif'))
    def text(value, x, y, w, h, size=22, color='text', bold=False):
        # Explicit wrapping and fixed line heights are shared by both renderers.
        for candidate in range(size, 12, -1):
            lines = []
            for paragraph in str(value).splitlines() or ['']:
                lines.extend(textwrap.wrap(paragraph, max(1, int(w / (candidate * .57))), break_long_words=True) or [''])
            if len(lines) * candidate * 1.28 <= h:
                break
        else:
            raise ValueError('Text exceeds the slide layout. Shorten the content or split it across slides.')
        objects.append(dict(kind='text', x=x, y=y, w=w, h=h, lines=lines, size=candidate, color=theme[color], bold=bold))
    def link(value, address, x, y, w, h):
        objects.append(dict(kind='link', x=x, y=y, w=w, h=h, lines=[value], size=15,
                            color=theme['accent'], bold=False, address=address))
    box(0, 0, 1200, 675, 'background')
    def pale(accent, background, amount=.88):
        a=tuple(int(accent[i:i+2],16) for i in (0,2,4));b=tuple(int(background[i:i+2],16) for i in (0,2,4))
        return ''.join(f'{round(a[i]*(1-amount)+b[i]*amount):02X}' for i in range(3))
    motif=pale(theme['accent'],theme['background'])
    line(1030,112,170,motif);line(1065,129,135,motif);line(1100,146,100,motif)
    if s.get('type')!='title':
        line(0,562,145,motif);line(0,579,110,motif);line(0,596,75,motif)
    t = TEMPLATES[s['type']]
    layout = t['layout']
    if layout == 'hero':
        # Reference-inspired cover: generous title scale, quiet metadata, no card chrome.
        title_images=(deck or {}).get('titleImages') or []
        title_image=None
        if title_images:
            # Shuffle the collection once, then rotate through it so every image
            # appears before one repeats. The ordering remains stable in preview/export.
            name=(deck or {}).get('name','')
            order=sorted(range(len(title_images)),key=lambda index:hashlib.sha256(
                f'{name}|title-image|{index}'.encode('utf-8')).digest())
            slides=(deck or {}).get('slides') or []
            title_ordinal=(deck or {}).get('previewTitleOrdinal')
            if title_ordinal is None:
                title_ordinal=sum(1 for candidate in slides[:number] if candidate.get('type')=='title')-1
            if title_ordinal < 0:title_ordinal=max(0,number-1)
            title_image=title_images[order[title_ordinal%len(order)]]
            objects.append(dict(kind='image',x=760,y=0,w=440,h=675,
                                raw=images.cover(title_image,440,675),role='title-image'))
        if theme['background'] != 'FFFFFF' and not title_image:
            box(970, 0, 230, 675, 'panel')
        text_width=620 if title_image else 1030
        eyebrow=s.get('eyebrow')
        if eyebrow is None:
            eyebrow='NOTEBOOK PRESENTATION' if s.get('subtitle')=='Notebook presentation' else 'CHAPTER' if s.get('content')=='Chapter' else 'PRESENTATION'
        if eyebrow:text(eyebrow, 78, 72, min(650,text_width), 36, 16, 'accent', True)
        text(s['title'], 78, 166, text_width, 150, 52, bold=True)
        text(s['subtitle'], 80, 350, text_width-40 if title_image else 990, 70, 26, 'muted')
        text(s['content'], 80, 492, text_width-40 if title_image else 980, 70, 19, 'muted')
        if number==1 and deck:
            footer_x=80
            if deck.get('logo'):
                raw,(iw,ih)=images.decode(deck['logo'])
                height=min(30,70*ih/iw);width=height*iw/ih
                objects.append(dict(kind='image',x=80,y=610+(30-height)/2,w=width,h=height,raw=raw,role='cover-logo'))
                footer_x=80+width+18
            if deck.get('preparedAt'):
                text('Deck prepared · '+deck['preparedAt'],footer_x,611,620-footer_x+80,28,13,'muted')
    else:
        section = {'summary':'OVERVIEW','cards':'KEY METRICS','comparison':'COMPARISON','chart':'STATISTICAL ANALYSIS','process':'PROCESS','timeline':'ROADMAP','table':'ACTION PLAN','notebook':'NOTEBOOK PAGE','image-focus':'VISUAL STORY','image-caption':'VISUAL INSIGHT','quote':'PERSPECTIVE','big-number':'HIGHLIGHT'}.get(layout,'ANALYSIS')
        text(section, 60, 31, 700, 30, 15, 'accent', True)
        text(s['title'], 60, 70, 1000, 78, 42, bold=True)
        if layout!='quote':text(s['subtitle'], 60, 135, 980, 48, 18, 'muted')
        rows = parse(s)
        n = len(rows)
        if layout == 'notebook':
            box(48, 196, 1092, 374, 'panel')
            box(48, 196, 8, 374, 'accent')
            text('READ · REFLECT · REMEMBER', 86, 218, 520, 26, 14, 'accent', True)
            text(s['content'] or ' ', 86, 260, 1010, 260, 27)
            box(86, 536, 80, 3, 'accent')
            if s.get('sourceUrl'):
                link('▶  Open supporting video', s['sourceUrl'], 60, 587, 260, 30)
            if s.get('localVideoReference'):
                text('Local media · ' + s['localVideoReference'], 345, 587, 730, 30, 15, 'muted')
        elif layout == 'summary':
            h = 390 / n
            for i, row in enumerate(rows):
                text(f'{i+1:02}', 60, 220+i*h, 55, h-6, 24, 'accent', True)
                text(row[0], 140, 220+i*h, 990, h-6, 26)
        elif layout == 'timeline':
            h = 380/n
            box(80, 230, 3, 380-h+20, 'accent')
            for i, row in enumerate(rows):
                y = 225+i*h
                box(73, y+8, 17, 17, 'accent')
                text(row[0], 115, y, 200, h-10, 25, 'accent', True)
                text(row[1], 345, y, 780, h-10, 25)
        elif layout == 'process':
            h = 380/n
            for i, row in enumerate(rows):
                y = 220+i*h
                text(f'{i+1:02}', 65, y, 65, h-10, 25, 'accent', True)
                text(row[0], 165, y, 300, h-10, 25, 'text', True)
                text(row[1], 500, y, 620, h-10, 24)
                if i < n-1:
                    box(90, y+32, 2, max(2,h-38), 'accent')
        elif layout in ('cards', 'comparison'):
            cols = min(n, 3)
            count_rows = math.ceil(n/cols)
            w, h = 1080/cols, 385/count_rows
            for i, row in enumerate(rows):
                x, y = 60+(i%cols)*w, 220+(i//cols)*h
                box(x, y, w-18, h-18, 'panel')
                headline = row[0] if layout != 'process' else f'{i+1}. {row[0]}'
                text(headline, x+20, y+18, w-58, (h-48)*.44, 36 if layout == 'cards' else 26, 'accent', True)
                text('\n'.join(row[1:]), x+20, y+20+(h-48)*.44, w-58, (h-48)*.56, 23)
        elif layout in ('timeline', 'table'):
            widths = [540, 280, 260] if layout == 'table' else [220, 860]
            data = [t['fields']] + rows
            h = 390/len(data)
            for i, row in enumerate(data):
                box(60, 215+i*h, 1080, h-3, 'panel' if i%2 == 0 else 'background')
                x = 60
                for cell, w in zip(row, widths):
                    text(cell, x+14, 220+i*h, w-28, h-12, 22, 'accent' if i == 0 else 'text', i == 0)
                    x += w
        elif layout == 'chart':
            if s.get('chartType') in statistical.KINDS:
                objects.extend(statistical.objects(s,theme))
            else:
                objects.append(dict(kind='chart', x=60,y=210,w=1080,h=410,source=s,theme=theme))
        elif layout == 'image-focus':
            if s.get('image'):
                objects.append(dict(kind='image',x=60,y=195,w=1080,h=390,raw=images.cover(s['image'],1080,390),role='slide-image'))
            else:
                box(60,195,1080,390,'panel');text('ADD A LARGE IMAGE',455,365,300,32,16,'muted',True)
            if s.get('content'):
                text(s['content'],60,590,960,25,14,'muted')
        elif layout == 'image-caption':
            if s.get('image'):
                objects.append(dict(kind='image',x=60,y=205,w=660,h=380,raw=images.cover(s['image'],660,380),role='slide-image'))
            else:
                box(60,205,660,380,'panel');text('ADD AN IMAGE',285,375,240,32,16,'muted',True)
            box(750,205,390,380,'panel');box(750,205,7,380,'accent')
            text('WHAT TO NOTICE',785,235,315,28,14,'accent',True)
            text(s['content'] or ' ',785,285,310,245,25)
        elif layout == 'quote':
            box(60,205,1080,365,'panel');box(60,205,8,365,'accent')
            text('“',92,220,100,105,76,'accent',True)
            text(s['content'] or ' ',175,260,860,190,34,'text',True)
            text('— '+s['subtitle'],175,485,760,36,18,'muted')
        elif layout == 'big-number':
            value,label,context=rows[0]
            box(60,210,1080,350,'panel');box(60,210,9,350,'accent')
            text(value,105,245,455,150,72,'accent',True)
            text(label,610,255,460,75,32,'text',True)
            text(context,610,350,455,100,24,'muted')
    if s.get('image') and layout not in ('image-focus','image-caption'):
        obj,reserved=images.object_for(s)
        scale=(1080-reserved-30)/1080
        offset=reserved+30 if s.get('imagePosition','right')=='left' else 0
        for o in objects[1:]:
            if o.get('role')=='background-motif':continue
            o['x']=60+(o['x']-60)*scale+offset
            o['w']*=scale
            if o['kind'] in ('text', 'link'):
                o['size']*=scale
        objects.append(obj)
        if layout == 'notebook':
            text('LOOK · CONNECT · UNDERSTAND', obj['x'], 196, obj['w'], 24, 14, 'accent', True)
            box(obj['x'], 216, min(72, obj['w']), 3, 'accent')
    if layout!='hero':
        total=(deck or {}).get('previewTotalSlides') or len((deck or {}).get('slides') or []) or number
        line(60,620,1080,motif)
        footer_x=60
        if deck and deck.get('logo'):
            raw,(iw,ih)=images.decode(deck['logo']);height=min(22,55*ih/iw);width=height*iw/ih
            objects.append(dict(kind='image',x=60,y=633+(22-height)/2,w=width,h=height,raw=raw,role='footer-logo'))
            footer_x=60+width+14
        if deck and deck.get('name'):
            text(deck['name'],footer_x,632,700-footer_x+60,24,13,'muted')
        text(f'{number:02} / {total:02}',1050,632,90,24,13,'muted')
    elif number!=1:
        text(f'{number:02}',1090,632,60,26,16,'muted')
    if deck and deck.get('logo') and layout=='hero' and not (s.get('type')=='title' and number==1) and not (deck.get('hideLogoOnTitle', True) and s.get('type') == 'title'):
        raw,(iw,ih)=images.decode(deck['logo'])
        width={'small':70,'medium':110,'large':150}[deck.get('logoSize','medium')]
        height=min(56,width*ih/iw);width=height*iw/ih
        position=deck.get('logoPosition','top-right')
        x=36 if position.endswith('left') else 1164-width
        y=28 if position.startswith('top') else 618-height
        objects.append(dict(kind='image',x=x,y=y,w=width,h=height,raw=raw,role='logo'))
    return objects

def svg(objects):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" role="img" aria-label="Slide preview">']
    for o in objects:
        if o['kind'] == 'rect':
            parts.append(f'<rect x="{o["x"]}" y="{o["y"]}" width="{o["w"]}" height="{o["h"]}" fill="#{o["color"]}"/>')
        elif o['kind']=='line':
            parts.append(f'<line x1="{o["x"]}" y1="{o["y"]}" x2="{o["x"]+o["w"]}" y2="{o["y"]+o["h"]}" stroke="#{o["color"]}" stroke-width="{o["width"]}"/>')
        elif o['kind']=='ellipse':
            parts.append(f'<ellipse cx="{o["x"]+o["w"]/2}" cy="{o["y"]+o["h"]/2}" rx="{o["w"]/2}" ry="{o["h"]/2}" fill="#{o["color"]}"/>')
        elif o['kind'] in ('chart','image'):
            raw=charts.preview(o['source'],o['theme']).encode() if o['kind']=='chart' else o['raw']
            mime='image/svg+xml' if o['kind']=='chart' else 'image/png'
            uri='data:'+mime+';base64,'+base64.b64encode(raw).decode()
            parts.append(f'<image x="{o["x"]}" y="{o["y"]}" width="{o["w"]}" height="{o["h"]}" preserveAspectRatio="none" href="{uri}"/>')
        else:
            prefix = f'<a href="{escape(o["address"], quote=True)}">' if o['kind'] == 'link' else ''
            for i, line in enumerate(o['lines']):
                parts.append(prefix + f'<text x="{o["x"]}" y="{o["y"]+o["size"]+i*o["size"]*1.28}" font-family="Arial, sans-serif" font-size="{o["size"]}" font-weight="{700 if o["bold"] else 400}" fill="#{o["color"]}">{escape(line)}</text>' + ('</a>' if prefix else ''))
    return ''.join(parts)+'</svg>'

def powerpoint(deck):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333333), Inches(7.5)
    unit = lambda v: Inches(v/90)
    zoom_requests=[]
    for i, s in enumerate(deck['slides']):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        transition_type=s.get('transition','inherit')
        if transition_type=='inherit':transition_type=(deck.get('transition') or {}).get('type','none')
        if transition_type!='none':
            transition=OxmlElement('p:transition')
            transition.set('spd',{'slow':'slow','medium':'med','fast':'fast'}[(deck.get('transition') or {}).get('speed','medium')])
            transition.set('advClick','1')
            effect=OxmlElement('p:'+transition_type)
            if transition_type=='push':effect.set('dir','l')
            if transition_type=='wipe':effect.set('dir','r')
            transition.append(effect)
            slide._element.insert(2,transition)
        for o in scene(s, THEMES[deck['theme']], i+1, deck):
            if o['kind'] in ('rect','ellipse'):
                shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE if o['kind']=='rect' else MSO_SHAPE.OVAL, unit(o['x']), unit(o['y']), unit(o['w']), unit(o['h']))
                shape.fill.solid()
                shape.fill.fore_color.rgb = RGBColor.from_string(o['color'])
                shape.line.fill.background()
            elif o['kind']=='line':
                shape=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,unit(o['x']),unit(o['y']),unit(o['x']+o['w']),unit(o['y']+o['h']))
                shape.line.color.rgb=RGBColor.from_string(o['color'])
                shape.line.width=Pt(o['width']*.8)
            elif o['kind']=='chart':
                charts.add_chart(slide,o,unit)
            elif o['kind']=='image':
                picture=slide.shapes.add_picture(BytesIO(o['raw']),unit(o['x']),unit(o['y']),unit(o['w']),unit(o['h']))
                if deck.get('pptImageZoom',True) and s.get('image') and o.get('role') not in ('logo','cover-logo','footer-logo'):
                    zoom_requests.append((slide,picture,o['raw'],o['w']/o['h'],s['title']))
            else:
                shape = slide.shapes.add_textbox(unit(o['x']), unit(o['y']), unit(o['w']), unit(o['h']))
                tf = shape.text_frame
                tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
                tf.word_wrap = False
                for j, line in enumerate(o['lines']):
                    p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                    p.text = line
                    if o['kind'] == 'link' and p.runs:
                        p.runs[0].hyperlink.address = o['address']
                    p.font.name = 'Arial'
                    p.font.size = Pt(o['size']*.8)
                    p.font.bold = o['bold']
                    p.font.color.rgb = RGBColor.from_string(o['color'])
                    p.space_before = p.space_after = Pt(0)
                    p.line_spacing = Pt(o['size']*.8*1.28)
    for source,picture,raw,ratio,title in zoom_requests:
        detail=prs.slides.add_slide(prs.slide_layouts[6])
        detail._element.set('show','0')
        background=detail.shapes.add_shape(MSO_SHAPE.RECTANGLE,0,0,prs.slide_width,prs.slide_height)
        background.fill.solid();background.fill.fore_color.rgb=RGBColor.from_string(THEMES[deck['theme']]['background']);background.line.fill.background()
        heading=detail.shapes.add_textbox(unit(50),unit(25),unit(1000),unit(45))
        heading.text_frame.text=title
        heading.text_frame.paragraphs[0].font.name='Arial';heading.text_frame.paragraphs[0].font.size=Pt(24);heading.text_frame.paragraphs[0].font.bold=True;heading.text_frame.paragraphs[0].font.color.rgb=RGBColor.from_string(THEMES[deck['theme']]['text'])
        max_w,max_h=1100,535
        width=min(max_w,max_h*ratio);height=width/ratio
        image=detail.shapes.add_picture(BytesIO(raw),unit((1200-width)/2),unit(80+(max_h-height)/2),unit(width),unit(height))
        back=detail.shapes.add_textbox(unit(55),unit(625),unit(220),unit(28))
        back.text_frame.text='← Back to slide'
        back.text_frame.paragraphs[0].font.name='Arial';back.text_frame.paragraphs[0].font.size=Pt(13);back.text_frame.paragraphs[0].font.bold=True;back.text_frame.paragraphs[0].font.color.rgb=RGBColor.from_string(THEMES[deck['theme']]['accent'])
        picture.click_action.target_slide=detail
        image.click_action.target_slide=source
        back.click_action.target_slide=source
    output = BytesIO()
    prs.save(output)
    return output.getvalue()
