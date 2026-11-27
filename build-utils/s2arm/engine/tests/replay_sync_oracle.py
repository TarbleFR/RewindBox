"""Fence order for the fixed NVN replay scene; command counts alone cannot prove these dependencies."""
import hashlib


# Frame work ordinals from record_frame: shadow, MRT, compute, lighting, downsample x2, composite/UI.
# Each Metal 3 encoder waits on the shared fence before its work, then publishes after its work.
# Render stage bits: vertex=1, fragment=2. The compute path uses the no-stage fence form.
PASSES = ((0, 64, 1), (64, 320, 1), (320, 321, None), (321, 338, 1),
          (338, 339, 2), (339, 340, 2), (340, 373, 2))


def split_pair(events, index, wait, update):
    if index + 1 >= len(events):
        return False
    at = events[index][0]
    stage = next((mask for first, last, mask in PASSES if first < at < last), None)
    return stage is not None and events[index:index+2] == [(at, update, 1, 3), (at, wait, 1, 1)]


def canonical_event(event, cuts, wait, fixed):
    # An adaptive cut in the MRT pass can shift the next budget boundary to
    # the first downsample. A fresh CB waits from vertex there, which also
    # covers the normal fragment dependency. Fixed work compares exact stages.
    if not fixed and cuts and event == (338, wait, 1, 1):
        return (338, wait, 1, 2)
    return event


def check_events(events, cuts, wait, update, backend, fixed):
    if fixed and cuts:
        raise ValueError("fixed-work profile split a render pass")
    if backend != "Metal3":
        if cuts:
            raise ValueError("unclassified split on this backend")
        return set()
    golden = []
    for first, last, stage in PASSES:
        golden.extend([(first, wait, 0), (last, update, 0)] if stage is None else
                      [(first, wait, 1, stage), (last, update, 1, 3)])
    extras = set()
    core = []
    i = 0
    while i < len(events):
        if split_pair(events, i, wait, update):
            extras.add(i)
            i += 2
        else:
            core.append(canonical_event(events[i], cuts, wait, fixed))
            i += 1
    # With inter-pass cuts disabled, shadow -> MRT (guest barrier 0x12) can
    # wait before the fragment stage in the same CB. Fixed runs still compare
    # every exact operand and every opcode with the fixed baseline.
    if fixed and len(core) == len(golden) and core[2] == (64, wait, 1, 2):
        golden[2] = core[2]
    if core != golden or len(extras) != cuts:
        raise ValueError(f"required fence sequence or authenticated split count differs: {core}, {len(extras)}/{cuts}")
    return extras


def sync_rows(log, frames):
    types = [s for s in log.splitlines() if s.startswith("SYNCOPS ")]
    if len(types) != 1:
        raise ValueError("missing synchronization opcode map")
    wait, update = map(int, types[0].split()[1:])
    rows = []
    for line in log.splitlines():
        if line.startswith("SYNCFRAME "):
            _, f, cuts, *words = line.split()
            if int(f) != len(rows)+1:
                raise ValueError("missing or reordered frame")
            rows.append((int(cuts), [tuple(map(int, w.split("/"))) for w in words]))
    if len(rows) != frames:
        raise ValueError("incomplete synchronization frame sample")
    return wait, update, rows


def canonical_trace(path, rows, extras, wait, fixed):
    """Erase only justified close/reopen pairs after verifying the same attachments are reopened."""
    data = path.read_text().splitlines()
    canonical = []
    frame = event = work = 0
    attachments = None
    i = 0
    while i < len(data):
        line = data[i]
        tag = line.split()[0]
        if tag == "F":
            if frame and event != len(rows[frame-1][1]):
                raise ValueError("missing diagnostic sync records")
            frame += 1
            if line != f"F {frame}" or frame > len(rows):
                raise ValueError("invalid diagnostic frame")
            event = work = 0
            attachments = None
        elif tag == "P":
            attachments = [item.split(":")[0] for item in line.split()[1:]]
        elif tag in ("D", "K"):
            work += 1
        elif tag == "S":
            cuts, events = rows[frame-1]
            if event >= len(events) or (work, *map(int, line.split()[1:])) != events[event]:
                raise ValueError("diagnostic trace differs from compact sync record")
            if event in extras[frame-1]:
                following = data[i+1:i+4]
                if (len(following) != 3 or following[0] != "E" or not following[1].startswith("P ") or
                        not following[2].startswith("S ") or not attachments or
                        [v.split(":")[0] for v in following[1].split()[1:]] != attachments or
                        any(v.split(":")[1] != "1" for v in following[1].split()[1:]) or
                        (work, *map(int, following[2].split()[1:])) != events[event+1]):
                    raise ValueError("extra fence pair does not close and reopen the same render attachments")
                event += 2
                i += 4
                continue
            line = "S " + " ".join(map(str, canonical_event(events[event], cuts, wait, fixed)[1:]))
            event += 1
        elif tag != "E":
            raise ValueError(f"unexpected diagnostic record {line}")
        canonical.append(line)
        i += 1
    if frame != len(rows) or event != len(rows[-1][1]):
        raise ValueError("incomplete diagnostic trace")
    return hashlib.sha256(("\n".join(canonical)+"\n").encode()).hexdigest()


def verify_negative_controls():
    wait, update = 49, 50
    source = []
    for first, last, stage in PASSES:
        source += [(first, wait, 0), (last, update, 0)] if stage is None else [
            (first, wait, 1, stage), (last, update, 1, 3)]
    pair = [(128, update, 1, 3), (128, wait, 1, 1)]
    sample = source[:3] + pair + source[3:]
    if check_events(sample, 1, wait, update, "Metal3", False) != {3}:
        raise ValueError("valid additional split rejected")
    conservative = [(338, wait, 1, 1) if event == (338, wait, 1, 2) else event for event in sample]
    if check_events(conservative, 1, wait, update, "Metal3", False) != {3}:
        raise ValueError("conservative downsample wait after an adaptive split rejected")
    unexpected_stage = [(338, wait, 1, 3) if event == (338, wait, 1, 1) else event for event in conservative]
    uncut_conservative = conservative[:3] + conservative[5:]
    for events, count, fixed in [(source[1:], 0, False), (source[1::-1]+source[2:], 0, False),
                                 ([(0, wait, 1, 2)]+source[1:], 0, False),
                                 (sample, 0, False), (sample, 1, True),
                                 (source[:3]+pair[::-1]+source[3:], 1, False),
                                 (source[:3]+[pair[0], (129, wait, 1, 1)]+source[3:], 1, False),
                                 (source[:3]+[(128, update, 1, 1), pair[1]]+source[3:], 1, False),
                                 (unexpected_stage, 1, False), (uncut_conservative, 0, False),
                                 (uncut_conservative, 0, True)]:
        try:
            check_events(events, count, wait, update, "Metal3", fixed)
        except ValueError:
            continue
        raise ValueError("malformed dependency fixture was accepted")
