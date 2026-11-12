#!/bin/bash
# Checks native/s2arm/prepare against S2Arm's own rewriter command line.
# Usage: run_prepare_test.sh <s2arm_prepare_cli> <s2a-rewrite> <work dir> <report>
set -u
cli=$1; reference=$2; work=$3; report=$4; here=$(cd "$(dirname "$0")" && pwd); bad=0
: > "$report"
check() { if eval "$2"; then echo "ok   $1" | tee -a "$report"; else echo "FAIL $1" | tee -a "$report"; bad=1; fi; }
rm -rf "$work"; mkdir -p "$work/out" "$work/ref"
python3 "$here/make_synth_exefs.py" "$work/exefs"

"$cli" rewrite "$work/exefs" "$work/out" > "$work/run.log" 2>&1; status=$?
cat "$work/run.log"
check "library rewrite succeeds (exit $status)" '[ "$status" = 0 ]'
check "modules are main, subsdk0, sdk and nothing else" \
  '[ "$(grep "^module" "$work/run.log" | cut -d" " -f3 | tr "\n" " ")" = "main subsdk0 sdk " ]'
# Reference: the pinned S2Arm command line, as pack/stage_rewrite.sh runs it (Apple target), with the spin pass off as on
# the phone (S2A_REWRITE_SPIN=0, native/s2arm/prepare/s2arm_prepare.c rewrite_one).
for module in main subsdk0 sdk; do
  env -u S2A_TARGET S2A_REWRITE_SPIN=0 "$reference" "$work/exefs/$module" "$work/ref" "$module" > "$work/ref/$module.rewrite.log" 2>&1 \
    || { echo "FAIL reference rewrite of $module" | tee -a "$report"; bad=1; }
done
cp "$work/exefs/main.npdm" "$work/ref/main.npdm"
diff -r -x '*.rewrite.log' "$work/out" "$work/ref" > "$work/diff.txt" 2>&1; same=$?
cat "$work/diff.txt"
check "outputs identical to S2Arm's command line ($(ls "$work/ref" | grep -vc rewrite.log) files)" '[ "$same" = 0 ]'
check "five tables per module and main.npdm are present" '[ "$(ls "$work/out" | grep -vc rewrite.log)" = 16 ]'
check "rtld and main.moduleconfig are left alone" '! ls "$work/out" | grep -q "^rtld\|moduleconfig"'

expect() { # label, expected exit, exefs dir, [cancel-after]
  want=$2; rm -rf "$work/neg"; mkdir -p "$work/neg"
  "$cli" rewrite "$3" "$work/neg" ${4:-} > "$work/neg.log" 2>&1; got=$?
  tail -1 "$work/neg.log"
  check "$1 (exit $got, expected $want)" '[ "$got" = "$want" ]'
}
cp -R "$work/exefs" "$work/nomain"; rm "$work/nomain/main"
expect "missing main is refused" 1 "$work/nomain"
cp -R "$work/exefs" "$work/nonpdm"; rm "$work/nonpdm/main.npdm"
expect "missing main.npdm is refused" 1 "$work/nonpdm"
cp -R "$work/exefs" "$work/notnso"; printf 'not a module' > "$work/notnso/sdk"
expect "a module that is not an NSO is refused" 1 "$work/notnso"
python3 "$here/make_synth_exefs.py" "$work/gap" --gap
expect "code the rewriter cannot rewrite is reported as such" 3 "$work/gap"
expect "cancellation stops between modules" 5 "$work/exefs" 1
check "cancellation left only the first module" '[ -f "$work/neg/main.patched.bin" ] && [ ! -f "$work/neg/subsdk0.patched.bin" ] && [ ! -f "$work/neg/main.npdm" ]'
exit $bad
