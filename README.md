# The Web Application Messaging Protocol: AI Support

Multi-repository workspace setup for AI assistants/agents specific configuration.

*Single Source of Truth*
- ✅ All AI config centralized in `wamp-ai` repo
- ✅ Versioned and evolvable over time
- ✅ Consistent across all WAMP projects

*Multi-AI Support*
- ✅ Claude (`CLAUDE.md`)
- ✅ Gemini (`.gemini/GEMINI.md`)
- ✅ Extensible for future AI assistants

*Dual-Level Coverage*
- ✅ Project-level: Each repo gets AI instructions
- ✅ Workspace-level: Working from ~/work/wamp/` also covered

*Standard Git Mechanisms*
- ✅ Git submodules (standard practice)
- ✅ Symlinks (filesystem-level solution)
- ✅ Automated setup via justfile

## Usage

Add this repo as a submodule to a WAMP related repo:

```
cd ~/work/wamp/txaio
git submodule add https://github.com/wamp-proto/wamp-ai.git .ai
cd .ai
just setup
```

Clone a WAMP related repo including submodules:

```
git clone --recursive git@github.com:crossbario/txaio.git
```

Initialize or update a WAMP related repo including submodules:

```
git submodule update --init --recursive
```

```
git submodule update --remote --merge
```
