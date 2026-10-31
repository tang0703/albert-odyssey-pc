"""Pack generated artwork into editable OpenRaster layers; no pose synthesis."""
from pathlib import Path
from io import BytesIO
import json
import zipfile
import xml.etree.ElementTree as ET
from PIL import Image
from build_landing25d_bundle import ROOT,ART,PROJECT,read,sha,write

def png(im):
    b=BytesIO();im.save(b,format='PNG');return b.getvalue()
def build():
    folder=PROJECT/'generated/enhanced25d-landing';data=read(folder/'appearance.json');layout=data['layout'];layers=[]
    zoom=4;size=(448*zoom,256*zoom)
    raw=Image.open(folder/layout['shell']['file']).convert('RGBA');shell=Image.new('RGBA',size)
    g=layout['shell']
    for y in range(len(g['source_y'])-1):
        for x in range(len(g['source_x'])-1):
            box=(round(g['art_x'][x]*raw.width/448),round(g['art_y'][y]*raw.height/256),round(g['art_x'][x+1]*raw.width/448),round(g['art_y'][y+1]*raw.height/256))
            rect=(g['source_x'][x]*zoom,g['source_y'][y]*zoom,(g['source_x'][x+1]-g['source_x'][x])*zoom,(g['source_y'][y+1]-g['source_y'][y])*zoom)
            shell.paste(raw.crop(box).resize(rect[2:],Image.Resampling.LANCZOS),rect[:2])
    layers.append(('Room shell - approved world projection',shell))
    rows=list(layout['layers']);feet={'object_0':[272,160],'object_2':[256,192],'object_3':[256,112],'object_4':[288,112],'object_5':[288,192],'object_6':[144,112],'object_7':[320,80]}
    for key,p in layout['dynamic_props'].items():
        foot=feet[key];rows.append({'id':key,'file':p['file'],'rect':[foot[0]+p['offset'][0],foot[1]+p['offset'][1],*p['size']],'preserve':p['preserve'],'depth':foot[1]+(1000 if key=='object_0' else 0)})
    for r in sorted(rows,key=lambda r:r['depth']):
        im=Image.open(folder/r['file']).convert('RGBA').crop(data['textures'][r['file']]['visible_box']);x,y,w,h=r['rect'];w*=zoom;h*=zoom;x*=zoom;y*=zoom
        if r['preserve']:
            s=min(w/im.width,h/im.height);nw,nh=round(im.width*s),round(im.height*s);x+=(w-nw)//2;y+=h-nh;w,h=nw,nh
        layer=Image.new('RGBA',size);layer.alpha_composite(im.resize((w,h),Image.Resampling.LANCZOS),(x,y));layers.append((r['id'],layer))
    foreground=Image.new('RGBA',size)
    for x,y,w,h in layout['foreground_rects']:
        box=(x*zoom,y*zoom,(x+w)*zoom,(y+h)*zoom);foreground.paste(shell.crop(box),box[:2])
    layers.append(('Foreground - south wall occlusion',foreground))
    root=ET.Element('image',{'w':str(size[0]),'h':str(size[1]),'name':'MAP001 landing 2.5D - independent generated layers','version':'0.0.3'});stack=ET.SubElement(root,'stack')
    merged=Image.new('RGBA',size)
    for _,im in layers: merged.alpha_composite(im)
    path=ART/'landing-layers.ora'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('mimetype','image/openraster',compress_type=zipfile.ZIP_STORED)
        for i,(name,im) in reversed(list(enumerate(layers))):
            src=f'data/layer{i:02}.png';ET.SubElement(stack,'layer',{'name':name,'src':src,'x':'0','y':'0','opacity':'1.0','visibility':'visible','composite-op':'svg:src-over'});z.writestr(src,png(im),compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('stack.xml',ET.tostring(root,encoding='utf-8',xml_declaration=True));z.writestr('mergedimage.png',png(merged))
        thumb=merged.copy();thumb.thumbnail((256,256));z.writestr('Thumbnails/thumbnail.png',png(thumb))
    write(ART/'production-layout.json',layout)
    write(ART/'layers-manifest.json',{'schema':'ao_pc_landing25d_editable_layers_v1','ora_sha256':sha(path),'layers':len(layers),'size':list(size),'layout_sha256':sha(ART/'production-layout.json'),'note':'Static room assembly; animated steam and LAIA/player remain separate PNG/atlas assets. No source images included.'})
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        tree=ET.fromstring(z.read('stack.xml'));composite=Image.new('RGBA',size)
        for layer in reversed(list(tree.find('stack'))): composite.alpha_composite(Image.open(BytesIO(z.read(layer.attrib['src']))).convert('RGBA'))
        assert composite.tobytes()==merged.tobytes()
    print(json.dumps({'ora':str(path),'layers':len(layers),'independent_layer_recomposition':True}))
if __name__=='__main__': build()
