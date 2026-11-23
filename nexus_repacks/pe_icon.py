"""Extract an ICO from PE resources by parsing bytes, without loading the PE."""
import struct
from pathlib import Path


def extract_icon(path: Path):
    if path.stat().st_size > 64 * 1024 * 1024:
        return None
    b = path.read_bytes()
    if b[:2] != b'MZ':
        return None
    def u16(o):
        return struct.unpack_from('<H', b, o)[0]
    def u32(o):
        return struct.unpack_from('<I', b, o)[0]
    try:
        pe = u32(60)
        if b[pe:pe + 4] != b'PE\0\0':
            return None
        opt = pe + 24
        dd = opt + (112 if u16(opt) == 0x20b else 96)
        sections = []
        for i in range(min(u16(pe + 6), 96)):
            o = opt + u16(pe + 20) + i * 40
            vs, va, size, raw = struct.unpack_from('<IIII', b, o + 8)
            sections.append((va, max(vs, size), raw))
        def rva(v):
            for va, size, raw in sections:
                if va <= v < va + size:
                    return raw + v - va
            raise ValueError('RVA hors section')
        base = rva(u32(dd + 16))
        def entries(offset):
            count = u16(base + offset + 12) + u16(base + offset + 14)
            if count > 4096:
                raise ValueError('Trop de ressources')
            return [struct.unpack_from('<II', b, base + offset + 16 + i * 8) for i in range(count)]
        def blobs(type_id):
            top = next((v for k, v in entries(0) if k == type_id), None)
            result = {}
            if top is None:
                return result
            for key, sub in entries(top & 0x7fffffff):
                langs = entries(sub & 0x7fffffff)
                if not langs:
                    continue
                offset = base + (langs[0][1] & 0x7fffffff)
                va, size = struct.unpack_from('<II', b, offset)
                raw = rva(va)
                if size <= 4 * 1024 * 1024 and raw + size <= len(b):
                    result[key] = b[raw:raw + size]
            return result
        icons, groups = blobs(3), blobs(14)
        if not groups:
            return None
        group = next(iter(groups.values()))
        count = struct.unpack_from('<H', group, 4)[0]
        if not 0 < count <= 128:
            return None
        output = bytearray(struct.pack('<HHH', 0, 1, count))
        payload = bytearray()
        for i in range(count):
            row = struct.unpack_from('<BBBBHHIH', group, 6 + i * 14)
            data = icons[row[-1]]
            output.extend(struct.pack('<BBBBHHII', *row[:6], len(data), 6 + count * 16 + len(payload)))
            payload.extend(data)
        return bytes(output + payload)
    except (struct.error, StopIteration, KeyError, ValueError, IndexError):
        return None
