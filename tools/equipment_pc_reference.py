"""PC instruction scheduler. Source bytes are never executed by this adapter.

The independently source-checked actor/camera components are shared with the
reference model; this dispatch path consumes the bounded conversion contract.
"""
import struct
from equipment_sequence_reference import Model
import event_actor_reference as actor
import event_effect_reference as effect
import interaction_animation
from equipment_contract import build


class PcModel(Model):
    def __init__(self, high, low, source, twn, contract):
        super().__init__(high, low, source, twn)
        if contract != build():raise ValueError('Unapproved PC interaction contract')
        self.instructions = {}
        self.starts = {}
        for name, rows in contract['programs'].items():
            self.starts[name] = rows[0]['source']['offset']
            for row in rows:
                self.instructions[row['source']['offset']] = row
        self.source = None  # Runtime dispatch cannot read source bytes.

    def dispatch(self, s, signals):
        if s is None or not s.active:
            return
        if s.wait is not None:
            if self.wait(s, signals):
                s.wait = None
            return
        for _ in range(32):
            row = self.instructions.get(s.pc)
            if row is None:
                raise ValueError('Unknown PC instruction cursor')
            action, args, origin = row['action'], row['args'], row['source']
            self.commands.append((s.owner, s.pc, origin['opcode']))
            s.pc += origin['span']
            if action == 'end':
                s.active = False
                if s.owner == 'actor': actor.put(self.player, 6, actor.word(self.player, 6) & 0xfffb)
                elif s.owner == 'decoration': actor.put(self.decor, 10, actor.word(self.decor, 10) & 0xfffb)
                elif s.owner == 'spark':
                    actor.put(self.spark,6,actor.word(self.spark,6)&0xfffb)
                    actor.put(self.spark,0x2a,2)
                return
            if action == 'branch_story':
                if self.story[0] not in args['allowed_bytes']:raise ValueError('Unsupported story branch')
                target=args['if_set'] if self.story[0]&args['mask'] else args['if_clear']
                if target is None:raise ValueError('Unverified story target')
                s.pc=target
            elif action == 'set_story_bit':
                if self.story[0]!=args['required_byte']:raise ValueError('Invalid story mutation')
                self.story=bytes([self.story[0]|1<<args['bit']])
            elif action == 'hide_decoration':actor.put(self.decor if args['object_id']==48 else self.ambient,10,0)
            elif action == 'grant_story_item':
                if self.item_count!=args['required_count']:raise ValueError('Invalid story item count')
                self.item_count=args['result_count']
            elif action == 'player_palette':actor.put(self.player,0x12,args['selector'])
            elif action == 'player_mode':actor.put(self.player,0x16,(actor.word(self.player,0x16)&0xff00)|args['mode'])
            elif action == 'player_aux_input':self.player[0x49]=args['value']
            elif action == 'player_pickup_y':actor.put(self.player,2,args['y_raw'])
            elif action == 'actor_animation':
                raw,profile=(self.spark,self.spark_profile) if s.owner=='spark' else (self.player,self.profile)
                interaction_animation.select(raw,profile,args['index']);s.wait=4
            elif action == 'save_actor_position':self.temp[args['slot']]=[actor.word(self.player,i) for i in (0,2,4)]
            elif action == 'offset_saved_position':self.temp[args['slot']]=[(v+d)&65535 for v,d in zip(self.temp[args['slot']],args['delta_raw'])]
            elif action == 'spawn_story_spark':
                self.spark,self.spark_profile=interaction_animation.spawn_spark(self.high,self.low,self.profile.base,self.temp[args['slot']][:2])
                self.effect=None;self.effect_xy=None
            elif action == 'remove_story_spark':actor.put(self.spark,6,0)
            elif action == 'attach_actor':self.attach(self.starts[args['program']],'actor' if args['actor_id']==0 else 'spark')
            elif action == 'wait_actor':
                s.target=args['actor_id'];raw=self.player if s.target==0 else self.spark
                if actor.word(raw,6)&4:s.wait=9
            elif action == 'lock_control':
                self.disabled = 255
                actor.put(self.player, 0x2c, 0)
                actor.put(self.player, 0x36, actor.word(self.player, 0x26))
            elif action == 'unlock_control': self.disabled = 0
            elif action == 'attach_player': self.attach(self.starts[args['program']], 'actor')
            elif action == 'wait_player':
                if actor.word(self.player, 6) & 4: s.wait = 9
            elif action == 'expression':
                self.spark=None
                self.effect = effect.Effect(counter=args['hold_updates'])
                self.effect_xy = tuple(actor.word(self.player, n) for n in (0, 2))
                s.wait = 23
            elif action == 'player_pose':
                self.player = actor.pose(self.player, args['heading'], self.profile)
                s.wait, s.arg = 0, 1
            elif action == 'camera_target':
                self.target = (args['x_raw'], args['y_raw'])
                self.speed, self.fixed = args['speed_raw'], True
            elif action == 'camera_follow_player': self.fixed = False
            elif action == 'wait_camera': s.wait, s.arg = 11, 2 if args['restore_speed'] else 0
            elif action == 'load_audio':
                self.resource='IVENT176.AIF' if args['id']=='cirrus_pickup_audio' else 'IVENT041.AIF'
                self.requests.append({'type': 'load_original_resource', 'id': self.resource})
            elif action == 'wait_audio_loaded': s.wait, s.arg = 15, 0
            elif action == 'play_audio': self.requests.append({'type': 'play_original_resource', 'id': self.resource})
            elif action == 'wait_audio_started': s.wait = 19
            elif action == 'attach_cirrus': self.attach(self.starts[args['program']], 'decoration')
            elif action == 'cirrus_animation':
                for offset, value in ((0x24, args['index']), (0x1e, 0), (0x1c, 0), (0x20, 8), (0x22, 46)):
                    actor.put(self.decor, offset, value)
                actor.put(self.decor, 0x14, actor.word(self.decor, 0x14) & 0xfffe)
                actor.put(self.decor, 10, actor.word(self.decor, 10) & 0xfeff)
                struct.pack_into('>I', self.decor, 0x30, self.decor_profile.image_pointers[46])
                s.wait = 16
            elif action == 'wait_updates': s.wait, s.arg = 0, args['count']
            elif action == 'source_text_layout': self.requests.append({'type': 'source_text_layout', 'y': args['y']})
            elif action == 'dialogue':
                self.requests.append({'type': 'dialogue', 'id': args['id']})
                s.wait = 8
            elif action == 'player_speed': actor.put(self.player, 0x24, args['index'])
            elif action == 'player_move_axis':
                axis, target = args['axis'], args['target_raw']
                if actor.word(self.player, axis * 2) & 0xfff0 != target & 0xfff0:
                    actor.put(self.player, 0x2c, 0)
                    actor.put(self.player, 0x30, 0)
                    s.wait, s.target = axis + 1, target
                    if self.wait(s, signals): s.wait = None
                    return
            else:
                raise ValueError('Unknown PC action: ' + action)
            if s.wait is not None:
                return
        raise ValueError('PC instruction budget exhausted')
