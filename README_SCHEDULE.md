# Scheduling the Open Science News Agent

Overview
- Script: `scripts/run_sys_prompt_agent.py`
- Purpose: Read `sys_prompt.md`, run the prompt with an LLM, and publish a GitHub Issue.
- Schedule: Weekdays at 06:00 CET (implemented via `Europe/Paris` timezone).

Setup
1. Create a Python virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\\Scripts\\activate on Windows

# Install dependencies with pip:
pip install -r requirements.txt

# Or, if you use the `uv` CLI package manager, install with `uv` after activating the venv:
uv install -r requirements.txt
```

2. Create a `.env` file in the repository root with these variables:

```
OPENAI_API_KEY=sk-...
GITHUB_TOKEN=ghp_...
GITHUB_REPO=owner/repo
# Optional
LANGSMITH_API_KEY=ls-...
```

Running
- Run once:

```bash
python scripts/run_sys_prompt_agent.py --once
```

- Run continuously (foreground):

```bash
python scripts/run_sys_prompt_agent.py
```

If `uv` provides a `run` subcommand that executes using the environment's Python, you can run with:

```bash
uv run python scripts/run_sys_prompt_agent.py --once
```

Adjust according to `uv --help` if its subcommands differ. The required steps are:
- create / activate a venv
- install dependencies (with `uv` or `pip`)
- run the script with the active environment's Python interpreter

Scheduling recommendations
- For a robust production setup, run the script inside a process supervisor (systemd, PM2, Docker) or use OS scheduler:

- Windows Task Scheduler (recommended if you don't run a long-lived process):
  - Create a Basic Task that runs `python c:\path\to\repo\scripts\run_sys_prompt_agent.py --once` at 06:00 on weekdays.

- Cron (Linux/macOS):
  - Use `TZ='Europe/Paris'` to ensure local CET/CEST timing, e.g.:

```bash
TZ='Europe/Paris' 0 6 * * 1-5 /path/to/.venv/bin/python /path/to/repo/scripts/run_sys_prompt_agent.py --once
```

Notes
- The script defaults to `gpt-3.5-turbo`; set `OPENAI_MODEL` env var to change.
- LangSmith logging is optional and best-effort.
- Ensure `GITHUB_TOKEN` has `repo` scope to create issues.
