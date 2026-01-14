# Scheduling the Open Science News Agent

Overview
- Script: `scripts/run_sys_prompt_agent.py`
This repository includes a GitHub Actions workflow that runs `scripts/run_sys_prompt_agent.py` on weekdays at 06:00 Europe/Paris and can also be triggered manually.

Setup
-----
- Add the following repository secrets in the GitHub repository settings:
  - `OPENAI_API_KEY` — your OpenAI API key (required to call OpenAI).
  - `GITHUB_TOKEN` — automatically provided to Actions; no manual action required, but keep scope in mind if using a different token.

- The workflow sets `GITHUB_REPO` automatically to the repository (`${{ github.repository }}`).

Usage
-----
- To run the job manually, open the repository Actions tab, select "Run sys_prompt_agent", and click "Run workflow" under the `workflow_dispatch` trigger.
- To run locally for testing:

```bash
python scripts/run_sys_prompt_agent.py --once
```

Notes
-----
- The workflow schedule uses a UTC cron and performs a timezone check inside the job to ensure the script only runs at 06:00 Europe/Paris local time and on weekdays. This avoids needing Actions cron timezone support and handles DST correctly.
- Logs and created issues will appear in the repository Issues list. Check the Actions run logs for detailed output.

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
```

Google Docs (optional)
- If you want the digest appended to a Google Document, add:

```
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json  # or the JSON string
GDOC_ID=your_google_doc_id_here
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
 - Ensure `GITHUB_TOKEN` has `repo` scope to create issues.
 - The script requires `openai>=1.0.0` (the new v1 python client). If you previously pinned `openai<1.0.0`, upgrade with:

```bash
pip install --upgrade "openai>=1.0.0"
```

If you cannot upgrade, pin to the legacy client and revert the script changes by installing `openai==0.28.x` (not recommended):

```bash
pip install "openai==0.28.1"
```
