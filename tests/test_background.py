import struct
import sys
import unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import decode_background as b


class BackgroundTests(unittest.TestCase):
    def fixture(self):
        vram, cram = bytearray(0x80000), bytearray(4096)
        for i, color in enumerate([0x001f, 0x03e0, 0x7c00, 0x7fff], 1):
            vram[4096+(i-1)*64:4096+i*64] = bytes([i])*64
            struct.pack_into(">H", cram, i*2, color)
        return vram, cram, {"cram_base": 0, "transparent_zero": True}

    def test_four_cells_palette_and_flips(self):
        v, c, p = self.fixture()
        image, address = b.decode_tile(v,c,128,p)
        self.assertEqual(address,4096)
        self.assertEqual([image.getpixel(xy) for xy in [(0,0),(8,0),(0,8),(8,8)]],
                         [(255,0,0,255),(0,255,0,255),(0,0,255,255),(255,255,255,255)])
        flipped,_ = b.decode_tile(v,c,128 | (3<<30),p)
        self.assertEqual(flipped.getpixel((0,0)),image.getpixel((15,15)))
        v[4096]=0
        self.assertEqual(b.decode_tile(v,c,128,p)[0].getpixel((0,0)),(0,0,0,0))

    def test_pattern_page_stride_and_provenance(self):
        v,c,p = self.fixture()
        struct.pack_into(">I",v,4*33,128)
        page, entries = b.decode_page(v,c,0,p)
        self.assertEqual(page.getpixel((16,16)),(255,0,0,255))
        self.assertEqual(entries[33]["pattern_offset"],132)
        self.assertEqual(entries[33]["tile_offset"],4096)
        with self.assertRaises(ValueError):
            b.decode_page(v,c,len(v)-1,p)
        with self.assertRaises(ValueError):
            b.decode_tile(v,c,0x7fff,p)

    def test_viewport_wraps_planes_in_both_directions(self):
        colors=["red","green","blue","white"]
        pages=[Image.new("RGBA",(512,512),color) for color in colors]
        view=b.viewport(pages,1023,1023)
        self.assertEqual(view.getpixel((0,0)),(255,255,255,255))
        self.assertEqual(view.getpixel((1,0)),(0,0,255,255))
        self.assertEqual(view.getpixel((0,1)),(0,128,0,255))
        self.assertEqual(view.getpixel((1,1)),(255,0,0,255))

    def test_real_parameters_and_unsupported_settings(self):
        lock=b.read_json(b.PROJECT/'savestate-lock.json')
        r=b.extract(b.verify_source(b.WORKSPACE,lock['path'],lock['sha256']),lock)["regs2"]
        self.assertEqual(b.parameters(r,1)["plane_offsets"],[8192]*4)
        for key,value in [("CHCTLA",0),("PNCNA",0x8000),("PLSZ",1),("SCRCTL",1),
                          ("ZMXIN0",2),("SCXDN0",128),("TVMD",0x8001)]:
            changed=dict(r);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                b.parameters(changed,0)

    def test_snapshot_pages_and_negative_raw_source_matches(self):
        report=b.run()
        self.assertEqual([r["unique_tiles"] for r in report["layers"]],[164,176])
        self.assertEqual([r["exact_source_tiles"] for r in report["layers"]],[0,0])
        self.assertEqual([r["decoded_source_tiles"] for r in report["layers"]],[164,176])
        self.assertEqual(len(report["layers"][0]["entries"]["0"]),1024)


if __name__ == "__main__":
    unittest.main()
