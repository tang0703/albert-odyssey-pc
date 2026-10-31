"""Local source-art coverage map; lookup cells are not all walkable tiles."""
import base64
import json
from landing_event_source import ROOT


def build():
    core=json.loads((ROOT/'generated/landing-event/core.json').read_bytes())
    fixture=json.loads((ROOT/'generated/landing-event/reference/equip.json').read_bytes())
    background=base64.b64encode((ROOT/'generated/transition/background.png').read_bytes()).decode()
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1792" height="1184" viewBox="0 0 448 296">',
         '<rect width="448" height="296" fill="#152837"/>',
         f'<image width="448" height="256" href="data:image/png;base64,{background}" style="image-rendering:pixelated"/>',
         '<rect x="128" y="24" width="320" height="224" fill="none" stroke="white" stroke-width="1"/>']
    for index in core['landing_query_indices']:
        x=(index%256)*8-512;y=(index//256)*8-1792
        svg.append(f'<rect x="{x}" y="{y}" width="8" height="8" fill="#2dd8dc" fill-opacity="0.18" stroke="#2dd8dc" stroke-width="0.3"/>')
    for key,colour in [('player','#d2ff8f'),('arrival_actor','#dd94ff')]:
        points=[]
        for row in fixture['post_commit']:
            state=row['expected']
            if state['scene']!=7 or not state.get(key):continue
            raw=bytes.fromhex(state[key]);point=(int.from_bytes(raw[:2],'big')/16-512,int.from_bytes(raw[2:4],'big')/16-1792)
            if not points or point!=points[-1]:points.append(point)
        encoded=' '.join(f'{x},{y}' for x,y in points)
        svg.append(f'<polyline points="{encoded}" fill="none" stroke="{colour}" stroke-width="0.7"/>')
    x,y,r,b=core['trigger']['bounds_raw']
    svg.append(f'<rect x="{x/16-512}" y="{y/16-1792}" width="{(r-x)/16}" height="{(b-y)/16}" fill="none" stroke="#ffaf53" stroke-width="0.6"/>')
    for offset,text in enumerate([f"Scene 7 / left event / {len(core['landing_query_indices'])} source-tested lookup cells",
        'Cyan: collision lookups, not walkable tiles. Green: player replay. Purple: forced NPC path.',
        'White: first-control viewport limit. Orange: verified event trigger. Other exits remain boundaries.',
        'Forced NPC movement does not authorize free exploration. Source artwork stays local.']):
        svg.append(f'<text x="6" y="{265+offset*8}" fill="white" font-family="sans-serif" font-size="5">{text}</text>')
    svg.append('</svg>')
    (ROOT/'reports/landing-event/landing-coverage.svg').write_text('\n'.join(svg),encoding='utf-8')


if __name__=='__main__':build()
