"""PC instruction scheduler. Source bytes are never executed by this adapter.

The independently source-checked actor/camera components are shared with the
reference model; this dispatch path consumes the bounded conversion contract.
"""
import struct
from event_sequence_reference import Model
import event_actor_reference as actor
import event_effect_reference as effect


class PcModel(Model):
    def __init__(self, high, low, source, twn, contract):
        super().__init__(high, low, source, twn)
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
                return
            if action == 'require_story_branch':
                if self.story[0] != args['byte'] or self.story[0] & args['mask'] != args['expected']:
                    raise ValueError('Unsupported story branch')
                s.pc = self.starts[args['next_program']]
            elif action == 'lock_control':
                self.disabled = 255
                actor.put(self.player, 0x2c, 0)
                actor.put(self.player, 0x36, actor.word(self.player, 0x26))
            elif action == 'unlock_control': self.disabled = 0
            elif action == 'attach_player': self.attach(self.starts[args['program']], 'actor')
            elif action == 'wait_player':
                if actor.word(self.player, 6) & 4: s.wait = 9
            elif action == 'expression':
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
            elif action == 'load_audio': self.requests.append({'type': 'load_original_resource', 'id': 'IVENT041.AIF'})
            elif action == 'wait_audio_loaded': s.wait, s.arg = 15, 0
            elif action == 'play_audio': self.requests.append({'type': 'play_original_resource', 'id': 'IVENT041.AIF'})
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
