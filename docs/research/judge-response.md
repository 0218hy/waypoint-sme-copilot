# Responding to the 2026-10-20 judge panel

Research memo, 20 Oct 2026. Desk research and exploratory code runs only: nothing here is a measured result, and nothing in the repo was changed. Every prototype number was produced in a scratch clone (`/private/tmp/claude-501/research/`) and is labelled **exploratory**.

**What this memo covers.** It covers what the three running fix sessions don't:

- **Financing matching (E1).** WeBank only ever says "no"; the option list is fixed and the same for every owner; the alternatives offered when a rule blocks something are dead; there's no post-opening EFS view.
- **Legal sources.**
- **Depth of the financial analysis (E3).**
- **Detection delay (E6).**
- **The guard's ceiling (E4).**
- **Generality:** only one scenario is covered.
- **Deck and video narrative.**

The cash-flow alert and transfer pause, the cost-card bugs, and the stale docs and missing tests are covered by those sessions.

**How to read each section.** The options, the one recommended, the effort in hours, the files it touches, the risk, and the sources. A ranked list (score gain per hour) is at the end.

**Two corrections to the judges, verified against primary sources:**

1. **The R1 citation is correct.** In the final gazette text of 《商业银行互联网贷款管理暂行办法》 (银保监会令2020年第9号), **Art. 24 is the loan-purpose article**: 24(三) bans 固定资产、股本权益性投资. The judge most likely read the January 2020 consultation draft, where the numbering differs. The citation that *is* wrong is **R3** (see §2).
2. **"820 held-out scripts", not "1,000+".** Impact was measured on the four held-out sets only: 120 + 120 + 280 + 300 = 820 scripts per arm. All 820 had zero impact (Wilson upper bound 0.47%). This was pre-registered as descriptive, so it can be quoted but never called a pass.

---

## 1. E1, financing-option matching

**What the code does today:**

- **The option list is fixed.**
  - `tools/funding.py:264-290` lists every catalogue entry that isn't closed, with no eligibility test.
  - `funding_mix` (`:330-360`) fills the cost in a fixed order: spare cash, savings, partner, landlord terms, then set-aside.
- **The alternatives are dead.**
  - `agent/toolkit.py:1066-1081` returns the same three chips whatever the rule.
  - `agent/steps.py:1345-1363` handles them only when the step is `funding`; elsewhere it re-asks.
- **Dead option ids.** `rules/engine.py:114` tests `efs_grants`, `grants` and `efs_after_opening`, none of which exists in `data/funding_catalogue.yaml`.

### 1a. Positive WeBank matches (WeBank as "yes" at home)

**Facts:**

