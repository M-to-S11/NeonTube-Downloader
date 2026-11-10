"""Bundled assets are prepared from the user-provided design reference.
This optional script is only for developers with the reference screenshot."""
from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path
import sys

src = Path(sys.argv[1]) if len(sys.argv)>1 else None
if not src or not src.is_file():
    raise SystemExit('Usage: python make_assets.py <path-to-reference-screenshot>')
out=Path(__file__).resolve().parent/'assets'
out.mkdir(exist_ok=True)
im=Image.open(src).convert('RGBA')

def cropbox(box,name):
    im.crop(box).save(out/name)

cropbox((14,414,296,1001),'sidebar_art.png')
cropbox((353,629,515,728),'preview_mountain.png')
cropbox((1121,354,1189,414),'thumb_music.png')
cropbox((1121,446,1189,507),'thumb_chill.png')
cropbox((1121,532,1189,594),'thumb_gaming.png')
# Das Hero-Banner, App-Icon und NeonTube-Logo wurden vom Benutzer personalisiert.
# Diese Assets NIE aus einem Screenshot regenerieren oder ueberschreiben:
# assets/hero_art.png, assets/neontube_logo.png, assets/app_icon.png, assets/app.ico
# Gradient header decorative background from reference; add darkness to prevent ghost text.
base=im.resize((1536,1024)).convert('RGB').filter(ImageFilter.GaussianBlur(55))
layer=Image.new('RGB',base.size,(6,7,29))
base=Image.blend(base,layer,0.77)
base.save(out/'ambient_background.jpg',quality=88)
# Button gradient artwork for actual interactive Canvas buttons.
def gradient_image(colors,name,w=1000,h=160):
    res=Image.new('RGB',(w,h)); p=res.load()
    for x in range(w):
        t=x/(w-1); segment=min(len(colors)-2,int(t*(len(colors)-1)))
        k=t*(len(colors)-1)-segment
        c0=colors[segment];c1=colors[segment+1]
        c=tuple(int(c0[i]*(1-k)+c1[i]*k) for i in range(3))
        for y in range(h):p[x,y]=c
    res.save(out/name)
gradient_image([(157,0,255),(232,0,235),(255,86,162),(255,173,62)],'gradient_hot.png')
gradient_image([(172,0,239),(84,28,245)],'gradient_purple.png')
print('Assets prepared:',out)
