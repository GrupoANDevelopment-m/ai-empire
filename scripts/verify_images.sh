#!/usr/bin/env bash
#
# verify_images.sh — checks every image in docker-compose.yml against the
# real Docker Hub / GitHub Container Registry.
#
# Uses each registry's HTTP API (no docker needed).
#
# Returns:
#   ✓ exists  — image:tag found in registry
#   ✗ 404     — image or tag does NOT exist (will fail in `docker pull`)
#   ⚠ latest  — uses :latest, version will float
#
set -uo pipefail

COMPOSE="${1:-docker-compose.yml}"
[ -f "$COMPOSE" ] || { echo "Usage: $0 docker-compose.yml"; exit 1; }

# Extract image references from compose (skips locally-built services).
IMAGES=$(awk '
  /^[[:space:]]*image:/ {
    line = $0
    sub(/^[[:space:]]*image:[[:space:]]*/, "", line)
    sub(/[[:space:]]*#.*$/, "", line)
    gsub(/['"'"'"]/, "", line)
    if (line != "") print line
  }
' "$COMPOSE" | sort -u)

[ -z "$IMAGES" ] && { echo "No images found"; exit 0; }

# For Docker Hub library images, the registry path includes /library/.
# We add it before the request.
normalize_repo() {
  local reg="$1" repo="$2"
  # If registry is docker.io and repo has no slash, it's an official/library image.
  if [[ "$reg" == "docker.io" ]] && [[ "$repo" != */* ]]; then
    echo "library/$repo"
  else
    echo "$repo"
  fi
}

TOTAL=$(echo "$IMAGES" | wc -l)
OK=0
FAIL=0
WARN=0
NEEDS_AUTH=0

printf "%-6s  %-65s  %s\n" "STATUS" "IMAGE" "INFO"
printf "%-6s  %-65s  %s\n" "------" "-----------------------------------------------------------------" "----"

for img in $IMAGES; do
  # Parse registry, repo, tag
  registry="docker.io"
  repo_tag="$img"
  if [[ "$img" == *"/"* ]]; then
    first="${img%%/*}"
    if [[ "$first" == *"."* ]] || [[ "$first" == *":"* ]]; then
      registry="$first"
      repo_tag="${img#*/}"
    fi
  fi
  repo="${repo_tag%%:*}"
  tag="${repo_tag##*:}"
  [ "$repo" = "$tag" ] && tag="latest"

  # For Docker Hub, prepend library/ if it's an official image
  if [ "$registry" = "docker.io" ]; then
    full_repo=$(normalize_repo "$registry" "$repo")
  else
    full_repo="$repo"
  fi

  # Try two APIs in order:
  #   1. /v2/repositories/{repo}/tags/{tag}   (Docker Hub Search API)
  #   2. /v2/{repo}/manifests/{tag}           (Docker Registry v2 — works for any registry)
  http1=$(curl -sS -m 8 -o /dev/null -w "%{http_code}" \
              "https://registry.hub.docker.com/v2/repositories/${full_repo}/tags/${tag}" 2>/dev/null || echo "000")
  if [ "$http1" = "200" ]; then
    status="✓"; info="(tag $tag)"
  elif [ "$http1" = "404" ]; then
    # Try registry v2 manifest endpoint (works for ghcr.io, mcr.microsoft.com, etc.)
    http2=$(curl -sS -m 8 -o /dev/null -w "%{http_code}" \
                -H "Accept: application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
                "https://${registry}/v2/${full_repo}/manifests/${tag}" 2>/dev/null || echo "000")
    if [ "$http2" = "200" ]; then
      status="✓"; info="(tag $tag via registry v2)"
    elif [ "$http2" = "401" ]; then
      status="⚠ auth"; info="(ghcr.io: needs auth — check manually)"
      NEEDS_AUTH=$((NEEDS_AUTH+1))
    elif [ "$http2" = "404" ]; then
      status="✗ 404"; info="(image or tag missing)"
      FAIL=$((FAIL+1))
    else
      status="? $http2"; info="(check manually)"
    fi
  else
    status="? $http1"; info="(Docker Hub unreachable)"
  fi

  # Annotate :latest
  if [[ "$status" == "✓"* ]]; then
    OK=$((OK+1))
    if [ "$tag" = "latest" ]; then
      info="$info — :latest floats"
      WARN=$((WARN+1))
    fi
  fi

  printf "%-6s  %-65s  %s\n" "$status" "$img" "$info"
done

echo
echo "================================================================"
echo "TOTAL: $TOTAL  OK: $OK  FAIL: $FAIL  :latest: $WARN  AUTH-NEEDED: $NEEDS_AUTH"
echo "================================================================"

[ $FAIL -eq 0 ]
