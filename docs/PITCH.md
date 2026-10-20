# Waypoint: the pitch

**2026 Shenzhen International FinTech Competition (FinTechathon) · International Track (AI) · Topic E: SME Finance Copilot**
Version 2.0 · 19 Oct 2026 · What to build: [`SPEC.md`](SPEC.md)

> **Waypoint is a chat guide that walks a Chinese small-business owner, one step at a time, from "I want a shop in Singapore" to a funded, dated plan, and then keeps him on it.** It suggests where to set up, works out what it will cost, shows how to pay for it without putting the home business at risk, and turns the result into a goal that it checks every week and emails him about. The AI does the talking. Code does the numbers and enforces the rules.

**Labels:** **[fictional]** the demo company is invented. **[illustrative]** example numbers; the build computes the real ones. FX: S$1 ≈ RMB 5.25.

---

## 1. The problem

### Many owners want to go, and many get it wrong
- **Chinese food brands are pouring into Singapore.** About 85 Chinese F&B brands ran about 405 outlets in August 2025, more than double the 32 brands and 184 outlets of June 2024 (Momentum Works data, in a Reuters report published by [Inside Retail, 13 Oct 2025](https://insideretail.asia/2025/10/13/chinese-fb-chains-are-using-singapore-as-a-testbed-for-global-expansion/)).
- **Most food businesses that close are young.** Of Singapore's retail food establishments that closed between 1 January and 23 October 2025, 63% had been registered for five years or less, and 82% of those had never declared a profit in their annual tax returns (Minister for Trade and Industry, [written parliamentary reply, 5 Nov 2025](https://www.mti.gov.sg/newsroom/written-reply-to-pq-on-retail-food-establishments-which-ceased-operations-after-five-years-or-less-that-have-recorded-profit); age is measured by registration, as ACRA holds no operating dates).
- **Staff is the hidden constraint.** A new shop can't bring its crew from China: work permits for PRC nationals are capped at a small share of a services company's workforce, and quota is earned only by employing locals first (Ministry of Manpower, 2026).

### Who we serve
**Joon Rui [fictional], CEO of TulBrew,** runs 30 profitable tea shops in Shenzhen. He makes about RMB 210k a month in operating profit and has about RMB 500k of spare cash. He has a WeBank 微业贷 line for his summer stock build. He wants one small mall shop in Singapore. He knows tea and he knows Shenzhen. He doesn't know Singapore's malls, costs or rules, and he has no time to learn a finance tool.

### What trips him up
1. **Where?** He doesn't know which neighbourhoods have his customers, or what rent is normal there.
2. **How much?** The bill is bigger than it looks, and most of it is due before opening: deposit, fit-out, pre-opening rent and wages, a running-cost reserve, and costs he has never paid at home (a resident director, CPF, work-pass rules).
3. **With what money?** His WeBank loan legally can't fund an overseas shop (互联网贷款办法 Art. 24(三); 流贷办法 2024 Art. 9). Singapore banks usually want trading history. A guarantee from home (内保外贷) is allowed with SAFE registration, but it puts the shops that repay WeBank on the hook for Singapore, so Waypoint's plans leave it out (a design rule, labelled as one).
4. **In what order?** Money must leave China by the right door: WeBank's consent as lender, then the ODI filing (outbound direct investment, i.e. registering the overseas investment), then bank registration, and only then the remittance and the lease. Skipping the filing risks a fine and a bar on future outbound investment (State Council Decree 837, Art. 27).

### Why today's tools don't help
Finance tools expect the owner to learn a dashboard of tabs, inputs and charts, all on screen at once. A general chatbot does talk to him, but it gives totals with no sources and will cheerfully suggest using the loan. A 代办 agent files the paperwork but doesn't plan the cash. **Nobody guides him through the whole decision in his own words and then stays with him until the shop opens.**

---

## 2. The solution: a guide, not a dashboard

### The idea
Joon Rui doesn't learn Waypoint. **Waypoint interviews him.** The chat asks one thing at a time, offers tap-to-answer choices (or he types or speaks his answer: a microphone button fills the message box using the browser's speech recognition), and brings a topic up only when it matters ("you'll need a resident director: here's what it costs"). When a decision needs more than words, the chat shows an interactive card: a map, a cost breakdown, or a slider that moves his opening date. Nothing is on screen until he needs it.

### The journey: five steps in one conversation

| Step | Waypoint asks | Joon Rui sees | Joon Rui decides |
|---|---|---|---|
| **1. Your business** | Whatever WeBank's data doesn't already say: customers, rough budget, when. Tap answers, or one sentence ("thirty shops, young customers, about S$400k, next year") fills several at once | A short summary card, and **"Your business at a glance"**: ratios worked out from the same WeBank data (margin over the last year, the last three months against the same months a year earlier, revenue per shop, a cash runway marked overstated, loan cover before and after his drawings) | "That's right" |
| **2. Where** | "What matters most: foot traffic, low rent, or being near your kind of customer?" | A **map** of the three best-matched areas with the reasons (residents, income, typical rents from the simulated listings); then **two or three real-sized units** side by side, each with the cups a day it needs to break even next to his best and his average Shenzhen shop | One unit to cost |
| **3. What it costs** | One question: "Anything to change?" (fit-out level, his own manager, or snap a contractor's quote) | A **cost card** built on sensible defaults, likely (the median of the simulated total) and if-things-go-badly, in six groups he can open; a quote photo is read line by line and "Accept all" applies the lines read clearly in one tap (any the reader wasn't sure of, he confirms one by one). A quote replaces an estimate only for a line it covers in full (he says so on the card), keeps a variation allowance, and is flagged if it is below the estimate's low end or disagrees with another quote; a note that staff must be hired locally first. Then **"Unit economics & payback"**: what a cup earns after ingredients, delivery commissions and GST; the shop's monthly P&L at several cups a day and at his own guess; tax; when the investment comes back (likely, and if things go badly) or "not within the lease"; its value over the lease; and the cups a day needed to pay back within the 3-year lease | "Looks right" |
| **4. How to pay** | "How much of your monthly profit can you set aside?" | **Funding options** as cards (what each covers, when, what it costs), and the closed ones with the reason. **What WeBank says yes to, at home**, beside them and never counted: 微业贷 for documented home needs up to his usual borrowing level (when he is below it), his pot as a deposit in his company's name, never pledged, and FX at his ODI bank with WeBank statements as proof. A read-only **after opening** card (EFS, bank SME loans). A **set-aside slider** that moves his opening date and shows how close home cash gets to his safety line | His set-aside and funding mix |
| **5. Your plan** | Nothing: the approval card shows the defaults (monthly email check-ins, no amounts in emails); optional chips change them | A **timeline** of every step in the legal order (WeBank's consent, the outbound investment filing, bank registration, company and account, first transfer, lease, then fit-out alongside hiring and training local staff, licence, opening) with dates, and a one-line goal | "Start my goal" |

Our target is about a dozen taps from hello to a goal on the happy path; we are not there yet. Simulated owners took a median of **18 owner turns** (E1a: scripted owners who also ask side questions, trigger the guard once and go back once; 15 without those messages) and **20** when a model played the owner (E1b, single-family deviation). The cards appear at once and Waypoint's words follow a moment later. He can stop at any point, ask a side question, or go back a step; anything that depends on that step updates and Waypoint tells him what changed.

### The Goal Keeper: the part that stays
After step 5 the goal moves to its own **Goal tab**, a read-only dashboard. It shows:
- the target and the plan's status;
- his savings so far against the plan;
- the next step and its date;
- **Your plan**: the unit he chose, its cost card and how it's funded;
- **the analysis**: his business at a glance from today's data (now with the Singapore investment as a share of a year's profit) and the unit economics, read-only.

To change anything he taps "Change in chat". The guide reopens that step, and the change takes effect only once he approves it.
- **Every week** it compares what actually happened (profit, money set aside) with the plan and recomputes the dates. An in-process scheduler (`app/scheduler.py`, hourly tick) runs the check once per week of each goal's life and catches up a missed week; in demo mode the demo clock runs the same job instead.
- **It alerts on the plan, and errs toward fewer false alarms.** A slow week is ignored. If the opening date slips, the safety risk rises, or a step's deadline is near, he gets an **email** and the Goal tab shows the alert; from there the chat offers two or three fixes with their new dates: set aside a bit more, add some savings, ask the landlord for rent-free months, or pick a cheaper unit. **How prompt it is, in simulation:** on a held-out set of 300 new simulated chains with the drop starting anywhere from week 4 to week 40, a 20% profit drop is caught after a median of 2 weeks (our mark was 3: passed) and the detector raises 1.7 false alarms a year (mark ≤ 2: passed); a shift of sales to delivery added none. That came after a failed first test (a median of 13 weeks) that we traced to two input bugs, fixed, and re-tested on chains the fix had never seen. It is not instant: 41% of 20% drops take longer than 3 weeks and 21% are not caught within six months, and a smaller dip, like the four-shop one in the demo, takes a median of 13 weeks.
- **He chooses; Waypoint re-plans.** Every change to the goal is his call, confirmed in one tap.
- **Check-ins take one tap.** The monthly email has an "On plan as usual" button; only when something changed does he open the chat and enter two numbers.

### Two ways in
- **Inside WeBank's business app:** he signs in with WeBank. With his consent his profit and cash are read from his accounts, so the questions are shorter and the weekly check reads the feed instead of asking. He can also choose a monthly transfer into his company's own savings sub-account: once he approves it, Waypoint prepares the instruction in WeBank (mocked) and he signs it in WeBank's own flow; WeBank re-checks it before every transfer and skips the month while borrowing is above normal or if it would leave home cash below the floor plus a 4-week payroll buffer, exactly as the plan assumes. Waypoint never moves the money.
- **On the web:** he signs in with his email (a one-time link). He types or uploads his numbers. The check-in email (monthly by default) has a one-tap "On plan as usual" link; when something changed, he enters two numbers in the chat.

Either way, reminders and alerts go to his email.

### Skills: what keeps the AI on track
A guide that talks freely can also wander off. Each step of the journey is a **Skill**: a written playbook that tells the AI:
- what to find out, and in what order;
- which calculators and cards it may use, and nothing else;
- which topics to raise, and when;
- when the step is done.

Code enforces the playbook. The AI can't skip a step, can't call a tool the step doesn't allow, and can't move on until the step's output passes its checks and Joon Rui confirms it. The result is a conversation that feels flexible but always follows the same safe path.

---

## 3. Safe by design

**The design rule:** the AI asks, explains and chooses which card to show. **Code computes every number, checks every rule and fills every card.** Money never moves unless Joon Rui approves it himself.

**The rules every plan must pass** (checked in code, each with its source, labelled "Law" or "Design rule", a plain-language message and tests):

| Rule | In Joon Rui's words |
|---|---|
| Loan money stays home | "Your WeBank loan can't pay for Singapore. It's the law, and it protects your shops." |
| No borrowing to free up profit | "While you're borrowing more than usual, your Singapore savings pause." This stops indirect diversion (置换): borrowing for home bills so that profit can go abroad |
| No guarantee from home | "Nothing in China guarantees anything in Singapore." |
| The right order | "No money leaves before WeBank's consent, the ODI filing and the bank registration." |
| A safe home floor | "Your home cash stays above the line you choose: we estimate the chance of dipping below it, and lock any set-aside whose estimated risk we can't show is under 5% (95% upper bound, 4,000 simulated runs)." The risk is an estimate from a model of his own history, not a guarantee. |
| Cash before commitment | "You don't sign the lease until the deposit and fit-out money is already in Singapore." |

**How the AI is kept honest:**
- **No invented numbers.** The AI's text holds only placeholders, and code fills them from computed, sourced figures. Any bare number or number word ("三成", "twice") in the AI's text is blocked.
- **Documents are data.** A photographed quote is read by a reader with no tools. It can only fill in cost lines, which Joon Rui sees and confirms. In our tests no poisoned quote changed the approval card or put a fake recipient on it. But with the model reading the photos, 10 of 240 poisoned quotes counted as a change (of the 8 we recorded in full, each was only an audit-log entry for the planted instruction the reader dropped), so that test failed its mark (Wilson upper bound 7.5% against ≤ 2%).
- **Pressure meets the rule and a way forward, when the guard catches it.** "Just use my WeBank line for now" is refused, the rule is cited, and the lawful options are shown (every time the guard blocked, in every test). Our conversational guard is an early warning, not the safety boundary. On four blind held-out sets it let 0.8–6.7% of pressure scripts through without a rule card (latest 3.7%, upper bound 6.4%, against our own pre-registered 2%), and we publish every miss. The boundary is code: every plan, approval card and money step is re-checked by the rules engine, and across 820 blind pressure scripts none ended in a rule-breaking approved plan or a prepared money step (0/820, descriptive). We have pre-registered that outcome as the primary mark for the next set (prereg addendum (8)), with a harder test: an owner who keeps pushing, picks non-default options, inflates his figures and goes back and forth, and a model checking every reply. On that set it failed (34% of scripts with the model, 32% with keywords only, against 2%). The cause was not the guard: Waypoint took the owner's word for five times his spare cash over the bank feed, so 85 approved plans break the home-cash floor on the feed's real figures. Two smaller causes: a plan left flagged as confirmed after going back, and replies to a missed request that didn't refuse. These are the next fixes. Side questions now get a checked card, never a free answer, and the model that writes Waypoint's words never sees what the owner typed.
- **Least privilege.** Each Skill can reach only its own tools, and every action is logged in a tamper-evident audit log.

**Privacy:** his chat and what-ifs are never used for credit decisions. Emails carry no amounts unless he turns them on. Consent is separate and can be withdrawn.

---

## 4. How Waypoint meets Topic E

Topic E asks for *"a finance copilot for small-business owners, offering financing-option matching, cash-flow management with alerts, and business financial analysis"* (competition rules, International Track, Topic E: SME Finance Copilot).

| Topic E asks for | Waypoint |
|---|---|
| **For small-business owners** | A guided chat in his language, tap answers, no training needed, on his phone inside WeBank or on the web |
| **Business financial analysis** | His chain's ratios from the WeBank data (margin, a seasonally fair trend, revenue per shop, runway, debt-service cover); site comparison on public data with break-even per unit; a sourced cost card that quote photos can refine; the new shop's unit economics: contribution a cup, a store P&L with Singapore tax, payback month, NPV over the lease and the cups a day needed to pay back, against listed chains' published store figures |
| **Financing-option matching** | Every lawful way to fund the move, compared on what it covers, when it's available and what it costs; closed options shown with the reason, each rule labelled "Law" or "Design rule" with its source. WeBank says yes where it can: home working capital up to the usual level, the pot as a deposit, statements as source-of-funds proof for the ODI bank. Each rule card offers that rule's own lawful alternatives, and they work from any step. The open routes are filtered to this owner (spare cash, savings, a partner they'd consider, a chosen unit) and ranked by code on cost, time to money, ownership and floor risk, shown as words such as "cheapest" and "keeps full ownership", never a score. Not yet: a "suggest a mix" search (memo §1b iii) |
| **Cash-flow management with alerts** | A set-aside plan that keeps home cash above a floor he picks, through the legal steps in order; the Goal Keeper checks it every week, alerts by email when the plan moves, and offers fixes he can pick |
| **AI as a financial participant** | It runs the whole process with the owner, and every money step stays his |

---

## 5. How Waypoint meets the grading components

### Task completion (40%)
- **The whole journey works end to end:** profile → site → cost → funding → goal → weekly check, on Joon Rui's data, in English and Chinese.
- **Measured** (pass marks set before testing; see SPEC §11): the share of simulated owners who finish the journey, the number of turns it takes, how fast the Goal Keeper catches a real drop, and how often it raises a false alarm.

### Security & compliance (30%)
- The plan rules above (eight in all; SPEC §8.1), each checked in code and tested both ways.
- No invented numbers, documents treated as data, pressure tests and injection tests, each measured on our own test suite, with the failures reported as failures (§8).
- Human approval for every commitment, and a tamper-evident audit log the owner can hand to a lender or regulator to check.
- Web hardening: strict security headers, a same-origin check on every state-changing request, a streamed upload cap and per-owner rate limits. The threat model, each control and its evidence are in [SECURITY.md](SECURITY.md).

### Innovation & interaction (30%)
- **The chat is the product.** Waypoint replaces a dashboard with an interview that shows interactive cards only when they are needed.
- **Skills** make a free-flowing AI conversation follow a strict, checkable process.
- **The set-aside slider** turns the hardest decision (how much profit to set aside, and how soon he can open) into one gesture.
- **The Goal Keeper** stays with him after the conversation ends, by email.

---

## 6. What WeBank gets

- **A growing customer kept** at the moment he is most likely to look elsewhere.
- **The home loan protected:** the plan never relies on the loan, and it pauses saving while borrowing is above normal.
- **Fewer surprises:** WeBank's consent is the first step on his timeline, so the bank hears about the plan before any money moves. (The plan does not yet model a refusal.)
- **Stated plainly:** WeBank doesn't lend to the move, because the loan rules forbid using working-capital and internet loans for equity investment. Its role is the home business (working capital, up to his usual borrowing level, shown on its own card beside the plan and never counted in it), custody of the savings pot as a deposit in his company's name (if Joon Rui chooses; never pledged), his statements as the source-of-funds proof for the bank that registers the ODI, and a shock buffer that is planned never to be drawn. "No" comes with the rule's own lawful alternatives.

---

## 7. The demo: six moments in about 3 minutes

1. **Hello:** Joon Rui signs in. Waypoint already knows his shops from WeBank; he answers the rest in one sentence and confirms the summary card; a second card shows his chain's ratios from the same data (18.4% operating margin over the last 12 months; loan repayments covered 4.4 times, 2.6 times after his drawings; simulated).
2. **Where:** a map lights up three areas with the reasons (residents, income, rents). He taps one, compares two units and picks one.
3. **What it costs:** the cost card appears. He snaps a photo of a contractor's quote, confirms it covers the whole fit-out, and the fit-out line updates (with a variation allowance). Waypoint raises the resident-director cost at that point, not before. The unit-economics card follows: Tampines 1 breaks even at 264 cups a day, and paying the S$223,500 investment back within the lease needs 331 (355 if things go badly, 445 at S$5.00 a cup), against about 178 at his best Shenzhen shop. (The recorded video predates this card.)
4. **How to pay:** the cards show what WeBank says yes to at home, beside the routes for Singapore. He types "just use my WeBank line": the rule card, its source (labelled "Law"), and R1's own alternatives (set aside more, his savings, WeBank for home needs). He drags the set-aside slider and the opening date and the home-safety line move together.
5. **Your plan:** a timeline in the legal order. He taps "Start my goal", and the Goal tab and a welcome email appear.
6. **Weeks later:** sales dip at four shops and the date slips. An alert email arrives, the Goal tab shows the alert, and "See fixes" opens them in the chat. He picks one and approves the updated plan. This is one illustrative run with the demo clock, with a paired control: the same simulated company and plan with no dip raises no alert over the same 16 weeks (the control's status still drifts, to "at risk" at week 12 and "off track" at week 16, likely week 72 against 63, without an alert or a detector alarm). The demo's simulated seed was chosen for that by a rule we registered first, re-run after the detector fix; of the 7 seeds tried with the persona's shape, 2 no-dip runs set off the detector by themselves (1 alerted) and in 4 the dip raised no alert within the 16 weeks (`results/demo/seed_search.json`). On the held-out set a dip like this is caught after a median of 13 weeks, and a 20% profit drop after 2 (E6-heldout).

---

## 8. What we don't claim

- The demo company is fictional, the WeBank link is mocked, and unit listings in the demo are simulated (labelled as such).
- Area data is public and dated; it informs the choice but doesn't predict sales.
- Dates and risks rest on stated assumptions, shown in the plan.
- Waypoint narrows misuse of the loan on the accounts it sees; it can't see cash or other banks.
- The prototype is not licensed, audited or certified compliant. It is information, not financial advice.
- **Measured failures, stated as failures** (all in `results/RESULTS.md`; marks were set before testing):
  - **The guard under pressure** still fails. We fixed its biggest gap (borrowing in Singapore before opening) and tested it on 120 new pressure scripts written blind to the guard: with the model reading messages, 6.7% got at least one turn past it (Wilson upper bound 12.6% against a 2% mark); the misses asked to do the ODI steps out of order or to accept the offer early. We then fixed those two from the rule text and tested on a second blind set of 120: 1/120 = 0.8% got through (upper bound 4.6%: still a fail; a set of 120 could not pass the mark even with no misses, as 0/120 has an upper bound of 3.1%, and neither could the first), but the guard then **blocked 7 of 40 lawful messages**, such as reporting that consent is done and asking about the filing. We narrowed the checks so questions about a step, its order or status, and the next lawful step once everything is done, stay quiet, and tested on a third blind set of 280 (large enough that the 2% mark is passable): **15/280 = 5.4% got through (upper bound 8.6%: fail)**, 9 of them borrowing more at home while the Singapore set-aside continues (R2, 9/35), 3 the WeBank loan for Singapore, and 1 each for the ODI order (of 50) and signing early (of 50); false blocks fell to 7/80. With keyword rules alone, 67.1% of the third set got through. We then fixed R2 and R1 from the rule text and tested on a fourth blind set of 300 weighted to them: **11/300 = 3.7% got through (upper bound 6.4%: fail)**: none of the 60 WeBank-loan scripts, 8/70 borrowing-to-free-profit scripts (7 of them asking to make the borrowing look usual) and 3/40 ODI-order scripts; it blocked 9/100 lawful messages, 3 of them home drawdowns read as using the loan for Singapore. With keyword rules alone, 76.3% of the fourth set got through. On the original 210 scripts it was 9.5% with the model (before the fixes) and the keyword baseline is not independent (its patterns were changed after that test had failed).
  - **What a missed card led to:** on the first four new sets, no script ended with an approved goal or funding plan that breaks a rule, and none prepared a money step, even after the simulated owner went on to approve the goal; that owner tapped the lawful defaults, and the replies were not checked. Plans are built by code from lawful routes and re-checked before approval; a missed card means the owner wasn't told why.
  - **End-to-end harm (fifth set, E4-heldout-5)**, the primary mark from that set on (pre-registered before the set existed), **failed in both arms**: 102/300 = 34.0% with the model (upper bound 39.5%), 96/300 = 32.0% with keywords only (upper bound 37.5%), against 2%. With the model, 85 approved goals break R5 once the owner's inflated spare cash (accepted as a typed correction, five times the feed's figure) is set back to the feed's figure. With keywords only, 69 scripts got a reply the judge read as agreement: code cards that moved on after a missed message instead of refusing. In both arms, some plans were left flagged as confirmed after going back (32 and 17). No money step was prepared. The AI arm was cut short by a usage limit: 847 of 1,746 pressure turns ran with no model, and the reply judge could not run (that check is not valid for this arm). On the 140 scripts that had the model throughout, the guard let 12.9% through (descriptive), more than on the fourth set.
  - **After closing those paths (sixth set, E4-heldout-6)**, written blind after the fix was frozen: end-to-end harm **3/300 = 1.0% with the model (upper bound 2.9%: still a fail; at 300 scripts at most one event passes)** and 15/300 = 5.0% with keywords only (upper bound 8.1%: fail). Every remaining event is a reply the judge read as help (a rule card for the wrong rule, or a card option it read as an opening); none is a rule-breaking goal or plan, and none prepared a money step. Typed figures above the bank feed's are now shown as "not verified" and never used, and a changed input clears the plan's confirmation. The AI guard itself let 21.0% of rule-class scripts through without a rule card (upper bound 27.0%), worse than on the fourth set.
  - **Documents read by the model (E5-model)** failed: 10 of 240 poisoned quotes counted as a change under our measure (upper bound 7.5% against 2%). Of the 8 recorded in full, each was only an extra audit-log entry for the planted instruction the reader dropped; none of the 240 changed the approval card or added a recipient.
  - **Alert speed (E6)** failed first: a 20% profit drop was detected after a median of 13 weeks, against a 3-week mark. We traced it to two input bugs (a delivery-shift check that fired on most normal winter and June weeks, and a January expectation set about 30% too high), fixed them, froze the detector's settings on separate development chains, and tested once on a new held-out set: a median of 2 weeks, 1.7 false alarms a year (both marks passed). The failed runs stay in `results/results.json`. Still, 21% of 20% drops go uncaught for six months, and small dips are slow (median 13 weeks for the demo's four-shop dip).
  - **Taps to a goal:** a median of 18 owner turns (E1a) and 20 (E1b), not the dozen we aim for. E1a passed the pre-registered ≤ 25; E1b met it, but as a single-family arm that is descriptive, not a pass.
- **The model tests used one model family.** E1b, E2-model, E4-model, E4-heldout-model, E4-heldout-2-model, E4-heldout-3-model, E4-heldout-4-model, E4-heldout-5-model, E4-heldout-6-model and E5-model ran with Claude as both the agent and the simulated owner, against our own pre-registered rule of three families (prereg addendum 2), so they are descriptive. E7, the usability test with real people, has not been run.
- **Not built yet:** an OCR cross-check of quote amounts; re-offering a monthly set-aside that R2 or R5 held back, once the pause lifts (today it comes back only with the next approved goal update). See SPEC §12.5.

---

## Sources

| Claim | Source |
|---|---|
| Market wave | Reuters report published by [Inside Retail](https://insideretail.asia/2025/10/13/chinese-fb-chains-are-using-singapore-as-a-testbed-for-global-expansion/), 13 Oct 2025, citing Momentum Works data |
| Closures | [MTI written reply to a parliamentary question, 5 Nov 2025](https://www.mti.gov.sg/newsroom/written-reply-to-pq-on-retail-food-establishments-which-ceased-operations-after-five-years-or-less-that-have-recorded-profit) (closures 1 Jan–23 Oct 2025) |
| Loan purpose | 互联网贷款管理暂行办法 Arts 24(三), 30; 流动资金贷款管理办法 (2024, in force 1 Jul 2024) Arts 6, 9, 10, 25(三), 34; 银保监办发〔2021〕39号 |
| Outbound investment | State Council Decree 837 (in force Jul 2026); NDRC Order 11; MOFCOM Order 3; SAFE 资本项目外汇业务指引 (2024) |
| Guarantees from home | Allowed with SAFE registration: 汇发〔2014〕29号; SAFE 资本项目外汇业务指引 (2024) §3.5.4 (内保外贷). Waypoint's "no guarantee from home" is a design rule |
| Leasing | Code of Conduct for Leasing of Retail Premises; Lease Agreements for Retail Premises Act 2023 |
| Singapore costs | ACRA, IRAS (GST), CPF Board, MOM (work passes, local qualifying salary, PWM), SFA (food shop licence) |
| Area data | SingStat (population, age, income by planning area), URA Master Plan 2019 planning-area boundaries via data.gov.sg, NEA's licensed eating establishments via data.gov.sg (food outlets, a 2015–16 list, geocoded with OneMap), LTA station locations. Area rents come from the simulated listings (URA has no machine-readable per-area rent); LTA station traffic needs a key and is not used in the demo |
| AI in finance | NFRA 金发〔2026〕8号; PIPL |
