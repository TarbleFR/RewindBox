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


def strengthened_waits(events, wait, update, backend, fixed):
    # Scene-specific: lighting writes t_light, then fs_down reads it through handle 3
    # into t_half. The guest requests ORDER_FRAGMENTS | INVALIDATE_TEXTURE (0x12).
    # A 64-draw segment begun inside the G-buffer can first become due between
    # passes at this transition: work 320 is still too early and 338 includes one dispatch.
    # sub_cut -> rb_new_main_cb clears g_last_end_relaxed; m3_wait then holds
    # the new render encoder before vertex instead of only before fragment.
    if fixed or backend != "Metal3" or len(events) != 16:
        return {}
    cuts = [events[i][0] for i in range(len(events)) if split_pair(events, i, wait, update)]
    if len(cuts) != 1 or not (64 < cuts[0] < 320 and 320 - cuts[0] < 64 <= 337 - cuts[0]):
        return {}
    transition = [(338, update, 1, 3), (338, wait, 1, 1),
                  (339, update, 1, 3), (339, wait, 1, 2)]
    for i in range(len(events)-3):
        if events[i:i+4] == transition:
            return {i+1: (338, wait, 1, 2)}
    return {}


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
    strengthened = strengthened_waits(events, wait, update, backend, fixed)
    core = []
    i = 0
    while i < len(events):
        if split_pair(events, i, wait, update):
            extras.add(i)
            i += 2
        else:
            core.append(strengthened.get(i, events[i]))
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


def canonical_trace(path, rows, extras, strengthened):
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
            events = rows[frame-1][1]
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
            if event in strengthened[frame-1]:
                line = "S " + " ".join(map(str, strengthened[frame-1][event][1:]))
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
    late_cut = [(266, update, 1, 3), (266, wait, 1, 1)]
    strong = source[:3] + late_cut + source[3:]
    strong[10] = (338, wait, 1, 1)
    if (check_events(strong, 1, wait, update, "Metal3", False) != {3} or
            strengthened_waits(strong, wait, update, "Metal3", False) != {10: source[8]}):
        raise ValueError("lighting/downsample ownership change not identified")
    no_cut = list(source)
    no_cut[8] = (338, wait, 1, 1)
    wrong_cut = strong[:3]+[(251, update, 1, 3), (251, wait, 1, 1)]+strong[5:]
    wrong_pass = list(strong)
    wrong_pass[10], wrong_pass[12] = source[8], (339, wait, 1, 1)
    unexpected_mask = list(strong)
    unexpected_mask[10] = (338, wait, 1, 3)
    rejected = [
        (strong, 1, True), (no_cut, 0, False), (no_cut, 0, True),
        (wrong_cut, 1, False), (wrong_pass, 1, False), (unexpected_mask, 1, False),
        (source[1:], 0, False), (source[1::-1]+source[2:], 0, False),
        ([(0, wait, 1, 2)]+source[1:], 0, False),
        (sample, 0, False), (sample, 1, True),
        (source[:3]+pair[::-1]+source[3:], 1, False),
        (source[:3]+[pair[0], (129, wait, 1, 1)]+source[3:], 1, False),
        (source[:3]+[(128, update, 1, 1), pair[1]]+source[3:], 1, False),
    ]
    for events, count, fixed in rejected:
        try:
            check_events(events, count, wait, update, "Metal3", fixed)
        except ValueError:
            continue
        raise ValueError("malformed dependency fixture was accepted")
