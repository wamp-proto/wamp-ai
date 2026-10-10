#!/usr/bin/env bash
# Copyright (c) typedef int GmbH, Germany, 2025. All rights reserved.
# Licensed under the MIT License (see LICENSE file).
#
# deps.sh - dependencies as plain checkouts at pinned commits, for a repository that must not
# carry git submodules (#69).
#
#   deps.sh sync  [--root <dir>] [--from <name>=<local clone>]... [<name>...]
#                                                 make .deps/ what deps.toml says (all, or those)
#   deps.sh check [--root <dir>]                                    exit 1 if .deps/ is not that
#   deps.sh set   [--root <dir>] <name> <url> <commit>              write one pin into deps.toml
#   deps.sh get   [--root <dir>] <name>                             print "<commit> <url>"
#
# WHY NOT SUBMODULES. wamp-cicd and wamp-ai are pinned as submodules (.cicd/, .ai/) by every other
# repository. A submodule inside them would be cloned by every recursive checkout of every one of
# those repositories - and two repositories that pin each other, or a fleet definition that pins
# them and is pinned by them, would nest one level deeper with every bump. So they get what they
# depend on the plain way: deps.toml (tracked) says which commit of which repository,
#
#     [wamp-ai]
#     url    = "https://github.com/wamp-proto/wamp-ai.git"
#     commit = "<40 hex>"
#
# and `sync` makes .deps/<name> (gitignored) a checkout of exactly that commit. Nothing follows a
# deps.toml inside a dependency, so this cannot recurse. See TOOLING-STRUCTURE.md.
#
# The same command on a developer machine, on a host without forge credentials, and in CI.
# `--from <name>=<clone>` takes the objects from a local clone instead of the URL (no network);
# the URL stays what .deps/<name> records as its origin.
#
# SELF-CONTAINED (bash, git, python3): a repository cannot fetch the script that fetches its
# dependencies from a dependency. Where a repository other than wamp-cicd carries this file, it
# is a managed, byte-identical copy.

set -uo pipefail
die() { echo "ERROR: $*" >&2; exit 2; }
usage() { sed -n '8,12p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

[ $# -ge 1 ] || usage
MODE="$1"; shift
ROOT="."; FROM=(); ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --root) ROOT="${2:-}"; shift 2 ;;
        --from) [[ "${2:-}" == *=* ]] || die "--from wants <name>=<local clone>"; FROM+=("$2"); shift 2 ;;
        -h|--help) usage ;;
        -*) die "unknown option: $1" ;;
        *) ARGS+=("$1"); shift ;;
    esac
done
ROOT="$(cd "${ROOT}" 2>/dev/null && pwd)" || die "no such directory (--root)"
TOML="${ROOT}/deps.toml"

# The pins, one per line: "<name> <commit> <url>". Anything the format does not allow is refused
# here, once, for every mode: a name is a directory under .deps/, a commit is a full commit ID.
pins() {
    python3 - "${TOML}" <<'PY'
import re, sys
try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib
try:
    data = tomllib.load(open(sys.argv[1], "rb"))
except FileNotFoundError:
    sys.exit(0)
except (OSError, tomllib.TOMLDecodeError) as e:
    sys.exit(f"ERROR: deps.toml: {e}")
for name, d in data.items():
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name) or not isinstance(d, dict):
        sys.exit(f"ERROR: deps.toml: [{name}] is not a valid dependency name (lower case, digits, . _ -)")
    url, commit = d.get("url"), d.get("commit")
    if not isinstance(url, str) or not url.strip() or any(c.isspace() for c in url):
        sys.exit(f"ERROR: deps.toml: [{name}] needs url = \"...\"")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        sys.exit(f"ERROR: deps.toml: [{name}] needs commit = \"<40 lower-case hex>\" (a full commit ID, never a branch)")
    extra = sorted(set(d) - {"url", "commit"})
    if extra:
        sys.exit(f"ERROR: deps.toml: [{name}] has unknown key(s): {', '.join(extra)}")
    print(name, commit, url)
PY
}

from_of() {  # from_of <name>: the --from clone for that name, or nothing
    local f
    for f in ${FROM[@]+"${FROM[@]}"}; do [ "${f%%=*}" = "$1" ] && { echo "${f#*=}"; return; }; done
}

state_of() {  # state_of <name> <commit>: ok | missing | at <commit> | modified
    local d="${ROOT}/.deps/$1" have
    [ -e "${d}/.git" ] && [ "$(git -C "${d}" rev-parse --show-toplevel 2>/dev/null)" = "${d}" ] || { echo missing; return; }
    have="$(git -C "${d}" rev-parse -q --verify HEAD 2>/dev/null || true)"
    [ "${have}" = "$2" ] || { echo "at ${have:-nothing}"; return; }
    [ -z "$(git -C "${d}" status --porcelain 2>/dev/null)" ] || { echo modified; return; }
    echo ok
}

