#!/usr/bin/env python3
"""Generate an original RGB fixture using only Python's standard library."""
import struct
import zlib
from pathlib import Path

WIDTH, HEIGHT = 800, 480
COLORS = [(0, 0, 0), (255, 255, 255), (255, 227, 0), (241, 20, 0), (0, 105, 246), (20, 166, 93)]


def chunk(kind, data):
    return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)


rows = bytearray()
for y in range(HEIGHT):
    rows.append(0)
    for x in range(WIDTH):
        rgb = (x * 255 // (WIDTH - 1), y * 255 // (HEIGHT - 1), (x + y) * 255 // (WIDTH + HEIGHT - 2))
        if y >= 350:
            rgb = COLORS[min(5, x * 6 // WIDTH)]
        if (x - 590) ** 2 + (y - 115) ** 2 < 62 ** 2:
            rgb = (255, 227, 0)
        if 50 < x < 350 and 55 < y < 300 and y > 300 - (x - 50) * .8:
            rgb = (20, 166, 93)
        if x < 8 or y < 8:
            rgb = (0, 105, 246)
        elif x >= WIDTH - 8 or y >= HEIGHT - 8:
            rgb = (241, 20, 0)
        rows.extend(rgb)
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', WIDTH, HEIGHT, 8, 2, 0, 0, 0))
png += chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b'')
target = Path(__file__).resolve().parents[1] / 'mobile/test/fixtures/photo.png'
target.write_bytes(png)
print('Original synthetic test image generated.')
