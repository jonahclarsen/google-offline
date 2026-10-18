"""Remap broker identities in resource string pools without changing indices."""
import struct
from patch_manifest import pool_strings, u16, u32


def remap_value(value, aliases):
    if value in aliases:
        return aliases[value]
    for old, new in aliases.items():
        if value.startswith(old + "/"):
            return new + value[len(old):]
        prefix = "content://" + old
        if value.startswith(prefix) and (len(value) == len(prefix) or value[len(prefix)] in "/.?"):
            return "content://" + new + value[len(prefix):]
        if value in (old + ".chimera", old + ".phenotype", old + ".gservices"):
            return new + value[len(old):]
    return value


def remap_resources(data, aliases):
    result = bytearray(data)
    offset, changed = u16(data, 2), 0
    while offset < len(data):
        kind, header, size = struct.unpack_from("<HHI", data, offset)
        if size < header or offset + size > len(data):
            raise ValueError("Malformed resource chunk")
        if kind == 1:
            pool = data[offset:offset + size]
            utf8, start = bool(u32(pool, 16) & 0x100), u32(pool, 20)
            for index, before in enumerate(pool_strings(pool)):
                after = remap_value(before, aliases)
                if after == before:
                    continue
                pos = start + u32(pool, header + index * 4)
                if utf8:
                    pos += 2 if pool[pos] & 0x80 else 1
                    pos += 2 if pool[pos] & 0x80 else 1
                else:
                    pos += 4 if u16(pool, pos) & 0x8000 else 2
                encoding = "utf-8" if utf8 else "utf-16le"
                old, new = before.encode(encoding), after.encode(encoding)
                if len(old) != len(new) or pool[pos:pos + len(old)] != old:
                    raise ValueError("Resource replacement must preserve encoded length")
                result[offset + pos:offset + pos + len(old)] = new
                struct.pack_into("<I", result, offset + 16, u32(pool, 16) & ~1)
                changed += 1
        offset += size
    return bytes(result), changed
