// Renders NeoStation's ambient loop through SoLoud's own mixer (the
// flutter_soloud sources resolved by `flutter pub get`, null driver, the
// app's init parameters) and checks every rendered sample against the asset
// decoded once in memory: no gap, no repeat, no click at any seam.
//
// Modes (one JSON line per run on stdout, exit status 1 on any mismatch):
//   loop <file> <loops> <block>  streamed (LoadMode.disk -> WavStream) and
//                                in memory (Wav), mixed in calls of <block>
//                                frames (the app's 2048, or odd sizes so a
//                                seam falls inside, at the start and at the
//                                end of a mix call);
//   seek <file> <loops> 2048     streamed, started at several positions the
//                                way HomeMusicService resumes after a game
//                                (paused voice, seek, unpause), then across
//                                the seams.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "soloud.h"
#include "soloud_wav.h"
#include "soloud_wavstream.h"

namespace {

constexpr unsigned kRate = 44100;

struct Result {
  double gain[2] = {0, 0};
  double worst = 0;
  unsigned long long worstAt = 0;
  unsigned long long longestSilentRun = 0;
};

// out[n] must equal gain * ref[(offset + n - 1) mod frames]: SoLoud's mixer
// delays a voice by one sample and applies the centre pan gain.
Result compare(SoLoud::Soloud &engine, const float *ref, unsigned frames, unsigned long long offset,
               unsigned long long total, unsigned block) {
  Result result;
  std::vector<float> out(block * 2);
  double fitNum[2] = {0, 0}, fitDen[2] = {0, 0};
  unsigned long long done = 0, zeroRun = 0;
  const unsigned long long fitStart = kRate, fitEnd = 2 * kRate;
  while (done < total) {
    const unsigned count = (unsigned)std::min<unsigned long long>(block, total - done);
    engine.mix(out.data(), count);
    for (unsigned i = 0; i < count; i++) {
      const unsigned long long n = done + i;
      for (int c = 0; c < 2; c++) {
        const double expected = n == 0 ? 0.0 : ref[c * frames + ((offset + n - 1) % frames)];
        const double got = out[i * 2 + c];
        if (n >= fitStart && n < fitEnd) {
          fitNum[c] += got * expected;
          fitDen[c] += expected * expected;
        }
        if (n == fitEnd && c == 0) {
          result.gain[0] = fitNum[0] / fitDen[0];
          result.gain[1] = fitNum[1] / fitDen[1];
        }
        if (n >= fitEnd) {
          const double error = std::fabs(got - result.gain[c] * expected);
          if (error > result.worst) {
            result.worst = error;
            result.worstAt = n;
          }
        }
      }
      const bool silent = out[i * 2] == 0.0f && out[i * 2 + 1] == 0.0f;
      zeroRun = silent ? zeroRun + 1 : 0;
      result.longestSilentRun = std::max(result.longestSilentRun, zeroRun);
    }
    done += count;
  }
  return result;
}

bool init(SoLoud::Soloud &engine) {
  // The app's SoLoud.init(): 44.1 kHz, 2048 frames, stereo. Clipping is
  // disabled so the comparison sees the voice exactly.
  if (engine.init(0, SoLoud::Soloud::NULLDRIVER, kRate, 2048, 2) != SoLoud::SO_NO_ERROR) return false;
  engine.setPostClipScaler(1.0f);
  return true;
}

int runLoop(const char *path, bool stream, unsigned loops, unsigned block) {
  SoLoud::Soloud engine;
  if (!init(engine)) return 2;
  SoLoud::Wav reference;
  if (reference.load(path) != SoLoud::SO_NO_ERROR) return 2;
  const unsigned frames = reference.mSampleCount;
  SoLoud::Wav memory;
  SoLoud::WavStream disk;
  SoLoud::AudioSource *source = nullptr;
  if (stream) {
    if (disk.load(path) != SoLoud::SO_NO_ERROR) return 2;
    source = &disk;
  } else {
    if (memory.load(path) != SoLoud::SO_NO_ERROR) return 2;
    source = &memory;
  }
  // flutter_soloud's play(looping: true, loopingStartAt: Duration.zero).
  const SoLoud::handle voice = engine.play(*source, 1.0f, 0.0f, false, 0);
  engine.setLooping(voice, true);
  engine.setLoopPoint(voice, 0.0);
  const unsigned long long total = (unsigned long long)frames * loops;
  const Result r = compare(engine, reference.mData, frames, 0, total, block);
  const unsigned loopCount = engine.getLoopCount(voice);
  std::printf(
      "{\"mode\":\"loop\",\"source\":\"%s\",\"block\":%u,\"frames\":%u,\"loopsRendered\":%u,"
      "\"loopCountReported\":%u,\"seconds\":%.3f,\"gainL\":%.9f,\"gainR\":%.9f,\"worstAbsError\":%.3e,"
      "\"worstAtFrame\":%llu,\"longestSilentRun\":%llu}\n",
      stream ? "disk" : "memory", block, frames, loops, loopCount, total / (double)kRate, r.gain[0],
      r.gain[1], r.worst, r.worstAt, r.longestSilentRun);
  engine.deinit();
  return r.worst < 1e-6 ? 0 : 1;
}

// Finds where a seek landed: the offset whose first rendered samples match
// the reference (the decoder may land a few samples from the request).
long long alignment(const float *rendered, unsigned count, const float *ref, unsigned frames,
                    long long requested) {
  const double gain = std::sqrt(0.5);
  for (long long delta = 0; delta <= 8192; delta++) {
    for (int sign : {1, -1}) {
      const long long candidate = requested + sign * delta;
      if (candidate < 0 || candidate >= (long long)frames) continue;
      bool match = true;
      for (unsigned n = 1; n < count && match; n++) {
        for (int c = 0; c < 2 && match; c++) {
          const double expected = gain * ref[c * frames + ((candidate + n - 1) % frames)];
          match = std::fabs(rendered[n * 2 + c] - expected) < 1e-5;
        }
      }
      if (match) return candidate;
      if (delta == 0) break;
    }
  }
  return -1;
}

int runSeek(const char *path, unsigned loops) {
  SoLoud::Wav reference;
  {
    SoLoud::Soloud probe;
    if (!init(probe)) return 2;
    if (reference.load(path) != SoLoud::SO_NO_ERROR) return 2;
    probe.deinit();
  }
  const unsigned frames = reference.mSampleCount;
  int status = 0;
  // A resume at the start, in the middle, and half a second before the seam.
  for (double seconds : {0.0, 23.25, frames / (double)kRate - 0.5}) {
    SoLoud::Soloud engine;
    if (!init(engine)) return 2;
    SoLoud::WavStream disk;
    if (disk.load(path) != SoLoud::SO_NO_ERROR) return 2;
    // HomeMusicService: play(paused: true, looping: true), seek, unpause.
    const SoLoud::handle voice = engine.play(disk, 1.0f, 0.0f, true, 0);
    engine.setLooping(voice, true);
    engine.setLoopPoint(voice, 0.0);
    if (seconds > 0) engine.seek(voice, seconds);
    engine.setPause(voice, false);
    // The first 256 frames locate the landing point; a second engine
    // replays the same sequence so the comparison starts at frame 0.
    std::vector<float> head(256 * 2);
    engine.mix(head.data(), 256);
    const long long requested = (long long)std::floor(seconds * kRate);
    const long long landed = alignment(head.data(), 256, reference.mData, frames, requested);
    engine.deinit();
    if (landed < 0) {
      std::printf("{\"mode\":\"seek\",\"requestedFrame\":%lld,\"landedFrame\":null}\n", requested);
      status = 1;
      continue;
    }
    SoLoud::Soloud replay;
    if (!init(replay)) return 2;
    SoLoud::WavStream again;
    if (again.load(path) != SoLoud::SO_NO_ERROR) return 2;
    const SoLoud::handle second = replay.play(again, 1.0f, 0.0f, true, 0);
    replay.setLooping(second, true);
    replay.setLoopPoint(second, 0.0);
    if (seconds > 0) replay.seek(second, seconds);
    replay.setPause(second, false);
    const unsigned long long total = (unsigned long long)frames * loops;
    const Result r = compare(replay, reference.mData, frames, (unsigned long long)landed, total, 2048);
    const unsigned loopCount = replay.getLoopCount(second);
    std::printf(
        "{\"mode\":\"seek\",\"requestedFrame\":%lld,\"landedFrame\":%lld,\"frames\":%u,"
        "\"loopsRendered\":%u,\"loopCountReported\":%u,\"gainL\":%.9f,\"gainR\":%.9f,"
        "\"worstAbsError\":%.3e,\"worstAtFrame\":%llu,\"longestSilentRun\":%llu}\n",
        requested, landed, frames, loops, loopCount, r.gain[0], r.gain[1], r.worst, r.worstAt,
        r.longestSilentRun);
    replay.deinit();
    if (r.worst >= 1e-6) status = 1;
  }
  return status;
}

}  // namespace

int main(int argc, char **argv) {
  if (argc != 5) {
    std::fprintf(stderr, "usage: %s loop|seek <file> <loops> <block>\n", argv[0]);
    return 2;
  }
  const unsigned loops = (unsigned)std::atoi(argv[3]);
  const unsigned block = (unsigned)std::atoi(argv[4]);
  if (loops == 0 || block == 0) return 2;
  if (std::strcmp(argv[1], "seek") == 0) return runSeek(argv[2], loops);
  if (std::strcmp(argv[1], "loop") != 0) return 2;
  int status = runLoop(argv[2], true, loops, block);
  status |= runLoop(argv[2], false, loops, block);
  return status;
}
