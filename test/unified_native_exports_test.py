#!/usr/bin/env python3
"""Verify the optional RPCS3 patch APIs in the exact reused Mach-O binary."""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
proof=json.loads((ROOT/'test/unified_native_rpcs3_exports.json').read_text())
if len(sys.argv)!=2:
    raise SystemExit('usage: unified_native_exports_test.py /path/to/pinned/libRPCS3Core.dylib')
data=Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(data).hexdigest()==proof['binary_sha256']
assert len(data)==proof['binary_bytes']
assert data[:4]==b'\xcf\xfa\xed\xfe' and struct.unpack_from('<I',data,4)[0]==0x100000c
count,command_bytes=struct.unpack_from('<II',data,16)
position=32;end=position+command_bytes;table=None
assert count<65536 and end<=len(data)
for _ in range(count):
    command,size=struct.unpack_from('<II',data,position)
    assert size>=8 and position+size<=end
    if command==2:
        assert size>=24
        table=struct.unpack_from('<IIII',data,position+8)
    position+=size
assert table and position==end
symbols,number,strings,string_bytes=table
assert symbols+number*16<=len(data) and strings+string_bytes<=len(data)
defined=set()
for index in range(number):
    string_index,kind,section,description,value=struct.unpack_from('<IBBHQ',data,symbols+index*16)
    if kind&0xe0 or not kind&1 or kind&0xe==0 or not string_index:
        continue
    assert string_index<string_bytes
    terminator=data.find(b'\0',strings+string_index,strings+string_bytes)
    assert terminator>=strings+string_index
    defined.add(data[strings+string_index:terminator].decode())
assert set(proof['required_exports'])<=defined
print('PASS: exact pinned RPCS3 SHA-256/size and all four defined external patch APIs in the Mach-O symbol table')
