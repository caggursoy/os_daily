# os_daily
Daily Open Science updates

## Agent Visualization

Below is a simple visualization and explanation of the agent implemented in `scripts/run_sys_prompt_agent.py`.

Mermaid diagram (GitHub will render this when enabled):

```mermaid
graph LR
	A["Scheduler<br/>(APScheduler, Mon–Fri 06:00 Europe/Paris)"] --> B["Read sys_prompt.md"]
	B --> G["Web Search<br/>(web_search.py)"]
	G --> H["Search Synthesizer<br/>(concatenate results into prompt context)"]
	H --> C["OpenAI Client<br/>(openai v1 or legacy fallback)"]
	C --> D["Sanitizer<br/>(normalize dates, 'Date:' lines)"]
	D --> E["GitHub Publisher<br/>(create issue via GitHub API)"]
	C --> F["Fallback Handler<br/>(log and raise on errors)"]
```

ASCII fallback (for environments without Mermaid):

```
Scheduler (APScheduler, Mon-Fri 06:00 Europe/Paris)
		|
		v
Read `sys_prompt.md` -> Web Search -> Search Synthesizer -> OpenAI Client (v1 or legacy)
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
- **Web Search:** Performs a freshness-focused web search (`web_search.py`) to gather recent open-science items.
- **Search Synthesizer:** Concatenates titles/snippets/URLs into a compact context block prepended to the system prompt.
- **OpenAI Client:** Calls OpenAI (supports `openai>=1.0.0` client or legacy `ChatCompletion` fallback).
- **Sanitizer:** Normalizes headings/date lines to prevent hallucinated dates in issues.
- **GitHub Publisher:** Creates an issue in the repository specified by the `GITHUB_REPO` env var using `GITHUB_TOKEN`.

Usage notes:

- Set environment variables in a `.env` file or system env: `OPENAI_API_KEY`, `GITHUB_TOKEN`, `GITHUB_REPO`.
- Run once: `python scripts/run_sys_prompt_agent.py --once`.
- Run scheduler: `python scripts/run_sys_prompt_agent.py`.
