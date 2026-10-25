"""Bounded Cirrus equipment semantics, pinned to executed SH-2 source."""
import hashlib
import json
from pathlib import Path
from interaction_contract import build as previous

ROOT=Path(__file__).resolve().parents[1]
MAIN_SHA='95054f9128b7ab47f88c6659b103e7bee9db94c13548f815bbda5999b30da2ff'
ROUTES=('equip-stairs','remove-stairs','reequip-stairs','unowned','cancel-owned','hold-equip','cancel-selection')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def canonical(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())

def source_contract(high=None):
    raw=(ROOT.parent/'work/extract/0').read_bytes()
    if sha(raw)!=MAIN_SHA:raise ValueError('Changed equipment executable source')
    ranges=[(0x17308,0x17386),(0x17478,0x17518),(0x17968,0x179ee),
            (0x17ece,0x18000),(0x180e6,0x18144),(0x181f4,0x18288)]
    evidence=[]
    for start,end in ranges:
        block=raw[start-0x10000:end-0x10000]
        if high is not None and high[start:end]!=block:raise ValueError('Runtime equipment routine changed')
        evidence.append({'address':0x6000000+start,'bytes':len(block),'sha256':sha(block)})
    address=0x2e164+27*32;item=raw[address-0x10000:address-0x10000+32]
    if item[:7]!=b'CIRRUS\0' or item[27]&7!=1:raise ValueError('Unknown weapon record')
    bonus_address=0x2fa24+item[29]*2
    bonus=int.from_bytes(raw[bonus_address-0x10000:bonus_address-0x10000+2],'big')
    if bonus!=5:raise ValueError('Unverified weapon bonus')
    if high is not None and (high[address:address+32]!=item or int.from_bytes(high[bonus_address:bonus_address+2],'big')!=bonus):
        raise ValueError('Runtime item record differs')
    return {'source_sha256':MAIN_SHA,'ranges':evidence,'item_id':27,'empty_weapon':255,'remove_menu_id':254,
            'weapon_address':0x060366b7,'inventory_address':0x060367cf,'attack_address':0x060366a0,
            'story_address':0x06036938,'story_mask':4,'sticky_story_bit':True,'base_attack':10,'attack_bonus':bonus,
            'item_record':{'address':0x6000000+address,'sha256':sha(item)},'bonus_address':0x6000000+bonus_address,
            'menu_scope':'PC semantic transactions only. Original menu navigation and cursor caches remain source evidence.'}

def build():
    result=previous()
    result['schema']='ao_pc_cirrus_equipment_contract_v1'
    result['story_values']=[1,3,7]
    for rows in result['programs'].values():
        for row in rows:
            if row['action']=='branch_story':
                row['args']['allowed_bytes']=[1,3,7]
                row['args']['if_set']=row['args']['source_if_set']
    raw=(ROOT.parent/'work/extract/MAP001.TWN').read_bytes()
    if raw[0x2fb2:0x2fb4]!=b'\0\0':raise ValueError('Changed equipped branch terminal')
    result['programs']['equipped_end']=[{'action':'end','args':{},'source':{'offset':0x2fb2,'span':2,'opcode':0,'bytes':raw[0x2fb2:0x2fb4].hex()}}]
    # Use precisely the same provenance shape as the existing converter.
    template=next(r for rows in result['programs'].values() for r in rows if r['action']=='end')
    result['programs']['equipped_end'][0]['source']={**template['source'],'offset':0x2fb2,'span':2,'opcode':0}
    for key in ('hex','bytes'):
        if key in template['source']:result['programs']['equipped_end'][0]['source'][key]='0000'
    result['equipment']=source_contract()
    result['limitations']=['No next room, generic inventory, equipment menu replication, battle or saves.',
        'Menu pauses world in the PC UI; only semantic operations reproduce source state changes.',
        'Source shadows omitted. Performance not accepted; no load tests in this stage.']
    return result
