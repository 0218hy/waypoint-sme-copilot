# Models

**Waypoint's words come from a model.** The Skills (`skills/*/SKILL.md`) tell it what each moment must convey; code supplies every number, rule and card, and rejects any message with a bare number or an unknown placeholder. Nothing the bot says is pre-written. Without a model, every card, number and rule still works, and the chat shows a notice with Retry where the words would be.

## Roles

`config/models.yaml` picks the provider and model per role:

| Role | What it does |
|---|---|
| `voice` | Writes every message from the turn's beats |
| `turn` | Understands typed text: maps it to an allowed action, a slot value or a topic (code validates it) |
| `intent` | Optional guard classifier: it can add a rule flag, never remove one. Configured but not called today: the model's guard flag is the `rule_id` of the `turn` call |
| `reader` | Vision: reads a quote photo into lines (no tools, no network) |
| `judge` | Evaluation only, never the product: judges a reply's content against the frozen rubric of prereg addendum 2026-10-20 (8) (`eval/reply_judge.py`; `claude-sonnet-5-5` with `claude_code`) |

## Providers

The default is `auto`:

| Provider | How it authenticates |
|---|---|
| `anthropic` | `ANTHROPIC_API_KEY`, or `ANTHROPIC_AUTH_TOKEN` (+ `ANTHROPIC_BASE_URL`) for a gateway |
| `claude_code` | The **Claude Agent SDK** with your local Claude Code login. Run `claude` then `/login` once, or set `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`). It runs with no tools, no project settings and a temp working directory |
| `openai` | `OPENAI_API_KEY` (+ `OPENAI_BASE_URL`) for any OpenAI-compatible endpoint |
| `auto` | `claude_code` if the `claude` CLI is installed, else `anthropic` if a key or token is set, else none |

So if the Claude Code CLI is installed and signed in on your machine, `auto` uses it without asking. To choose explicitly, set `WAYPOINT_LLM_PROVIDER` to `anthropic`, `openai` or `none`.

With the `claude_code` provider, understanding typed messages (`turn`) and the guard classifier (`intent`) run on a small fast model (`claude-haiku-5-5`), and the voice and the quote reader use the Claude Code default model. With `anthropic`, every role uses `claude-sonnet-5-5` unless overridden. Each `claude_code` call asks for one plain JSON answer that code validates, falling back to the SDK's structured output only if it doesn't validate.

## A Chinese model (Qwen)

Production inside WeBank would use a domestic model filed with the CAC; nothing in the code names a model, so it is a configuration change. Qwen is reachable through the `openai` provider and Alibaba Cloud Model Studio's OpenAI-compatible endpoint, for example in `.env`:

```
WAYPOINT_LLM_PROVIDER=openai
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=your-model-studio-key
WAYPOINT_LLM_MODEL=qwen-plus
WAYPOINT_LLM_READER_MODEL=qwen-vl-plus
```

The base URL depends on the region your key was created in (Beijing above; see the Model Studio console). **Not yet tested in this build:** the evaluations so far ran with Claude (see `results/prereg.md`, addendum 2), and re-running them with a Qwen owner or agent is listed under "Not done yet" in the README.

## Running it

If your credentials live in `~/.zshrc` (e.g. `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` for a gateway), start Waypoint from a terminal that has loaded it (`make serve` in your usual shell does). Each reply takes a few seconds; the cards appear at once and the words follow. The Docker image has no Claude Code CLI, so in Docker use `anthropic` or `openai` with a key in `.env`.

Overrides: `WAYPOINT_LLM_PROVIDER`, `WAYPOINT_LLM_MODEL`, and per role `WAYPOINT_LLM_<ROLE>_PROVIDER` / `_MODEL` / `_BASE_URL` / `_API_KEY`. `GET /api/health` shows whether the voice model is ready (not after a recent provider failure, such as a failed startup check).
