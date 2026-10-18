"""Bounded source-attested PS2 filenames and complete PS3 static programs.

These parsers never infer a CRC from a title, move an address between editions,
or turn an NCL freeze/pointer/scan program into a one-time native patch.
"""
from pathlib import PurePosixPath
import re

from unified_formats import FormatError, cheat, game, parse_pnach, text

SERIAL=re.compile(r'\b([A-Z]{4})[-_]([0-9]{5})\b')

def parse_edition_pnach(data, options):
    path=PurePosixPath(options.get('path',''))
    if any(word in ('/'+path.as_posix().casefold()) for word in ('/prototype','/experimental','/beta/','/demo/')):
        raise FormatError('non-retail-or-experimental-source-kept-out-of-gameplay-expansion')
    stem=path.stem
    modern=re.match(r'^([A-Z]{4})-([0-9]{5})_([0-9A-Fa-f]{8})(?:[-_.].*)?$',stem)
    leading=re.match(r'^([0-9A-Fa-f]{8})(?:\s+-\s+|[-_.])(.+)$',stem)
    if modern:
        crc=modern[3].upper(); serial=modern[1]+modern[2]
    elif leading:
        crc=leading[1].upper(); serials={a+b for a,b in SERIAL.findall(stem)}
        # One executable can be explicitly shared by several releases. Its
        # attested CRC remains usable; do not choose one serial arbitrarily.
        serial=next(iter(serials)) if len(serials)==1 else ''
    elif re.fullmatch(r'[0-9A-Fa-f]{8}',stem):
        crc=stem.upper();serial=''
    else:
        raise FormatError('source-filename-has-no-attested-executable-crc')
    if crc=='00000000':raise FormatError('zero-executable-crc-is-not-an-edition')
    title=options.get('title','')
    if leading and not title:
        title=SERIAL.sub('',leading[2]).strip(' -_')
    local={**options,'path':crc+'.pnach'}
    if title:local['title']=title
    result=parse_pnach(data,local)
    for row in result:
        current={(i['type'],i['scheme']):i['value'] for i in row['identities']}
        if current.get(('ps2_crc','pcsx2-executable-crc'),crc)!=crc:
            raise FormatError('conflicting-source-executable-crc')
        current_serial=current.get(('serial','ps2-disc-serial'))
        if current_serial and serial and current_serial!=serial:
            raise FormatError('conflicting-source-disc-serial')
        if serial and not current_serial:
            row['identities'].append({'type':'serial','scheme':'ps2-disc-serial','value':serial})
        row['source_member']=path.as_posix()
        if leading and len(serials)>1:row['source_serial_aliases']=sorted(serials)
        # The exact source file attests a CRC. Unknown region/language remains
        # unknown; a serial prefix is never used to invent release metadata.
        for program in row['cheats']:
            program['source_member']=path.as_posix()
            program['enabled']=False
            authors=re.findall(r'(?im)^\s*author\s*=\s*(.+)$',program['code'])
            descriptions=re.findall(r'(?im)^\s*description\s*=\s*(.+)$',program['code'])
            if authors:program['author']=', '.join(dict.fromkeys(authors))
            if descriptions:program['notes']='\n'.join(dict.fromkeys(descriptions))
    return result

def editions_from_ncl(path):
    stem=PurePosixPath(path).stem
    serials=list(re.finditer(r'\b[BN][A-Z]{3}[0-9]{5}\b',stem))
    pending=[];result=[]
    # A version closes the preceding ID list, never a following list. In
    # particular, av01.03 for a later release must not overwrite an earlier
    # explicit 01.00 release in the same filename. v-only remains ambiguous.
    for index,item in enumerate(serials):
        pending.append(item[0])
        end=serials[index+1].start() if index+1<len(serials) else len(stem)
        suffix=stem[item.end():end]
        explicit=set(re.findall(r'(?i)\bav([0-9]{2}\.[0-9]{2})\b',suffix))
        bare=set(re.findall(r'(?<![A-Za-z0-9])([0-9]{2}\.[0-9]{2})(?![A-Za-z0-9])',suffix))
        if len(explicit)==1:
            result.extend((serial,next(iter(explicit)),'explicit-app-ver') for serial in pending)
        elif not explicit and len(bare)==1 and not re.search(r'(?i)\bv[0-9]{2}\.[0-9]{2}',suffix):
            result.extend((serial,next(iter(bare)),'shared-bare-source-version') for serial in pending)
        elif not re.search(r'[0-9]{2}\.[0-9]{2}',suffix):
            continue
        pending=[]
    return sorted(set(result))

