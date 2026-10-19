"""Minimal 7z writer for the HD texture archive tests.

The test hosts have no 7z tool, so this writes the format directly (7z
format specification, 7zFormat.txt of the LZMA SDK): signature header, packed
streams, then a plain or LZMA-encoded header. Each folder has exactly one
coder (Copy, LZMA, LZMA2 or Deflate) and may hold several files (solid
block). It is only used to build test inputs; production reads 7z through the
vendored LZMA SDK database parser.
"""
import lzma
import struct
import zlib

COPY, LZMA, LZMA2, DEFLATE = b'\x00', b'\x03\x01\x01', b'\x21', b'\x04\x01\x08'


def number(value):
    for extra in range(8):
        if value < 1 << (8 * extra + 7 - extra):
            first = (0xff << (8 - extra)) & 0xff | (value >> (8 * extra))
            return bytes([first]) + value.to_bytes(8, 'little')[:extra]
    return b'\xff' + value.to_bytes(8, 'little')


def lzma2_prop(dictionary):
    for prop in range(40):
        if (2 | (prop & 1)) << (prop // 2 + 11) >= dictionary:
            return prop
    return 40


def compress(method, data, dictionary=1 << 16):
    """Returns (packed bytes, coder properties)."""
    if method == COPY:
        return data, b''
    if method == DEFLATE:
        engine = zlib.compressobj(9, zlib.DEFLATED, -15)
        return engine.compress(data) + engine.flush(), b''
    if method == LZMA:
        packed = lzma.compress(data, format=lzma.FORMAT_RAW, filters=[
            {'id': lzma.FILTER_LZMA1, 'dict_size': dictionary, 'lc': 3, 'lp': 0, 'pb': 2}])
        props = bytes([(2 * 5 + 0) * 9 + 3]) + struct.pack('<I', dictionary)
        return packed, props
    if method == LZMA2:
        packed = lzma.compress(data, format=lzma.FORMAT_RAW, filters=[
            {'id': lzma.FILTER_LZMA2, 'dict_size': dictionary}])
        return packed, bytes([lzma2_prop(dictionary)])
    raise ValueError(method)


def coder(method, props):
    flags = len(method) | (0x20 if props else 0)
    out = bytes([flags]) + method
    if props:
        out += number(len(props)) + props
    return out


def streams_info(pack_position, packs, folders, substreams):
    """packs: packed sizes; folders: [(method, props, unpack size, crc or None)];
    substreams: per folder, list of (size, crc) for its files (None = no SubStreamsInfo)."""
    out = b'\x06' + number(pack_position) + number(len(packs)) + b'\x09'
    for size in packs:
        out += number(size)
    out += b'\x00'
    out += b'\x07\x0b' + number(len(folders)) + b'\x00'
    for method, props, _, _ in folders:
        out += number(1) + coder(method, props)
    out += b'\x0c'
    for _, _, size, _ in folders:
        out += number(size)
    crcs = [crc for *_, crc in folders]
    if all(crc is not None for crc in crcs) and crcs:
        out += b'\x0a\x01' + b''.join(struct.pack('<I', crc) for crc in crcs)
    out += b'\x00'
    if substreams is not None:
        out += b'\x08\x0d'
        for files in substreams:
            out += number(len(files))
        out += b'\x09'
        for files in substreams:
            for size, _ in files[:-1]:
                out += number(size)
        # A folder with one stream and its own CRC carries no extra digest.
        digests = b''
        for (_, _, _, folder_crc), files in zip(folders, substreams):
            if len(files) == 1 and folder_crc is not None:
                continue
            for _, crc in files:
                digests += struct.pack('<I', crc)
        if digests:
            out += b'\x0a\x01' + digests
        out += b'\x00'
    return out + b'\x00'


def bits(flags):
    out = bytearray((len(flags) + 7) // 8)
    for index, flag in enumerate(flags):
        if flag:
            out[index >> 3] |= 0x80 >> (index & 7)
    return bytes(out)


def build(entries, method=LZMA2, solid=True, encode_header=True, dictionary=1 << 16,
          folder_crc=False, attributes=None):
    """entries: [(name, bytes or None for a directory)]. Returns archive bytes."""
    files = [(name, data) for name, data in entries if data]
    groups = [files] if solid and files else [[item] for item in files]
    packed, folders, substreams = b'', [], []
    for group in groups:
        raw = b''.join(data for _, data in group)
        blob, props = compress(method, raw, dictionary)
        packed += blob
        folders.append((method, props, len(raw), zlib.crc32(raw) if folder_crc else None))
        substreams.append([(len(data), zlib.crc32(data)) for _, data in group])
    pack_sizes = []
    position = 0
    for group in groups:
        raw = b''.join(data for _, data in group)
        size = len(compress(method, raw, dictionary)[0])
        pack_sizes.append(size)
        position += size
    header = b'\x01\x04' + streams_info(0, pack_sizes, folders, substreams)
    header += b'\x05' + number(len(entries))
    empty = [not data for _, data in entries]
    if any(empty):
        vector = bits(empty)
        header += b'\x0e' + number(len(vector)) + vector
        empty_files = [data is not None for name, data in entries if not data]
        vector = bits(empty_files)
        header += b'\x0f' + number(len(vector)) + vector
    names = b'\x00' + b''.join(name.encode('utf-16-le') + b'\x00\x00' for name, _ in entries)
    header += b'\x11' + number(len(names)) + names
    if attributes:
        values = b'\x01\x00' + b''.join(struct.pack('<I', value) for value in attributes)
        header += b'\x15' + number(len(values)) + values
    header += b'\x00\x00'
    next_header = header
    if encode_header:
        blob, props = compress(LZMA, header, 1 << 16)
        next_header = b'\x17' + streams_info(len(packed), [len(blob)],
                                              [(LZMA, props, len(header), zlib.crc32(header))], None)
        packed += blob
    start = struct.pack('<QQI', len(packed), len(next_header), zlib.crc32(next_header))
    return b'7z\xbc\xaf\x27\x1c\x00\x04' + struct.pack('<I', zlib.crc32(start)) + start + packed + next_header
