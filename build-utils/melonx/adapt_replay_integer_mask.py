"""A recorded pipeline variant is replayed with the integer-format mask a draw has for its colour attachments: the mask is
recomputed by the draw's rule when the replay reads the variant, and the pipelineVariants summary counts the recomputes
(every title).

Evidence (IPA 749 / Core 030cc14f, Hogwarts Legacy, private journals, pid 12613; counts and times only):
- stderr: 3 MoltenVK warnings VK_ERROR_FEATURE_NOT_PRESENT for blending on an attachment whose format cannot blend, all
  for R16_UINT, at 04:59:22 (1) and 04:59:23 (repeated 2 times), 1.99 and 3.44 s after the process start, amid the
  startup's main-cache lookups, warm-ups and replays; none in the stderr of the SSBU sessions 12550 and 14991 (11238 has
  no stderr). Core log of 12613: replays built 2043 (compile 1494 ms, queue wait 4541 ms), refused 0, skipped 2; late
  creations left 23 (123 ms): new 20, planned not built yet 3, built but missed 0.
- Plan 748 rank 18 reads the warnings as replayed records whose AttachmentIntegerFormatMask lacks the bit of their
  R16_UINT target: the draw's rule always sets it (FramebufferParams.cs l. 145-148, PipelineConverter.cs l. 363-366,
  FormatTable.cs l. 26), so such a record's key matches no draw's key and its compile is lost (at most 3 per launch).
- What the code of this Core shows: the formats, colour slots and mask a variant records all come from the draw's one
  FramebufferParams (PipelineBase.UpdatePipelineAttachmentFormats copies formats and mask together; NoteLateVariant and
  NoteQueuedVariant write that framebuffer's slots), and the rule has not changed since the journal's schema (Core 711;
  MeloNX revision 13700519 throughout, no adapter has edited the mask since): a record any of these Cores wrote carries
  the rule's mask. The embedded MoltenVK v1.4.2 (MVKPipeline.mm l. 1980-1996, addFragmentOutputToPipeline) warns for
  every colour attachment whose Metal format cannot blend, whatever its blendEnable: a pipeline with an R16_UINT target
  warns although PipelineState.CreateGraphicsPipeline disabled its blending under MoltenVK. The same R16_UINT warning is
  in the stderr logs of earlier sessions since 7 November. The warnings therefore do not show an inconsistent record: 0
  recomputes are expected on the device and the warnings stay; the count tells whether a record with another mask exists
  at all.

Change (PipelineState.cs, PipelineCacheManager.cs; every title, replays only):
- PipelineState.TryReadVariant (its one caller is ShaderCollection's replay Schedule): once the variant is read and
  valid, the mask is recomputed from the colour formats and slots read (IntegerFormatMask: bit s for each colour
  attachment in slot s whose format is an integer format, as FramebufferParams and PipelineConverter set it). The Vulkan
  format of an attachment is FormatTable's for its GAL format (ConvertToVkFormat substitutes only depth-stencil and
  R4G4B4A4 formats), only an IsInt GAL format maps to an integer Vulkan format, and FormatTable's reverse map gives back
  a GAL format with the same IsInt (unknown formats read as B8G8R8A8Unorm, not integer): the rule is exact from the
  Vulkan formats. A mask that differs is replaced and counted (PipelineVariantJournal.IntegerMasksRecomputedTotal,
  process total); the record, its id and its bytes on disk are unchanged. A variant that fails to read is refused as
  before, uncounted.
- PipelineVariantJournal keeps that count when it is created; its summary says "integer masks recomputed N" for its
  session, after "still planned P of Q" (the "Journal: ..." sentence and every other count unchanged).
  PipelineCacheManager.cs gains no reference to another type (fixtures compile it alone).
Guest-visible behaviour: for every record this Core writes the mask read is the one recorded, so nothing changes. A
record with another mask (none expected) is replayed as its draw's own state instead of a state no draw binds: a draw
then finds it built, or its failure marker, under its own key, as for every other recorded state (the replay policy of
adapt_pipeline_variant_replay), and the pipeline it binds is the one it would have created. No log line type is added.

Bound (plan 748 rank 18, from the logs, not measured): at most 3 replay compilations per Hogwarts launch, measured on
one launch; from the code above the expected effect is none (0 recomputes). Memory: one int in the process and one per
journal.

Expected on the device: "integer masks recomputed 0" in every pipelineVariants summary (session, at pause, at close); a
nonzero count means recorded variants with another mask exist, each now replayed with the draw's key. The MoltenVK
R16_UINT warnings at the Hogwarts launch are expected to remain. Not measured on an iPhone; no FPS, launch or memory
gain claimed. Runs after every adapter of Core 030cc14f (its post-image of both files) and before adapt_nextendo_online
(other files). Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'
MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'

BASELINE = {
    STATE: '48da13bf57871582be963bc2c1386d2d5e0a241e9d2a9c2eb080d00831006d2c',  # Core 030cc14f (adapt_build_journal_load_wait)
    MANAGER: '00f924ff5a1ea08a97e9c436fd37ce41e13bb30188eec8cd403019d4c22cea43',  # Core 030cc14f (adapt_queued_variant_record)
}

# --- PipelineState.cs: a variant read and valid gets the draw's integer-format mask for its colour attachments ---
READ_OLD = '''            return ok && offset == data.Length &&
                (colorCount == 0 ? ColorBlendAttachmentStateCount == 0 : colorSlots[colorCount - 1] + 1 == ColorBlendAttachmentStateCount);
        }
'''
READ_NEW = '''            if (!ok || offset != data.Length ||
                (colorCount == 0 ? ColorBlendAttachmentStateCount != 0 : colorSlots[colorCount - 1] + 1 != ColorBlendAttachmentStateCount))
            {
                return false;
            }

            // RewindBox (adapt_replay_integer_mask): the integer-format mask a draw has for these colour attachments,
            // recomputed from the formats and slots read. A recorded mask that differs matches no draw's key; with the draw's
            // mask the replayed state is the draw's own. Counted when it differs (the record itself is unchanged).
            uint integerMask = IntegerFormatMask(formats, colorSlots[..colorCount]);

            if (integerMask != Internal.AttachmentIntegerFormatMask)
            {
                Internal.AttachmentIntegerFormatMask = integerMask;
                System.Threading.Interlocked.Increment(ref PipelineVariantJournal.IntegerMasksRecomputedTotal);
            }

            return true;
        }

        // RewindBox (adapt_replay_integer_mask): the draw's rule (FramebufferParams, PipelineConverter), bit s for each colour
        // attachment in slot s whose format is an integer format. An attachment's Vulkan format is FormatTable's for its GAL
        // format and only an IsInt GAL format maps to an integer Vulkan format, so FormatTable's reverse map tells it from the
        // Vulkan format.
        internal static uint IntegerFormatMask(ReadOnlySpan<Format> colorFormats, ReadOnlySpan<int> colorSlots)
        {
            uint mask = 0;

            for (int i = 0; i < colorSlots.Length; i++)
            {
                if (Ryujinx.Graphics.GAL.FormatExtensions.get_IsInt(FormatTable.GetFormat(colorFormats[i])))
                {
                    mask |= 1u << colorSlots[i];
                }
            }

            return mask;
        }
'''

# --- PipelineCacheManager.cs: the journal counts its session's recomputes in its summary ---
COUNT_OLD = '''        internal string Summary(string window)
        {
'''
COUNT_NEW = '''        // RewindBox (adapt_replay_integer_mask): variants read with a recomputed integer-format mask (PipelineState.
        // TryReadVariant), in this process; the summary counts those of this journal's session (read since it was created).
        internal static int IntegerMasksRecomputedTotal;
        private readonly int _integerMasksBefore = Volatile.Read(ref IntegerMasksRecomputedTotal);

        internal int IntegerMasksRecomputed => Volatile.Read(ref IntegerMasksRecomputedTotal) - _integerMasksBefore;

        internal string Summary(string window)
        {
'''

SUMMARY_OLD = '''                    $"{_inFlight}, still planned {planned} of {Planned}. Journal: {_records.Count} of {MaxRecords} states, given up for " +
'''
SUMMARY_NEW = '''                    $"{_inFlight}, still planned {planned} of {Planned}, integer masks recomputed {IntegerMasksRecomputed}. " +
                    $"Journal: {_records.Count} of {MaxRecords} states, given up for " + // RewindBox (adapt_replay_integer_mask)
'''

EDITS = {
    STATE: ((READ_OLD, READ_NEW),),
    MANAGER: ((COUNT_OLD, COUNT_NEW), (SUMMARY_OLD, SUMMARY_NEW)),
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in EDITS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