def parse_static_ncl(data, options):
    if len(data)>4*1024*1024:raise FormatError('ncl-source-file-too-large')
    path=options.get('path','');editions=editions_from_ncl(path)
    if not editions:raise FormatError('ncl-without-unambiguous-source-serial-and-version')
    raw=text(data).replace('\r\n','\n').replace('\r','\n')
    programs=[];rejected=[]
    for block in raw.split('#'):
        # Keep the three header positions. Removing an empty author could
        # accidentally turn the first instruction into attribution.
        lines=[line.strip() for line in block.strip().splitlines()]
        if not lines:continue
        if len(lines)<4 or lines[1]!='0':
            rejected.append({'name':lines[0],'reason':'non-static-mode-or-missing-whole-body'});continue
        body=lines[3:]
        parsed=[re.fullmatch(r'0 ([0-9A-Fa-f]{8}) ([0-9A-Fa-f]{8})',line) for line in body]
        if (len(body)>64 or not all(parsed) or
            any(not 0x10000<=int(m[1],16)<0x02000000 or int(m[1],16)%4 for m in parsed)):
            rejected.append({'name':lines[0],'reason':'whole-program-needs-ncl-ram-pointer-scan-width-or-runtime-support'});continue
        source_code='\n'.join(body)
        programs.append(cheat(lines[0],'\n'.join(line[2:].upper() for line in body),'ps3-static-be32',
            author=lines[2],source_code=source_code,source_dialect='artemis-ncl',source_member=path,
            enabled=False,conversion={'id':'whole-ncl-mode0-static-ppu-be32','runtime_ppu_binding_required':True,
                'source_mode':'0','complete_source_program':True}))
    result=[]
    title=re.split(r'\b[BN][A-Z]{3}[0-9]{5}\b',PurePosixPath(path).stem)[0].strip()
    for serial,version,evidence in editions:
        row=game(title,'ps3',options,[{'type':'serial','scheme':'ps3-title-id','value':serial}])
        row.update(revision=version,edition_confirmation_required=True,source_member=path,
            source_version_evidence=evidence,source_rejections=rejected)
        row['cheats']=[dict(c) for c in programs]
        result.append(row)
    return result

PARSERS={'edition-pnach':parse_edition_pnach,'static-ppu-ncl':parse_static_ncl}

def parse_pnach_rar(data,options):
    """Read the pinned data-only RAR in memory; never extract filesystem paths.

    libarchive is needed only by the catalogue generator. Encrypted entries,
    unsafe paths, truncated reads and expansion beyond 32 MiB fail closed.
    """
    import ctypes as c
    import ctypes.util
    library=ctypes.util.find_library('archive')
    if not library:raise FormatError('rar-source-needs-system-libarchive-at-generation-only')
    api=c.CDLL(library)
    signatures=[('archive_read_new',[],c.c_void_p),
        ('archive_read_support_format_rar',[c.c_void_p],c.c_int),
        ('archive_read_support_format_rar5',[c.c_void_p],c.c_int),
        ('archive_read_open_memory',[c.c_void_p,c.c_void_p,c.c_size_t],c.c_int),
        ('archive_read_next_header',[c.c_void_p,c.POINTER(c.c_void_p)],c.c_int),
        ('archive_entry_pathname',[c.c_void_p],c.c_char_p),
        ('archive_entry_size',[c.c_void_p],c.c_longlong),
        ('archive_entry_is_encrypted',[c.c_void_p],c.c_int),
        ('archive_read_data',[c.c_void_p,c.c_void_p,c.c_size_t],c.c_ssize_t),
        ('archive_read_free',[c.c_void_p],c.c_int)]
    for name,args,result in signatures:
        function=getattr(api,name);function.argtypes=args;function.restype=result
    handle=api.archive_read_new();buffer=c.create_string_buffer(data)
    result=[];expanded=0;count=0;rejected=[]
    try:
        api.archive_read_support_format_rar(handle);api.archive_read_support_format_rar5(handle)
        if api.archive_read_open_memory(handle,buffer,len(data))!=0:raise FormatError('invalid-rar-source')
        entry=c.c_void_p()
        while True:
            status=api.archive_read_next_header(handle,c.byref(entry))
            if status==1:break  # ARCHIVE_EOF
            if status!=0:raise FormatError('invalid-or-truncated-rar-entry')
            count+=1
            if count>10000 or api.archive_entry_is_encrypted(entry):raise FormatError('unsafe-rar-source')
            name=api.archive_entry_pathname(entry).decode('utf-8').replace('\\','/')
            path=PurePosixPath(name);size=api.archive_entry_size(entry)
            if path.is_absolute() or '..' in path.parts or ':' in name:raise FormatError('unsafe-rar-path')
            if size<0 or size>2*1024*1024:raise FormatError('oversized-rar-entry')
            expanded+=size
            if expanded>32*1024*1024:raise FormatError('rar-expansion-limit')
            if not name.lower().endswith('.pnach'):continue
            block=c.create_string_buffer(size+1);got=api.archive_read_data(handle,block,size+1)
            if got!=size:raise FormatError('truncated-rar-program')
            # This source contains source-attested modern filenames. A bad
            # member invalidates the input rather than silently hiding it.
            try:
                result.extend(parse_edition_pnach(block.raw[:size],{**options,'path':options.get('path','')+'!/'+name}))
            except FormatError as error:
                rejected.append({'path':options.get('path','')+'!/'+name,'reason':str(error)})
        if rejected:
            if not result:result.append(game('Unsupported RAR members','ps2',options))
            result[0]['source_rejections']=rejected
        return result
    finally:
        api.archive_read_free(handle)

PARSERS['edition-pnach-rar']=parse_pnach_rar
