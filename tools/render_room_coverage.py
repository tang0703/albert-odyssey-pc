"""Local-only source-map diagnostic; an overlay is never collision evidence."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw
from character_graphics import BackgroundSource


def render(report: dict, out: Path) -> None:
    if not report.get('passed') or report['unobserved_required_queries']:
        raise ValueError('Coverage diagram requires an accepted source comparison')
    project = Path(__file__).resolve().parents[1]
    source = BackgroundSource((project.parent/'work/extract/MAP001.TWN').read_bytes())
    origin, size = (512,1536),(448,256)
    original=Image.new('RGBA',size,(0,0,0,255))
    for y in range(size[1]):
        for x in range(size[0]):
            layers=[(source.pixel(layer,x+origin[0],y+origin[1]),layer) for layer in (0,1)]
            # NBG0 wins equal priority, as in the original source decoder.
            visible=[(value,layer) for value,layer in layers if value['rgba'][3]]
            if visible:
                value,_=max(visible,key=lambda row:(row[0]['priority'],-row[1]))
                original.putpixel((x,y),value['rgba'])
    overlay=Image.new('RGBA',size);draw=ImageDraw.Draw(overlay)
    for index in report['verified_query_indices']:
        x,y=(index%256)*8-origin[0],(index//256)*8-origin[1]
        draw.rectangle((x,y,x+7,y+7),fill=(45,211,156,55),outline=(45,211,156,120))
    for x,y in report['coverage']['reachable_raw_xy']:
        draw.point((x//16-origin[0],y//16-origin[1]),fill=(220,250,248,120))
    for boundary in report['boundaries']:
        l,t,r,b=boundary['raw_bounds_inclusive']
        draw.rectangle((l//16-origin[0],t//16-origin[1],r//16-origin[0],b//16-origin[1]),
                       fill=(255,140,50,100),outline=(255,174,85,255),width=1)
    composite=Image.alpha_composite(original,overlay).resize((1344,768),Image.Resampling.NEAREST)
    output=Image.new('RGB',(1344,850),(15,27,37));output.paste(composite,(0,68))
    labels=ImageDraw.Draw(output)
    labels.text((18,12),'MAP001 ROOM | verified source lookup cells / reachable-model audit / event test boundaries',fill='white')
    labels.text((18,34),f"Green: {len(report['verified_query_indices'])} source-compared cells | Orange: event/exit test boundary | Background: original local source",fill=(160,225,205))
    out.parent.mkdir(parents=True,exist_ok=True);output.save(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();render(json.loads(args.report.read_text()),args.out)
