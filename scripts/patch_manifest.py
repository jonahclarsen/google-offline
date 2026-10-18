#!/usr/bin/env python3
"""Remove INTERNET from binary AndroidManifest.xml without rebuilding resources/dex."""
import argparse
import struct
import zipfile
from pathlib import Path

INTERNET = "android.permission.INTERNET"


def u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def pool_strings(chunk):
    header_size = u16(chunk, 2)
    count, _, flags, start = struct.unpack_from("<IIII", chunk, 8)
    utf8 = bool(flags & 0x100)

    def length(pos):
        if utf8:
            n = chunk[pos]
            return (((n & 0x7f) << 8) | chunk[pos + 1], pos + 2) if n & 0x80 else (n, pos + 1)
        n = u16(chunk, pos)
        return (((n & 0x7fff) << 16) | u16(chunk, pos + 2), pos + 4) if n & 0x8000 else (n, pos + 2)

    strings = []
    for i in range(count):
        pos = start + u32(chunk, header_size + 4 * i)
        n, pos = length(pos)
        if utf8:
            n, pos = length(pos)
        strings.append(chunk[pos:pos + n * (1 if utf8 else 2)].decode("utf-8" if utf8 else "utf-16le", errors="surrogatepass"))
    return strings


def patch(data):
    if u16(data, 0) != 3 or u32(data, 4) != len(data):
        raise ValueError("Not a complete binary Android XML document")
    offset = u16(data, 2)
    chunks, strings, depth, removed = [], None, 0, 0
    while offset < len(data):
        kind, header, size = struct.unpack_from("<HHI", data, offset)
        if size < header or size < 8 or offset + size > len(data):
            raise ValueError("Invalid binary XML chunk")
        chunk = data[offset:offset + size]
        offset += size
        if kind == 1:
            strings = pool_strings(chunk)
        if depth:
            if kind == 0x102:
                depth += 1
            elif kind == 0x103:
                depth -= 1
            continue
        if kind == 0x102:
            if strings is None:
                raise ValueError("Missing string pool")
            tag = strings[u32(chunk, header + 4)]
            attribute_start, attribute_size, count = struct.unpack_from("<HHH", chunk, header + 8)
            if tag in ("uses-permission", "uses-permission-sdk-23"):
                for i in range(count):
                    pos = header + attribute_start + i * attribute_size
                    namespace, name, raw = struct.unpack_from("<III", chunk, pos)
                    value = raw if raw != 0xffffffff else (u32(chunk, pos + 16) if chunk[pos + 15] == 3 else None)
                    if namespace != 0xffffffff and strings[namespace] == "http://schemas.android.com/apk/res/android" and strings[name] == "name" and value is not None and strings[value] == INTERNET:
                        depth, removed = 1, removed + 1
                        break
            if depth:
                continue
        chunks.append(chunk)
    if depth or removed == 0:
        raise ValueError("No complete INTERNET permission element removed")
    result = bytearray(data[:u16(data, 2)] + b"".join(chunks))
    struct.pack_into("<I", result, 4, len(result))
    return bytes(result), removed


def patch_apk(source, destination):
    with zipfile.ZipFile(source) as src:
        names = src.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        manifest, removed = patch(src.read("AndroidManifest.xml"))
        with zipfile.ZipFile(destination, "w") as dst:
            for info in src.infolist():
                upper = info.filename.upper()
                if upper.startswith("META-INF/") and (upper.endswith((".SF", ".RSA", ".DSA", ".EC")) or upper == "META-INF/MANIFEST.MF"):
                    continue
                dst.writestr(info, manifest if info.filename == "AndroidManifest.xml" else src.read(info.filename))
    return removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"Removed {patch_apk(args.source, args.destination)} INTERNET declaration(s)")
