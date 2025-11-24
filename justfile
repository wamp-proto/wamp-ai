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

# List all recipes.
default:
    @echo ""
    @echo "The Web Application Messaging Protocol: AI Support Module"
    @echo ""
    @just --list
    @echo ""

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
    # the symlink will be created (the link name’s location)
    ln -sf .ai/AI_POLICY.md ../AI_POLICY.md
    ln -sf .ai/AI_GUIDELINES.md ../CLAUDE.md
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

    # Get current date, branch, and repo name
    CURRENT_DATE=$(date +%Y-%m-%d)
    CURRENT_BRANCH=$(git -C .. symbolic-ref --short HEAD 2>/dev/null || echo "unknown")
    REPO_NAME=$(basename "$(git -C .. rev-parse --show-toplevel)" 2>/dev/null || echo "unknown")

    # Create .audit directory if it doesn't exist
    mkdir -p ../.audit

    # Target audit file
    AUDIT_FILE="../.audit/WORK.md"

    # Check if audit file already exists
    if [ -f "$AUDIT_FILE" ]; then
        echo "⚠️  Audit file already exists: $AUDIT_FILE"
        echo "   Please edit it manually or remove it first."
        exit 1
    fi

    # Copy template to target location
    cp templates/AUDIT.md "$AUDIT_FILE"

    echo "✅ Audit file created: $AUDIT_FILE"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Edit $AUDIT_FILE to document your AI-assisted work"
    echo "   2. Fill in the audit entry fields (AI Assistant, Scope, Files, Testing, Review)"
    echo "   3. Commit the audit file with your changes"
    echo ""
    echo "Current context:"
    echo "   Repository: $REPO_NAME"
    echo "   Branch: $CURRENT_BRANCH"
    echo "   Date: $CURRENT_DATE"
