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
    @just --list
    @echo ""

_setup-githooks:
    #!/usr/bin/env bash
    set -e

    # Configure Git to use the versioned hooks directory
    cd .. && git config core.hooksPath .ai/.githooks
    echo "✔ Git hooks are now configured to use .ai/.githooks"
    echo "  (run 'git config core.hooksPath' to verify)"

_setup-files:
    #!/usr/bin/env bash
    set -e

    # the target path you specify is interpreted relative to the directory where
    # the symlink will be created (the link name’s location)
    ln -sf .ai/AI_POLICY.md ../AI_POLICY.md
    ln -sf .ai/AI_GUIDELINES.md ../CLAUDE.md
    mkdir -p ../.gemini
    ln -sf ../.ai/AI_GUIDELINES.md ../.gemini/GEMINI.md

# Setup AI policy & guideline files and Git hooks in current repository, should be run after adding submodule in target repository.
setup-repo: (_setup-githooks) (_setup-files)
    echo "✅ Repo AI configuration complete"

# Setup AI policy & guideline files in workspace, should be run from wamp-ai repository.
setup-workspace: (_setup-files)
    echo "✅ Workspace AI configuration complete"
