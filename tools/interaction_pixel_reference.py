"""Interaction pixel comparison with independently predicted player texture IDs."""
from event_pixel_reference import Pixels as BasePixels
from character_draw_order import _matches


class Pixels(BasePixels):
    def add_draw(self, current, commands, end):
        for piece in current['ordered_pieces']:
            if 'expected_texture_sha256' not in piece:
                continue
            match=[row for row in commands if _matches(piece,bytes.fromhex(row['command_hex']))]
            if len(match)!=1 or match[0]['texture']['sha256']!=piece['expected_texture_sha256']:
                raise ValueError('Source player texture upload differs from the continuously predicted pose')
        return super().add_draw(current,commands,end)
