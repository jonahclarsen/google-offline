"""Rebind Gboard's app ID so the experimental APK can coexist with stock Gboard."""
import hashlib
import struct
import zlib
import zipfile
from patch_manifest import pool_strings, u16, u32

ORIGINAL_PACKAGE = "com.google.android.inputmethod.latin"
CLONE_PACKAGE = "com.google.android.inputmethod.local"


def replace_package(data):
    if len(ORIGINAL_PACKAGE) != len(CLONE_PACKAGE):
        raise ValueError("Package replacements must preserve encoded lengths")
    for encoding in ("utf-8", "utf-16le"):
        data = data.replace(ORIGINAL_PACKAGE.encode(encoding), CLONE_PACKAGE.encode(encoding))
    return data


def dex_strings(data):
    count, offset = struct.unpack_from("<II", data, 56)
    result = []
    for index in range(count):
        pos = u32(data, offset + index * 4)
        for _ in range(5):
            value = data[pos]
            pos += 1
            if value < 128:
                break
        result.append(data[pos:data.index(b"\0", pos)])
    return result


# This pinned APK's SignatureUtils has a production Google digest and two
# development digests. Retain the production digest; replace one development
# trust slot with the actual clone signer's digest. Verification still compares
# certificate hashes rather than accepting arbitrary signatures.
DEVELOPMENT_CERT = bytes.fromhex("103938ee4537e59e8ee792f654504fb8346fc6b346d0bbc4415fc339fcfc8ec1")
CERT_PAYLOAD = struct.pack("<HHI", 0x0300, 1, 32) + DEVELOPMENT_CERT


def trust_clone_signer(data, digest):
    if len(digest) != 32:
        raise ValueError("Expected SHA-256 signing certificate digest")
    count = data.count(CERT_PAYLOAD)
    if count > 1 or data.count(DEVELOPMENT_CERT) != count:
        raise ValueError("Unexpected certificate payload layout")
    return data.replace(CERT_PAYLOAD, CERT_PAYLOAD[:8] + digest), count


def rewrite_dex(data):
    old = dex_strings(data)
    changed = replace_package(data)
    new = dex_strings(changed)
    for index, (before, after) in enumerate(zip(old, new)):
        if before != after:
            # IDs are sorted in DEX. A generic package rename can silently
            # break this ordering; the selected namespace keeps this family
            # between inputmethod.korean and inputmethod.pinyin.
            if (index and new[index - 1] >= after) or (index + 1 < len(new) and after >= new[index + 1]):
                raise ValueError("Package rename would break DEX string ordering")
    changed = changed[:12] + hashlib.sha1(changed[32:]).digest() + changed[32:]
    return changed[:8] + struct.pack("<I", zlib.adler32(changed[12:]) & 0xffffffff) + changed[12:]


def label_manifest(data, label="Gboard Offline"):
    chunks, offset, strings, new_index = [], u16(data, 2), None, None
    while offset < len(data):
        kind, header, size = struct.unpack_from("<HHI", data, offset)
        chunk = bytearray(data[offset:offset + size])
        offset += size
        if kind == 1:
            strings = pool_strings(chunk)
            count, styles, flags, start = struct.unpack_from("<IIII", chunk, 8)
            if styles:
                raise ValueError("Styled manifest string pool not supported")
            new_index = count
            utf8 = bool(flags & 0x100)
            encoded = label.encode("utf-8" if utf8 else "utf-16le")
            if utf8:
                addition = bytes([len(label), len(encoded)]) + encoded + b"\0"
            else:
                addition = struct.pack("<H", len(label)) + encoded + b"\0\0"
            old_data = bytes(chunk[start:])
            offsets = bytes(chunk[header:header + count * 4]) + struct.pack("<I", len(old_data))
            content = old_data + addition
            content += b"\0" * (-len(content) % 4)
            chunk = chunk[:header] + offsets + content
            struct.pack_into("<I", chunk, 4, len(chunk))
            struct.pack_into("<I", chunk, 8, count + 1)
            struct.pack_into("<I", chunk, 16, flags & ~1)
            struct.pack_into("<I", chunk, 20, header + (count + 1) * 4)
        elif kind == 0x102 and strings is not None:
            tag = strings[u32(chunk, header + 4)]
            if tag in ("application", "service"):
                attr_start, attr_size, count = struct.unpack_from("<HHH", chunk, header + 8)
                for index in range(count):
                    pos = header + attr_start + index * attr_size
                    namespace, name = struct.unpack_from("<II", chunk, pos)
                    if namespace != 0xffffffff and strings[namespace] == "http://schemas.android.com/apk/res/android" and strings[name] == "label":
                        struct.pack_into("<I", chunk, pos + 8, new_index)
                        chunk[pos + 15] = 3
                        struct.pack_into("<I", chunk, pos + 16, new_index)
        chunks.append(chunk)
    result = bytearray(data[:u16(data, 2)] + b"".join(chunks))
    struct.pack_into("<I", result, 4, len(result))
    return bytes(result)


def clone(source, destination, signing_digest=None):
    changed, trust_updates = [], 0
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(destination, "w") as dst:
        for info in src.infolist():
            name = info.filename
            if name.upper().startswith("META-INF/") and (name.upper().endswith((".SF", ".RSA", ".DSA", ".EC")) or name.upper() == "META-INF/MANIFEST.MF"):
                continue
            if name == "stamp-cert-sha256":
                continue
            before = src.read(name)
            after = before
            if name.endswith(".dex"):
                if signing_digest is not None:
                    before_trust, count = trust_clone_signer(before, signing_digest)
                    trust_updates += count
                else:
                    before_trust = before
                after = rewrite_dex(before_trust)
            elif name == "AndroidManifest.xml":
                after = label_manifest(replace_package(before))
            elif name == "resources.arsc":
                after = replace_package(before)
            if before != after:
                changed.append(name)
            dst.writestr(info, after)
    if signing_digest is not None and trust_updates != 1:
        raise ValueError("Expected exactly one clone certificate trust update")
    return changed
