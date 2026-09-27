"""Import the shared KestrelIQ Notebook XLSX format without network dependencies."""
import base64
import posixpath
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

COLUMNS = ('Notebook', 'Chapter', 'Page Heading', 'Page Details', 'Video URL',
           'Local Video URL', 'Diagram', 'Page Order')
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _children(node, name):
    return [item for item in node.iter() if _local(item.tag) == name]


def _rels(archive, path):
    directory, filename = posixpath.split(path)
    rel_path = posixpath.join(directory, '_rels', filename + '.rels')
    try:
        root = ET.fromstring(archive.read(rel_path))
    except KeyError:
        return {}
    result = {}
    for item in root:
        if item.attrib.get('TargetMode') == 'External':
            continue
        target = item.attrib.get('Target', '')
        result[item.attrib.get('Id')] = posixpath.normpath(
            target.lstrip('/') if target.startswith('/') else posixpath.join(directory, target)
        )
    return result


def _cell_column(reference):
    letters = re.match(r'[A-Z]+', reference or '')
    value = 0
    for char in letters.group(0) if letters else '':
        value = value * 26 + ord(char) - 64
    return value - 1


def _shared_strings(archive):
    try:
        root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    except KeyError:
        return []
    return [''.join(node.text or '' for node in item.iter() if _local(node.tag) == 't')
            for item in root if _local(item.tag) == 'si']


def _cell_value(cell, shared):
    kind = cell.attrib.get('t')
    if kind == 'inlineStr':
        return ''.join(node.text or '' for node in cell.iter() if _local(node.tag) == 't')
    values = _children(cell, 'v')
    value = values[0].text if values and values[0].text is not None else ''
    if kind == 's' and value:
        try:
            return shared[int(value)]
        except (ValueError, IndexError):
            return ''
    return value


def _sheet_path(archive):
    book = ET.fromstring(archive.read('xl/workbook.xml'))
    sheets = _children(book, 'sheet')
    if not sheets:
        raise ValueError('The workbook has no worksheets.')
    rel_id = sheets[0].attrib.get(f'{{{REL_NS}}}id')
    path = _rels(archive, 'xl/workbook.xml').get(rel_id)
    if not path:
        raise ValueError('The first worksheet could not be read.')
    return path


def _diagram_images(archive, sheet_path, sheet, diagram_column):
    images = {}
    sheet_rels = _rels(archive, sheet_path)
    for drawing in _children(sheet, 'drawing'):
        drawing_path = sheet_rels.get(drawing.attrib.get(f'{{{REL_NS}}}id'))
        if not drawing_path:
            continue
        drawing_xml = ET.fromstring(archive.read(drawing_path))
        drawing_rels = _rels(archive, drawing_path)
        anchors = [node for node in drawing_xml.iter()
                   if _local(node.tag) in ('oneCellAnchor', 'twoCellAnchor')]
        for anchor in anchors:
            origins = [node for node in anchor if _local(node.tag) == 'from']
            if not origins:
                continue
            cols, rows = _children(origins[0], 'col'), _children(origins[0], 'row')
            if not cols or not rows or int(cols[0].text or -1) != diagram_column:
                continue
            row = int(rows[0].text or -1)
            blips = _children(anchor, 'blip')
            image_path = drawing_rels.get(blips[0].attrib.get(f'{{{REL_NS}}}embed')) if blips else None
            if not image_path:
                continue
            if row in images:
                raise ValueError(f'Use one diagram per row in the Diagram column (row {row + 1}).')
            raw = archive.read(image_path)
            if len(raw) > 5 * 1024 * 1024:
                raise ValueError(f'Diagram in row {row + 1} exceeds 5 MB.')
            extension = image_path.rsplit('.', 1)[-1].lower()
            mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                    'webp': 'image/webp'}.get(extension)
            if not mime:
                raise ValueError(f'Diagram in row {row + 1} must be PNG, JPEG, or WebP.')
            images[row] = f'data:{mime};base64,{base64.b64encode(raw).decode()}'
    return images


