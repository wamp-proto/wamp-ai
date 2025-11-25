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

    # Change to parent directory (target repository)
    cd ..

    # Get current branch name
    BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "unknown")

    # Sanitize branch name: replace / with -, remove dots, replace special chars with _
    SANITIZED_BRANCH=$(echo "$BRANCH" | sed 's/\//-/g' | sed 's/\.//g' | sed 's/[^a-zA-Z0-9_-]/_/g')

    # Get GitHub username from origin remote URL
    ORIGIN_URL=$(git remote get-url origin 2>/dev/null || echo "")
    if [[ "$ORIGIN_URL" =~ github\.com[:/]([^/]+)/ ]]; then
        GITHUB_USER="${BASH_REMATCH[1]}"
    else
        # Fallback to git config user.name if can't extract from URL
        GITHUB_USER=$(git config user.name | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
    fi

    # Get repository URL for AI_POLICY.md link
    if [[ "$ORIGIN_URL" =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
        REPO_URL="https://github.com/${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    else
        REPO_URL="https://github.com/OWNER/REPO"
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

    # Render template using Python and Jinja2
    python3 << 'PYTHON_SCRIPT'
import os
import sys
from pathlib import Path

try:
    from jinja2 import Template
except ImportError:
    print("Error: jinja2 not installed. Installing...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "jinja2"], check=True)
    from jinja2 import Template

# Read template
template_path = Path(".ai/audit/templates/audit-file.md.j2")
template_content = template_path.read_text()

# Get variables from environment
context = {
    'user': os.environ['GITHUB_USER'],
    'branch': os.environ['BRANCH'],
    'date': os.environ['CURRENT_DATE'],
    'repo_url': os.environ['REPO_URL'],
}

# Render template
template = Template(template_content)
output = template.render(context)

# Write to audit file
audit_file = Path(os.environ['AUDIT_FILE'])
audit_file.write_text(output)
PYTHON_SCRIPT

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