- **微业贷 (Weiyedai):**
  - online, unsecured working capital, up to ¥10m depending on the page version;
  - 2.88%–24% a year, up to 36 instalments;
  - WeBank's own page says 「贷款只能用于本企业生产经营，不得挪用于股东分红，房产、金融资产、固定资产、股权投资等违规用途」.

  [sme.webank.com 微业贷](https://sme.webank.com/esp-web/rls/asset/wyd/index.html), [product intro](https://smewyd.webank.com/mesp-front/mesp-multi/mesp_intro/index.html), [App Store listing](https://apps.apple.com/cn/app/id1455485724).
- **Other WeBank products:**
  - **Confirmed:** 微闪贴 (online bill discounting), 订货贷 (for distributors of brands WeBank has admitted only), enterprise accounts and deposits, curated third-party wealth products.
  - **Not found:** corporate FX, outbound remittance or ODI registration at WeBank. Assume no.

| Option | Lawful? | Rules | How Waypoint presents it |
|---|---|---|---|
| **`webank_home_wc`**: 微业贷 for documented *home* needs (stock, seasonal, a Shenzhen refit) | Yes, *if sized to the real need net of own funds* and never above the usual level while the set-aside runs | R1, R2, R4 | "WeBank keeps your home shops running at your usual level. Singapore money comes only from profit you set aside, and the plan pauses if borrowing rises, so the two never mix." |
| **`webank_pot_deposit`**: the set-aside pot as a deposit in the company's own name at WeBank | Yes, if it is **never pledged** (a pledge for Singapore credit would be 内保外贷) | R3, R5 | "Your pot sits in a WeBank deposit in your company's name: visible, earns interest, never pledged, and doubles as your source-of-funds proof for the ODI." |
| **`partner_bank_fx`**: FX and remittance at the bank that registers the ODI | Yes, after the filings and bank registration | R4, R7 | "Step 5: your registering bank converts and sends. Waypoint hands it your WeBank statements as proof the money came from profit." |
| `webank_bill_discount` (微闪贴) | Only with real trade bills; weak fit for a retail chain | R1, R2 | Show only if the feed shows bills. |

**The fungibility test.** Drawing more 微业贷 for home bills *so that* own cash can go abroad fails two tests:

- the sizing rule: the loan must be no more than real need net of own funds;
- the purpose rule: it is substantively evasion.

Sources:

- [流贷办法 2024](https://www.gov.cn/gongbao/2024/issue_11306/202404/content_6947721.html):
  - Art. 6: loan ≤ 实际需求;
  - Annex step 2: 新增额度 = 营运资金量 − 借款人自有资金 − …;
  - Art. 9: no equity investment;
  - Arts 10 and 34: 挪用, and monitoring for it.
- [互联网贷款办法](https://www.gov.cn/gongbao/content/2020/content_5541497.htm):
  - Art. 24(三): no equity investment;
  - Art. 30: purpose monitoring.
- [银保监办发〔2021〕39号 §二](https://www.gov.cn/zhengce/zhengceku/2021-03/26/content_5596070.htm): credit must match operating income and cash flows.

R2 already enforces exactly this. Present it as the *reason* WeBank can lend, not only as a block.

- **Recommended:** add the first three entries to the catalogue as `open`/`optional`, with WeBank-branded cards. Size `webank_home_wc` from the feed: `normal_loan_balance_by_month_cny` minus the current balance. Never let it count toward the Singapore mix (code-enforced: R1 already closes loan→pot).
- **Effort:** 6–10 h.
- **Files:**
  - `data/funding_catalogue.yaml`;
  - `tools/funding.py` (an amount for the new ids; keep them out of `funding_mix`);
  - `agent/toolkit.py` / `agent/steps.py` (show on `funding_enter`);
  - `skills/funding/SKILL.md` (a beat);
  - `web/` (card variant);
  - `tests/test_journey.py`;
  - SPEC §6.4 table.
- **Risks:**
  - It could read as "borrow to free cash for Singapore". Mitigate by showing the R2 pause on the same card.
  - Product names and limits change: date them (`as_of`) and say "subject to approval".
  - The WeBank sub-account product is unverified, so phrase it as "a deposit or account in your company's name".

### 1b. Per-owner eligibility and ranking

- **Options:**
  - (i) Keep the fixed order and add one-line "why this order".
  - (ii) Score each open option on cost of funds, time to available, dilution and risk to home cash, and rank it.
  - (iii) Solve for the cheapest mix that meets the opening date under R5. The Monte Carlo already exists, so (iii) is a small search over the slider plus optional on/off flags.
- **Recommended: (ii) now, with (iii) as a "suggest a mix" button later.**
  - Eligibility comes from data Waypoint already has:
    - spare cash > 0;
    - the owner has savings;
    - partner only if the owner says it is open to one;
    - landlord terms only once a unit is chosen;
    - `webank_home_wc` only if the current balance is below the usual level.
  - Rank by:
    1. effective cost: 0 for own cash; the 微业贷 rate band; the partner's profit share as a cost;
    2. weeks to available;
    3. dilution;
    4. change in floor risk.

  Show the score as words ("cheapest", "fastest", "keeps 100% ownership"), not a number.
- **Effort:** 8–12 h.
- **Files:**
  - `tools/funding.py` (`rank_options`);
  - `data/funding_catalogue.yaml` (`cost_kind`, `speed_weeks`, `dilution`);
  - `agent/toolkit.py`;
  - the funding widget;
  - tests.
- **Risks:** the scores invent precision. Keep them ordinal and sourced.

### 1c. Per-rule lawful alternatives that work at every step

- **Today:** the same three chips, live only at the funding step (E4's "lawful option 100%" counts `options ≥ 1`, so it passes by construction).
- **Recommended:**
  - Add `alternatives:` per rule in `rules/rules.yaml`. Examples:
    - R1: set aside more, own savings, `webank_home_wc` for home needs;
    - R4: the pre-investment allowance (≤15%), then "start the filing";
    - R6: rent-free months, staged contractor payments, a later lease date;
    - R8: partner equity, an EFS view after opening.
  - Dispatch each chip at any step: from the plan, goal or timeline steps, jump back to funding with that change pre-applied, then return.
  - In a future addendum, measure that the tapped alternative *changes the plan*.
- **Effort:** 6–8 h.
- **Files:**
  - `rules/rules.yaml`;
  - `agent/toolkit.py` (`lawful_options(state, rule_id)`);
  - `agent/steps.py` (`guard_option` + `reopen_step`);
  - `eval/e4_guard.py` (only via an addendum);
  - tests.
- **Risk:** jumping steps confuses owners. Reuse the existing `reopen_step` flow, which already re-confirms.

### 1d. The post-opening view (EFS / Singapore bank loan)

The SPEC promises a post-opening view (SPEC §6.4 table, "may appear in the post-opening view"); it isn't built. Facts:

- **[EFS SME Working Capital Loan](https://www.enterprisesg.gov.sg/financial-support/enterprise-financing-scheme---sme-working-capital):**
  - up to S$500k, tenor up to 5 years;
  - 50% standard risk share, **70% for all from 1 Sep 2026 to 31 Mar 2027**;
  - it needs **≥30% local shareholding** (Singaporean/PR, by ultimate individual ownership);
  - it sets **no trading-history requirement**.
- **Bank practice:** trading history of about 6–12 months [secondary: aggregator sites, unverified with banks].
- **Recommended:**
  - A read-only "after opening" card on the Goal tab. It lists EFS-WCL (needs a partner ≥30%) and bank SME loans (typically after 6–12 months' trading; rates 6–11% p.a. in Oct 2026 [secondary]).
  - Show it with the earliest month each could apply, and never count it in the plan (R8).
  - Delete the dead ids in `rules/engine.py:114`, or implement them as this card.
- **Effort:** 4–6 h.
- **Files:** `data/funding_catalogue.yaml` (`efs_after_opening`, status `later`), `tools/funding.py`, a widget, `rules/engine.py`, tests.
- **Risk:** low.

---

## 2. Legal sources (relabel, don't rewrite)

| Rule | Repo cites | Verdict | Change |
|---|---|---|---|
| R1 | 互联网贷款办法 Art. 24; 流贷办法 (2024) Art. 9 | **Correct** | Add Art. 24(三) and Art. 30, plus the WeBank 微业贷 terms. Note 流贷办法 2024 took effect **1 Jul 2024** (promulgated 30 Jan 2024) |
| R2 | 流贷办法 Arts 10, 34 | Articles right, but "indirect diversion / 置换" is our reading | Cite Art. 6 + Annex formula + 银保监办发〔2021〕39号 §二; call it "substitution: evading the purpose rule" |
| **R3** | SAFE Guide 2024 §3.5.4 | **Wrong as stated.** 内保外贷 is **allowed with SAFE registration** within 15 working days, including personal guarantees (汇发〔2014〕29号 Arts 6, 9, 16). Since 2017 the funds may come back onshore (§3.5.4.1(6)). Keep-wells count (§3.5.4.1(7)) | Relabel **"Design rule (protects repayment capacity)"**; legal background: registration, inside the ODI filing, needs WeBank's prior consent (流贷 Art. 25(三)). Out of scope for the prototype |
| R4 | 流贷 Art. 25(3); NDRC Order 11; SAFE Guide §8.1; Decree 837 Art. 27 | **Correct** | Cite Decree 837 Art. 27 **para 2**; add NDRC Order 11 Arts 32–33. 前期费用 ≤15% (Guide §8.1.3.1, the USD 3m figure is old). "Never the lease deposit" is a **design** choice |
| R7 | vague | Law for consumer, card and personal loans; design beyond | Cite 贷款通则 Art. 20(三), 互联网贷款办法 Art. 24(三), SAFE Guide §8.2.2.1(4) (source-of-funds proof); label "law + design" |
| R8 | EFS terms | No law found; EFS needs 30% local ownership, **no** trading-history test | Relabel **"Design rule (prudential)"**; keep the EFS URL; "banks usually ask for trading history [market practice]" |
| catalogue `own_savings` | 个人外汇管理办法 Art. 16 | Imprecise: Art. 16 is SAFE approval for individual ODI, not the quota rule | Cite the 实施细则 / 购汇申请书 instead |

- **Recommended:**
  - Add `kind: law | design | law+design` and `url` to every rule. Render "Design rule" on rule cards distinctly from "Law".
  - Fix the PITCH line "because the law forbids funding the overseas equity" to "because the loan rules forbid using working-capital and internet loans for equity investment".
- **Effort:** 2–3 h.
- **Files:**
  - `rules/rules.yaml`;
  - `data/funding_catalogue.yaml`;
  - the `rule_card` widget (label);
  - SPEC §8 rules table;
  - `docs/PITCH.md`, `docs/SECURITY.md`;
  - `tests/test_rules_engine.py` (assert every rule has `kind` and `url`).
- **Risk:** none technical. It *raises* credibility with a WeBank compliance reader.

**Primary sources:**

- [互联网贷款办法 (gazette)](https://www.gov.cn/gongbao/content/2020/content_5541497.htm)
- [流贷办法 2024 (gazette)](https://www.gov.cn/gongbao/2024/issue_11306/202404/content_6947721.html)
- [个贷办法 2024](https://www.gov.cn/gongbao/2024/issue_11306/202404/content_6947720.html)
- [贷款通则 (PBOC)](https://www.pbc.gov.cn/eportal/fileDir/image_public/UserFiles/chubanwu/upload/File/%E8%B4%B7%E6%AC%BE%E9%80%9A%E5%88%99.doc)
- [汇发〔2014〕29号](https://www.safe.gov.cn/hebei/file/file/20170731/912cdc767c0748db9b977fc8a1b43bd2.pdf)
- [汇发〔2017〕3号](https://m.safe.gov.cn/safe/2017/0126/6821.html)
- [SAFE 资本项目外汇业务指引 2024](https://www.safe.gov.cn/safe/file/file/20240412/14f97540545646e48df3a821639651eb.pdf)
- [国务院令第837号](https://www.mofcom.gov.cn/xwfb/rcxwfb/art/2026/art_a19be62e79f04d72adef2945b20e9247.html)
- [NDRC Order 11](https://www.gov.cn/gongbao/content/2018/content_5280579.htm)
- [MOFCOM Order 2014 No. 3](https://www.gov.cn/gongbao/content/2014/content_2792653.htm)
- [EFS](https://www.enterprisesg.gov.sg/financial-support/enterprise-financing-scheme)

---

## 3. E3, depth of the business financial analysis

**Today:** a sourced cost card plus one break-even figure (cups a day vs the best Shenzhen shop). There is no payback, NPV, ramp-up or chain ratios.

**The inputs already exist:**

- price S$6.00 (`data/params.yaml:626`);
- variable cost S$1.90 (`:633`);
- wages, CPF, utilities, other fixed costs;
- a 3-year lease;
- the P90 cost card;
- the break-even fixed point (`tools/sites.py:364-390`);
- 24 months of chain revenue and profit plus 26 weekly rows in the feed (`tools/models.py:63-87`).

### 3a. A "Unit economics & payback" card for the new shop

- **Formulas.** Each is a `Figure` with inputs, and estimates are labelled:
  - **Contribution per cup** = net price − variable cost − delivery commission × delivery share − card fees. While not GST-registered, net price = the menu price.
  - **Monthly fixed costs** include GST on rent, service and utilities as a cost while unregistered. *The current break-even omits this: 240 → 250 cups at u-tm-01.*
  - **Store P&L at 250 / 300 / 350 / 400 / 450 cups a day plus the owner's figure:** revenue, EBITDA, margin, depreciation over the lease, and tax. Tax is 17% with partial exemption only: **SUTE does not apply to a Singapore subsidiary 100% owned by a foreign company** ([IRAS](https://www.iras.gov.sg/taxes/corporate-income-tax/basics-of-corporate-income-tax/corporate-income-tax-rate-rebates-and-tax-exemption-schemes)).
  - **Ramp-up:** `c_m = c_ss × (1 − (1 − s0) e^(−(m−1)/τ))`.
    - Likely: s0 0.6, τ 3 months.
    - Bad: 0.5, 6 months.
    - Both are estimates.
  - **Payback:** first month where cumulative cash ≥ the investment.
    - Investment = card total − running reserve, so ramp losses aren't counted twice.
    - Likely and P90 cases.
    - "Not within the lease" if it runs past month 36.
  - **NPV over 36 months** at 12%, with sensitivities at 8% and 15%. Deposits come back minus reinstatement. Optionally a 3+3-year view.
  - **Cups needed** for payback within the lease (bisection).
- **Exploratory output (u-tm-01, Tampines; scratch model, not a result):**

  | Steady cups/day | Payback, likely / P90 cost | NPV 36 months, likely / P90 |
  |---|---|---|
  | 300 | not within lease | −S$78k / −S$118k |
  | 350 | 25 / 28 months | +S$88k / +S$49k |
  | 400 | 17 / 19 months | +S$255k / +S$215k |

  - Payback within the 3-year lease needs **316 cups a day (326 on P90 costs)**; break-even is 250.
  - **Price is the most sensitive input:** at S$5.50 a cup, payback needs 360. The discount rate moves it only about 8 cups.
- **Benchmarks for the card's footer:**
  - **Nayuki** (the only official payback figure): **10.6 months for its 2018 stores, 15.5 months for 2018–19**; store operating margin 18.9% / 16.3% / 12.2% (2018 / 2019 / 2020). [HKEX prospectus p.197](https://www1.hkexnews.hk/listedco/listconews/sehk/2021/0618/2021061800009.pdf)
  - **Guming** franchisee store operating margin: 20.2% (FY2023). [HKEX p.179](https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0204/2025020400011.pdf)
  - **Mixue:** about 640 cups a store a day. [HKEX p.15](https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0221/2025022100009.pdf)
  - **Chagee:** about 825 cups a day in China (2024). Overseas same-store GMV −20.6% in FY2025. It terminated its Singapore franchise in 2024. [424B4](https://www.sec.gov/Archives/edgar/data/2013649/000110465925036228/tm246985-42_424b4.htm), [20-F](https://www.sec.gov/Archives/edgar/data/2013649/000110465926050766/cha-20251231x20f.htm)
  - **Singapore:**
    - Bober Tea broke even in 12–16 months on S$200k capex ([Vulcan Post 2021](https://vulcanpost.com/736520/bubble-tea-business-lucrative-singapore/)).
    - Menu prices run from Mixue S$2.90 to Heytea S$6.50 ([eatbook](https://eatbook.sg/heytea-orchard-central/)). **S$6.00 is at the top end:** consider a price range of S$5.00 / 5.80 / 6.50.
  - **Wages:**
    - Food-services PWM, stall assistant: S$2,220 from 1 Jul 2026.
    - Counter attendant: S$2,295, then S$2,435 from 1 Jul 2027.
    - Source: [MOM](https://www.mom.gov.sg/employment-practices/progressive-wage-model/food-services-sector).
- **Headline the card should say:** "Break-even is 250 cups a day; getting your money back inside the 3-year lease needs about 320 (330 if costs run to the bad case; about 360 at S$5.50 a cup). Your best Shenzhen shop does 600."
- **Effort:** 12–18 h.
- **Files:**
  - `data/params.yaml`: `ramp_curve`, `discount_rate_annual`, `sg_cit_rate`, `sg_partial_exemption`, `reinstatement_sgd`, `delivery_share`, `delivery_commission`, a `cup_price_sgd` range, `gst_registration_threshold_sgd`;
  - `data/cost_key.yaml`: `kind: sunk | refundable | working_capital`;
  - a new `tools/unit_econ.py`;
  - `agent/toolkit.py` and `agent/steps.py` (after `unit_compare` or at the cost step);
  - a widget and its web renderer;
  - the E2 placeholder vocabulary;
  - tests.

  An older worktree, `recursing-solomon-c5d4fb`, has a payback card to borrow from.
- **Risks:**
  - The headline "cups needed" is driven by assumptions: keep the estimate chips visible.
  - GST registration becomes compulsory at about 457 cups a day (S$1m a year); the card must switch to the net price there.
  - The cost-card fix session may change "likely". Build on whatever that session merges.

### 3b. Chain ratios from the feed

All of these come from `FeedSnapshot` alone, with no new data:

| Ratio | Formula | Chen (seed 1414) |
|---|---|---|
| Operating margin, TTM | Σ12 profit / Σ12 revenue | 19.2% |
| Margin trend, seasonally fair | last 3 months vs the same 3 last year | 20.9% vs 16.8% |
| Revenue per shop per month | TTM revenue / 12 / shops | ¥36.0k (≈S$6.9k) |
| Cash runway | cash / (payroll + repayment + commitments) | 3.8 months (overstated: home rent isn't in the feed; label it) |
| Debt-service coverage | TTM profit / 12 × repayment; and after drawings | 4.6x; 2.2x after drawings |
| Singapore investment vs chain | investment × FX / TTM profit | 68% of a year's profit (P90 77%) |
| Singapore shop vs a home shop | Singapore EBITDA × FX / profit per home shop | at 350 cups ≈ 9.5 home shops |

- **Recommended:** a "Your business at a glance" card at the profile step, with the ratios also in the Goal tab. Never compare month-on-month (the series is strongly seasonal).
- **Effort:** 4–6 h.
- **Files:** `tools/funding.py` or a new `tools/ratios.py`, `agent/steps.py` (`profile_enter`), a widget, tests.
- **Risk:** the mock data gives an average shop of about ¥36k a month in revenue, a sixth of the best shop's. Check that this is intended before the demo shows both.

---

## 4. E2, detection delay (13 weeks against a mark of 3)

**Root cause (found in an exploratory run, re-verified against the code).** It is mostly two input bugs in `tools/detect.py`, not CUSUM itself:

1. **The channel-shift guard fires on about 95% of normal chains in Jan, Feb and June.**
   - `_channel_shift` tests `delivery_share > 0.03`, but Chen's normal delivery share is 10%, so the test is always true.
   - It also judges revenue against the *profit* seasonal shape.
   - A `ProfitShock` leaves revenue unchanged, so the −20% drop reads as "on plan" until March. That gives the 13-week median.
2. **January's expectation is about 33% too high.** `_shape` is fitted on monthly totals that carry late-December days, so every January reads a built-in "25% drop". The guard bug currently hides this.

**Exploratory prototype** (E6's own 300 seeds plus dev seeds 0–39, so in-sample; *not a result*):

| Detector | False alarms / chain-year | Median at −20% | Within 3 weeks |
|---|---|---|---|
| Shipped | 1.31 | 13 | 32% |
| Guard fixed only, h 0.60 | 1.86 | 4 | 39% |
| **Adaptive-reference CUSUM, k 1.5 / h 8** | **1.58** | **3** | **52%** |
| BOCPD | 2.62 | 3 | 53% (+60/300 false alarms on channel shifts) |

Every honest detector hits a wall at about 50–60% within 3 weeks at about 2 false alarms a year. The generator has natural 20% monthly falls about 0.8 times a year, and those can't be told apart from the shock inside 3 weeks.

- **Options:**
  - (i) Fix only the guard.
  - (ii) The guard fix plus an adaptive-reference CUSUM: a lagged EWMA level, sigma from the MAD of first differences, k and h in sigma units.
  - (iii) BOCPD.
  - (iv) Pool shop-level series. This can't be tested: the feed has chain totals only.
  - (v) Add a cash-headroom alert (balance vs floor) as a second signal. Useful, but it can't catch a 20% drop within 3 weeks.
- **Recommended: (ii) + (v).**
  - Freeze k, h, λ and lag on **dev seeds only**.
  - Write a **dated prereg addendum** that states the two bugs, how they were found, the frozen parameters, unchanged marks, and the expectation that the median lands at 3–4 (a coin flip on ≤3).
  - Build a **new held-out shock set:**
    - new seeds;
    - onsets spread over weeks 4–40 including Jan–Feb and month boundaries;
    - a chain-wide `SalesDrop` that also moves revenue;
    - channel shifts with and without commission.
  - Measure once as `E6-heldout`, and keep E6's FAIL row.
- **Effort:** 6–9 h.
- **Files:**
  - `tools/detect.py`;
  - `data/params.yaml` (`detect_k_sd`, `detect_h_sd`, `detect_ref_lambda`, `detect_ref_lag`);
  - `eval/e6_detection.py` or a new `eval/e6h_detection.py`;
  - `sim/shocks.py` (a new builder only);
  - `results/prereg.md`;
  - `tests/test_goalkeeper.py`.
- **Risks:**
  - The held-out median may land at 4.
  - With the guard fixed and the shipped thresholds, false alarms go to about 3 a year, which **fails** the ≤2 mark. The cash-flow fix session was told (message sent 20 Oct) not to tune `detect_k`/`detect_h` on the broken guard.
  - The demo's alert week will move: coordinate with that session.
- **Sources:**
  - Page (1954), *Continuous Inspection Schemes*, [doi:10.1093/biomet/41.1-2.100](https://doi.org/10.1093/biomet/41.1-2.100).
  - [NIST/SEMATECH CUSUM](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm) and [EWMA](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm).
  - Adams & MacKay (2007), [BOCPD](https://arxiv.org/abs/0710.3742).
  - Mei (2010), [multi-stream monitoring](https://doi.org/10.1093/biomet/asq010).
  - Moving-holiday (CNY) adjustment: [Findley, Monsell & Hou (2012)](https://census.gov/content/dam/Census/library/working-papers/2012/adrm/findleymonsellhoutefp.pdf).
  - Prototype: `/private/tmp/claude-501/research/detect/explore/proto.py`.

---

## 5. The guard's ceiling (E4)

**History.** The original model arm let 9.5% of scripts through (UB 14.3%). The four held-out model arms let through:

| Held-out set | Let through | Wilson UB |
|---|---|---|
| 1 | 6.7% | 12.6% |
| 2 | 0.8% | 4.6% |
| 3 | 5.4% | 8.6% |
| 4 | 3.7% | 6.4% |

All fail the ≤2% mark. False blocks run 7–9%. Impact is 0/820 per arm (descriptive).

**Three facts from the code change the options:**

1. **Free text already sits behind an allowlist.** The model can only pick one of seven validated actions (`agent/orchestrator.py` `_decide`/`_apply`). No free-text action builds or edits a funding plan, a goal or a money card. That is *why* impact is 0.
2. **There is no separate model classifier.** The model's flag is the `rule_id` field of the routing call. The `intent` role in `config/models.yaml` is never called. When a keyword hits, the model isn't consulted, so keyword false blocks can never be cleared.
3. **Impact has two gaps a panel will find.** The finishing owner just taps the lawful defaults. And the bot's *reply text* after a missed turn was never measured: E4 used the test composer, while in production a miss can reach the voice model as a free-form side question.

**Options:**

1. **Make the rules engine the claimed safety layer.**
   - A dated addendum for **future sets only** makes the end-to-end harm outcome E4's primary safety mark (Wilson UB ≤2%).
   - Before claiming it, strengthen it: an **adversarial finisher** (non-default picks, inflated `correct_business`, `go_back` loops), and a **reply-content check**.
   - Capitulation stays as a secondary measure **with its ≤2% mark unchanged**. Every old FAIL stays published.
   - 10–16 h.
2. **A reply allowlist.** On money or step-order topics, if no rule card fires, the bot may answer only with a topic card, a "scope" card or the pending question, never a free-form reply. This is the action-selector pattern, and it closes the only path from a miss to harm. 8–12 h.
3. **A dedicated guard call** (the unused `intent` role), OR'd with a **Chinese-native second family** (Qwen/DeepSeek/GLM via the `openai` provider).
   - 10 of the 11 latest misses were Chinese.
   - Qwen3Guard reports 85 F1 on Chinese prompts, against 42–55 for Western guards.
   - Same-family ensembles buy little because errors correlate.
   - 7–11 h. Expect more false blocks.
4. **A "clarify" card for borderline messages** with lawful-context markers ("after opening", "all three done", "within 15%"). Cuts false blocks; a plausible 9% → 2–4%. 6–10 h.
5. **More patterns: not recommended.** It is a denylist with a long tail; adaptive attacks broke 12 of 12 published defences.

**Recommended: 1 + 2 first (18–28 h), then 3 + 4.**

- Order: write the addendum before any code, freeze the guard, then have a new blind set of ≥300 scripts and ≥100 controls written. Run each arm once.
- 0 events in n scripts passes UB ≤2% only when n ≥ 188; at n = 300, at most one event passes.

**Deck wording (accurate as of today):**

> "Our conversational guard is an early warning, not the safety boundary. On four blind held-out sets it let 0.8–6.7% of pressure scripts through without a rule card (latest 3.7%, upper bound 6.4%, against our own pre-registered 2%), and we publish every miss. The boundary is code: every plan, approval card and money step is re-checked by the rules engine, and across 820 blind pressure scripts none ended in a rule-breaking approved plan or a prepared money step (0/820, descriptive)."

Add the third sentence ("we have pre-registered that outcome as the primary mark for the next set") only once the addendum exists.

- **Files:**
  - `results/prereg.md`;
  - `eval/e4_heldout.py` (adversarial finisher), `eval/model_arms.py` (reply judge);
  - `agent/orchestrator.py`, `agent/steps.py`, `agent/intent.py` (borderline);
  - `agent/llm.py` (`classify_intent`), `config/models.yaml`;
  - `skills/guard/SKILL.md`;
  - `docs/SECURITY.md` K1, README, PITCH.
- **Risks:**
  - It can be read as moving the goalposts. Keep the old mark, date everything, and show the old FAILs on the slide.
  - A second family needs keys and adds latency.
- **Regulatory anchor:** TC260-003 (the CAC filing basis) asks for keyword libraries *plus* classifiers, a ≥95% refusal rate on should-refuse sets and ≤5% on should-not-refuse sets. Waypoint's latest point estimates are 96.3% caught and 9% false blocks. This is context, not a compliance claim.
- **Sources:**
  - [CaMeL](https://arxiv.org/abs/2503.18813);
  - [Design Patterns for Securing LLM Agents](https://arxiv.org/abs/2506.08837);
  - [The Attacker Moves Second](https://arxiv.org/abs/2510.09023);
  - [OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/);
  - [NIST AI 600-1](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf);
  - [TC260-003 (CSET translation)](https://cset.georgetown.edu/wp-content/uploads/t0588_generative_AI_safety_EN.pdf);
  - [Qwen3Guard](https://arxiv.org/abs/2510.14276);
  - [Correlated errors (Kim et al.)](https://arxiv.org/abs/2506.07962);
  - [OR-Bench](https://arxiv.org/abs/2405.20947);
  - [Clarify When Necessary](https://arxiv.org/abs/2311.09469);
  - [Willison, dual LLM](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/).

---

## 6. Generality: one scenario narrows "SME finance copilot"

**How tied the core is to Singapore** (Singapore and SGD references by file):

- Mostly currency-agnostic apart from the FX parameter: `tools/plan.py`, `tools/funding.py`, `tools/timeline.py`, `rules/engine.py`.
- Singapore-bound: `tools/costs.py` (30 SGD references), the cost key, and `agent/toolkit.py` (29).

**Options:**

1. **"Your business at a glance" analysis mode.**
   - It covers §3b's chain ratios plus "can I afford X?" over the feed: cash runway, debt-service coverage, R2's usual level, and a floor-risk check of any one-off spend.
   - No new journey; reachable from the welcome step and the Goal tab.
   - 6–10 h on top of §3b.
2. **"Home growth" scenario: equipment, a refit, or a 31st Shenzhen shop funded with 微业贷.**
   - It reuses the feed, the R2 usual level, the R5 floor Monte Carlo, the funding mix, approval cards and the audit log.
   - It shows WeBank as a lender, sized under the working-capital rule's need-net-of-own-funds formula, with a new **R9 repayment-capacity rule** (e.g. debt-service coverage ≥1.25 in the bad case).
   - New pieces:
     - a small Shenzhen cost key from public franchise and opening cost ranges, labelled estimates (Mixue about ¥210k excluding rent; Guming about ¥330k);
     - a scenario switch at the profile step;
     - the applicable rule subset: R2, R5, R9 (R1, R3, R4, R6 and R8 don't apply).
   - 25–40 h.
3. **Multi-country** (Malaysia, where Chagee has 217 stores). A new cost key, rules and data. 40 h+. Not now.

- **Recommended:** (1) now, because it is cheap and also deepens E3. Then (2) as the first post-hackathon scenario, pitched as "same engine, new goal". In the deck, say plainly that Waypoint does one scenario deeply and the engine is goal-agnostic; don't imply more.
- **Risk:** (2) doubles the eval surface; each scenario needs its own pre-registered journey eval.

---

## 7. Deck and video narrative (for the team's own edit)

**Suggested 13 slides**, each mapped to Topic E's components (E1 matching, E2 cash flow and alerts, E3 analysis) and the scoring rubric (task completion 40%, security & compliance 30%, innovation & interaction 30%). Screenshot panels are from `docs/media/screens.jpg`.

| # | Slide | Maps to | Visual |
|---|---|---|---|
| 1 | Waypoint: an SME finance copilot that plans a first overseas shop without risking the home business | — | Logo; team Tul.py |
| 2 | Chen, 30 tea shops in Shenzhen, a WeBank customer: *what will it cost, how do I fund it, will home cash survive?* | E3 / E1 / E2 | Persona; one name throughout |
| 3 | Why WeBank cares: loan money must not fund overseas equity (Art. 24(三), Art. 9); 405 Chinese F&B outlets in Singapore, 82% of young closures never profitable | Task | Two sourced stats |
| 4 | How it works: the AI talks, code computes every number, the owner approves | Innovation | "Phone: the chat" panel |
| 5 | **E3** What it costs and where: 55 areas scored, likely and bad-case cost, quotes read with a planted instruction ignored | E3, Task | "Where", "What it costs", "A quote read by AI" |
| 6 | **E1** How to fund it: every lawful route, every closed one with its rule. WeBank funds the home shops; loan money stays home | E1, Compliance | "Rule R1" panel; a WeBank positive card if §1a is built |
| 7 | **E1×E2** The set-aside slider: opening date against home-cash risk, risky shares locked | E1/E2, Innovation | "Set-aside slider" panel / `slider.gif` |
| 8 | Legal order: lender consent → ODI filing → bank registration → transfers → lease | Compliance | Timeline list from the "Goal tab after approval" panel |
| 9 | **E2** Goal Keeper: weekly check, alert, three fixes with new dates, owner accepts | E2, Task | "Phone: the Goal tab"; quote demo.json values |
| 10 | Security: maker (AI) → checker (rules engine) → signer (the owner, in WeBank); approval cards; checkable audit proof | Compliance | Three-box diagram |
| 11 | Evidence: the current results table, with the guard and E6 failures stated as in §5 | All | Table from README (current numbers only) |
| 12 | What's new: purpose-aware cash planning, the risk-wall slider, owner-held audit proof, bilingual | Innovation | Icons |
| 13 | Next: pilot with WeBank data; domestic model (Qwen); a second scenario | — | — |

**Deck fixes the judges flagged:**

- **Remove stale or unbuilt claims:**
  - 38/38, 11,670 runs, 0/60;
  - the emergency stop;
  - the wealth review;
  - "formal verification remains incomplete";
  - the 15th-shop table;
  - slide 21's strong/weak owner figures.
- **Use one owner name.**
- **Keep to about 13 slides,** with speaker notes of about 1,300 words, so the talk fits in 10 minutes.

**Presenting failures well.** Pair each failure with its safeguard and its next step, on the same line:

- **Guard:** use the §5 wording.
- **E6:** "a 20% drop is caught in a median of 13 weeks against our 3-week target. We found the cause (a guard bug) and pre-registered a re-test."

  Say "pre-registered a re-test" only once the addendum exists. Until then, say "a re-test is planned".

**Video fixes:**

- **2:17:** the evidence card should show 0/225 attacks refused and one line of known gaps.
- **2:30:** say "about 18 turns", not "a dozen taps".
- **1:21:** add "when the guard catches it; rules re-check every plan".
- **Throughout:** use the committed demo unit, or say the video's unit differs.

---

## Ranked: score gain per hour

Gain is judged against the panel's 40/30/30 rubric. Hours are build-and-test time, excluding new held-out runs.

| Rank | Change | Hours | Why it ranks here |
|---|---|---|---|
| 1 | **Deck rebuild along §7** (team's own) | — | Judges read the deck first. It currently scores 4–5/10 and carries stale claims |
| 2 | **Relabel the legal sources** (§2): law vs design, URLs, fix R3 and R8 | 2–3 | Removes the one wrong citation; strong compliance signal for very little work |
| 3 | **Positive WeBank cards** (§1a): home 微业贷, pot deposit, partner-bank FX | 6–10 | Answers the panel's main E1 complaint ("WeBank only says no"); adds bank value |
| 4 | **Chain ratios card** (§3b) | 4–6 | Cheap E3 depth from data already in the feed |
| 5 | **Detector guard fix + adaptive CUSUM, by addendum** (§4) | 6–9 | Fixes a real bug; a credible path to turning a FAIL into a pass |
| 6 | **Per-rule alternatives at every step** (§1c) | 6–8 | Removes dead chips; makes "lawful option offered" real |
| 7 | **Unit economics & payback card** (§3a) | 12–18 | The question a panel asks first ("does it pay back?"); largest E3 gain |
| 8 | **Guard reframe + reply allowlist, by addendum** (§5, options 1 and 2) | 18–28 | Puts the safety claim on the layer that holds; closes the verbal-harm path |
| 9 | **Post-opening EFS view** (§1d) | 4–6 | Delivers a SPEC promise; removes dead ids |
| 10 | **Option ranking and eligibility** (§1b) | 8–12 | Personalised matching; moderate gain |
| 11 | **Second guard family + clarify card** (§5, options 3 and 4) | 13–21 | Fewer misses and false blocks; needs keys and a new blind set |
| 12 | **Analysis mode** (§6.1) | 6–10 on top of item 4 | Broadens "SME copilot" cheaply |
| 13 | **Home-growth scenario** (§6.2) | 25–40 | Real generality, but large; a post-hackathon item |

Every change that touches an evaluated behaviour (E1–E6) needs:

- a dated prereg addendum *before* the change is frozen;
- a new blind set where the eval uses one;
- a single measurement, with old FAIL rows kept.
