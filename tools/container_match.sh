#!/bin/bash
#
# tools/container_match.sh - play tournament-style matches between two bot images.
#
#     ./tools/container_match.sh IMAGE_A IMAGE_B [SEED ...]
#     ./tools/container_match.sh shortstack:latest drew-bot:latest 11 12 13
#
# Build an image from a repo checkout with the organizers' Dockerfile:
#     docker build -f docker/Dockerfile.agent -t NAME:TAG <repo root>
# (or pull one another team pushed: docker pull USER/IMAGE:TAG)
#
# Each half runs in brand-new containers with the tournament's limits
# (1 CPU, 4 GB, read-only files, 512 MB /tmp), as the tournament does. The
# judge runs in a container too, on a private Docker network, so requests
# don't pay Docker Desktop's host port-forwarding latency, which would be
# charged to both time banks. IMAGE_A is agent1 (seat 0 in half 1).
#
# Results go to results/container/ (JSON per half and a log per match).
# Options (environment variables): CPUS=1 MEMORY=4g DEALS=1000
#     LOGS=1 (every hand in the half JSONs, for deal-by-deal diffs)
#     ENV_A / ENV_B="KEY=VALUE ..." (environment for that bot, values without
#       spaces), e.g. ENV_A='SHORTSTACK_PARAMS={"defend_agg":0.3}'
#     TAG=name (added to the result file names, to keep candidates apart)
#     JUDGE_IMAGE=poker-agent-base:local (any image with Python 3)

set -uo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

if [ $# -lt 2 ]; then
  sed -n '3,25p' "$0"
  exit 2
fi
A="$1"; B="$2"; shift 2
SEEDS=("${@:-1}")
CPUS="${CPUS:-1}"
MEMORY="${MEMORY:-4g}"
DEALS="${DEALS:-1000}"
LOG_ARGS=()
[ "${LOGS:-0}" = 1 ] && LOG_ARGS=(--logs)
JUDGE_IMAGE="${JUDGE_IMAGE:-poker-agent-base:local}"
ROOT="$(pwd -W 2>/dev/null || pwd)"
OUT="results/container"
NET="poker-match-$$"
mkdir -p "$OUT"

cleanup() {
  docker rm -f "botA-$$" "botB-$$" >/dev/null 2>&1
  docker network rm "$NET" >/dev/null 2>&1
}
trap cleanup EXIT
docker network create "$NET" >/dev/null || exit 1

start_bot() {   # name image port env
  local envs=() kv
  for kv in $4; do envs+=(--env "$kv"); done
  docker run --detach --name "$1" --network "$NET" "${envs[@]}" \
    --read-only --tmpfs /tmp:rw,nosuid,nodev,size=512m \
    --cpus "$CPUS" --memory "$MEMORY" --env PORT="$3" "$2" >/dev/null
}

judge() {       # judge_engine.py arguments...
  docker run --rm --network "$NET" --cpus 1 -v "$ROOT:/judge" -w /judge \
    --user "$(id -u 2>/dev/null || echo 0)" "$JUDGE_IMAGE" python judge_engine.py "$@"
}

for seed in "${SEEDS[@]}"; do
  tag="$(echo "${A}_vs_${B}" | tr '/:' '__')${TAG:+_$TAG}_s${seed}"
  log="$OUT/$tag.log"
  : > "$log"
  for half in 1 2; do
    docker rm -f "botA-$$" "botB-$$" >/dev/null 2>&1
    start_bot "botA-$$" "$A" 5008 "${ENV_A:-}" && start_bot "botB-$$" "$B" 5009 "${ENV_B:-}" || exit 1
    echo "== seed $seed half $half" >> "$log"
    # The judge waits up to 15 s for both bots to answer GET /.
    judge --agent1 "http://botA-$$:5008" --agent2 "http://botB-$$:5009" \
      --half "$half" --seed "$seed" --deals "$DEALS" "${LOG_ARGS[@]}" --json "$OUT/${tag}_h$half.json" >> "$log" 2>&1
  done
  docker rm -f "botA-$$" "botB-$$" >/dev/null 2>&1
  echo "== combined" >> "$log"
  judge combine "$OUT/${tag}_h1.json" "$OUT/${tag}_h2.json" >> "$log" 2>&1
  echo "seed $seed: $(grep -E 'RESULT|agent1:' "$log" | tail -2 | tr '\n' ' ')"
  sed -n '/^== combined/,$p' "$log" | grep -E "half[12]: thinking|forfeit" | sed 's/^ */    /'
done
