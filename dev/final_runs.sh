#!/usr/bin/env bash
# Reproduce every live number in WRITEUP.md. Writes results/final/*.
set -u
cd "$(dirname "$0")/.."
R=results/final
one() { # name budget extra-args...
  local n=$1 b=$2; shift 2
  ./run data/items.json --budget "$b" --out "$R/$n.json" --trace "$R/$n.trace.jsonl" "$@" > "$R/$n.log" 2>&1
  python3 data/score.py data/visible_key.json "$R/$n.json" > "$R/$n.score.txt" 2>&1
  echo "$n $(tail -c 300 $R/$n.score.txt | tr '\n' ' ')"
}
case "${1:-all}" in main|all) ;; *) false;; esac && for b in 1x 3x 10x; do for r in 1 2 3; do one full_${b}_r$r $b & done; wait; done
abl() { local b=$1
  one novote_$b $b --ablate vote &
  one noprior_$b $b --ablate prior_pick &
  one noprefilter_$b $b --ablate prefilter &
  one adaptive_$b $b --enable adaptive &
  wait; }
case "${1:-all}" in
  abl1) one noprior_1x 1x --ablate prior_pick & one noprefilter_1x 1x --ablate prefilter & wait; abl 3x ;;
  abl2) abl 10x ;;
  all) one noprior_1x 1x --ablate prior_pick & one noprefilter_1x 1x --ablate prefilter & wait; abl 3x; abl 10x ;;
esac
