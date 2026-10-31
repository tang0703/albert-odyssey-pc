"""Diagnostic ninth-stage model. No runtime acceptance is implied.

Extends the continuous original-room/transfer model without relaxing the old
entry or eight contracts. Event commands come from pinned bounded programs;
later source positions, script cursors and flags are never injected.
"""
from event_sequence_reference import Slot
from event_actor_reference import word, put, decode, free_step
import event_actor_reference as actor
import interaction_animation
import landing_event_actor
import probe_movement
from transition_reference import Model as Transition
from transition_objects import Resources, step_object
from landing_event_source import programs


def camera_step(state, target, speed, fixed, limits):
    result = dict(state)
    result.update(display_x=state['x'], display_y=state['y'], dx=0, dy=0)
    signed = probe_movement.signed16
    for index, axis in enumerate(('x', 'y')):
        center = 0 if fixed else (0xa80, 0x780)[index]
        margin = 0 if fixed else 0x200
        upper, lower = (signed(state[axis]+center+d) for d in (margin, -margin))
        if target[index] > upper:
            delta = min(speed, signed(target[index]-upper))
            proposed = signed(state[axis]+delta)
            if proposed > limits[index+2]: proposed, delta = limits[index+2], 0
            result[axis], result['d'+axis] = proposed, delta
        if target[index] < lower:
            delta = min(speed, signed(lower-target[index]))
            proposed = signed(result[axis]-delta)
            if proposed < limits[index]: proposed, delta = limits[index], 0
            result[axis], result['d'+axis] = proposed, -delta
    return result