case "${MODE}" in
sync)
    list="$(pins)" || exit 2
    if [ ${#ARGS[@]} -gt 0 ]; then
        for n in "${ARGS[@]}"; do
            awk -v n="${n}" '$1==n {f=1} END {exit f ? 0 : 1}' <<<"${list}" || die "no [${n}] in deps.toml"
        done
        list="$(awk -v want=" ${ARGS[*]} " 'index(want, " " $1 " ")' <<<"${list}")"
    fi
    [ -n "${list}" ] || { echo "--> no deps.toml (or no pins) in ${ROOT}: nothing to do"; exit 0; }
    # .deps/ must never be committed: it would be added as an embedded repository.
    git -C "${ROOT}" check-ignore -q .deps/x 2>/dev/null \
        || die ".deps/ is not ignored in ${ROOT}: add '.deps/' to .gitignore first"
    rc=0
    while read -r name commit url; do
        d="${ROOT}/.deps/${name}"; src="$(from_of "${name}")"
        case "$(state_of "${name}" "${commit}")" in
            ok) echo "  ok         .deps/${name} at ${commit:0:7}"; continue ;;
            modified) echo "  MODIFIED   .deps/${name}: local changes in a pinned checkout - look, then remove them" >&2; rc=1; continue ;;
            missing) mkdir -p "${d}" && git -C "${d}" init --quiet && git -C "${d}" remote add origin "${url}" || { rc=1; continue; } ;;
        esac
        git -C "${d}" remote set-url origin "${url}"
        if ! git -C "${d}" rev-parse -q --verify "${commit}^{commit}" >/dev/null 2>&1; then
            if [ -n "${src}" ]; then
                git -C "${d}" -c protocol.file.allow=always fetch --quiet "${src}" 'refs/heads/*:refs/remotes/local/*' HEAD 2>/dev/null \
                    || git -C "${d}" -c protocol.file.allow=always fetch --quiet "${src}" HEAD 2>/dev/null || true
            else
                git -C "${d}" fetch --quiet origin 2>/dev/null || git -C "${d}" fetch --quiet origin "${commit}" 2>/dev/null || true
            fi
        fi
        if ! git -C "${d}" rev-parse -q --verify "${commit}^{commit}" >/dev/null 2>&1; then
            echo "  FAILED     .deps/${name}: cannot get ${commit} from ${src:-${url}}" >&2; rc=1; continue
        fi
        if git -C "${d}" checkout --quiet --detach "${commit}" 2>/dev/null; then
            echo "  synced     .deps/${name} at ${commit:0:7}"
        else
            echo "  FAILED     .deps/${name}: cannot check out ${commit:0:7} (local changes?)" >&2; rc=1
        fi
    done <<<"${list}"
    exit "${rc}"
    ;;
check)
    [ ${#ARGS[@]} -eq 0 ] || usage
    list="$(pins)" || exit 2
    rc=0
    while read -r name commit url; do
        [ -n "${name}" ] || continue
        s="$(state_of "${name}" "${commit}")"
        if [ "${s}" = ok ]; then echo "  ok         .deps/${name} at ${commit:0:7}"
        else echo "  ${s^^}  .deps/${name} (deps.toml: ${commit:0:7})"; rc=1; fi
    done <<<"${list}"
    [ "${rc}" = 0 ] || echo "--> .deps/ is not what deps.toml says: run  bash $(basename "$0") sync  (or: just deps)" >&2
    exit "${rc}"
    ;;
get)
    [ ${#ARGS[@]} -eq 1 ] || usage
    list="$(pins)" || exit 2
    awk -v n="${ARGS[0]}" '$1==n {print $2, $3; found=1} END {exit found ? 0 : 1}' <<<"${list}"
    ;;
set)
    [ ${#ARGS[@]} -eq 3 ] || usage
    pins >/dev/null || exit 2     # refuse to rewrite a file that is not valid as it stands
    python3 - "${TOML}" "${ARGS[@]}" <<'PY' || exit 2
import os, re, sys
try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib
path, name, url, commit = sys.argv[1:5]
if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name):
    sys.exit(f"ERROR: '{name}' is not a valid dependency name (lower case, digits, . _ -)")
if not re.fullmatch(r"[0-9a-f]{40}", commit):
    sys.exit(f"ERROR: '{commit}' is not a full commit ID (40 lower-case hex)")
if not url or any(c.isspace() or c == '"' for c in url):
    sys.exit(f"ERROR: '{url}' is not a usable URL")
data = tomllib.load(open(path, "rb")) if os.path.exists(path) else {}
data[name] = {"url": url, "commit": commit}
out = ["# Dependencies as plain checkouts at pinned commits in .deps/ (gitignored) - not submodules.",
       "# `just deps` makes .deps/ match this file. See TOOLING-STRUCTURE.md.", ""]
for n in sorted(data):
    out += [f"[{n}]", f'url    = "{data[n]["url"]}"', f'commit = "{data[n]["commit"]}"', ""]
open(path, "w").write("\n".join(out))
PY
    echo "  pinned     ${ARGS[0]} at ${ARGS[2]:0:7} (deps.toml)"
    ;;
*) usage ;;
esac
