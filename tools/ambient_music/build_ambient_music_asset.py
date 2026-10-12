#!/usr/bin/env python3
"""Build NeoStation's ambient music loop from the published MP3 (reproducible).

Source: "Once Upon a Time (loop)" by TAD, OpenGameArt, CC0 1.0
(https://opengameart.org/content/once-upon-a-time-loop). The MP3 was made
by GarageBand/iTunes and carries an `iTunSMPB` gapless tag: 528 samples of
encoder priming, 2 539 957 samples of music, 1 979 samples of padding. A
decoder that ignores the tag (dr_mp3, used by SoLoud, does not read
iTunSMPB) would play the priming and the padding at every loop: a silence
and a click. This tool therefore cuts exactly the music samples out of the
MP3 and re-encodes them in a container whose length is exact (Ogg Vorbis
records the last sample in its final granule position), so the decoder has
nothing to guess.

Steps (all checked):
1. the MP3 is the published file (SHA-256);
2. it is decoded to 32-bit float PCM by ffmpeg, without any gapless
   processing (ffmpeg keeps the MP3 decoder's 529-sample delay);
3. the music starts after 528 + 529 samples and lasts 2 539 957 samples
   (iTunSMPB), which the signal confirms (first sample above -40 dBFS);
4. the loop seam (last sample -> first sample) is a step of about -29 dBFS
   in the original: the end of the music is cut mid-wave while the first
   beat starts. The first 32 samples (0.73 ms) are cross-faded, at equal
   power, from a linear-prediction continuation of the end (Burg, order 32)
   into the original start. The length (and so the tempo and the bars) is
   unchanged, nothing else is modified;
5. the result is quantized to 16-bit stereo 44.1 kHz with triangular
   dither from a fixed seed (reproducible), kept as a lossless FLAC
   intermediate, then encoded as Ogg Vorbis quality 8.

Why Ogg Vorbis and not PCM: NeoStation streams the loop from disk
(SoLoud `LoadMode.disk`, a few kilobytes of memory instead of ~20 MB of
float samples). In SoLoud 4.0.12's streaming path, WAV and FLAC loops are
wrong for up to 512 samples around every seam (the decode buffer is not
realigned on rewind), while Ogg Vorbis loops exactly: measured by
test/ambient_music_loop_test.py, which renders 21 loops (20 min 10 s)
through SoLoud's own mixer. Vorbis keeps the exact length (final granule
position) and the smoothed seam.

The measures printed by `--report` are those of docs/ambient-music-build448.md.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SOURCE_SHA256 = '20c5f05efcf9fd973c4eda5d9d4f214a64ae81e0dbc4e4cd1356b1b41475e280'
SAMPLE_RATE = 44100
PRIMING = 0x210          # iTunSMPB encoder delay
DECODER_DELAY = 529      # MPEG-1 Layer III synthesis delay kept by ffmpeg
LOOP_FRAMES = 0x26C1B5   # iTunSMPB original sample count (2 539 957)
PADDING = 0x7BB          # iTunSMPB padding (1 979)
SEAM_FADE = 32           # samples cross-faded at the start of the loop
LPC_ORDER = 32
LPC_FIT = 1024
DITHER_SEED = 448
VORBIS_QUALITY = 8


def decode(mp3: Path) -> np.ndarray:
    raw = subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(mp3), '-f', 'f32le', '-acodec', 'pcm_f32le',
         '-ac', '2', '-ar', str(SAMPLE_RATE), '-'],
        check=True, stdout=subprocess.PIPE).stdout
    return np.frombuffer(raw, dtype='<f4').reshape(-1, 2).astype(np.float64)


def burg(signal: np.ndarray, order: int) -> np.ndarray:
    forward = signal.copy()
    backward = signal.copy()
    a = np.zeros(order + 1)
    a[0] = 1.0
    for m in range(1, order + 1):
        f = forward[m:]
        b = backward[m - 1:-1]
        denominator = np.dot(f, f) + np.dot(b, b)
        k = -2.0 * np.dot(f, b) / denominator if denominator > 0 else 0.0
        previous = a.copy()
        for i in range(1, m + 1):
            a[i] = previous[i] + k * previous[m - i]
        forward[m:], backward[m:] = f + k * b, b + k * f
    return a


def extrapolate(history: np.ndarray, count: int) -> np.ndarray:
    a = burg(history[-LPC_FIT:], LPC_ORDER)
    buffer = list(history[-LPC_ORDER:])
    out = []
    for _ in range(count):
        value = -sum(a[k] * buffer[-k] for k in range(1, LPC_ORDER + 1))
        out.append(value)
        buffer.append(value)
    return np.array(out)


def seam_fix(loop: np.ndarray) -> np.ndarray:
    fixed = loop.copy()
    t = (np.arange(SEAM_FADE) + 0.5) / SEAM_FADE
    rise = np.sin(0.5 * np.pi * t)
    fall = np.cos(0.5 * np.pi * t)
    for channel in range(loop.shape[1]):
        continuation = extrapolate(loop[:, channel], SEAM_FADE)
        fixed[:SEAM_FADE, channel] = loop[:SEAM_FADE, channel] * rise + continuation * fall
    return fixed


def to_pcm16(samples: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(DITHER_SEED)
    lsb = 1.0 / 32768.0
    dither = (rng.random(samples.shape) - rng.random(samples.shape)) * lsb
    return np.clip(np.round((samples + dither) * 32767.0), -32768, 32767).astype('<i2')


def seam_transient_db(loop: np.ndarray, window: int = 64) -> tuple:
    """High-passed energy of the seam against the surrounding second."""
    context = np.concatenate([loop[-SAMPLE_RATE // 2:], loop[:SAMPLE_RATE // 2]])
    hp = context[2:] - 2 * context[1:-1] + context[:-2]
    centre = SAMPLE_RATE // 2 - 1

    def energy(c):
        segment = hp[c - window // 2:c + window // 2]
        return float((segment ** 2).sum())

    seam = energy(centre)
    reference = np.array([energy(c) for c in range(window, len(hp) - window, window // 2) if abs(c - centre) >= 2 * window])
    return 10 * np.log10(seam / np.median(reference)), 10 * np.log10(seam / np.percentile(reference, 90))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    data = args.source.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise SystemExit('Unexpected source MP3 (SHA-256 differs)')
    decoded = decode(args.source)
    # The decoder delay shifts the stream; it adds no sample to it.
    if decoded.shape[0] != PRIMING + LOOP_FRAMES + PADDING:
        raise SystemExit(f'Unexpected decoded length {decoded.shape[0]}')
    start = PRIMING + DECODER_DELAY
    mono = np.abs(decoded.mean(axis=1))
    onset = int(np.argmax(mono > 0.01))
    if onset != start:
        raise SystemExit(f'Music onset {onset} does not match iTunSMPB start {start}')
    loop = decoded[start:start + LOOP_FRAMES]
    before = seam_transient_db(loop)
    fixed = seam_fix(loop)
    after = seam_transient_db(fixed)
    pcm = to_pcm16(fixed)
    changed = np.flatnonzero(np.any(np.abs(fixed - loop) > 0, axis=1))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    lossless = args.output.with_suffix('.flac')
    subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 's16le', '-ar', str(SAMPLE_RATE), '-ac', '2',
         '-i', '-', '-map_metadata', '-1', '-fflags', '+bitexact', '-flags:a', '+bitexact', '-c:a', 'flac',
         '-compression_level', '8', str(lossless)],
        input=pcm.tobytes(), check=True)
    subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(lossless), '-map_metadata', '-1',
         '-fflags', '+bitexact', '-flags:a', '+bitexact', '-c:a', 'libvorbis', '-q:a', str(VORBIS_QUALITY),
         '-metadata', 'title=Once Upon a Time (loop)', '-metadata', 'artist=TAD',
         '-metadata', 'copyright=CC0 1.0 Universal (public domain dedication)',
         '-metadata', 'comment=https://opengameart.org/content/once-upon-a-time-loop', str(args.output)],
        check=True)
    lossless.unlink()
    report = {
        'sourceSha256': SOURCE_SHA256,
        'sampleRate': SAMPLE_RATE,
        'channels': 2,
        'loopFrames': LOOP_FRAMES,
        'loopSeconds': LOOP_FRAMES / SAMPLE_RATE,
        'musicStartInDecodedMp3': start,
        'seamFadeSamples': SEAM_FADE,
        'modifiedFrames': [int(changed.min()), int(changed.max())] if changed.size else [],
        'seamTransientBeforeDb': {'vsLocalMedian': round(before[0], 2), 'vsLocalP90': round(before[1], 2)},
        'seamTransientAfterDb': {'vsLocalMedian': round(after[0], 2), 'vsLocalP90': round(after[1], 2)},
        'pcmMd5': hashlib.md5(pcm.tobytes()).hexdigest(),
        'vorbisQuality': VORBIS_QUALITY,
        'assetBytes': args.output.stat().st_size,
        'assetSha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.report:
        args.report.write_text(text + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
