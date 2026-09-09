import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import decode_map_graphics as g


def stream(size,payload):
    data=b'\x05'+struct.pack('>I',size)+payload
    return data + b'\x01'*((-len(data))%4)


class GraphicsTests(unittest.TestCase):
    def test_literals_and_overlap_low_length_nibble(self):
        self.assertEqual(g.decode_mode5(stream(3,b'\x07ABC'))[0],b'ABC')
        # low nibble F is length 18, not the high bits of distance.
        self.assertEqual(g.decode_mode5(stream(19,b'\x01A\x01\x0f'))[0],b'A'*19)

    def test_high_distance_nibble(self):
        literals=b''.join(b'\xff'+bytes(range(i,i+8)) for i in range(0,256,8))
        output,_=g.decode_mode5(stream(259,literals+b'\x00\x00\x10'))
        self.assertEqual(output,bytes(range(256))+b'\0\1\2')

    def test_rejects_invalid_references_sizes_truncation_and_trailing_data(self):
        for data in [b'',stream(0,b''),stream(0x80001,b''),stream(3,b'\0\0\0'),
                     stream(2,b'\x01A\x01\x0f'),stream(10,b'\xffAB'),
                     stream(1,b'\x01A')+b'\0'*4]:
            with self.subTest(data=data[:12]),self.assertRaises(ValueError):
                g.decode_mode5(data)

    def test_container_rejects_changed_header_and_trailer(self):
        raw=(g.WORKSPACE/'work/extract/MAP001.TWN').read_bytes()
        blocks=g.map001_blocks(raw)
        self.assertEqual([b['tag'] for b in blocks],[1,2,3,4,5,6])
        self.assertEqual(blocks[0]['payload_offset'],0xf238)
        for pos in [0xf230,len(raw)-1]:
            changed=bytearray(raw);changed[pos]^=1
            with self.assertRaises(ValueError):g.map001_blocks(changed)

    def test_full_source_vram_match(self):
        report=g.run()
        self.assertEqual(report['transfer_evidence']['bytes'],262144)
        self.assertTrue(report['transfer_evidence']['exact_match'])
        self.assertEqual(report['transfer_evidence']['sha256'],
                         '1cd20cdec5fd885aae0f79bb583154c6b4c7165ac598455add8b686b77dfec7b')
        self.assertEqual(report['decoded_blocks'][0]['alignment_tail_hex'],'010101')
        self.assertFalse(report['transfer_evidence']['runtime_upload_call_verified'])


if __name__=='__main__':unittest.main()
