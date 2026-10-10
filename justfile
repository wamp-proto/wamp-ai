# Copyright (c) typedef int GmbH, Germany, 2025. All rights reserved.
# Licensed under the MIT License (see LICENSE file).

# -----------------------------------------------------------------------------
# -- just global configuration
# -----------------------------------------------------------------------------

set unstable := true
set positional-arguments := true
set script-interpreter := ['uv', 'run', '--script']

# Project base directory = directory of this justfile
PROJECT_DIR := justfile_directory()

# -----------------------------------------------------------------------------
# -- Way-A shared workflow recipes (wamp-cicd workflow.just)
# -----------------------------------------------------------------------------
# wamp-ai is a tooling source and carries no submodules (TOOLING-STRUCTURE.md):
# wamp-cicd is a plain checkout under .deps/ (deps.toml, scripts/deps.sh), hence
# the optional import - `just deps` first in a fresh clone. The default branch is
# `main`, workflow.just's default, so WORKFLOW_MAIN is not overridden.
import? '.deps/wamp-cicd/workflow.just'

# List all recipes.
default:
    @echo ""
    @echo "The Web Application Messaging Protocol: AI Support Module"
    @echo ""
    @just --list
    @echo ""

# Run the tests of the aspects this repository provides (standard library only, Python 3.11+).
test:
    python3 -m unittest discover -s tests -v

# Make .deps/ what deps.toml says (after a clone, after a pull).
deps *args:
    bash scripts/deps.sh sync {{args}}

# Internal guard: `.deps/` must match deps.toml.
_deps-ok:
    @bash scripts/deps.sh check >/dev/null || { echo "ERROR: .deps/ does not match deps.toml - run: just deps" >&2; exit 1; }

# Add AI submodule from `wamp-ai` to dir `.ai` in target repository (should be run from root dir in target repository).
add-repo-submodule:
    #!/usr/bin/env bash
    set -e

    git submodule add https://github.com/wamp-proto/wamp-ai.git .ai
    git submodule update --init --recursive
    echo "✅ Workspace AI submodule added. Now run `just setup-repo` in dir `.ai`."

# Update AI submodule following `wamp-ai` in dir `.ai` in this repository (should be run from `.ai` dir after adding submodule in target repository).
update-repo-submodule:
    #!/usr/bin/env bash
    set -e

    git submodule update --remote --merge
    echo "✅ Workspace AI submodule updated. Now add & commit the change (to `.ai`) in this repository."

_setup-repo-githooks:
    #!/usr/bin/env bash
    set -e

    # Configure Git to use the versioned hooks directory
    cd .. && git config core.hooksPath .ai/.githooks
    echo "✔ Git hooks are now configured to use .ai/.githooks"
    echo "  (run 'git config core.hooksPath' to verify)"

_setup-repo-files:
    #!/usr/bin/env bash
    set -e

    # the target path you specify is interpreted relative to the directory where
    # the symlink will be created (the link name's location)
    ln -sf .ai/AI_POLICY.md ../AI_POLICY.md
    ln -sf .ai/AI_GUIDELINES.md ../CLAUDE.md
    ln -sf .ai/OVERVIEW.md ../OVERVIEW.md
    mkdir -p ../.gemini
    ln -sf ../.ai/AI_GUIDELINES.md ../.gemini/GEMINI.md

_setup-workspace-files:
    #!/usr/bin/env bash
    set -e

    # the target path you specify is interpreted relative to the directory where
    # the symlink will be created (the link name’s location)
    ln -sf wamp-ai/AI_POLICY.md ../AI_POLICY.md
    ln -sf wamp-ai/AI_GUIDELINES.md ../CLAUDE.md
    mkdir -p ../.gemini
    ln -sf ../wamp-ai/AI_GUIDELINES.md ../.gemini/GEMINI.md

# Setup AI policy & guideline files and Git hooks in this repository (should be run from `.ai` dir after adding submodule in target repository).
setup-repo: (_setup-repo-githooks) (_setup-repo-files)
    echo "✅ Repo AI configuration complete"

# Setup AI policy & guideline files in workspace (should be run from root dir in `wamp-ai` repository).
setup-workspace: (_setup-workspace-files)
    echo "✅ Workspace AI configuration complete"

# Generate audit file in target repository from template (should be run from `.ai` dir in target repository).
generate-audit-file:
    #!/usr/bin/env bash
    set -e

    # Change to parent directory (target repository)
    cd ..

    # Get current branch name
    BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "unknown")

    # Sanitize branch name: replace / with -, remove dots, replace special chars with _
    SANITIZED_BRANCH=$(echo "$BRANCH" | sed 's/\//-/g' | sed 's/\.//g' | sed 's/[^a-zA-Z0-9_-]/_/g')

    # Get GitHub username from git remotes
    ORIGIN_URL=$(git remote get-url origin 2>/dev/null || echo "")

    # Try to extract from GitHub URL (dev PC case)
    if [[ "$ORIGIN_URL" =~ github\.com[:/]([^/]+)/ ]]; then
        GITHUB_USER="${BASH_REMATCH[1]}"
    # Try to extract from bare repo path (asgard1 case: /scm/repos/USERNAME/...)
    elif [[ "$ORIGIN_URL" =~ /scm/repos/([^/]+)/ ]]; then
        GITHUB_USER="${BASH_REMATCH[1]}"
    # Fallback to git config
    else
        GITHUB_USER=$(git config user.name | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
    fi

    # Get current date (UTC)
    CURRENT_DATE=$(date -u +%Y-%m-%d)

    # Create .audit directory if it doesn't exist
    mkdir -p .audit

    # Target audit file
    AUDIT_FILE=".audit/${GITHUB_USER}_${SANITIZED_BRANCH}.md"

    # Check if audit file already exists
    if [ -f "$AUDIT_FILE" ]; then
        echo "⚠️  Audit file already exists: $AUDIT_FILE"
        echo "   Please edit it manually or remove it first."
        exit 1
    fi

    # Generate audit file from template
    cat > "$AUDIT_FILE" << 'AUDIT_EOF'
    - [ ] I did **not** use any AI-assistance tools to help create this pull request.
    - [x] I **did** use AI-assistance tools to *help* create this pull request.
    - [x] I have read, understood and followed the project's AI_POLICY.md when creating code, documentation etc. for this pull request.

    Submitted by: @GITHUB_USER_PLACEHOLDER
    Date: CURRENT_DATE_PLACEHOLDER
    Related issue(s): #XXX
    Branch: GITHUB_USER_PLACEHOLDER:BRANCH_PLACEHOLDER
    AUDIT_EOF

    # Now replace placeholders (avoiding leading dashes which just interprets)
    sed -i "s|GITHUB_USER_PLACEHOLDER|${GITHUB_USER}|g" "$AUDIT_FILE"
    sed -i "s|CURRENT_DATE_PLACEHOLDER|${CURRENT_DATE}|g" "$AUDIT_FILE"
    sed -i "s|BRANCH_PLACEHOLDER|${BRANCH}|g" "$AUDIT_FILE"
    # Remove leading indentation
    sed -i 's/^    //' "$AUDIT_FILE"

    echo "✅ Audit file created: $AUDIT_FILE"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Edit $AUDIT_FILE and update 'Related issue(s)' with actual issue numbers"
    echo "   2. Adjust AI assistance checkboxes if needed"
    echo "   3. Commit the audit file with your PR changes"
    echo ""
    echo "Current context:"
    echo "   GitHub User: $GITHUB_USER"
    echo "   Branch: $BRANCH (sanitized: $SANITIZED_BRANCH)"
    echo "   Date: $CURRENT_DATE"
