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

# Setup AI policy Git hooks in current repository, should be run after adding submodule in target repository.
setup-githooks:
    #!/usr/bin/env bash
    set -e

    # Configure Git to use the versioned hooks directory
    git config core.hooksPath .githooks
    echo "✔ Git hooks are now configured to use .githooks/"
    echo "  (run 'git config core.hooksPath' to verify)"

# Setup AI policy & guideline files, should be run after adding submodule in target repository or in this repository for workspace level.
setup-files:
    #!/usr/bin/env bash
    set -e

    # the target path you specify is interpreted relative to the directory where
    # the symlink will be created (the link name’s location)
    ln -sf .ai/AI_POLICY.md ../AI_POLICY.md
    ln -sf .ai/AI_GUIDELINES.md ../CLAUDE.md
    mkdir -p ../.gemini
    ln -sf .ai/AI_GUIDELINES.md ../.gemini/GEMINI.md

setup: (setup-githooks) (setup-files)
    echo "✅ Repo or Workspace AI configuration complete"
