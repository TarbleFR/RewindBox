#!/usr/bin/env python3
"""Keep complete command evidence and print a bounded, non-authoritative excerpt.

python3 scripts/ai-output.py run -- python3 -B test/example_test.py
python3 scripts/ai-output.py file /path/to/existing.log
"""

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


IMPORTANT = re.compile(
    r"error|fail|exception|traceback|fatal|assert|panic|timeout|timed out|"
    r"denied|refused|segmentation|sanitizer|not ok",
    re.IGNORECASE,
)
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MAX_LINE = 240
MAX_EXCERPT = 8000


def clean(text):
    text = ANSI.sub("", text)
    return "".join(char if char.isprintable() else " " for char in text).strip()


def scan_log(path):
    """Scan binary fragments so even an unbroken huge line uses bounded memory."""
    digest = hashlib.sha256()
    head, tail = [], deque(maxlen=8)
    first_matches, last_matches = [], deque(maxlen=12)
    byte_count = line_count = match_count = 0
    prefix = carry = matched_text = ""
    matched = pending = False

    def keep_line():
        nonlocal line_count, match_count
        line_count += 1
        entry = (line_count, matched_text if matched else prefix)
        if len(head) < 4:
            head.append(entry)
        tail.append(entry)
        if matched:
            match_count += 1
            if len(first_matches) < 12:
                first_matches.append(entry)
            else:
                last_matches.append(entry)

    with path.open("rb") as source:
        for raw in iter(lambda: source.readline(65536), b""):
            digest.update(raw)
            byte_count += len(raw)
            pending = True
            text = clean(raw.decode("utf-8", errors="replace"))
            prefix = (prefix + text)[:MAX_LINE]
            searchable = carry + text
            match = IMPORTANT.search(searchable)
            if match and not matched:
                start = max(0, match.start() - 60)
                matched_text = searchable[start:start + MAX_LINE]
                matched = True
            carry = searchable[-80:]
            if raw.endswith(b"\n"):
                keep_line()
                prefix = carry = matched_text = ""
                matched = pending = False
        if pending:
            keep_line()

    selected = dict(head + first_matches + list(last_matches) + list(tail))
    excerpt = "\n".join(f"{number}: {selected[number]}" for number in sorted(selected))
    clipped = len(excerpt) > MAX_EXCERPT
    if clipped:
        excerpt = excerpt[:3900] + "\n[excerpt clipped; read the complete log]\n" + excerpt[-3900:]
    return {
        "bytes": byte_count,
        "lines": line_count,
        "sha256": digest.hexdigest(),
        "matching_lines": match_count,
        "unselected_lines": line_count - len(selected),
        "excerpt_clipped": clipped,
        "excerpt": excerpt,
    }


def print_summary(path, result, status):
    print(f"Status: {status}")
    print(f"Complete log: {path}")
    print(f"SHA-256: {result['sha256']}")
    print(f"Bytes: {result['bytes']}; lines: {result['lines']}; matching lines: {result['matching_lines']}")
    print(f"Lines outside selection: {result['unselected_lines']}; excerpt clipped: {result['excerpt_clipped']}")
    print("Excerpt only. Keywords and their absence do not establish a test verdict.")
    print(result["excerpt"] or "[empty output]")


def run_command(args):
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("run requires a command after --")
    directory = Path(tempfile.mkdtemp(prefix="rewindbox-ai-output-", dir=args.log_dir)).resolve()
    log_path = directory / "output.log"
    receipt_path = directory / "receipt.json"
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    return_code = 127
    launch_error = None
    interrupted = False
    print(f"Recording complete output in {log_path}", flush=True)
    with log_path.open("wb") as output:
        try:
            child = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, shell=False)
        except OSError as error:
            launch_error = str(error)
        else:
            try:
                return_code = child.wait()
            except KeyboardInterrupt:
                interrupted = True
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                return_code = 130

    result = scan_log(log_path)
    receipt = {
        "command": command,
        "cwd": str(Path.cwd()),
        "started_utc": started,
        "duration_seconds": round(time.monotonic() - clock, 3),
        "return_code": return_code,
        "interrupted": interrupted,
        "launch_error": launch_error,
        "log_path": str(log_path),
        **{key: value for key, value in result.items() if key != "excerpt"},
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    status = f"child exit {return_code}"
    if launch_error:
        status = f"command could not start ({launch_error})"
    if interrupted:
        status = "interrupted; partial output retained"
    print(f"Receipt: {receipt_path}")
    print_summary(log_path, result, status)
    return return_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    run = modes.add_parser("run", help="capture a command and preserve its exit status")
    run.add_argument("--log-dir", type=Path, help="existing parent directory; defaults to system temporary storage")
    run.add_argument("command", nargs=argparse.REMAINDER)
    existing = modes.add_parser("file", help="read an existing log without modifying it")
    existing.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "run":
            return run_command(args)
        path = args.path.resolve()
        before = path.stat()
        result = scan_log(path)
        after = path.stat()
        changed = (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
        print_summary(path, result, "file changed during scan" if changed else "file excerpt; command outcome unknown")
        return 2 if changed else 0
    except (OSError, ValueError) as error:
        print(f"ai-output: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    exit_code = main()
    if exit_code < 0 and os.name == "posix":
        import signal
        sys.stdout.flush()
        sys.stderr.flush()
        if -exit_code != signal.SIGKILL:
            signal.signal(-exit_code, signal.SIG_DFL)
        os.kill(os.getpid(), -exit_code)
    sys.exit(exit_code)
