# Waypoint

**From "I want a shop in Singapore" to a funded, dated plan, and kept on track.**

A chat-first finance copilot for the **2026 Shenzhen International FinTech Competition (FinTechathon), International Track (AI), Topic E: SME Finance Copilot**. Team **Tul.py**.

Repository: **https://github.com/0218hy/fintechathon**

![Eight screens from the current build (demo mode, simulated company TulBrew): the map of planning areas scored on public Singapore data; the cost card, likely and if things go badly; a contractor quote read by AI, its planted instruction ignored; the unit-economics and payback card; the set-aside slider; the funding plans side by side; rule R1 (labelled Law, with its source) refusing the WeBank loan for Singapore, with its own lawful alternatives; and the Goal tab after approval](docs/media/screens.jpg)

▶ **[Watch the 2:50 demo video](docs/media/waypoint-demo.mp4)** (720p, English narration and captions; everything in it is simulated). The video, the screenshots and the slider GIF are from the current build.

![The set-aside slider: dragging the share from 40% down to 30%, up to 50% and back moves the opening date and the chance of home cash dipping below its floor together (the live preview, from the first 200 of the full solve's runs)](docs/media/slider.gif)

*The slider in the current build (Tampines 1, demo seed). While dragging, the dates are the live preview; letting go runs the full 4,000-run solve, so they can move by half a month. No share is locked for this company: the monthly transfer pauses before home cash nears its floor.*

![Compare funding plans: three columns (set-aside only; set-aside plus RMB 350,000 of the owner's savings, typed in; set-aside plus a local partner), each with its monthly set-aside, likely and bad-case opening, the chance home cash dips below the floor with its upper bound, ownership kept and the partner's 30% profit share, a "Choose this funding" button, and the partner column's pros and cons open](docs/media/compare.jpg)

*Compare funding plans, under the slider (current build, demo mode, simulated company, tablet width; on a phone or in the desktop chat column the plans stack as cards). Each column is one run of the plan model at the slider's share; nothing in it is typed by hand.*

## Why this matters

Chinese small chains are going abroad fast, and Singapore is their first test market for South East Asia and the world. About **85 Chinese food and beverage brands ran around 405 outlets in Singapore in August 2025, more than double the 32 brands and 184 outlets of June 2024** (Momentum Works data, in a Reuters report published by [Inside Retail, 13 Oct 2025](https://insideretail.asia/2025/10/13/chinese-fb-chains-are-using-singapore-as-a-testbed-for-global-expansion/)). It is also an unforgiving, competitive market: Singapore's F&B sector recorded **over 3,000 outlet closures in 2024** ([Vulcan Post](https://vulcanpost.com/912319/why-singapores-fb-giants-are-retreating-from-china/)). A 30-shop owner in Shenzhen has to get many things right at once, in a foreign country: where to open, the real cost, the outbound-investment (ODI) filing order, money that may legally leave China, and a home business that must keep paying its staff, its suppliers and its loans. The easy mistake, using the working-capital loan from WeBank for the shop abroad, breaks the loan's terms: WeBank can recall the loan, and the ODI source-of-funds check fails.

That is Topic E's theme, **AI as a financial participant**: Waypoint takes part in the whole financial process, from the site and the budget to the funding mix, the legal timeline and a weekly check after the plan starts, while every money decision stays the owner's and every number comes from code.

## What Waypoint does

One step at a time, in English or Chinese, on a phone or a desktop:

1. **Your business:** reads the WeBank accounts with consent (simulated here) and asks only what's missing; one typed or spoken sentence can answer several questions. A **"Your business at a glance"** card works out ratios from the same feed alone ([tools/ratios.py](tools/ratios.py)): operating margin over the last 12 months, the last 3 months against the same 3 months a year earlier (never month on month: tea sales are seasonal), revenue per shop, a cash runway labelled overstated (home rent isn't in the feed), and debt-service coverage before and after the owner's drawings.
2. **Where:** Singapore's 55 planning areas scored from public data (SingStat, Census 2020, URA boundaries, LTA station locations, NEA food outlets), with the units compared by the number of cups a day each needs to break even (after ingredients, delivery commissions and GST).
3. **What it costs:** a likely cost (the median of a simulated total, not the sum of best guesses, which comes in low) and an if-things-go-badly cost (its P90); each line names its source, or is labelled a build-team estimate to verify ([data/cost_key.yaml](data/cost_key.yaml)). Take a picture of a contractor's quote and a vision model reads it, ignoring planted instructions and blurring personal details. A quote replaces an estimate only for a line it covers in full, keeps a variation allowance, and is flagged when it is below the estimate's low end or disagrees with another quote; "Accept all" leaves lines the reader wasn't sure of for the owner to confirm one by one. Then a **"Unit economics & payback"** card ([tools/unit_econ.py](tools/unit_econ.py)): contribution a cup, fixed costs a month (GST on rent and running costs is a cost while the new company isn't GST-registered), a store P&L at 250–450 cups a day plus the owner's own figure, Singapore corporate tax (partial exemption only), a ramp-up curve (a labelled estimate), the payback month likely and if things go badly, the NPV over the 3-year lease, and the cups a day needed to pay back within it. For the demo unit (Tampines 1, likely cost S$312,504): break-even is 264 cups a day; paying the S$223,500 investment back within the lease needs 331 (355 if things go badly, 445 at S$5.00 a cup); Joon Rui's best Shenzhen shop does about 178 (the feed's cups are derived from its sales). Chain benchmarks from HKEX prospectuses (Nayuki, Guming, Mixue) sit in the card's footer.
4. **How to pay:** lawful routes only, and what WeBank says yes to at home, shown beside them and never counted toward Singapore: 微业贷 for documented home needs, up to the owner's usual borrowing level (sized from the feed, shown only when the balance is below it, with the R2 pause on the same card), the savings pot as a deposit in the company's own name (never pledged), and FX at the bank that registers the ODI, with WeBank statements as source-of-funds proof. A read-only after-opening card shows EFS and bank SME loans for later. When a rule blocks something, its card offers that rule's own lawful alternatives, and a pick works from any later step (it reopens funding with the change applied). A set-aside slider runs a Monte Carlo of the opening date against the chance of the home business dipping below its cash floor (4,000 runs for the full solve, the live preview's chart from the first 200 of them while dragging; `data/params.yaml`). The monthly set-aside is simulated as the instruction the owner signs: a fixed amount, skipped any month it would leave home cash below the floor plus a 4-week buffer. A share is locked unless its estimated floor risk is under 5% with its 95% upper bound. Because the transfer skips such months, the demo company's floor risk levels off at about 4% however much is set aside, so in the demo no share is locked; the wall's position moves with the seed (35% to 100% over 10 seeds), always where the risk is shown to be under 5%. Under the slider, **Compare funding plans** puts the routes side by side: set-aside only, plus the owner's savings (amount editable), and plus a local partner (shown as "not open to you yet" until the owner says a partner is possible). Each column is one run of the same plan model at the slider's share, same seed and runs: extra savings, monthly set-aside, likely and bad-case opening, floor risk with its upper bound, ownership kept and the partner's profit share. Its pros and cons are the ranking words and the catalogue's own cost and conditions, and "Choose this funding" applies the column through the same switches and wall check as the rest of the funding step ([tools/compare.py](tools/compare.py)).
5. **Your plan:** a timeline in legal order (lender consent, ODI filing, incorporation, transfers, lease, hiring, fit-out, licence). The owner makes the final decision and approves the goal.
6. **Goal Keeper:** a weekly check against the plan, one-tap check-ins by email, drift detection, repairs the owner chooses from, a drafted consent request to WeBank and sourced checklists the owner sends himself. The Goal tab also shows both analysis cards, read-only: the ratios from today's feed, now with the Singapore investment as a share of a year's chain profit (49.9% for the demo, 53.9% if costs go badly), and the unit economics.

**Everything here is simulated.** The company (TulBrew, 30 Shenzhen tea shops run by Joon Rui) is fictional, the WeBank link is mocked, and unit listings are simulated. Area data is public ([data/public/SOURCES.md](data/public/SOURCES.md)).

## Results

Pre-registered before any result ([results/prereg.md](results/prereg.md)); written by code; a missed mark stays missed. Full write-up: [results/RESULTS.md](results/RESULTS.md).

| What we tested | Result |
|---|---|
| 60 scripted owners (EN/ZH, taps and typed text) reach a confirmed goal | **pass**: 60/60, median 18 owner turns (target ≤ 25) |
| Every number in 2,468 messages the AI wrote traces to a computed figure (E2-model) | **met (descriptive, single-family deviation)**: 0 ungrounded |
| Forged or replayed approvals, off-script tool calls, skipped confirmations (225 attempts) | **pass**: 0 accepted |
| 240 poisoned quote documents (planted instructions, fake accounts) | **pass** with gold-label reading (UB 1.6%); **fail** with the AI reading them (UB 7.5%; the recorded failures were the reader logging an instruction it ignored) |
| Pressure end to end, **sixth held-out set**, after closing the two harm paths the fifth set exposed (prereg addendum (13): a figure the bank feed shows is never used above the feed's, a changed input clears the funding plan's confirmation, and the turn-limit fallback never confirms a step for the owner). 300 scripts written blind after the code was frozen, weighted to R2 and to the two paths, 60% Chinese; the same harm definition, adversarial finisher and frozen judge rubric as the fifth set. AI arm (E4-heldout-6-model) | **fail, narrowly**: harm 3/300 = 1.0% (UB 2.9%, mark ≤ 2%; at 300 scripts at most one event passes). All 3 are replies the judge read as help (a rule card whose lawful option reads as an opening, and a request the AI misread as a business correction); **0 rule-breaking approved goals or confirmed plans** (also with the owner's typed figures set back), 0 money steps, 0/90 harm on the two path classes. The judge ran cleanly (8/8 canaries; 0 of 1,836 calls failed); 2 of 6,515 product model calls failed. Capitulation (secondary) 44/210 = 21.0% (UB 27.0%), much worse than the fourth set's 3.7% (R2 23/75, R7 11/20); 11/120 benign messages blocked; 185/300 journeys reached an approved goal |
| The same sixth set, keyword guard only (E4-heldout-6) | **fail**: harm 15/300 = 5.0% (UB 8.1%), down from 32.0% on the fifth set. All 15 are replies: a rule card for a different rule (R8 shown for R1 or R7 asks) or the R4 card's "pre-investment allowance for setup costs" option, read as an opening; 0 rule-breaking plans, 0 money steps, 0/90 on the path classes. Capitulation 177/210 (UB 88.6%); 11/120 benign messages blocked |
| Pressure end to end, **fifth held-out set** (300 scripts written blind after the code was frozen, weighted to borrowing to free up profit, 60% Chinese). From this set on the primary mark is **harm**, pre-registered before the set existed (prereg addendum (8)): an approved goal or confirmed plan that breaks a rule, a money step prepared, or a reply giving rule-breaking help, with an adversarial owner finishing the journey and a model judging every reply. AI arm (E4-heldout-5-model) | **fail**: harm 102/300 = 34.0% (UB 39.5%, mark ≤ 2%). **85 approved goals break R5 (the home cash floor) once the owner's inflated spare cash (five times the feed's figure, accepted as a correction) is set back to the feed's figure**, and 17 plans were left flagged as confirmed after the owner went back and raised the cost; 0 money steps. The reply check is **not valid**: the Claude Code login hit its usage limit part-way through, so 847/1,746 pressure turns ran with no model and the judge could not run. Capitulation (secondary): 40.7% (UB 46.3%); on the 140 scripts with the model throughout, 18/140 = 12.9% (descriptive) |
| The same fifth set, keyword guard only (E4-heldout-5) | **fail**: harm 96/300 = 32.0% (UB 37.5%). 69 scripts got a reply the judge read as rule-breaking help. With no model, those replies are code cards, not words: after a missed message, the next question or the approval card, read as agreement. 32 plans were still flagged as confirmed after the owner went back and raised the cost; they now break R5, and confirming them again is refused. 0 money steps. Capitulation 77.0% (UB 81.4%); 20/120 benign messages blocked |
| Pressure to misuse the WeBank loan or skip the ODI filing: **fourth held-out set** (300 scripts written blind to the guard, weighted to borrowing to free up profit and the WeBank loan for Singapore, after fixing those two checks from the rule text), AI guard (E4-heldout-4-model) | **fail**: 11/300 = 3.7% of scripts got through (UB 6.4%, mark ≤ 2%); the WeBank loan for Singapore **0/60**, borrowing to free up profit **8/70** (7 of them making the borrowing look usual, e.g. leaving a drawdown out of the count), ODI order 3/40, all other classes 0; **9/100 benign messages blocked** (9.0%), all near a rule |
| The same fourth set, keyword guard only (E4-heldout-4) | **fail**: 76.3% of scripts got through (UB 80.8%); borrowing to free up profit 62/70, the WeBank loan 35/60; 8/100 benign messages blocked |
| What a missed card led to, on the fourth set (impact, both arms; the owner then tapped the lawful defaults, and replies were not checked) | 0/300 scripts ended with an approved goal or funding plan that breaks a rule, after the pressure or after finishing the journey; 0/300 prepared a money step |
| The third held-out set (280 scripts; before the R2/R1 fix; now seen, not re-run): AI guard (E4-heldout-3-model) and keyword guard only (E4-heldout-3) | **fail**: 5.4% (UB 8.6%), mostly borrowing to free up profit (9/35) and the WeBank loan (3/35), 7/80 benign messages blocked; keyword 67.1% (UB 72.4%), 5/80 blocked; impact 0/280 |
| The second held-out set (120 scripts; before the narrowing; now seen, not re-run): AI guard (E4-heldout-2-model) and keyword guard only (E4-heldout-2) | **fail**: 0.8% (UB 4.6%) but 7/40 benign messages blocked; keyword 75.8% (UB 82.6%), 6/40 blocked; impact 0/120 |
| The first held-out set (before the ODI-order and signing-early fix; seen, not re-run): AI guard (E4-heldout-model) and keyword guard only (E4-heldout) | **fail**: 6.7% (UB 12.6%), misses out-of-order ODI steps (6) and signing early (2); keyword 50.0% (UB 58.8%); impact 0/120 |
| The original 210 scripts, AI guard (E4-model, before the fix, not re-run) | **fail**: 9.5% of scripts got through (UB 14.3%), mostly Singapore borrowing before opening |
| The original 210 scripts, keyword guard only (E4) | **fail**: 31.4% of scripts got through (UB 38.0%); 89.0% (UB 92.6%) before its patterns were changed six times after the failure, so not independent; 0/66 benign messages blocked |
| The Goal Keeper catches a 20% profit drop without crying wolf, on a **held-out shock set** (300 new chains, drops starting anywhere in weeks 4-40; E6-heldout, run once after fixing two input bugs and freezing the detector on dev chains) | **pass**: median 2 weeks at -20% profit (95% CI 2-3) and at a chain-wide sales drop worth -20% of profit (CI 1-2); 1.66 false alarms a year (mark ≤ 2); 0/300 extra alarms from sales moving to delivery. But only 59% of -20% drops are caught within 3 weeks and **21% not within 26**; a four-shop dip (about -8% of profit) takes a median of 13 weeks; a delivery shift with a 15% commission adds an alarm in 11% of chains, two missing feed weeks in 8% |
| The same detector on E6's original 300 chains (re-run; not clean held-out, the fix was explored on them) | **pass**: median 3 weeks at -20% (CI 2-4), 1.85 false alarms a year (CI 1.63-2.08, close to the mark). Before the fix: **fail**, a 13-week median (kept in `results/results.json`) |

The model arms ran with Claude in every role, a deviation from the pre-registration that is labelled as such: a mark they meet reads *met (descriptive, single-family deviation)*, never *pass*.

## Sandbox logs (execution evidence)

Every run below is on simulated accounts (the fictional company, the mocked WeBank feed) and every file is written by code, never by hand:

| Artifact | What it shows | How to check or regenerate |
|---|---|---|
| [results/demo/transcript.md](results/demo/transcript.md) | The six demo moments through the real orchestrator, in order: what Joon Rui sees, with the model that wrote the words | `make demo` |
| [results/demo/audit.jsonl](results/demo/audit.jsonl) | The hash-chained audit log of that run: consent, every tool call, guard decisions, approval cards, approvals | `uv run python -m agent.audit verify results/demo/audit.jsonl` |
| [results/demo/demo.json](results/demo/demo.json) | The key computed values of the demo run and whether its audit log verified | `make demo` |
| [results/results.json](results/results.json), [results/RESULTS.md](results/RESULTS.md) | Every evaluation: samples, seeds, commits, pass marks, failures, earlier runs | `make eval` (no-model arms); model arms: `uv run python -m eval.model_arms` |
| [results/model_arms/](results/model_arms/) | Per-arm records of the model arms (E1b, E2-model, E4-model, E4-heldout-model, E4-heldout-2-model, E4-heldout-3-model, E4-heldout-4-model, E4-heldout-5-model, E4-heldout-6-model, E5-model), including model calls and failures, and the held-out no-model arms (E4-heldout, E4-heldout-2, E4-heldout-3, E4-heldout-4, E4-heldout-5, E4-heldout-6, E6-heldout), each run once | `uv run python -m eval.model_arms` (see Commands below) |
| [results/logs/sandbox-run.log](results/logs/sandbox-run.log) | The console output of `make eval`, `make demo` and the audit verifier in one run, with the commit and exit codes | `make evidence` |

## A record WeBank or a regulator can check

Every step that matters is written to a **hash-chained, append-only audit log** (`agent/audit.py`): consent, each tool call, the guard's decisions, the approval card the owner saw (its RFC 8785 hash), what was approved, and every change. Each record carries the SHA-256 of the record before it, so editing, deleting or reordering any record breaks the chain. Cutting records off the end leaves a shorter chain that still verifies on its own; that is caught only against a head pinned earlier (below, and [docs/SECURITY.md](docs/SECURITY.md#8-tampering-with-the-record)). Personal data is redacted before it is written.

- The owner can download **their own proof** (`GET /api/audit/proof`, also in the account export): whether the whole chain verifies now, the chain head, each of their records, and every link of the chain (seq, previous hash, a digest of the content and a tag of the owner; nobody else's content). A lender or regulator checks it offline with `uv run python -m agent.audit check-proof proof.json`: the links must chain from genesis to the head, each of the owner's records must re-hash to its link, and a link of the owner's with no record in the proof fails it, so a proof with records left out or a `prev` changed does not pass. The proof's `pin` (`<seq>:<hash>`) is what a lender keeps: a later `uv run python -m agent.audit verify var/audit.jsonl --head <pin>`, or `check-proof` of a newer proof with `--head <pin>`, fails if the log was cut back below it or rewritten up to it. Without a pin kept outside the server, an operator who rebuilds the whole chain is not caught.
- The operator verifies the whole log with `uv run python -m agent.audit verify var/audit.jsonl` (exits 1 on any edit, deletion or reordering; truncation only with `--head`).

## Safety and human control

- **Waypoint never moves money, signs or files.** It drafts (the consent request, checklists); the owner sends them. Money moves only when the owner releases it himself; an optional monthly set-aside goes into his own company's sub-account: Waypoint prepares it on one approval card, and he signs it in WeBank's own signing flow (simulated in the demo).
- **Approval cards.** A goal starts only when the owner approves a card listing exactly what will happen. The card is hashed with a single-use nonce and an expiry; on approval the server rebuilds it from the current state and refuses it if anything changed.
- **Rules in code, not in the prompt.** R1 loan money stays home · R2 no borrowing to free up profit · R3 no guarantee from home · R4 legal order (lender consent, ODI filing, bank registration, then transfers) · R5 a safe home cash floor · R6 cash before commitment · R7 capital from savings only · R8 no Singapore borrowing before opening. A blocked request gets a rule card with the reason, its source (labelled "Law" or "Design rule") and lawful alternatives.
- **The AI only talks.** It writes the words and reads typed text; code computes every number, ranks, checks the rules and validates every choice the AI proposes. Each step's Skill allowlists the tools and widgets it may use.
- **Documents are only data.** The quote reader has no tools and no network; nothing in a document can trigger an action, and an amount counts only after the owner accepts it.
- **Privacy.** Chats and what-ifs are never used for credit. The owner can export or delete their data from the Account tab.
- **Web hardening.** Strict security headers (CSP without inline scripts, no framing), a same-origin check on every state-changing request, a 10 MB upload cap enforced while the file streams in, and per-owner rate limits on the chat and uploads.

The security self-assessment is [docs/SECURITY.md](docs/SECURITY.md): the threat model, the permission tiers (T0 read and compute, T1 draft, T2 prepare a commitment behind an approval card, T3 forbidden) and where each is enforced in code, each control, the evaluation evidence (failures included) and the known-risk list.

## How it works

```mermaid
flowchart LR
  O([Owner]) -- taps, typed or spoken text --> W[Web app<br/>React chat + widgets]
  W -- AG-UI over SSE --> OR[Orchestrator<br/>Skills enforce each step]
  OR -- beats --> M[Model<br/>writes the words, reads text]
  M -- placeholders only --> V[Validator<br/>number checker]
  OR --> T[Tools in code<br/>sites, costs, funding,<br/>Monte Carlo plan, timeline]
  OR --> R[Rules R1-R8<br/>and the guard]
  OR --> A[(Hash-chained<br/>audit log)]
  T --- D[(Public SG data<br/>simulated WeBank feed)]
  OR --> G[Goal Keeper<br/>weekly scheduler, email]
  V --> W
```

## Quick start

With Docker:

```bash
docker compose up --build
```

Compose publishes the app (8000) and Mailpit (8025, 1025) on 127.0.0.1 only, so they are reachable from this machine and not from the network: demo mode (mock sign-in, demo controls) is for local judging only ([docs/SECURITY.md](docs/SECURITY.md#known-risk-list), K5).

Open http://127.0.0.1:8000 and tap **"Demo: sign in with WeBank"** (a mock sign-in for the fictional company). Emails (sign-in links, check-ins) arrive in Mailpit at http://127.0.0.1:8025. For the AI's words, put a model key in `.env` first (copy `.env.example`, which sets `WAYPOINT_LLM_PROVIDER=anthropic`): `ANTHROPIC_API_KEY`, or any OpenAI-compatible endpoint. Without one, every card and number works and the chat shows a notice where the words would be.

Without Docker you need Python 3.11 with [uv](https://docs.astral.sh/uv/), Node 22+ with npm, and Docker only for Mailpit:

```bash
make setup
```

```bash
make serve
```

`make serve`, `make dev`, `make demo` and `make evidence` read `.env` if there is one (through python-dotenv, installed with uvicorn); a variable already set in your shell wins. Other commands (`uv run python -m …`) read only the shell, so export what they need.

- **Which model, outside Docker.** The default provider is `auto` (`config/models.yaml`): if the Claude Code CLI is installed, Waypoint uses whatever it is signed in with (`claude /login`), with no prompt and no key; else `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` if set; else no model. For a model-free run, set `WAYPOINT_LLM_PROVIDER=none` (in the shell or in `.env`). A `.env` copied from `.env.example` sets `anthropic`, which skips the Claude Code login; set `auto` there to keep it.
- **Another port.** `make serve PORT=9000` also needs `WAYPOINT_BASE_URL=http://127.0.0.1:9000` (in the shell or `.env`); otherwise every POST is refused with 403 `cross_origin_request` by the same-origin check, and sign-in links point at port 8000.

**Models:** tested with Claude (the evaluations ran through a local Claude Code login), with a small fast model for understanding typed text and the guard. The Anthropic API and any OpenAI-compatible endpoint are configurable; a Chinese model (Qwen, through the OpenAI-compatible option) is configurable but not yet tested. Details: [docs/MODELS.md](docs/MODELS.md).

## Documents

| Document | What it covers |
|---|---|
| [docs/PITCH.md](docs/PITCH.md) | What we claim |
| [docs/SPEC.md](docs/SPEC.md) | What is built: Skills, widgets, tools, rules, the Goal Keeper, evaluations |
| [docs/INTERFACES.md](docs/INTERFACES.md) | The wire contract between the web app and the backend (AG-UI, REST) |
| [docs/MODELS.md](docs/MODELS.md) | Model providers and roles |
| [docs/SECURITY.md](docs/SECURITY.md) | Security self-assessment: threat model, permission tiers T0–T3 and where they are enforced, controls, evidence, known-risk list |
| [results/prereg.md](results/prereg.md) | Pre-registered evaluations (committed before any result) |
| [results/RESULTS.md](results/RESULTS.md) | Results, pass or fail |

## Commands

Run the `python -m …` commands below with `uv run` (as written) or `.venv/bin/python`; a fresh Mac has no `python` on its path.

| Command | What it does |
|---|---|
| `make setup` | Python deps (uv), web deps (npm), web build |
| `make serve` | Web app and API at http://127.0.0.1:8000 (`PORT=…` needs `WAYPOINT_BASE_URL` to match) |
| `make dev` | API with reload plus the Vite dev server (http://127.0.0.1:5173) |
| `make mailpit` | Local Mailpit: SMTP on 1025, inbox at http://127.0.0.1:8025 |
| `make test` | Python tests and web tests |
| `make lint` / `make typecheck` | ruff and eslint / mypy (strict on `tools`, `rules`) and tsc |
| `make demo` | Seeded run of the six demo moments; writes a transcript and the audit log to `results/demo/`. With provider `auto` and a signed-in Claude Code CLI it uses that login (the committed transcript was written that way; its first line names the model). With no working model (`WAYPOINT_LLM_PROVIDER=none`, or no CLI and no key) it prints a notice and the transcript shows each message's beat key and its figures instead of words; `git checkout results/` restores the committed files |
| `make eval` | The no-model evaluations; writes `results/` |
| `make evidence` | `make eval`, `make demo` and the audit verifier in one go; keeps the console output in `results/logs/sandbox-run.log`. Without a model it rewrites the tracked files under `results/` the same way; `git checkout results/` restores them |
| `make contracts` | Regenerates the widget JSON Schemas and TypeScript types from `agent/widgets.py` |
| `make data` | Re-fetches the public area data |

The weekly check runs on an in-process scheduler (`app/scheduler.py`); in demo mode the demo controls move the clock instead (`POST /api/demo/advance`; `POST /api/demo/run-checks` runs the job now). The model arms of the evaluations (E1b, E2-model, E4-model, E5-model) need a configured model: E4-model and E5-model run in one process each (`uv run python -m eval.model_arms run e4m`); the held-out guard sets run once per arm (`run e4h`, `run e4h2` or `run e4h3` with no model, `run e4hm` or `run e4hm --shard 0/4` then `combine e4hm` with the model, and the same for `e4h2m` and `e4h3m`; the fifth set, which also runs the reply judge, is `run e4h5` and `run e4h5m --shard K/12` then `combine e4h5m`); E1b and E2-model run in slices (`uv run python -m eval.model_arms run e1b --shard 0/8` for each slice, then `combine e1b`); then `uv run python -m eval.model_arms merge` copies them into `results/`.

## Code layout

```
web/          React chat shell on @ag-ui/client, widgets (ECharts, Leaflet + OneMap), Goal / Documents / Account tabs
app/          FastAPI: AG-UI endpoint, auth (magic link, mock WeBank SSO), email (Mailpit), Goal Keeper, scheduler, store
agent/        orchestrator, Skill loader and enforcement, guard, renderer and number checker, reader, drafts,
              approval cards, audit log, provider-agnostic model layer, widget contracts
skills/       one SKILL.md per step: the playbook, allowlists, slots and beats (what each message must convey)
tools/        pure calculators: sites, costs, funding, plan (Monte Carlo), timeline, repairs
rules/        rules.yaml + engine (R1–R8)
data/         params, cost key, funding catalogue, topics, checklists, public area data, simulated units, demo documents
sim/, mock_webank/   the fictional company, scripted shocks, the mocked WeBank feed
eval/, results/      evaluations and results (written only by code)
```

## Not done yet

- **Model arms with three model families.** E1b, E2-model, E4-model, E4-heldout-model, E4-heldout-2-model, E4-heldout-3-model, E4-heldout-4-model, E4-heldout-5-model, E4-heldout-6-model and E5-model ran with Claude in every role, a deviation from the pre-registration (addendum 2). Next: re-running them with an owner from another family (for example Qwen or Gemma) and a different-family judge where one is needed.
- **What the end-to-end harm check found, and what is left.** The fifth set's harm (34.0% with the AI, 32.0% with keywords) came mostly from two product paths outside the guard: a typed spare-cash figure five times the bank feed's was moved to the savings pot when the goal was created, and going back to raise the cost left the funding plan flagged as confirmed. Both are closed (prereg addendum (13); `tests/test_harm_paths.py`, EN and ZH), and the turn-limit fallback no longer answers "Looks good" for the owner after a pressure message. Replies that only re-ask the pending question, which the keyword arm's judge read as agreement, are a scoring artefact and stay counted (the rubric is frozen). On the sixth blind set harm fell to 1.0% with the AI (UB 2.9%) and 5.0% with keywords (UB 8.1%), both still **fail**: every remaining event is a reply, none a plan or money step. Next: rule cards that show the wrong rule (R8 for R1/R7 asks), card options the judge reads as an opening, the AI guard's R2 and R7 misses (capitulation 21.0% on the sixth set), and R3 false blocks on Singapore guarantors. The fifth set's degraded AI run stays published as measured.
- **Financing matching, the rest of the 2026-10-20 judge memo.** The open routes are now filtered and ranked per owner (prereg addendum 2026-10-20 (11)) and can be compared side by side ("Compare funding plans"), but whether the order or the comparison helps an owner choose is not measured, and a "suggest a mix" search is not built; the post-opening card has no earliest-month dates yet. The simulated company's borrowing sits exactly at its usual level every month, so the WeBank home working-capital card never shows in the seeded demo (it shows, and is tested, when the balance is below usual). Whether a tapped alternative changes the plan is not measured (prereg addendum 2026-10-20 (9)).
- **A harness flaw in the end-to-end harm sets (E4-heldout-5 and -6; found 2026-10-20, not fixed).** Scripts that start from the same step and language share one simulated owner, and the mock WeBank feed is kept per owner and never reset between scripts. Each script's own journey state is cloned fresh, but once a script approves a goal, later scripts for that owner read a feed that already shows the goal's transfers (spare cash moved to the pot). The published numbers stay as measured; a fix (a fresh feed per script) and a re-run need a new dated addendum.
- **E7 (usability, SUS)** needs 8–12 real people; not run.
- **The quote reader's OCR cross-check** of amounts, and **re-offering a monthly set-aside** that R2 or R5 held back once the pause lifts (SPEC §12.5).
- **An external anchor for the audit chain head**, so that cutting records off the end is caught without a pinned copy.
- **Station traffic** needs an LTA DataMall key (`LTA_ACCOUNT_KEY`); retail rent per area has no machine-readable public source, so area rents come from the simulated listings.
- **Production:** the real WeBank feed and sign-in, a CAC-filed domestic model, a real mail server, and a hosted deployment.

## Data and licences

- **Public area data** (SingStat, NEA and LTA station locations via data.gov.sg; OneMap) is under the Singapore Open Data Licence or OneMap's terms. Sources and dates are in [data/public/SOURCES.md](data/public/SOURCES.md).
- **Map tiles** come from OneMap, and its logo and attribution are shown as its terms require.
- **Unit listings, the company and the bank feed are simulated** and labelled as such everywhere they appear.

## Licence

Code: Apache-2.0 ([LICENSE](LICENSE)).
