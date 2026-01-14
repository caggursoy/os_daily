# os_daily
Daily Open Science updates

## Agent Visualization

Below is a simple visualization and explanation of the agent implemented in `scripts/run_sys_prompt_agent.py`.

Mermaid diagram (GitHub will render this when enabled):

```mermaid
graph LR
  A[Scheduler \n(APScheduler, Mon-Fri 06:00 Europe/Paris)] --> B[Read `sys_prompt.md`]
  B --> C[OpenAI Client \n(openai v1 or legacy fallback)]
  C --> D[Sanitizer \n(normalize dates, "Date:" lines)]
  D --> E[GitHub Publisher \n(create issue via GitHub API)]
  C --> F[Fallback Handler \n(log and raise on errors)]
```

ASCII fallback (for environments without Mermaid):

```
Scheduler (APScheduler)
	|
	v
Read `sys_prompt.md` -> OpenAI Client (v1 or legacy)
	|
	v
  Sanitizer (normalize dates)
	|
	v
GitHub Publisher (create issue via API)
```

Key components:

- **Scheduler:** Runs the job on weekdays at 06:00 Europe/Paris using `apscheduler`.
- **Reader:** Loads the system prompt from `sys_prompt.md`.
- **OpenAI Client:** Calls OpenAI (supports `openai>=1.0.0` client or legacy `ChatCompletion` fallback).
- **Sanitizer:** Normalizes headings/date lines to prevent hallucinated dates in issues.
- **GitHub Publisher:** Creates an issue in the repository specified by the `GITHUB_REPO` env var using `GITHUB_TOKEN`.

Usage notes:

- Set environment variables in a `.env` file or system env: `OPENAI_API_KEY`, `GITHUB_TOKEN`, `GITHUB_REPO`.
- Run once: `python scripts/run_sys_prompt_agent.py --once`.
- Run scheduler: `python scripts/run_sys_prompt_agent.py`.