class Model(Transition):
    def reset(self):
        super().reset()
        self.event_programs = programs()
        self.instructions = {r['offset']: r for rows in self.event_programs.values() for r in rows}
        self.event_slots = {}
        self.event_runs = 0
        self.event_completed = False
        self.event_commands = []
        self.ambient_loops = 0
        self.event_signals = {'text_active': False}
        self.left_contact = next(b for b in self.boundaries if b.get('script_offset') == 0x2c17)

    def scene_resources_ready(self, generation, request_id):
        if not super().scene_resources_ready(generation, request_id): return False
        self.arrival_profile = landing_event_actor.Profile(Resources(self.room.story+bytes(127)))
        return True

    def step(self, pad, signals=None, pressed=0, *, source_replay=False):
        self.event_signals = signals or {'text_active': False}
        self.event_commands = []
        # Keep all previous boundary rules except the single approved research
        # target. This diagnostic model is not an expanded runtime allow-list.
        old = self.boundaries
        self.boundaries = [b for b in old if b.get('script_offset') != 0x2c17]
        try: return super().step(pad, signals, pressed, source_replay=source_replay)
        finally: self.boundaries = old

    def raw_for(self, owner):
        if owner == 'player': return self.player, self.room.profile
        if owner == 'laia': return self.arrival_actor, self.arrival_profile
        raise ValueError('Event command requires an actor owner')

    def set_actor(self, owner, raw):
        if owner == 'player': self.room.player = raw
        elif owner == 'laia': self.arrival_actor = raw
        else: raise ValueError('Unknown actor owner')

    def attach_event_actor(self, name, actor_id):
        owner = 'player' if actor_id == 0 else 'laia'
        if any(s.active and s.owner == owner for s in self.event_slots.values()):
            raise ValueError('Actor already has active event')
        slot = next(i for i in range(1, 32) if i not in self.event_slots or not self.event_slots[i].active)
        self.event_slots[slot] = Slot(self.event_programs[name][0]['offset'], owner)
        raw, _ = self.raw_for(owner)
        put(raw, 6, word(raw, 6)|4)
        put(raw, 0x38, slot)

    def wait_event(self, s):
        if s.wait == 0:
            old = s.arg
            s.arg = (old-1)&65535
            return old == 0
        if s.wait in (1, 2):
            raw, profile = self.raw_for(s.owner)
            fn = landing_event_actor.forced_step if s.owner == 'laia' else actor.forced_step
            raw, done = fn(raw, s.wait-1, s.target, profile)
            self.set_actor(s.owner, raw)
            return done
        if s.wait == 4:
            return interaction_animation.wait_step(*self.raw_for(s.owner))
        if s.wait == 8: return not self.event_signals['text_active']
        if s.wait == 9: return not word(self.arrival_actor, 6)&4
        if s.wait == 11:
            done = not self.cameras[0]['dx'] and not self.cameras[0]['dy']
            if done: self.room.fixed = False; self.room.speed = 128
            return done
        raise ValueError('Unknown landing-event wait')

    def dispatch_event(self, slot):
        s = self.event_slots.get(slot)
        if s is None or not s.active: return
        if s.wait is not None:
            if self.wait_event(s): s.wait = None
            return
        for _ in range(32):
            instruction = self.instructions.get(s.pc)
            if instruction is None: raise ValueError('Unknown landing-event instruction')
            self.event_commands.append((slot, s.pc, instruction['opcode']))
            s.pc += instruction['span']
            action, args = instruction['action'], instruction['args']
            if action == 'end':
                s.active = False
                if s.owner != 'root':
                    raw, _ = self.raw_for(s.owner)
                    put(raw, 6, word(raw, 6)&0xfffb)
                    if s.owner == 'laia': put(raw, 0x2a, 2)
                return
            if action == 'branch_story':
                if self.room.story not in (b'\x07', b'\x0f'): raise ValueError('Unverified event story state')
                s.pc = args['if_set'] if self.room.story[0]&8 else args['if_clear']
            elif action == 'set_story_bit':
                if self.room.story != b'\x07': raise ValueError('Event already completed')
                self.room.story = b'\x0f'
            elif action == 'lock_control':
                self.room.disabled = 255
                self.fade = 3  # 060A14DE writes normal event-loop phase.
                put(self.player, 0x2c, 0); put(self.player, 0x36, word(self.player, 0x26))
                self.event_runs += 1
            elif action == 'unlock_control':
                self.room.disabled = 0; self.event_completed = True
                self.requests.append({'type': 'landing_event_completed'})
            elif action == 'attach_actor': self.attach_event_actor(args['program'], args['actor_id'])
            elif action == 'wait_actor':
                if word(self.arrival_actor, 6)&4: s.wait = 9
            elif action == 'camera_target':
                self.room.fixed = True; self.room.speed = args['speed_raw']
                self.room.target = (args['x_raw'], args['y_raw'])
            elif action == 'camera_follow_player': self.room.fixed = False
            elif action == 'wait_camera': s.wait = 11; s.arg = 2
            elif action == 'dialogue':
                self.requests.append({'type': 'dialogue', 'id': args['id']}); s.wait = 8
            elif action == 'wait_updates': s.wait = 0; s.arg = args['count']
            elif action == 'actor_pose':
                raw, profile = self.raw_for(s.owner)
                fn = landing_event_actor.pose if s.owner == 'laia' else actor.pose
                self.set_actor(s.owner, fn(raw, args['heading'], profile))
                s.wait = 0; s.arg = 1
            elif action == 'actor_speed': put(self.raw_for(s.owner)[0], 0x24, args['index'])
            elif action == 'actor_move_axis':
                raw, _ = self.raw_for(s.owner)
                axis, target = args['axis'], args['target_raw']
                if word(raw, axis*2)&0xfff0 != target&0xfff0:
                    put(raw, 0x2c, 0); put(raw, 0x30, 0)
                    s.wait = axis+1; s.target = target
                    if self.wait_event(s): s.wait = None
                    return
            elif action == 'actor_animation':
                interaction_animation.select(*self.raw_for(s.owner), args['index']); s.wait = 4
            elif action == 'jump': s.pc = args['target']; self.ambient_loops += 1
            else: raise ValueError('Unknown landing-event action')
            if s.wait is not None: return
        raise ValueError('Landing-event instruction budget exhausted')

    def _landing_update(self, pad):
        self.room.player = bytearray(probe_movement.replay_input_gate(self.player, pad, self.fade, self.room.disabled)[0])
        x, y = (word(self.player, i) for i in (0, 2))
        bounds = self.left_contact['bounds_raw']
        if self.stage == 'landing' and bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]:
            if 0 not in self.event_slots or not self.event_slots[0].active:
                self.event_slots[0] = Slot(0x2c17, 'root')
        self.dispatch_event(0)
        if word(self.player, 6)&4: self.dispatch_event(word(self.player, 0x38))
        else:
            self.room.player, diag = free_step(self.player, self.room.profile, self.room.flags, self.room.disabled)
            self.landing_queries.update(d['index'] for d in diag['lookups'])
        if word(self.arrival_actor, 6)&4: self.dispatch_event(word(self.arrival_actor, 0x38))
        elif word(self.arrival_actor, 0x2a) == 1: decode(self.arrival_actor, self.arrival_profile, True)
        xy = self.room.target if self.room.fixed else tuple(probe_movement.signed16(word(self.player, i)) for i in (0, 2))
        self.room.cameras = [camera_step(c, xy, self.room.speed, self.room.fixed, self.camera_rules.limits) for c in self.cameras]
        self.objects = [step_object(o, p) for o, p in zip(self.objects, self.programs)]
        self.landing_updates += 1