def _chunks(text, limit):
    text = str(text or '').strip()
    if not text:
        return ['']
    paragraphs = [part.strip() for part in re.split(r'\n+', text) if part.strip()]
    result, current = [], ''
    for paragraph in paragraphs:
        pieces = [paragraph[i:i + limit] for i in range(0, len(paragraph), limit)] or ['']
        for piece in pieces:
            candidate = (current + '\n' + piece).strip()
            if current and len(candidate) > limit:
                result.append(current)
                current = piece
            else:
                current = candidate
    if current:
        result.append(current)
    return result or ['']


def import_notebook(data, theme='ocean'):
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except (zipfile.BadZipFile, TypeError) as exc:
        raise ValueError('Choose a valid .xlsx Notebook template.') from exc
    with archive:
        sheet_path = _sheet_path(archive)
        sheet = ET.fromstring(archive.read(sheet_path))
        shared = _shared_strings(archive)
        raw_rows = []
        for row in _children(sheet, 'row'):
            values = {}
            for cell in [node for node in row if _local(node.tag) == 'c']:
                values[_cell_column(cell.attrib.get('r'))] = _cell_value(cell, shared)
            raw_rows.append((int(row.attrib.get('r', len(raw_rows) + 1)) - 1, values))
        if not raw_rows:
            raise ValueError('The first worksheet is empty.')
        headers = {index: str(value).strip() for index, value in raw_rows[0][1].items()}
        names = list(headers.values())
        missing = [name for name in COLUMNS if name != 'Local Video URL' and name not in names]
        if missing:
            raise ValueError('Missing columns: ' + ', '.join(missing))
        diagram_column = next(index for index, name in headers.items() if name == 'Diagram')
        diagrams = _diagram_images(archive, sheet_path, sheet, diagram_column)
        rows = []
        for sheet_row, values in raw_rows[1:]:
            item = {name: str(values.get(index, '') or '').strip() for index, name in headers.items()}
            if not any(item.values()) and sheet_row not in diagrams:
                continue
            item['_row'] = sheet_row
            item['_image'] = diagrams.get(sheet_row)
            rows.append(item)
    if not rows:
        raise ValueError('The Notebook template has no page rows.')
    def order(item):
        try:
            return (0, float(item.get('Page Order') or 0), item['_row'])
        except ValueError:
            return (1, 0, item['_row'])
    rows.sort(key=order)
    name = next((row.get('Notebook') for row in rows if row.get('Notebook')), 'Notebook presentation')
    slides = [{'type': 'title', 'eyebrow': 'NOTEBOOK PRESENTATION', 'title': name, 'subtitle': 'Notebook presentation',
               'content': f'{len(rows)} pages'}]
    previous_chapter = None
    for row in rows:
        chapter = row.get('Chapter') or 'Notebook'
        if chapter != previous_chapter:
            slides.append({'type': 'title', 'eyebrow': 'CHAPTER', 'title': chapter, 'subtitle': name, 'content': 'Chapter'})
            previous_chapter = chapter
        image = row.get('_image')
        chunks = _chunks(row.get('Page Details'), 500 if image else 900)
        for index, content in enumerate(chunks):
            slide = {'type': 'notebook',
                     'title': (row.get('Page Heading') or 'Untitled page') + (' — continued' if index else ''),
                     'subtitle': chapter, 'content': content,
                     'sourceUrl': row.get('Video URL', ''),
                     'localVideoReference': row.get('Local Video URL', '')}
            if image and index == 0:
                slide.update(image=image, imagePosition='right', imageSize='medium')
            slides.append(slide)
    if len(slides) > 60:
        raise ValueError(f'Import creates {len(slides)} slides; Slide Studio supports up to 60. Split the workbook and try again.')
    return {'name': name, 'theme': theme, 'slides': slides}
