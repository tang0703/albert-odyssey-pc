"""Source pixel atlases for the scene-7 camera extent, independent of old room."""
from PIL import Image
from character_graphics import BackgroundSource
ORIGIN=(512,1792)
SIZE=(448,256)

def atlases(source_map: bytes) -> tuple[Image.Image,Image.Image]:
    source=BackgroundSource(source_map)
    background=Image.new('RGBA',SIZE,(0,0,0,255))
    foreground=Image.new('RGBA',SIZE)
    for y in range(SIZE[1]):
        for x in range(SIZE[0]):
            candidates=[source.pixel(layer,x+ORIGIN[0],y+ORIGIN[1]) for layer in (0,1)]
            opaque=[r for r in candidates if r['index']]
            if opaque:
                winner=max(opaque,key=lambda r:(r['priority'],-r['layer']))
                background.putpixel((x,y),winner['rgba'])
                if winner['priority']==3: foreground.putpixel((x,y),winner['rgba'])
    return background,foreground
