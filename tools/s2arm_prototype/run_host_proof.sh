#!/bin/bash
# Run the positive case and the negative controls of the host proof.
# Usage: run_host_proof.sh <host_loader> <rewriter output dir> <report file>
set -u
loader=$1; dir=$2; report=$3; bad=0
: > "$report"
run() { # mode, expectation (zero | nonzero)
  "$loader" "$dir" "$1" > "$report.$1.log" 2>&1; status=$?
  cat "$report.$1.log"
  if [ "$2" = zero ]; then [ "$status" = 0 ] && verdict=ok || verdict=FAIL
  else [ "$status" != 0 ] && [ "$status" != 2 ] && verdict=ok || verdict=FAIL; fi
  [ "$verdict" = ok ] || bad=1
  echo "$verdict mode=$1 exit=$status expected=$2" | tee -a "$report"
}
run pass zero
# Each control removes one piece; a setup error (exit 2) does not count as the expected failure.
for mode in nogate wrongtls nokeypage nobrk; do run "$mode" nonzero; done
exit $bad
