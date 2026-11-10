#!/usr/bin/env python3
"""Host test of REWINDBOX_TEXTURE_LOOKUP_MEMO_660 on the real Core 660 texture cache.

The memo lets a sampler slot of VKGSRender::load_texture_env reuse the descriptor an identical lookup
returned earlier in the same validation epoch (Assassin's Creed, IPA 657: 904 lookups per frame, 61 %
of them confirmed without hashing). A wrong hit would show a stale texture, so the test runs the real
code with the memo off and on and requires identical results.

Static, from the trees:
- key completeness: every texture accessor the lookup uses (upload_texture_impl, get_texture_size,
  upload_sampler_texture) reads only registers among lookup_words(), indexed exactly as lookup_words()
  indexes them (fragment and vertex, transitively over RSXTexture.cpp);
- writer census: every function of cached_texture_section, ranged_storage_block and
  vk::cached_texture_section that writes a field an exact lookup reads (protection, dirty, context,
  format, dimensions, pitch, swizzle, view flags, ranges, image, block sections) bumps a generation,
  and the buffered_section writers are reached only through bumping wrappers;
- one cache lock: upload_sampler_texture takes one reader lock and hands it to upload_texture_impl,
  which then takes none; revalidate_overlapping drops memo entries with the slot bindings;
- the VKDraw call sites (memo refresh on m_samplers_dirty, unchanged skip conditions and non-iOS path),
  the memo's storage restriction and verification constants, the title policy, setting and COREPROF line;
- scope: the files this change touches, none of them a PPU/SPU codegen input, identities unchanged.
Dynamic (g++, ASan + UBSan; vptr off: rsx::thread's RTTI lives in RSXThread.cpp; then the same runs built
by clang++ without sanitizers must give the same records):
- the real rsx::texture_cache, its sections and storage, buffered_section, the register accessors and
  size helpers, vk::cached_texture_section::create/destroy/set_rsx_pitch and
  vk::texture_cache::create_new_texture/set_component_order, compiled from the Core 660 control tree and
  from the candidate, run 21 scenarios (A/B/A, register rewrites, epochs, scoped writes, CPU writes,
  section creation and reuse, swizzle mismatch, the address index threshold, component order, eviction,
  purge, memory pressure, residency, frame end, m_samplers_dirty, bound render target, IO remap,
  compressed lookups and framebuffer locks, tiled memory, epoch off, vertex/BX2/disabled units, blit
  sources, 400 hits, and a write that bypasses every choke point);
- control, candidate off, candidate with hits served, with the boot verification (first 256 hits) and
  verify-all give identical descriptors, views, images, contents and section states after every draw,
  and identical hash and CPU-upload counts;
- each invalidation drops the entry (the next lookup misses for the expected reason), hits occur where
  expected, the verification samples the first 256 hits and then one in 64, and the forced mismatch is
  served stale without verification, but caught, logged once and turns the memo off with it;
- negative controls: without the section generation, the range invalidation or the epoch checks, the
  served results diverge from the control.
Host model of the RSX texture cache; no Metal, iPhone or frame-rate claim.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The RewindBox codegen audits are imported read-only: no bytecode cache is written next to them.
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rpcs3_texture_lookup_memo660_harness as bh  # noqa: E402

REWINDBOX = Path(__file__).resolve().parents[1]
MARK = 'REWINDBOX_TEXTURE_LOOKUP_MEMO_660'
MEMO_H = 'rpcs3/ios/IOSTextureLookupMemo.h'
UTILS_H = 'rpcs3/Emu/RSX/Common/texture_cache_utils.h'
DRAW = 'rpcs3/Emu/RSX/VK/VKDraw.cpp'
RSXTEX_H = 'rpcs3/Emu/RSX/RSXTexture.h'
EXPECTED_FILES = {
    'rpcs3/Emu/RSX/Common/texture_cache.h', UTILS_H, 'rpcs3/Emu/RSX/VK/VKTextureCache.h', 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp',
    DRAW, RSXTEX_H, 'rpcs3/Emu/RSX/RSXTexture.cpp', 'rpcs3/Emu/system_config.h', 'rpcs3/ios/IOSTitleLevers.h',
    'rpcs3/ios/RPCS3IOSExperimentalPolicy.h', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp', 'rpcs3/ios/RPCS3IOSPerformance.cpp',
    'rpcs3/ios/RPCS3IOSSettings.cpp', MEMO_H,
}
require = bh.require
text = bh.text
block = bh.block


# ---------------------------------------------------------------------------------------------
# Static checks
# ---------------------------------------------------------------------------------------------
def accessor_table(rsxtex: str, cls: str) -> dict:
    """{method: (register index expressions read, methods called)}."""
    table = {}
    for match in re.finditer(r'\n\t[^\n;{}]*?\b' + cls + r'::(\w+)\(([^)]*)\) const\n\t\{', rsxtex):
        first = match.start() + 1
        body = rsxtex[first:bh.braced_from(rsxtex, first)]
        body = body[body.index('{'):]
        reads = set(re.findall(r'registers\[(NV4097_SET_(?:VERTEX_)?TEXTURE_[A-Z0-9_]+\s*\+\s*(?:\(m_index \* 8\)|m_index))\]', body))
        calls = set(re.findall(r'(?<![\w.>:])(\w+)\(\)', body)) - {match.group(1)}
        table[match.group(1)] = (reads, calls)
    return table


def closure(table: dict, name: str, seen: set) -> set:
    if name in seen or name not in table:
        return set()
    seen.add(name)
    reads, calls = table[name]
    result = set(reads)
    for call in calls:
        result |= closure(table, call, seen)
    return result


def register_of(expression: str) -> str:
    return re.match(r'NV4097_SET_(?:VERTEX_)?TEXTURE_([A-Z0-9_]+)', expression).group(1)


def check_key(candidate: Path) -> dict:
    tex = text(candidate, bh.TEX)
    upload = block(tex, '\t\tsampled_image_descriptor upload_texture_impl(commandbuffer_type& cmd, const RsxTextureType& tex, surface_store_type& m_rtts, reader_lock* held_lock, Args&&... extras)\n')
    hook = block(tex, '\t\tsampled_image_descriptor upload_sampler_texture(commandbuffer_type& cmd, const RsxTextureType& tex, surface_store_type& m_rtts, u32 index, u32 memo_flags)\n')
    utils = text(candidate, bh.UTILS_CPP)
    sizes = block(utils, '\tusz get_texture_size_with_mipmaps(const RSXTexture auto& texture, u16 mipmaps)\n') + \
        block(utils, '\tusz get_texture_size_impl(const RSXTexture auto& texture, u8 mip_level)\n')
    used = set(re.findall(r'\btex\.(\w+)\(', upload + hook)) | set(re.findall(r'\btexture\.(\w+)\(', sizes))
    require({'offset', 'location', 'format', 'width', 'height', 'pitch', 'decoded_remap', 'lookup_words'} <= used, 'accessor scan')
    used.discard('lookup_words')
    require('get_texture_size(tex' in upload, 'upload_texture_impl sizes the texture with get_texture_size')
    rsxtex = text(candidate, 'rpcs3/Emu/RSX/RSXTexture.cpp')
    report = {}
    for cls in ('fragment_texture', 'vertex_texture'):
        table = accessor_table(rsxtex, cls)
        reads = set()
        for name in used:
            require(name in table, f'{cls}::{name} not found')
            reads |= closure(table, name, set())
        words = table['lookup_words'][0]
        require(all(re.sub(r'\s+', ' ', r) in {re.sub(r'\s+', ' ', w) for w in words} for r in reads),
                f'{cls}: the lookup reads registers lookup_words() lacks or indexes differently: {sorted(reads - words)}')
        report[cls] = {'lookup_reads': sorted({register_of(r) for r in reads}), 'key_words': sorted({register_of(w) for w in words})}
    require(report['fragment_texture']['key_words'] == ['ADDRESS', 'CONTROL1', 'CONTROL3', 'FORMAT', 'IMAGE_RECT', 'OFFSET'], 'fragment key words')
    require(report['vertex_texture']['key_words'] == ['ADDRESS', 'CONTROL3', 'FORMAT', 'IMAGE_RECT', 'OFFSET'], 'vertex key words (no CONTROL1)')
    vertex_words = block(rsxtex, '\tstd::array<u32, 6> vertex_texture::lookup_words() const\n')
    require('\t\t\t0u,\n' in vertex_words, 'the vertex key keeps CONTROL1 empty')
    # Everything else the memo hook reads from the unit: the resolved address and the compressed flag.
    require('rsx::get_address(tex.offset(), tex.location())' in hook and 'helpers::is_compressed_gcm_format(tex.format() & ~(CELL_GCM_TEXTURE_LN | CELL_GCM_TEXTURE_UN))' in hook,
            'the hook resolves the address and the compressed path as upload_texture does')
    require('g_cfg' not in block(tex, '\t\tsampled_image_descriptor fast_texture_search(\n')[:block(tex, '\t\tsampled_image_descriptor fast_texture_search(\n').index('if (!overlapping_locals.empty())')],
            'no configuration read before the exact local return')
    return report


FIELDS = ['dirty', 'context', 'gcm_format', 'width', 'height', 'depth', 'mipmaps', 'rsx_pitch', 'real_pitch', 'swizzled', 'view_flags',
          'image_type', 'vram_texture', 'managed_texture', 'triggered_exists_callbacks', 'locked', 'protection', 'protection_strat',
          'cpu_range', 'confirmed_range', 'locked_range', 'mem_hash', 'validated_epoch', 'sections', 'm_address_index']
KEYWORDS = {'if', 'for', 'while', 'switch', 'return', 'catch', 'sizeof'}
BUMP = re.compile(r'ios_memo_changed\(\)|texture_lookup_memo::section_changed\(')


def functions(source: str, indent: str) -> list[tuple[str, str]]:
    result = []
    pattern = re.compile(r'\n' + indent + r'(?!(?:if|for|while|switch|else|return|do)\b)([^\n;{}#/]*?\b(~?\w+)\s*\([^;{}]*\)[^;{}\n]*)\n' + indent + r'\{')
    for match in pattern.finditer(source):
        if match.group(2) in KEYWORDS:
            continue
        first = match.start() + 1
        result.append((match.group(2), source[first:bh.braced_from(source, first)]))
    return result


def writes(body: str) -> set:
    found = set()
    for field in FIELDS:
        # A parameter or local of the same name: only this->field is the member.
        prefix = r'this->' if re.search(r'\b(?:u8|u16|u32|u64|bool|auto|const auto)\s+' + field + r'\b', body) else r'(?<![\w.>:])(?:this->)?'
        if re.search(prefix + field + r'\s*(?:=(?!=)|\+=|-=|\|=|&=)', body) or \
                re.search(prefix + field + r'\.(?:reset|invalidate|merge|clear|emplace_back|push_back|insert|erase|start\s*=|end\s*=)', body):
            found.add(field)
    return found


def check_writers(candidate: Path) -> dict:
    utils = text(candidate, UTILS_H)
    vkh = text(candidate, 'rpcs3/Emu/RSX/VK/VKTextureCache.h')
    regions = {
        'ranged_storage_block': utils[utils.index('\tclass ranged_storage_block\n'):utils.index('\tclass ranged_storage\n')],
        'cached_texture_section': utils[utils.index('\tclass cached_texture_section : public rsx::buffered_section'):],
        'buffered_section (header)': utils[utils.index('\tclass buffered_section\n'):utils.index('\tclass cached_texture_section : public rsx::buffered_section')],
        'vk::cached_texture_section': vkh[vkh.index('\tclass cached_texture_section : public rsx::cached_texture_section'):vkh.index('\tclass texture_cache : public rsx::texture_cache')],
    }
    # Writers whose state changes are tracked otherwise (each reason is checked below or by the scenarios).
    allowed = {
        ('buffered_section (header)', 'reset_validation'): 'CELL573 scoped revalidation: revalidate_overlapping drops the memo entries over the range',
        ('ranged_storage_block', 'initialize'): 'block construction, before any section',
        ('cached_texture_section', 'initialize'): 'section construction, before any range',
        ('ranged_storage_block', 'remove_address_entry'): 'only from on_section_range_invalid (cached invalidate_range bumps first)',
        ('ranged_storage_block', 'add_address_entry'): 'only from on_section_range_valid (cached notify_range_valid bumps first)',
    }
    census, missing = {}, []
    for region, source in regions.items():
        for name, body in functions(source, '\t\t'):
            fields = writes(body)
            if not fields:
                continue
            bumped = bool(BUMP.search(body))
            census.setdefault(region, []).append({'function': name, 'writes': sorted(fields), 'bumps': bumped})
            if not bumped and (region, name) not in allowed:
                missing.append(f'{region}::{name} writes {sorted(fields)} without a generation bump')
    # Out-of-line members of vk::cached_texture_section (VKTextureCache.cpp): a write of a field the lookup reads
    # must bump too. dma_transfer writes rsx_pitch (bumped when it changes) and real_pitch (not read by the lookup).
    vkcpp = text(candidate, 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp')
    out_of_line = []
    for match in re.finditer(r'\n\t[^\n;{}]*?\bcached_texture_section::(\w+)\(([^;{}]*)\)[^;{}\n]*\n\t\{', vkcpp):
        first = match.start() + 1
        name, code = match.group(1), vkcpp[first:bh.braced_from(vkcpp, first)]
        fields = writes(code) - {'real_pitch'}
        out_of_line.append({'function': name, 'writes': sorted(fields), 'bumps': bool(BUMP.search(code))})
        if fields and not BUMP.search(code):
            missing.append(f'vk::cached_texture_section::{name} (VKTextureCache.cpp) writes {sorted(fields)} without a generation bump')
    require(out_of_line and any(entry['function'] == 'dma_transfer' for entry in out_of_line), 'the out-of-line members were not found')
    census['vk::cached_texture_section (VKTextureCache.cpp)'] = out_of_line
    dma = block(vkcpp, '\tvoid cached_texture_section::dma_transfer(')
    require(re.search(r'if \(pitch != rsx_pitch\)\n\t\t\{\n\t\t\tios_memo_changed\(\);\n\t\t\}\n#endif\n\t\trsx_pitch = pitch;', dma),
            'dma_transfer bumps before it changes rsx_pitch')
    require(not missing, 'writer census: ' + '; '.join(missing))
    block_code = regions['ranged_storage_block']
    for helper, callback in (('remove_address_entry', 'on_section_range_invalid'), ('add_address_entry', 'on_section_range_valid')):
        require(len(re.findall(r'\b' + helper + r'\(section\)', utils)) == 1 and helper + '(section);' in block(block_code, '\t\tinline void ' + callback + '(section_storage_type &section)\n'),
                helper + ' only from ' + callback)
    require(utils.count('m_block->on_section_range_valid(*derived());') == 1 and utils.count('m_block->on_section_range_invalid(*derived());') == 1,
            'the range callbacks come only from notify_range_valid/invalidate_range')
    # buffered_section's own writers (texture_cache.cpp) are reached only through the bumping wrappers.
    cpp = text(candidate, bh.CPP)
    for name in ('reset', 'invalidate_range', 'protect', 'unprotect', 'discard'):
        callers = re.findall(r'(?:rsx::)?buffered_section::' + name + r'\(', utils)
        require(callers, f'buffered_section::{name} callers')
    wrappers = {
        'reset': block(utils, '\t\tvoid reset(const address_range32& memory_range)\n\t\t{\n\t\t\tAUDIT(memory_range.valid());'),
        'invalidate_range': block(utils, '\t\tvoid invalidate_range()\n\t\t{\n#ifdef RPCS3_IOS\n\t\t\tios_memo_changed();'),
        'protect': block(utils, '\t\tinline void protect(utils::protection prot)\n'),
        'protect_range': block(utils, '\t\tinline void protect(utils::protection prot, const std::pair<u32, u32>& range_confirm)\n'),
        'unprotect': block(utils, '\t\tinline void unprotect()\n'),
        'discard': block(utils, '\t\tinline void discard(bool set_dirty = true)\n'),
    }
    for name, code in wrappers.items():
        require(BUMP.search(code) or 'post_protect(' in code, f'the {name} wrapper bumps (directly or through post_protect)')
    require(BUMP.search(block(utils, '\t\tvoid post_protect(utils::protection old_prot, utils::protection prot)\n')), 'post_protect bumps')
    require(len(re.findall(r'rsx::buffered_section::(?:reset|protect|unprotect|discard)\(|buffered_section::invalidate_range\(', utils)) == 6,
            'buffered_section writers are called only from the six wrappers')
    require(all(f'buffered_section::{name}(' in cpp for name in ('reset', 'invalidate_range', 'protect', 'discard', 'sync')), 'buffered_section methods')
    set_context = block(utils, '\t\tvoid set_context(rsx::texture_upload_context upload_context)\n')
    require('context == rsx::texture_upload_context::framebuffer_storage &&\n\t\t\t\tupload_context == rsx::texture_upload_context::framebuffer_storage' in set_context,
            'set_context bumps from the old and the new context')
    create = block(vkh, '\t\tvoid create(u16 w, u16 h, u16 depth, u16 mipmaps, vk::image* image, u32 rsx_pitch, bool managed, u32 gcm_format, bool pack_swap_bytes = false)\n')
    require(create.index('ios_memo_changed()') < create.index('vram_texture = new_texture;'), 'vk create bumps before its direct writes')
    callback = block(utils, '\t\tvoid on_section_resources_created()\n')
    require(callback.index('ios_memo_changed()') < callback.index('if (triggered_exists_callbacks) return;'), 'the created callback bumps before its early return')
    order = block(text(candidate, 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp'), '\tvoid texture_cache::set_component_order(cached_texture_section& section, u32 gcm_format, rsx::component_order expected_flags)\n')
    require(order.index('section.ios_memo_changed()') < order.index('image->set_native_component_layout(mapping);'), 'set_component_order bumps before disposing the views')
    block_code = regions['ranged_storage_block']
    require(BUMP.search(block(block_code, '\t\tinline section_storage_type& create_section()\n')) and BUMP.search(block(block_code, '\t\tinline void clear()\n')),
            'create_section and clear bump')
    return {region: entries for region, entries in census.items()}


def check_lock_and_hook(candidate: Path) -> dict:
    tex = text(candidate, bh.TEX)
    hook = block(tex, '\t\tsampled_image_descriptor upload_sampler_texture(commandbuffer_type& cmd, const RsxTextureType& tex, surface_store_type& m_rtts, u32 index, u32 memo_flags)\n')
    off_branch = hook[:hook.index('const u64 lookup_begin = utils::get_tsc();')]
    require(off_branch.count('return result;') == 1 and 'prepare_sampler_validation(index)' in off_branch and
            'finish_sampler_validation(index, result, validation_stamp, m_rtts)' in off_branch and 'reader_lock' not in off_branch,
            'lever off: the Core 659 sequence, no lock of its own')
    on_branch = hook[len(off_branch):]
    require(on_branch.count('reader_lock lock(m_cache_mutex);') == 1 and on_branch.count('upload_texture_impl(cmd, tex, m_rtts, &lock)') == 1,
            'one reader lock for the binding, the memo and the lookup, handed to upload_texture_impl')
    require('prepare_sampler_validation(' not in on_branch and 'finish_sampler_validation(' not in on_branch.replace('finish_sampler_validation_locked(', ''),
            'no second lock through prepare/finish')
    require(on_branch.count('finish_sampler_validation_locked(index, result, m_rtts)') == 2, 'the binding finishes under the same lock (hit and lookup)')
    # The served hit hands the sampler validation what the full lookup would (review 660): the store's current write
    # tag, this lookup's validation stamp, then the binding, then the return (the dynamic scenarios keep one write tag).
    hit = on_branch[on_branch.index('if (found.value && !verify)'):]
    hit = hit[:hit.index('return result;') + len('return result;')]
    order = [hit.find(needle) for needle in ('sampled_image_descriptor result = *found.value;', 'result.surface_cache_tag = m_rtts.write_tag;',
                                              'result.ios_validation_stamp = validation_stamp;', 'finish_sampler_validation_locked(index, result, m_rtts);',
                                              'return result;')]
    require(min(order) >= 0 and order == sorted(order), 'the served hit restamps the write tag and the validation stamp, then binds')
    # One shared lock per lookup, never a second one by the same thread (a pending writer would block it): no other
    # lock of m_cache_mutex in the hook, nor in the memo or the locked finish it calls.
    require(hook.count('m_cache_mutex') == 1, 'upload_sampler_texture names m_cache_mutex once (its one reader lock)')
    finish_locked = block(tex, '		u64 finish_sampler_validation_locked(')
    memo_header = text(candidate, MEMO_H)
    locks = re.compile(r'\b(?:m_cache_mutex|mutex|lock_guard|reader_lock|writer_lock|scoped_lock|unique_lock|shared_lock)\b')
    require(not locks.search(finish_locked) and not locks.search(re.sub(r'//[^\n]*', '', memo_header)),
            'no lock in finish_sampler_validation_locked or in the memo')
    impl = block(tex, '\t\tsampled_image_descriptor upload_texture_impl(commandbuffer_type& cmd, const RsxTextureType& tex, surface_store_type& m_rtts, reader_lock* held_lock, Args&&... extras)\n')
    require('if (!held_lock)\n\t\t\t{\n\t\t\t\town_lock.emplace(m_cache_mutex);\n\t\t\t}\n\t\t\treader_lock& lock = held_lock ? *held_lock : *own_lock;\n#else\n\t\t\treader_lock lock(m_cache_mutex);\n#endif' in impl,
            'upload_texture_impl uses the caller lock or its own, never both')
    require(impl.count('lock.upgrade();') == 1, 'the CPU upload upgrades that lock')
    wrapper = block(tex, '\t\tsampled_image_descriptor upload_texture(commandbuffer_type& cmd, const RsxTextureType& tex, surface_store_type& m_rtts, Args&&... extras)\n')
    require('return upload_texture_impl(cmd, tex, m_rtts, nullptr, std::forward<Args>(extras)...);' in wrapper, 'upload_texture keeps its own lock')
    direct = on_branch[on_branch.index('const bool direct ='):on_branch.index('switch (m_lookup_memo.end(')]
    for condition in ('result.image_handle', 'result.upload_context == rsx::texture_upload_context::shader_read',
                      'result.external_subresource_desc.op == deferred_request_command::nop', '!result.is_cyclic_reference',
                      '!result.ios_direct_framebuffer', 'result.ref_address == key.address', 'result.ios_validation_range.start == key.address'):
        require(condition in direct, 'stored only when ' + condition)
    revalidate = block(tex, '\t\tvoid revalidate_overlapping(const address_range32& range)\n')
    require(revalidate.count('range.start, range.valid() ? u64{range.end} - range.start + 1 : 0);') == 2 and 'm_lookup_memo.invalidate(' in revalidate,
            'revalidate_overlapping drops memo entries with the slot bindings')
    # A hit skips sync_protection's last_use_frame update: exact because the residency frame advances only
    # in on_frame_end, after the epoch advance that ends every entry.
    frame_end = block(tex, '\t\tvirtual void on_frame_end()\n')
    require(frame_end.index('rpcs3::ios::texture_validation::advance_epoch();') < frame_end.index('rpcs3::ios::texture_residency::advance_frame();'),
            'on_frame_end advances the epoch before the residency frame')
    advances = subprocess.run(['grep', '-rn', '--include=*.cpp', '--include=*.h', '--include=*.hpp', '--include=*.mm', 'texture_residency::advance_frame()',
                               str(candidate / 'rpcs3')], capture_output=True, text=True).stdout.splitlines()
    require(len([line for line in advances if '/rpcs3/ios/tests/' not in line]) == 1, 'texture_residency::advance_frame callers: ' + repr(advances))
    memo = text(candidate, MEMO_H)
    require('constexpr std::uint64_t verify_first = 256;' in memo and 'constexpr std::uint64_t verify_period = 64;' in memo and
            'return value == mode::verify_all || hit < verify_first || (hit - verify_first) % verify_period == 0;' in memo,
            'verification: the first 256 hits, then one in 64, every hit in verify_all')
    require("memo::disabled.store(true, std::memory_order_relaxed);" in on_branch and "if (!memo::mismatch_logged.exchange(true, std::memory_order_relaxed))" in on_branch,
            'a mismatch disables the memo and logs once')
    return {'locks_per_lookup': 1, 'stored_conditions': 7}


def check_draw(candidate: Path, control: Path) -> dict:
    new, old = text(candidate, DRAW), text(control, DRAW)
    env_new = block(new, 'void VKGSRender::load_texture_env()\n')
    env_old = block(old, 'void VKGSRender::load_texture_env()\n')
    refresh = ('\tstd::lock_guard lock(m_sampler_mutex);\n#ifdef RPCS3_IOS\n\t// REWINDBOX_TEXTURE_LOOKUP_MEMO_660: a global sampler refresh (frame end, blit, access violation, unmap,\n'
               '\t// tile change, surface eviction) drops every texture lookup memo entry before any slot is looked up.\n'
               '\tif (m_samplers_dirty && rpcs3::ios::texture_lookup_memo::consolidated())\n\t{\n\t\trpcs3::ios::texture_lookup_memo::sampler_refresh();\n\t}\n#endif\n')
    require(env_new.count(refresh) == 1, 'the memo refresh right after the sampler lock')
    require(env_new.count('m_texture_cache.upload_sampler_texture(') == 2 and env_new.count('if (rpcs3::ios::texture_lookup_memo::consolidated())') == 2,
            'both slot loops take upload_sampler_texture with the lever')
    require('rpcs3::ios::texture_lookup_memo::fragment_flags(current_fp_metadata.bx2_texture_reads_mask, i)' in env_new and
            'rpcs3::ios::texture_lookup_memo::vertex_flag' in env_new, 'BX2 and vertex key flags')
    for condition in ('\t\tif (!m_samplers_dirty &&\n\t\t\t!m_textures_dirty[i] &&\n', '\t\tif (!m_samplers_dirty &&\n\t\t\t!m_vertex_textures_dirty[i] &&\n'):
        start_new, start_old = env_new.index(condition), env_old.index(condition)
        require(env_new[start_new:env_new.index('\t\t{', start_new)] == env_old[start_old:env_old.index('\t\t{', start_old)], 'skip condition unchanged')
    # Insertion only (the delivered census contract of test/rpcs3_feedback_census_test.py): removing the inserted
    # lines gives the control's load_texture_env, whose prepare/upload/finish sequence is what runs without the lever.
    fragment = ('\t\t// REWINDBOX_TEXTURE_LOOKUP_MEMO_660: with the lever, the sampler validation binding and the lookup under\n'
                '\t\t// one cache lock and through the lookup memo (ios/IOSTextureLookupMemo.h); without it, the sequence below.\n'
                '\t\tif (rpcs3::ios::texture_lookup_memo::consolidated())\n\t\t{\n'
                '\t\t\t*sampler_state = m_texture_cache.upload_sampler_texture(*m_current_command_buffer, tex, m_rtts, i,\n'
                '\t\t\t\trpcs3::ios::texture_lookup_memo::fragment_flags(current_fp_metadata.bx2_texture_reads_mask, i));\n'
                '\t\t}\n\t\telse\n\t\t{\n')
    vertex = ('\t\t// REWINDBOX_TEXTURE_LOOKUP_MEMO_660: as for a fragment slot; the vertex slots follow the fragment ones.\n'
              '\t\tif (rpcs3::ios::texture_lookup_memo::consolidated())\n\t\t{\n'
              '\t\t\t*sampler_state = m_texture_cache.upload_sampler_texture(*m_current_command_buffer, tex, m_rtts, validation_index,\n'
              '\t\t\t\trpcs3::ios::texture_lookup_memo::vertex_flag);\n'
              '\t\t}\n\t\telse\n\t\t{\n')
    close_fragment = '\t\tm_texture_cache.finish_sampler_validation(i, *sampler_state, validation_stamp, m_rtts);\n\t\t}\n#endif\n'
    close_vertex = '\t\tm_texture_cache.finish_sampler_validation(validation_index, *sampler_state, validation_stamp, m_rtts);\n\t\t}\n#endif\n'
    for piece in (fragment, vertex, close_fragment, close_vertex):
        require(env_new.count(piece) == 1, 'the memo branch: ' + piece.strip().splitlines()[0][:70])
    stripped = env_new.replace(refresh, '\tstd::lock_guard lock(m_sampler_mutex);\n').replace(fragment, '', 1).replace(vertex, '', 1)
    stripped = stripped.replace(close_fragment, close_fragment.replace('\t\t}\n', '', 1), 1).replace(close_vertex, close_vertex.replace('\t\t}\n', '', 1), 1)
    original = env_old
    require(stripped == original, 'load_texture_env differs from the control outside the memo call sites')
    return {'call_sites': 2}


def check_policy(candidate: Path) -> dict:
    levers = text(candidate, 'rpcs3/ios/IOSTitleLevers.h')
    require('constexpr bool serves_texture_lookup_memo(std::string_view title_id) noexcept\n{\n\treturn is_assassins_creed_title(title_id);\n}' in levers and
            'constexpr bool verifies_texture_lookup_memo(std::string_view title_id) noexcept\n{\n\treturn is_black_ops_ii_title(title_id);\n}' in levers,
            'Automatic: Assassin\'s Creed served, Black Ops II verified')
    policy = text(candidate, 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp')
    resolve = policy[policy.index('void resolve_experimental_policy() noexcept'):]
    require(resolve.index('texture_validation::epoch_enabled.store(') < resolve.index('memo::configure(memo_mode);'), 'configured after the epoch flag')
    require('if (resolved.texture_validation_epoch && memo_setting != ios_experimental_mode::disabled)' in resolve, 'needs the epoch; Disabled is off')
    # The epoch flag is written once per boot, right before configure() starts new generations (an entry
    # never survives a change of epoch_enabled).
    stores = subprocess.run(['grep', '-rn', '--include=*.cpp', '--include=*.h', '--include=*.hpp', '--include=*.mm', 'epoch_enabled.store(',
                             str(candidate / 'rpcs3')], capture_output=True, text=True).stdout.splitlines()
    stores = [line for line in stores if '/rpcs3/ios/tests/' not in line]
    require(len(stores) == 1 and 'RPCS3IOSExperimentalPolicy.cpp' in stores[0], 'epoch_enabled stores: ' + repr(stores))
    require('Resolved title policy 660: texture_lookup_memo=%d verify_all=%d' in resolve, 'boot line')
    config = text(candidate, 'rpcs3/Emu/system_config.h')
    require('cfg::_enum<ios_experimental_mode> texture_lookup_memo{ this, "Texture Lookup Memo", ios_experimental_mode::automatic };' in config, 'setting node')
    settings = text(candidate, 'rpcs3/ios/RPCS3IOSSettings.cpp')
    require('GAME_SETTING("experimental.texture_lookup_memo", "Experimental", "FPS Experiments", "Texture lookup memo",' in settings and
            'g_cfg.ios_experimental.texture_lookup_memo, 0, 0, 0)' in settings, 'per-game setting')
    perf = text(candidate, 'rpcs3/ios/RPCS3IOSPerformance.cpp')
    line = perf[perf.index('"COREPROF TEXMEMO660 '):perf.index('scope=process_window_counters window_boundary_approximate=1",', perf.index('"COREPROF TEXMEMO660 '))]
    keys = re.findall(r'(\w+)=%', line)
    for key in ('mode', 'disabled', 'lookups', 'hits', 'verified', 'mismatches', 'stores', 'miss_empty', 'miss_epoch', 'miss_revision',
                'miss_range', 'miss_context', 'miss_section', 'miss_bound', 'miss_disabled', 'unstored_kind', 'unstored_changed',
                'unstored_bound', 'local_bumps', 'fb_bumps', 'context_bumps', 'cpu_uploads', 'locks_avoided', 'first_reuses', 'seen_full',
                'hit_ms', 'lookup_ms'):
        require(key in keys, 'COREPROF TEXMEMO660 ' + key)
    return {'coreprof_fields': len(keys)}


def changed_files(tree: Path) -> set:
    """Every file of the tree (no git history needed: the Core 660 driver builds its trees as plain copies)."""
    return {path.relative_to(tree).as_posix() for path in tree.rglob('*')
            if path.is_file() and not path.is_symlink() and path.relative_to(tree).parts[0] not in ('.git', '3rdparty')}


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


# Mutations the static hook checks must reject (review 660: the dynamic scenarios keep one write tag and cannot see a
# second shared lock on the fast path of RPCS3's shared_mutex).
HOOK_MUTATIONS = {
    'no_write_tag_restamp': ('\t\t\t\tresult.surface_cache_tag = m_rtts.write_tag;\n\t\t\t\tresult.ios_validation_stamp', '\t\t\t\tresult.ios_validation_stamp'),
    'no_stamp_restamp': ('\t\t\t\tresult.ios_validation_stamp = validation_stamp;\n\t\t\t\tfinish_sampler_validation_locked(index, result, m_rtts);\n\t\t\t\tmemo::count(memo::counters.hits);',
                         '\t\t\t\tfinish_sampler_validation_locked(index, result, m_rtts);\n\t\t\t\tmemo::count(memo::counters.hits);'),
    'nested_reader_lock': ('\t\t\t\tsampled_image_descriptor result = *found.value;\n', '\t\t\t\treader_lock nested(m_cache_mutex);\n\t\t\t\tsampled_image_descriptor result = *found.value;\n'),
}


def hook_negative_controls(candidate: Path, work: Path) -> dict:
    caught = {}
    for name, (old, new) in HOOK_MUTATIONS.items():
        tree = work / ('hook_' + name)
        for rel in (bh.TEX, MEMO_H):
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate / rel, tree / rel)
        source = (tree / bh.TEX).read_text(encoding='utf-8')
        require(source.count(old) == 1, 'hook mutation site ' + name)
        (tree / bh.TEX).write_text(source.replace(old, new, 1), encoding='utf-8')
        try:
            check_lock_and_hook(tree)
            caught[name] = False
        except SystemExit:
            caught[name] = True
    require(all(caught.values()), 'a hook mutation passes the static checks: ' + json.dumps(caught))
    return caught


def check_scope(candidate: Path, control: Path) -> dict:
    # The control is Core 660 without this lot (the other Core 660 changes included): the memo's files are the
    # files whose bytes differ between the two trees, and every other Core 660 change is identical in both.
    names = changed_files(candidate) | changed_files(control)
    ours = {name for name in names
            if not ((candidate / name).exists() and (control / name).exists() and (candidate / name).read_bytes() == (control / name).read_bytes())}
    require(ours == EXPECTED_FILES, 'files changed by the memo: ' + repr(sorted(ours ^ EXPECTED_FILES)))
    for name in sorted(ours - {MEMO_H}):
        old, new = (control / name).read_bytes(), (candidate / name).read_bytes()
        require(old.count(b'\r\n') == new.count(b'\r\n') == 0, name + ' line endings')
        require(MARK.encode() in new and MARK.encode() not in old, name + ' marker')
    codegen = module('core619_codegen', REWINDBOX / 'test/rpcs3_core619_codegen_test.py')
    inputs = set(codegen.codegen_inputs(candidate))
    require(len(inputs) == 41 and not (ours & inputs), 'a codegen input changed: ' + repr(sorted(ours & inputs)))
    c610 = module('core610_codegen', REWINDBOX / 'test/rpcs3_core610_codegen_test.py')
    c616 = module('core616_codegen', REWINDBOX / 'test/rpcs3_core616_codegen_test.py')
    identities = {}
    for label, tree in (('control', control), ('candidate', candidate)):
        cmake = (tree / 'rpcs3/Emu/CMakeLists.txt').read_text()
        table = c610.aliases((tree / 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake').read_text())
        identities[label] = {kind: c616.identity(tree, cmake, table, kind)[0] for kind in ('PPU', 'SPU')}
    require(identities['candidate'] == identities['control'] == {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}, 'codegen identities ' + repr(identities))
    return {'files': sorted(ours), 'codegen_inputs': len(inputs), 'identities': identities['candidate']}


# ---------------------------------------------------------------------------------------------
# Dynamic checks
# ---------------------------------------------------------------------------------------------
MODES = ['off', 'active_served', 'active_boot', 'verify_all']

# Event -> {slot: expected outcome of the slot's next lookup (prefix)} in active_served.
DROPS = {
    ('epoch', 'advance_epoch'): {0: 'miss_epoch', 1: 'miss_epoch'},
    ('scoped_write', 'revalidate_A'): {0: 'miss_range', 1: 'hit'},
    ('scoped_write', 'revalidate_elsewhere'): {0: 'hit', 1: 'hit'},
    ('scoped_write', 'rsx_write_A'): {0: 'miss_range', 1: 'miss_section'},
    ('scoped_write', 'commit_as_fbo_A'): {0: 'miss_range', 1: 'miss_section'},
    ('cpu_write_reuse_pitch', 'cpu_write_A'): {0: 'miss_epoch'},
    ('component_order', 'set_component_order'): {0: 'miss_section'},
    ('eviction_purge_oom_residency', 'purge_unreleased'): {0: 'miss_section', 1: 'miss_section'},
    ('eviction_purge_oom_residency', 'blit_destination'): {0: 'miss_section', 1: 'miss_section'},
    ('eviction_purge_oom_residency', 'memory_pressure_severe'): {0: 'miss_section', 1: 'miss_section'},
    ('eviction_purge_oom_residency', 'residency_evict'): {0: 'miss_section', 2: 'miss_section'},
    ('frame_end', 'frame_end'): {0: 'miss_epoch'},
    ('samplers_dirty', 'samplers_dirty'): {0: 'miss_context'},
    ('render_target_bound', 'bind_rt'): {0: 'miss_bound'},
    ('render_target_bound', 'unbind_rt'): {0: 'miss_empty'},
    ('io_remap', 'io_remap'): {0: 'miss_empty'},
    ('io_remap', 'io_restore'): {0: 'miss_section'},
    ('compressed_and_framebuffer', 'lock_framebuffer'): {0: 'miss_section', 1: 'miss_section'},
    ('compressed_and_framebuffer', 'relock_framebuffer'): {0: 'miss_section', 1: 'hit'},
    ('tiled', 'revalidate_elsewhere'): {0: 'miss_range'},
    ('epoch_disabled', 'epoch_off'): {0: 'miss_epoch'},
    ('forced_mismatch', 'poke_gcm_format'): {0: 'hit'},
}

# Exact outcome sequences in active_served (slot:outcome, events in brackets).
SEQUENCES = {
    'aba': '0:miss_empty 0:miss_empty 0:miss_empty+stored 0:miss_empty+stored 0:hit 0:hit 0:hit 0:hit',
    'same_key_rewrite': '0:miss_empty 0:miss_empty+stored 0:hit 0:hit 0:hit 0:hit',
    'epoch': '0:miss_empty 1:miss_empty 0:miss_empty+stored 1:miss_empty+stored 0:hit [advance_epoch] 0:miss_epoch+stored 1:miss_epoch+stored '
             '0:hit [unsynchronized_write] 0:hit [advance_epoch] 0:miss_epoch 1:miss_epoch+stored 0:miss_empty+stored 0:hit',
    'other_section_change': '0:miss_empty 0:miss_empty+stored 0:hit 1:miss_empty 0:miss_section+stored 0:hit',
    'tiled': '0:miss_empty 0:miss_empty+stored 0:hit [revalidate_elsewhere] 0:miss_range+stored 0:hit',
    'epoch_disabled': '0:miss_empty 0:miss_empty+stored 0:hit [epoch_off] 0:miss_epoch 0:miss_empty 0:miss_empty 0:miss_empty [epoch_on] 0:miss_empty+stored 0:hit 0:hit',
    'vertex_bx2_disabled': '0:miss_empty 3:disabled 16:miss_empty 0:miss_empty+stored 3:disabled 16:miss_empty+stored 0:miss_empty+stored 3:disabled 16:hit 0:hit 3:disabled 16:hit',
    'blit_source_never_memoized': '[blit_source] 0:miss_empty 0:miss_empty 0:miss_empty 0:miss_empty',
}

# Negative controls: a mutation of the candidate's memo and the scenarios whose served results must diverge.
MUTATIONS = {
    'no_section_generation': ([(MEMO_H, '''	all_generation.fetch_add(1, std::memory_order_acq_rel);
	if (!framebuffer_only)
	{
		local_generation.fetch_add(1, std::memory_order_acq_rel);
	}''', '	(void)framebuffer_only;')], {'component_order', 'eviction_purge_oom_residency', 'swizzle_mismatch'}),
    'no_range_invalidation': ([('rpcs3/Emu/RSX/Common/texture_cache.h', '''			m_lookup_memo.invalidate(range.start, range.valid() ? u64{range.end} - range.start + 1 : 0);
''', '')], {'scoped_write'}),
    'no_epoch_revision_range_checks': ([(MEMO_H, '''			if (!now.epoch || e.gen.epoch != now.epoch)
			{
				reason = miss::epoch;
			}
			else if (e.stamp.memory != texture_validation::sampler_revision.load(std::memory_order_acquire))
			{
				reason = miss::revision;
			}
			else if (!m_ranges.matches(index, e.stamp))''', '''			if (!m_ranges.matches(index, e.stamp) && e.stamp.range != 0 && false)''')], {'epoch', 'epoch_disabled', 'scoped_write'}),
}


def sequence(records: list) -> str:
    items = []
    for r in records:
        if r['k'] == 'event':
            items.append('[' + r['what'] + ']')
        elif r['k'] == 'lookup':
            items.append(f"{r['slot']}:{r['outcome']}")
    return ' '.join(items)


def canonical(records: list) -> list:
    return [{k: v for k, v in r.items() if k != 'outcome'} for r in records]


def run(binary: Path, mode: str) -> dict:
    # LeakSanitizer exists on Linux only; Apple's ASan aborts when asked for it (Core 660 Apple host tests, run 41991624737).
    leaks = 'detect_leaks=1:' if sys.platform.startswith('linux') else ''
    env = {'ASAN_OPTIONS': leaks + 'abort_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
    result = subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=600, env=env)
    require(result.returncode == 0, f'{binary.name} {mode} failed ({result.returncode}):\n' + result.stderr[-4000:])
    return json.loads(result.stdout)


def check_runs(runs: dict) -> dict:
    control = runs['control']['scenarios']
    require(len(control) == 21, 'scenarios')
    diverging = {}
    for mode in MODES:
        diverging[mode] = sorted(name for name, records in runs[mode]['scenarios'].items() if canonical(records) != canonical(control[name]))
    require(diverging == {'off': [], 'active_served': ['forced_mismatch'], 'active_boot': [], 'verify_all': []},
            'results differ from the Core 660 control: ' + json.dumps(diverging))
    served = runs['active_served']['scenarios']
    for (scenario, what), expected in DROPS.items():
        records = served[scenario]
        index = next(i for i, r in enumerate(records) if r['k'] == 'event' and r['what'] == what)
        for slot, outcome in expected.items():
            nxt = next(r for r in records[index + 1:] if r['k'] == 'lookup' and r['slot'] == slot)
            require(nxt['outcome'].startswith(outcome), f'{scenario} after {what}: slot {slot} {nxt["outcome"]}, expected {outcome}')
    for scenario, expected in SEQUENCES.items():
        require(sequence(served[scenario]) == expected, f'{scenario} outcomes: {sequence(served[scenario])}')
    # Hits on every A/B/A switch once both are stored; never a hit of a blit source; no hit with the epoch off.
    sampling = {mode: [r['outcome'] for r in runs[mode]['scenarios']['verification_sampling'] if r['k'] == 'lookup'][2:] for mode in MODES[1:]}
    require(sampling['active_served'].count('hit') == 394 and sampling['active_served'].count('verified') == 6, 'sampling (served): ' + str({o: sampling['active_served'].count(o) for o in set(sampling['active_served'])}))
    require(sampling['active_boot'].count('verified') == 259 and sampling['active_boot'].count('hit') == 141 and
            sampling['active_boot'][:256] == ['verified'] * 256, 'sampling (boot): the first 256 hits verified, then one in 64')
    require(sampling['verify_all'] == ['verified'] * 400, 'verify_all verifies every hit')
    for mode in ('active_boot', 'verify_all'):
        records = runs[mode]['scenarios']['forced_mismatch']
        outcomes = [r['outcome'] for r in records if r['k'] == 'lookup']
        require(outcomes[3] == 'verified+mismatch' and all(o == 'miss_disabled' for o in outcomes[4:]), f'{mode} forced mismatch: {outcomes}')
        require(runs[mode]['texmemo_errors'] == 1 and runs[mode]['memo']['mismatches'] == 1 and runs[mode]['memo']['disabled'] == 1,
                f'{mode}: one logged mismatch, memo off afterwards')
        others = [r['outcome'] for name, recs in runs[mode]['scenarios'].items() if name != 'forced_mismatch' for r in recs if r['k'] == 'lookup']
        require(not any('mismatch' in o for o in others), f'{mode}: no mismatch outside the forced one')
    require(runs['active_served']['texmemo_errors'] == 0 and runs['active_served']['memo']['mismatches'] == 0, 'served: no verified mismatch')
    # The first reuse of each (slot, key) is verified in the Core's modes; active_served turns it off to serve directly.
    require(runs['active_boot']['memo']['first_reuses'] > 0 and runs['active_served']['memo']['first_reuses'] == 0,
            'first-reuse verification: ' + json.dumps({mode: runs[mode]['memo']['first_reuses'] for mode in ('active_boot', 'active_served')}))
    for mode in MODES[1:]:
        memo = runs[mode]['memo']
        require(memo['locks_avoided'] == 2 * memo['lookups'] and memo['lookups'] > 0 and memo['cpu_uploads'] > 0, mode + ': one lock per lookup, CPU uploads on it')
    require(runs['off']['memo']['lookups'] == 0 and all(r['outcome'] in ('off', 'disabled') for recs in runs['off']['scenarios'].values() for r in recs if r['k'] == 'lookup'),
            'off: the Core 659 path')
    hits = runs['active_served']['memo']['hits']
    lookups = runs['active_served']['memo']['lookups']
    return {'diverging': diverging, 'served_hits': hits, 'lookups': lookups, 'drops_checked': sum(len(v) for v in DROPS.values()),
            'memo': {mode: runs[mode]['memo'] for mode in MODES}}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--candidate', type=Path, required=True, help='the tree after the texture memo step')
    parser.add_argument('--control', type=Path, required=True, help='the tree before it')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--cxx', default='g++', help='compiler of the sanitized runs')
    parser.add_argument('--skip-mutations', action='store_true')
    parser.add_argument('--skip-clang', action='store_true', help='skip the unsanitized clang++ pass (the compiler family of the iOS build)')
    args = parser.parse_args()
    candidate, control = args.candidate.resolve(), args.control.resolve()
    require(MARK in text(candidate, MEMO_H) and not (control / MEMO_H).exists(), 'candidate and Core 660 control trees')
    report = {'static': {}}
    report['static']['key'] = check_key(candidate)
    report['static']['writers'] = check_writers(candidate)
    report['static']['lock'] = check_lock_and_hook(candidate)
    report['static']['draw'] = check_draw(candidate, control)
    report['static']['policy'] = check_policy(candidate)
    report['static']['scope'] = check_scope(candidate, control)
    with tempfile.TemporaryDirectory(prefix='texmemo660-') as temporary:
        work = Path(temporary)
        report['static']['hook_negative_controls'] = hook_negative_controls(candidate, work)
        control_bin = bh.compile_harness(control, work, 'control', bh.render(control, False), {'CANDIDATE': 0}, cxx=args.cxx)
        candidate_bin = bh.compile_harness(candidate, work, 'candidate', bh.render(candidate, True), {'CANDIDATE': 1}, cxx=args.cxx)
        runs = {'control': run(control_bin, 'control')}
        for mode in MODES:
            runs[mode] = run(candidate_bin, mode)
        report['dynamic'] = check_runs(runs)
        if not args.skip_mutations:
            mutations = {}
            for name, (edits, expected) in MUTATIONS.items():
                binary = bh.compile_harness(candidate, work, 'mutant_' + name, bh.render(candidate, True), {'CANDIDATE': 1}, mutations=edits, cxx=args.cxx)
                mutant = run(binary, 'active_served')
                diverging = {scenario for scenario, records in mutant['scenarios'].items()
                             if canonical(records) != canonical(runs['control']['scenarios'][scenario])} - {'forced_mismatch'}
                require(expected <= diverging, f'negative control {name}: expected divergence in {sorted(expected)}, got {sorted(diverging)}')
                mutations[name] = sorted(diverging)
            report['dynamic']['negative_controls'] = mutations
        if not args.skip_clang and shutil.which('clang++'):
            # Same scenarios built by clang++ (no sanitizer runtimes on this host): same results.
            clang_control = bh.compile_harness(control, work, 'clang_control', bh.render(control, False), {'CANDIDATE': 0}, cxx='clang++', sanitize=False)
            clang_candidate = bh.compile_harness(candidate, work, 'clang_candidate', bh.render(candidate, True), {'CANDIDATE': 1}, cxx='clang++', sanitize=False)
            clang_runs = {'control': run(clang_control, 'control')}
            for mode in MODES:
                clang_runs[mode] = run(clang_candidate, mode)
            for mode in MODES:
                require(clang_runs[mode]['memo'] == runs[mode]['memo'], f'clang++ {mode} counters differ from g++')
                for name, records in clang_runs[mode]['scenarios'].items():
                    require(canonical(records) == canonical(runs[mode]['scenarios'][name]) and sequence(records) == sequence(runs[mode]['scenarios'][name]),
                            f'clang++ {mode} {name} differs from g++')
            require(all(canonical(records) == canonical(runs['control']['scenarios'][name]) for name, records in clang_runs['control']['scenarios'].items()),
                    'clang++ control differs from g++ control')
            report['dynamic']['clang'] = 'identical to the g++ runs (' + subprocess.run(['clang++', '--version'], capture_output=True, text=True).stdout.splitlines()[0] + ')'
    report.update(result='passed', compiler='g++ ' + subprocess.run(['g++', '-dumpfullversion'], capture_output=True, text=True).stdout.strip(),
                  sanitizers=['address', 'undefined (vptr off)'], physical_device_tested=False, fps_gain_claimed=False)
    text_report = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.write_text(text_report)
    d = report['dynamic']
    print(f"PASS: memo off/served/boot-verified/verify-all = Core 660 control in every scenario except the served forced mismatch; "
          f"{d['served_hits']} served hits over {d['lookups']} lookups; {d['drops_checked']} invalidation drops; "
          f"negative controls {json.dumps(d.get('negative_controls', 'skipped'))}")


if __name__ == '__main__':
    main()
