#!/usr/bin/env python3
"""MoltenVK in-pass read transitions (RewindBox RPCS3 Core 655): the real barrier and fence code, executed on a host.

The RPCS3 Core 655 records a transition to VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL of an image that is not an
attachment of the open render pass inside that pass (REWINDBOX_IN_PASS_READ_TRANSITION_655) instead of ending it.
The patched MoltenVK (build-utils/rpcs3/patches/moltenvk-1.4.2-deferred-cache.patch, MVKCmdPipeline.mm) then records
the barrier's stage fences (setBarrier) and makes the current render encoder wait for them, which upstream does only
for the next encoder when the barrier is outside a render pass.

This test compiles, from the patched MoltenVK source given on the command line:
- the complete body of MVKCmdPipelineBarrier<N>::encode (MVK_MACOS off: the iOS build), unmodified;
- MVKCommandEncoder::setBarrier, getBarrierStageFence, barrierWait and barrierUpdate (render, blit and compute),
  encodeBarrierWaits and encodeBarrierUpdates, with their Objective-C message sends rewritten as C++ calls on
  recording doubles of the Metal encoders, nothing else changed;
- mvkBarrierStagesFromPipelineStageFlags, unmodified, against the repository's Vulkan headers;
and drives them with a model of the encoder life cycle (a render encoder waits when it begins and updates its fences
when it ends, as beginMetalRenderPass and endMetalRenderEncoding do; a blit encoder likewise) and of Metal fences (a
wait is satisfied by the latest update of that fence encoded before the waiting encoder; drivers may hoist a wait to
the start of its encoder; an encoder must never wait for a fence it updates itself).

Checks, each on the real code:
1. Covering: for every in-pass read transition, the fences the open encoder waits for, with the encoders whose
   updates satisfy them, include every wait of the upstream path (the same barrier ending the pass and the same pass
   beginning again), except the restarted pass's wait for the ended pass itself (needed only because it ended).
2. Ordering: the writer of the image (a render pass that rendered it, a blit that uploaded it) happens before the
   reading pass's vertex and fragment stages, through the fence graph, for the recorded scenarios (a strict model: a
   wait is satisfied only by the latest earlier update of its fence); the unpatched encode body (the RewindBox block
   removed) fails the same check (negative control). The report also counts the scenarios where upstream's restarted
   pass is ordered in that strict model (it reuses the writer's fence slot when no barrier intervened).
3. Metal rule: no encoder waits for a fence it updates (with waits hoisted to the encoder start).
4. Scope: other barriers inside a pass (another layout, a buffer or memory barrier, GENERAL that restarts the pass)
   and every barrier without a residency set are encoded exactly as upstream (same waits, updates and restarts).
5. Randomized sequences (seeded) of passes, blits, outside and in-pass barriers: 1 and 3 on every in-pass read.
No Metal device, iPhone or FPS claim; the GPU behaviour of fences is Apple's documented contract, modelled here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VULKAN_INCLUDE = ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/include'
PIPELINE = 'MoltenVK/MoltenVK/Commands/MVKCmdPipeline.mm'
BUFFER = 'MoltenVK/MoltenVK/Commands/MVKCommandBuffer.mm'
DATATYPES = 'MoltenVK/MoltenVK/Vulkan/mvk_datatypes.mm'
sys.path.insert(0, str(ROOT / 'build-utils/rpcs3'))
import patch_moltenvk_deferred_cache as adapter  # noqa: E402

MARK_BEGIN = '\t// RewindBox (rbx_mvk_in_pass_read_barrier_waits): the RPCS3 Core records a transition to\n'


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def body(text: str, signature: str) -> str:
    """The text between the braces of the one definition that starts with this signature."""
    require(text.count(signature) == 1, 'signature not found once: ' + signature)
    start = text.index('{', text.index(signature))
    depth = 0
    for index in range(start, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start + 1:index]
    raise SystemExit('FAIL: unbalanced ' + signature)


def objc_to_cpp(code: str) -> str:
    """Rewrite the few Objective-C message sends of the extracted encoder functions; nothing else."""
    code = re.sub(r'\[(\w+) insertDebugSignpost:@"[^"]*"\];', r'/* \1 signpost */', code)
    code = re.sub(r'\[(\w+) waitForFence:(\w+) beforeStages:(\w+)\];', r'\1->waitForFence(\2, \3);', code)
    code = re.sub(r'\[(\w+) waitForFence:(\w+)\];', r'\1->waitForFence(\2, 0);', code)
    code = re.sub(r'\[(\w+) updateFence:(\w+) afterStages:(\w+)\];', r'\1->updateFence(\2, \3);', code)
    code = re.sub(r'\[(\w+) updateFence:(\w+)\];', r'\1->updateFence(\2, 0);', code)
    require(not re.search(r'\[\s*[A-Za-z_]\w*\s+[A-Za-z_]\w*(?::|\])', code), 'an Objective-C send was left in the extracted encoder code')
    return code


HARNESS = r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>
#include <random>
#include <vulkan/vulkan_core.h>
#define MVK_MACOS 0
typedef enum { kMVKBarrierStageVertex = 0, kMVKBarrierStageFragment, kMVKBarrierStageCompute, kMVKBarrierStageCopy,
               kMVKBarrierStageNone, kMVKBarrierStageCount = kMVKBarrierStageNone } MVKBarrierStage;
static const int kMVKBarrierFenceCount = 64;
typedef enum { kMVKCommandUseNone, kMVKCommandUsePipelineBarrier, kMVKCommandUseRestartSubpass, kMVKCommandUseBeginRenderPass,
               kMVKCommandUseCopyBufferToImage, kMVKCommandUseDispatch } MVKCommandUse;
typedef int MTLRenderStages;
static const MTLRenderStages MTLRenderStageVertex = 1, MTLRenderStageFragment = 2;
template <typename T, typename M> static bool mvkIsAnyFlagEnabled(T value, M mask) { return (value & mask) != 0; }
template <typename T, typename M> static bool mvkAreAllFlagsEnabled(T value, M mask) { return (value & mask) == (T)mask; }
template <typename T, typename M> static void mvkEnableFlags(T& value, M mask) { value |= mask; }
template <typename T, typename M> static void mvkDisableFlags(T& value, M mask) { value &= ~mask; }

static uint64_t mvkBarrierStagesFromPipelineStageFlags(VkPipelineStageFlags2 flags) {
@STAGES@
}

// ---- Metal model: fences and encoders --------------------------------------------------------------------------
struct Fence { int stage, slot; bool operator<(const Fence& o) const { return stage != o.stage ? stage < o.stage : slot < o.slot; }
    bool operator==(const Fence& o) const { return stage == o.stage && slot == o.slot; } };
struct Event { bool wait; Fence fence; int stages; };
struct Encoder { int id = 0; char kind = 0; std::vector<Event> events; bool ended = false; virtual ~Encoder() = default;
    void waitForFence(Fence f, int stages) { events.push_back({true, f, stages}); }
    void updateFence(Fence f, int stages) { events.push_back({false, f, stages}); } };
struct RenderEncoderModel : Encoder {}; struct BlitEncoderModel : Encoder {}; struct ComputeEncoderModel : Encoder {};
typedef RenderEncoderModel* RenderEnc; typedef BlitEncoderModel* BlitEnc; typedef ComputeEncoderModel* ComputeEnc;

struct Trace { std::vector<Encoder*> encoders; std::vector<std::shared_ptr<Encoder>> owned; int restarts = 0; };

struct BarrierFenceSlots { uint32_t updateDirtyBits = ~0u; int update[kMVKBarrierStageCount] = {}; int wait[kMVKBarrierStageCount][kMVKBarrierStageCount] = {}; };
struct EncodingContext { BarrierFenceSlots fenceSlots; };
struct MVKDeviceModel { bool residency = true; Fence getFence(MVKBarrierStage stage, int index) { return Fence{(int)stage, index}; }
    bool hasResidencySet() { return residency; }
    template <typename B, typename E> void applyMemoryBarrier(B&, E*, MVKCommandUse) {} };
typedef MVKDeviceModel MVKDevice;
struct MetalFeatures { bool memoryBarriers = false; bool tileBasedDeferredRendering = true; };
struct ResourceModel { template <typename B, typename E> void applyBufferMemoryBarrier(B&, E*, MVKCommandUse) {}
    template <typename B, typename E> void applyImageMemoryBarrier(B&, E*, MVKCommandUse) {} };
typedef ResourceModel MVKBuffer; typedef ResourceModel MVKImage;

struct MVKPipelineBarrier {
    typedef enum : uint8_t { None, Memory, Buffer, Image } MVKPipelineBarrierType;
    MVKPipelineBarrierType type = None;
    VkPipelineStageFlags2 srcStageMask = 0; VkAccessFlags2 srcAccessMask = 0;
    VkPipelineStageFlags2 dstStageMask = 0; VkAccessFlags2 dstAccessMask = 0;
    MVKBuffer* mvkBuffer = nullptr; MVKImage* mvkImage = nullptr;
    VkImageLayout newLayout = VK_IMAGE_LAYOUT_UNDEFINED;
};

static MVKBarrierStage commandUseToBarrierStage(MVKCommandUse use) {
    switch (use) { case kMVKCommandUseCopyBufferToImage: return kMVKBarrierStageCopy; case kMVKCommandUseDispatch: return kMVKBarrierStageCompute;
                   default: return kMVKBarrierStageNone; }
}

struct MVKCommandEncoder {
    Trace* trace; MVKDeviceModel* _device; EncodingContext context; EncodingContext* _pEncodingContext = &context;
    MetalFeatures features; bool argumentBuffers = true;
    RenderEnc _mtlRenderEncoder = nullptr; ComputeEnc _mtlComputeEncoder = nullptr; BlitEnc _mtlBlitEncoder = nullptr;
    MVKCommandUse _mtlComputeEncoderUse = kMVKCommandUseNone, _mtlBlitEncoderUse = kMVKCommandUseNone;
    int nextId = 0;
    MetalFeatures& getMetalFeatures() { return features; }
    bool isUsingMetalArgumentBuffers() { return argumentBuffers; }
    MVKDeviceModel* getDevice() { return _device; }
    template <typename T> T* make(char kind) { auto e = std::make_shared<T>(); e->id = nextId++; e->kind = kind;
        trace->owned.push_back(e); trace->encoders.push_back(e.get()); return e.get(); }
    // Life cycle as MVKCommandEncoder::beginMetalRenderPass / endMetalRenderEncoding / getMTLBlitEncoder / endCurrentMetalEncoding.
    void beginMetalRenderPass(MVKCommandUse use) { endCurrentMetalEncoding(); _mtlRenderEncoder = make<RenderEncoderModel>('R'); encodeBarrierWaits(use); }
    void endMetalRenderEncoding() { if (!_mtlRenderEncoder) return; encodeBarrierUpdates(); _mtlRenderEncoder->ended = true; _mtlRenderEncoder = nullptr; }
    void endCurrentMetalEncoding() { endMetalRenderEncoding(); encodeBarrierUpdates();
        if (_mtlComputeEncoder) { _mtlComputeEncoder->ended = true; _mtlComputeEncoder = nullptr; } _mtlComputeEncoderUse = kMVKCommandUseNone;
        if (_mtlBlitEncoder) { _mtlBlitEncoder->ended = true; _mtlBlitEncoder = nullptr; } _mtlBlitEncoderUse = kMVKCommandUseNone; }
    BlitEnc getMTLBlitEncoder(MVKCommandUse use) { bool needWaits = false;
        if (!_mtlBlitEncoder) { needWaits = true; endCurrentMetalEncoding(); _mtlBlitEncoder = make<BlitEncoderModel>('B'); }
        if (_mtlBlitEncoderUse != use) { needWaits = true; _mtlBlitEncoderUse = use; }
        if (needWaits) encodeBarrierWaits(use); return _mtlBlitEncoder; }
    void encodeStoreActions(bool) {}
    void restartPass() { trace->restarts++; }

    // ---- extracted from MVKCommandBuffer.mm (Objective-C sends rewritten) ----
    void barrierWait(MVKBarrierStage stage, RenderEnc mtlEncoder, MTLRenderStages beforeStages) {@WAIT_RENDER@}
    void barrierWait(MVKBarrierStage stage, BlitEnc mtlEncoder) {@WAIT_BLIT@}
    void barrierWait(MVKBarrierStage stage, ComputeEnc mtlEncoder) {@WAIT_COMPUTE@}
    void barrierUpdate(MVKBarrierStage stage, RenderEnc mtlEncoder, MTLRenderStages afterStages) {@UPDATE_RENDER@}
    void barrierUpdate(MVKBarrierStage stage, BlitEnc mtlEncoder) {@UPDATE_BLIT@}
    void barrierUpdate(MVKBarrierStage stage, ComputeEnc mtlEncoder) {@UPDATE_COMPUTE@}
    Fence getBarrierStageFence(MVKBarrierStage stage) {@GET_FENCE@}
    void setBarrier(uint64_t sourceStageMask, uint64_t destStageMask) {@SET_BARRIER@}
    void encodeBarrierWaits(MVKCommandUse use) {@ENCODE_WAITS@}
    void encodeBarrierUpdates() {@ENCODE_UPDATES@}
};

template <size_t N, bool PATCHED>
struct MVKCmdPipelineBarrier {
    std::vector<MVKPipelineBarrier> _barriers; VkDependencyFlags _dependencyFlags = 0;
    void encode(MVKCommandEncoder* cmdEncoder);
};
template <size_t N, bool PATCHED> void MVKCmdPipelineBarrier<N, PATCHED>::encode(MVKCommandEncoder* cmdEncoder) {
    if (PATCHED) {@ENCODE_PATCHED@} else {@ENCODE_UPSTREAM@}
}

// ---- happens-before over the encoder trace ----------------------------------------------------------------------
// Node (encoder, stage): stage 0 vertex, 1 fragment, 2 compute, 3 copy. A wait on fence F is satisfied by the latest
// update of F in an earlier encoder; Metal may hoist waits to the encoder start and updates to its end.
static std::map<std::pair<int,int>, std::set<std::pair<int,int>>> graph(const Trace& t) {
    std::map<std::pair<int,int>, std::set<std::pair<int,int>>> pred;
    std::map<Fence, std::pair<int,int>> latest; // fence -> (encoder, stages mask of the update)
    for (auto* e : t.encoders) {
        for (auto& ev : e->events) if (ev.wait) {
            auto it = latest.find(ev.fence);
            if (it == latest.end()) continue;
            int from = it->second.first; int ustages = it->second.second;
            // Render update afterStages: fragment (2) or vertex (1); blit/compute updates cover their whole stage.
            std::vector<int> fromStages; Encoder* fe = t.encoders[from];
            if (fe->kind == 'R') { if (ustages & 2) fromStages.push_back(1); if (ustages & 1) fromStages.push_back(0); }
            else fromStages.push_back(fe->kind == 'B' ? 3 : 2);
            std::vector<int> toStages; if (e->kind == 'R') { if (ev.stages & 1) toStages.push_back(0); if (ev.stages & 2) toStages.push_back(1); }
            else toStages.push_back(e->kind == 'B' ? 3 : 2);
            for (int s : fromStages) for (int d : toStages) pred[{e->id, d}].insert({from, s});
        }
        for (auto& ev : e->events) if (!ev.wait) latest[ev.fence] = {e->id, ev.stages};
    }
    for (auto* e : t.encoders) if (e->kind == 'R') pred[{e->id, 1}].insert({e->id, 0}); // vertex before fragment
    return pred;
}
static bool before(const Trace& t, std::pair<int,int> a, std::pair<int,int> b) {
    auto pred = graph(t); std::vector<std::pair<int,int>> stack{b}; std::set<std::pair<int,int>> seen;
    // A fragment update also covers the vertex stage of the same encoder (fragment follows vertex).
    while (!stack.empty()) { auto n = stack.back(); stack.pop_back(); if (n == a || (n.first == a.first && a.second == 0 && n.second == 1)) return true;
        if (!seen.insert(n).second) continue; for (auto& p : pred[n]) stack.push_back(p); }
    return false;
}
static bool metal_rule(const Trace& t) {
    for (auto* e : t.encoders) { std::set<Fence> updated; for (auto& ev : e->events) if (!ev.wait) updated.insert(ev.fence);
        for (auto& ev : e->events) if (ev.wait && updated.count(ev.fence)) return false; }
    return true;
}
// Fences an encoder waits for, with the encoder whose update satisfies each.
static std::set<std::pair<Fence,int>> satisfied_waits(const Trace& t, int encoder) {
    std::map<Fence, int> latest; std::set<std::pair<Fence,int>> out;
    for (auto* e : t.encoders) { if (e->id == encoder) { for (auto& ev : e->events) if (ev.wait) { auto it = latest.find(ev.fence);
                out.insert({ev.fence, it == latest.end() ? -1 : it->second}); } break; }
        for (auto& ev : e->events) if (!ev.wait) latest[ev.fence] = e->id; }
    return out;
}

static MVKPipelineBarrier read_transition(VkPipelineStageFlags2 src) {
    static MVKImage image; MVKPipelineBarrier b; b.type = MVKPipelineBarrier::Image; b.mvkImage = &image;
    b.srcStageMask = src; b.dstStageMask = VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT | VK_PIPELINE_STAGE_2_VERTEX_SHADER_BIT;
    b.dstAccessMask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_INPUT_ATTACHMENT_READ_BIT; b.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL; return b;
}

struct Run { Trace trace; MVKDeviceModel device; MVKCommandEncoder enc; Run() { enc.trace = &trace; enc._device = &device; } };

template <bool PATCHED> static void barrier(Run& r, std::vector<MVKPipelineBarrier> barriers, VkDependencyFlags flags = 0) {
    MVKCmdPipelineBarrier<4, PATCHED> cmd; cmd._barriers = barriers; cmd._dependencyFlags = flags; cmd.encode(&r.enc);
}
static int begin_pass(Run& r) { r.enc.beginMetalRenderPass(kMVKCommandUseBeginRenderPass); return r.enc._mtlRenderEncoder->id; }
static void end_pass(Run& r) { r.enc.endMetalRenderEncoding(); }
static int blit(Run& r) { r.enc.getMTLBlitEncoder(kMVKCommandUseCopyBufferToImage); int id = r.enc._mtlBlitEncoder->id; r.enc.endCurrentMetalEncoding(); return id; }

static int checks = 0;
#define CHECK(c, m) do { checks++; if (!(c)) { std::printf("{\"result\":\"failed\",\"check\":\"%s\"}\n", m); std::exit(1); } } while (0)

// Writer (pass A or blit E), then pass B begins, draws, then needs the image: in pass (patched) or after ending B (upstream).
template <bool PATCHED> static Trace in_pass_scenario(bool blit_writer, bool unrelated_outside_barrier, bool residency, int* reader, int* writer) {
    Run r; r.device.residency = residency;
    if (blit_writer) { begin_pass(r); end_pass(r); *writer = blit(r); }
    else { *writer = begin_pass(r); end_pass(r); }
    if (unrelated_outside_barrier) { MVKPipelineBarrier m; m.type = MVKPipelineBarrier::Memory; m.srcStageMask = VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT;
        m.dstStageMask = VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT; barrier<false>(r, {m}); }
    *reader = begin_pass(r);
    barrier<PATCHED>(r, {read_transition(blit_writer ? VK_PIPELINE_STAGE_2_TRANSFER_BIT : VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT)});
    end_pass(r);
    return r.trace;
}
// The upstream path for the same work: the barrier ends B (outside the pass) and B begins again (B').
static Trace restart_scenario(bool blit_writer, bool unrelated_outside_barrier, int* reader, int* ended) {
    Run r;
    if (blit_writer) { begin_pass(r); end_pass(r); blit(r); } else { begin_pass(r); end_pass(r); }
    if (unrelated_outside_barrier) { MVKPipelineBarrier m; m.type = MVKPipelineBarrier::Memory; m.srcStageMask = VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT;
        m.dstStageMask = VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT; barrier<false>(r, {m}); }
    *ended = begin_pass(r); end_pass(r);
    barrier<false>(r, {read_transition(blit_writer ? VK_PIPELINE_STAGE_2_TRANSFER_BIT : VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT)});
    *reader = begin_pass(r); end_pass(r);
    return r.trace;
}

int main() {
    int scenarios = 0, negatives = 0, random_reads = 0, upstream_ordered = 0;
    for (int blitw = 0; blitw < 2; blitw++) for (int unrelated = 0; unrelated < 2; unrelated++) {
        int reader, writer, rr, ended;
        Trace patched = in_pass_scenario<true>(blitw, unrelated, true, &reader, &writer);
        Trace upstream = restart_scenario(blitw, unrelated, &rr, &ended);
        CHECK(metal_rule(patched), "metal rule (patched in-pass wait)");
        CHECK(before(patched, {writer, blitw ? 3 : 1}, {reader, 0}) && before(patched, {writer, blitw ? 3 : 1}, {reader, 1}),
              "writer happens before the reading pass (patched)");
        // Informational: the strict model (a wait is satisfied only by the latest update of its fence) does not
        // always order the writer before upstream's restarted pass, which waits for the ended pass's reuse of the
        // writer's fence slot; the in-pass wait is encoded before that reuse.
        if (before(upstream, {writer, blitw ? 3 : 1}, {rr, 1})) upstream_ordered++;
        // Covering: the in-pass waits include every wait of the restart (encoder ids are equal before the reader),
        // except the restart's wait for the ended pass itself, which exists only because the pass ended.
        auto a = satisfied_waits(patched, reader), b = satisfied_waits(upstream, rr);
        std::set<std::pair<Fence,int>> a_satisfied; for (auto& w : a) if (w.second >= 0) a_satisfied.insert(w);
        bool covers = true; for (auto& w : b) if (w.second >= 0 && w.second != ended && !a_satisfied.count(w)) covers = false;
        CHECK(covers, "in-pass waits cover the restart's waits minus the ended pass");
        int nr, nw; Trace unpatched = in_pass_scenario<false>(blitw, unrelated, true, &nr, &nw);
        CHECK(!before(unpatched, {nw, blitw ? 3 : 1}, {nr, 1}), "negative control: upstream in-pass barrier orders nothing");
        negatives++;
        int r2, w2; Trace noresidency = in_pass_scenario<true>(blitw, unrelated, false, &r2, &w2);
        int r3, w3; Trace noresidency_up = in_pass_scenario<false>(blitw, unrelated, false, &r3, &w3);
        CHECK(noresidency.encoders.size() == noresidency_up.encoders.size(), "no residency set: patched path not taken");
        for (size_t i = 0; i < noresidency.encoders.size(); i++) CHECK(noresidency.encoders[i]->events.size() == noresidency_up.encoders[i]->events.size(), "no residency set: same events");
        scenarios++;
    }
    // Scope: other in-pass barriers are encoded as upstream.
    for (int kind = 0; kind < 4; kind++) {
        Run p, u;
        for (Run* r : {&p, &u}) { begin_pass(*r); end_pass(*r); begin_pass(*r); }
        MVKPipelineBarrier b = read_transition(VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT);
        VkDependencyFlags flags = 0;
        if (kind == 0) b.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        if (kind == 1) { b.type = MVKPipelineBarrier::Buffer; b.mvkImage = nullptr; static MVKBuffer buf; b.mvkBuffer = &buf; }
        if (kind == 2) b.type = MVKPipelineBarrier::Memory;
        if (kind == 3) b.newLayout = VK_IMAGE_LAYOUT_GENERAL;
        barrier<true>(p, {b}, flags); barrier<false>(u, {b}, flags);
        end_pass(p); end_pass(u);
        CHECK(p.trace.encoders.size() == u.trace.encoders.size(), "other barriers: same encoders");
        for (size_t i = 0; i < p.trace.encoders.size(); i++) {
            CHECK(p.trace.encoders[i]->events.size() == u.trace.encoders[i]->events.size(), "other barriers: same events");
            for (size_t k = 0; k < p.trace.encoders[i]->events.size(); k++) {
                auto& x = p.trace.encoders[i]->events[k]; auto& y = u.trace.encoders[i]->events[k];
                CHECK(x.wait == y.wait && !(x.fence < y.fence) && !(y.fence < x.fence) && x.stages == y.stages, "other barriers: identical events");
            }
        }
        // A mixed barrier (a read transition with anything else) is encoded as upstream too.
        Run pm, um; for (Run* r : {&pm, &um}) { begin_pass(*r); end_pass(*r); begin_pass(*r); }
        barrier<true>(pm, {read_transition(VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT), b}); barrier<false>(um, {read_transition(VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT), b});
        end_pass(pm); end_pass(um);
        size_t ep = 0, eu = 0; for (auto* e : pm.trace.encoders) ep += e->events.size(); for (auto* e : um.trace.encoders) eu += e->events.size();
        CHECK(ep == eu, "mixed barrier encoded as upstream");
    }
    // Randomized sequences.
    std::mt19937 rng(655);
    for (int round = 0; round < 3000; round++) {
        Run r; int steps = 6 + rng() % 30; bool open = false;
        for (int s = 0; s < steps; s++) {
            int op = rng() % 6;
            if (op == 0) { if (open) end_pass(r); begin_pass(r); open = true; }
            else if (op == 1 && open) { end_pass(r); open = false; }
            else if (op == 2) { if (open) { end_pass(r); open = false; } blit(r); }
            else if (op == 3 && !open) { barrier<false>(r, {read_transition(rng() % 2 ? VK_PIPELINE_STAGE_2_TRANSFER_BIT : VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT)}); }
            else if (op == 4 && open) {
                // The source: the most recent ended encoder of the barrier's source kind (if any) must happen before this pass.
                bool from_blit = rng() % 2; int writer = -1;
                for (auto* e : r.trace.encoders) if (e->ended && e->kind == (from_blit ? 'B' : 'R')) writer = e->id;
                int reader = r.enc._mtlRenderEncoder->id;
                barrier<true>(r, {read_transition(from_blit ? VK_PIPELINE_STAGE_2_TRANSFER_BIT : VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT)});
                CHECK(metal_rule(r.trace), "metal rule (random)");
                if (writer >= 0) { CHECK(before(r.trace, {writer, from_blit ? 3 : 1}, {reader, 1}), "random: latest writer happens before the reading pass"); random_reads++; }
            }
        }
        if (open) end_pass(r);
        CHECK(metal_rule(r.trace), "metal rule after the sequence");
    }
    std::printf("{\"result\":\"passed\",\"checks\":%d,\"scenarios\":%d,\"negativeControls\":%d,\"randomReads\":%d,\"upstreamRestartOrderedStrictModel\":%d}\n", checks, scenarios, negatives, random_reads, upstream_ordered);
    return 0;
}
'''


def build_harness(source: Path) -> str:
    pipeline = (source / PIPELINE).read_text()
    buffer = (source / BUFFER).read_text()
    datatypes = (source / DATATYPES).read_text()
    encode = body(pipeline, 'void MVKCmdPipelineBarrier<N>::encode(MVKCommandEncoder* cmdEncoder) {')
    require(encode.count(MARK_BEGIN) == 1, 'the RewindBox block is in the patched encode body exactly once')
    start = encode.index(MARK_BEGIN)
    end = encode.index('\tMVKDevice* mvkDvc = cmdEncoder->getDevice();')
    upstream = encode[:start] + encode[end:]
    upstream = upstream.replace('\tbool rbxRenderpassRestarted = false;\n', '').replace('\t\t\trbxRenderpassRestarted = true;\n', '')
    require('rbx' not in upstream, 'the upstream body still holds RewindBox code')
    adapt = lambda code: code.replace('cmdEncoder->beginMetalRenderPass(kMVKCommandUseRestartSubpass);',
                                      'cmdEncoder->beginMetalRenderPass(kMVKCommandUseRestartSubpass); cmdEncoder->restartPass();')
    stages = body(datatypes, 'uint64_t mvkBarrierStagesFromPipelineStageFlags(VkPipelineStageFlags2 flags) {')
    pieces = {
        '@WAIT_RENDER@': body(buffer, 'void MVKCommandEncoder::barrierWait(MVKBarrierStage stage, id<MTLRenderCommandEncoder> mtlEncoder, MTLRenderStages beforeStages) {'),
        '@WAIT_BLIT@': body(buffer, 'void MVKCommandEncoder::barrierWait(MVKBarrierStage stage, id<MTLBlitCommandEncoder> mtlEncoder) {'),
        '@UPDATE_RENDER@': body(buffer, 'void MVKCommandEncoder::barrierUpdate(MVKBarrierStage stage, id<MTLRenderCommandEncoder> mtlEncoder, MTLRenderStages afterStages) {'),
        '@UPDATE_BLIT@': body(buffer, 'void MVKCommandEncoder::barrierUpdate(MVKBarrierStage stage, id<MTLBlitCommandEncoder> mtlEncoder) {'),
        '@WAIT_COMPUTE@': body(buffer, 'void MVKCommandEncoder::barrierWait(MVKBarrierStage stage, id<MTLComputeCommandEncoder> mtlEncoder) {'),
        '@UPDATE_COMPUTE@': body(buffer, 'void MVKCommandEncoder::barrierUpdate(MVKBarrierStage stage, id<MTLComputeCommandEncoder> mtlEncoder) {'),
        '@GET_FENCE@': body(buffer, 'id<MTLFence> MVKCommandEncoder::getBarrierStageFence(MVKBarrierStage stage) {'),
        '@SET_BARRIER@': body(buffer, 'void MVKCommandEncoder::setBarrier(uint64_t sourceStageMask, uint64_t destStageMask) {'),
        '@ENCODE_WAITS@': body(buffer, 'void MVKCommandEncoder::encodeBarrierWaits(MVKCommandUse use) {'),
        '@ENCODE_UPDATES@': body(buffer, 'void MVKCommandEncoder::encodeBarrierUpdates() {'),
    }
    text = HARNESS.replace('@STAGES@', stages).replace('@ENCODE_PATCHED@', adapt(encode)).replace('@ENCODE_UPSTREAM@', adapt(upstream))
    for key, code in pieces.items():
        text = text.replace(key, objc_to_cpp(code))
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('source', type=Path, help='patched MoltenVK checkout (root holding MoltenVK/MoltenVK)')
    parser.add_argument('--cxx', default=shutil.which('clang++') or 'g++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    actual = adapter.fingerprints(source)
    require(actual == adapter.POSTIMAGES, 'the MoltenVK checkout is not the reviewed patched source: ' +
            str([p for p in adapter.POSTIMAGES if actual[p] != adapter.POSTIMAGES[p]]))
    text = build_harness(source)
    with tempfile.TemporaryDirectory(prefix='mvk-in-pass-read-') as temporary:
        work = Path(temporary)
        (work / 'harness.cpp').write_text(text)
        compile_ = subprocess.run([args.cxx, '-std=c++17', '-O1', '-Wall', '-Wno-unused-variable', '-Wno-unused-function',
                                   '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I', str(VULKAN_INCLUDE),
                                   str(work / 'harness.cpp'), '-o', str(work / 'harness')], capture_output=True, text=True)
        require(compile_.returncode == 0, 'harness does not compile:\n' + compile_.stderr[-4000:])
        run = subprocess.run([str(work / 'harness')], capture_output=True, text=True, timeout=600)
        require(run.returncode == 0, 'harness failed:\n' + run.stdout[-2000:] + run.stderr[-2000:])
        result = json.loads(run.stdout.strip().splitlines()[-1])
    require(result['result'] == 'passed' and result['scenarios'] == 4 and result['negativeControls'] == 4 and result['randomReads'] > 1000,
            'unexpected harness result: ' + json.dumps(result))
    require(result['upstreamRestartOrderedStrictModel'] <= 4, 'informational count out of range')
    report = dict(result='passed', harness=result, cxx=args.cxx, sanitizers=['address', 'undefined'],
                  source_postimages={PIPELINE: actual[PIPELINE]}, patch_sha256=hashlib.sha256(adapter.PATCH.read_bytes()).hexdigest(),
                  extracted=['MVKCmdPipelineBarrier<N>::encode', 'setBarrier', 'getBarrierStageFence', 'barrierWait (render, blit, compute)',
                             'barrierUpdate (render, blit, compute)', 'encodeBarrierWaits', 'encodeBarrierUpdates', 'mvkBarrierStagesFromPipelineStageFlags'],
                  metal_model='fence wait satisfied by the latest earlier update; waits may hoist to the encoder start',
                  metal_device=False, iphone_tested=False, fps_gain_claimed=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: MoltenVK in-pass read transitions wait for every fence a pass restart would (but the ended pass), the writer happens '
          'before the reading pass (the upstream in-pass barrier does not), no encoder waits for its own fence, other '
          'barriers are encoded as upstream: ' + json.dumps(result))


if __name__ == '__main__':
    main()
