"""Generate the original vector mark and Windows icon from shared geometry."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

root=Path(__file__).resolve().parents[1]
svg='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<rect width="256" height="256" rx="58" fill="#0d1922"/>
<circle cx="128" cy="128" r="102" fill="#16303c" stroke="#335c6b"/>
<path d="M82 180V76L174 180V76" fill="none" stroke="#37606e" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M82 180V76L174 180V76" fill="none" stroke="#adefff" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''
(root/'assets/nexus-aurora.svg').write_text(svg,encoding='utf-8')
s=4
im=Image.new('RGBA',(256*s,256*s))
d=ImageDraw.Draw(im)
d.rounded_rectangle((0,0,256*s-1,256*s-1),radius=58*s,fill='#0d1922')
d.ellipse((26*s,26*s,230*s,230*s),fill='#16303c',outline='#335c6b',width=s)
points=[(82*s,180*s),(82*s,76*s),(174*s,180*s),(174*s,76*s)]
for color,width in (('#37606e',26),('#adefff',10)):
    d.line(points,fill=color,width=width*s,joint='curve')
    for x,y in points:
        r=width*s/2
        d.ellipse((x-r,y-r,x+r,y+r),fill=color)
im=im.resize((256,256),Image.Resampling.LANCZOS)
im.save(root/'assets/nexus-aurora.png')
im.save(root/'assets/nexus.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('Generated original SVG, static PNG and Windows ICO.')
