"""Reopen the delivered Blender source and validate weights, UVs and loops."""
import bpy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'art/unity/startroom-u4/startroom-rig.blend'))
rig=bpy.data.objects['MAP001_RIG'];scene=bpy.context.scene
assert len(rig.data.bones)==22
skins=[o for o in scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
assert skins
count=0
for obj in skins:
    assert len(obj.data.uv_layers)>0
    for v in obj.data.vertices:
        assert abs(sum(g.weight for g in v.groups)-1)<1e-5
        count+=1
actions={a.name:a for a in bpy.data.actions}
expected={'idle','walk','pickup_35','pickup_36','pickup_37','pickup_38'}
assert expected<=set(actions)
for name in expected:
    rig.animation_data.action=actions[name]
    if hasattr(rig.animation_data,'action_slot') and len(actions[name].slots):rig.animation_data.action_slot=actions[name].slots[0]
    snapshots=[]
    for f in range(int(actions[name].frame_range[0]),int(actions[name].frame_range[1])+1):
        scene.frame_set(f)
        assert rig.pose.bones['root'].location.length<1e-7
        snapshots.append({b.name:tuple(v for row in b.matrix for v in row) for b in rig.pose.bones})
    if name in ('idle','walk'):
        assert max(abs(a-b) for n in snapshots[0] for a,b in zip(snapshots[0][n],snapshots[-1][n]))<1e-5
report={'passed':True,'bones':22,'weighted_vertices':count,'actions':sorted(expected),'normalized_weights':True,'editable_uvs':True,'root_translation_zero':True,'loop_endpoints_equal':True,'performance_tested':False}
(ROOT/'reports/unity/u4-rig-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
