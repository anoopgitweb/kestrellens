"""Validate local raster images and calculate shared placement bounds."""
import base64
import warnings
from io import BytesIO
from PIL import Image, ImageOps

def decode(uri):
    try:
        if not isinstance(uri,str) or len(uri)>7_000_000: raise ValueError()
        prefix,payload=uri.split(',',1)
        if prefix not in ('data:image/png;base64','data:image/jpeg;base64','data:image/webp;base64'):raise ValueError()
        raw=base64.b64decode(payload,validate=True)
        if len(raw)>5*1024*1024:raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as im:
                if im.format not in ('PNG','JPEG','WEBP') or im.width*im.height>20_000_000:raise ValueError()
                im.load();im=ImageOps.exif_transpose(im).convert('RGBA')
                im.thumbnail((2400,2400));out=BytesIO();im.save(out,format='PNG')
                return out.getvalue(), im.size
    except Exception as exc:raise ValueError('Use a valid PNG, JPEG, or WebP image under 5 MB and 20 megapixels.') from exc

def object_for(s):
    raw,(iw,ih)=decode(s['image'])
    side=s.get('imagePosition','right');size=s.get('imageSize','medium')
    if side not in ('left','right') or size not in ('small','medium','large'):raise ValueError('Choose a valid image placement and size.')
    w={'small':300,'medium':420,'large':520}[size];h=395
    x=60 if side=='left' else 1140-w;y=215
    ratio=min(w/iw,h/ih);pw,ph=iw*ratio,ih*ratio
    return dict(kind='image',x=x+(w-pw)/2,y=y+(h-ph)/2,w=pw,h=ph,raw=raw),w
