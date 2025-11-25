# Audit File Templates

This directory contains templates for generating audit files that track AI-assisted work.

## Overview

Per `AI_POLICY.md`, contributors must disclose when AI assistance tools are used. The audit file provides a standardized format for this disclosure.

## File Naming Convention

Audit files are named: `<github-username>_<sanitized-branch-name>.md`

Examples:
- `oberstet_fix_1771.md` (branch: fix_1771)
- `oberstet_rel_v25.10.1_part1.md` (branch: rel/v25.10.1-part1)

**Branch name sanitization**:
- Dots (`.`) → removed or replaced with dashes
- Slashes (`/`) → replaced with dashes
- Other special characters → replaced with underscores or removed
- This ensures Windows compatibility

## Template

The `templates/audit-file.md.j2` Jinja2 template generates audit files with:
- AI assistance disclosure checkboxes
- Contributor information
- Date of submission
- Related issue references
- Branch information

## Usage

From within the `.ai/` directory in a target repository:

```bash
just generate-audit-file
```

This creates: `../.audit/<username>_<branch>.md`

## Manual Editing

After generation, edit the audit file to:
1. Update "Related issue(s)" with actual issue numbers
2. Adjust AI assistance checkboxes if needed
3. Verify all information is correct

## Integration with PRs

Include the audit file in your pull request commits. This provides transparency about AI tool usage and compliance with `AI_POLICY.md`.
