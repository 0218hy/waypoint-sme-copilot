---
name: funding
version: 5
step: funding
goal: Agree how the move is paid for, without putting the home business at risk.
requires:
- cost_card.confirmed
produces: FundingPlan
slots:
- id: setaside_share
  type: share
  ask: slider_intro
- id: own_savings
  type: money_cny
  default: '0'
  ask: ask_savings
  optional: true
- id: rent_free
  type: months
  default: '1'
  ask: ask_rent_free
  optional: true
- id: partner
  type: bool
  default: 'false'
  optional: true
tools:
- funding.floor
- funding.gap
- funding.options
- funding.closed
- funding.mix
- plan.simulate
- plan.wall
- rules.check_plan
widgets:
- funding_options
- closed_options
- setaside_slider
- funding_compare
- funding_mix
- quick_replies
- confirm_card
- topic_card
topics:
- T-WEBANK-ROLE
- T-SAFETY-FLOOR
- T-PARTNER
actions:
- set_share
- add_savings
- set_rent_free
- ask_partner
- toggle_option
- looks_good
- confirm
max_turns: 16
confirms:
- lever
done_when: funding plan passes every rule and owner confirmed
next: goal_plan
beats:
  gap_intro:
    convey: Say how much more than their spare cash they need, and that the cards list every lawful way to cover
      it.
    must:
    - '{{fig:funding.gap}}'
    - '{{fig:home.spare_cash}}'
  webank_yes_home:
    convey: "Say what WeBank does say yes to, from the WeBank cards: working capital from its 微业贷 for documented
      needs of the home shops, up to their usual borrowing level (the room left this month), sized to the real need
      and subject to WeBank's approval; the savings pot as a deposit in the company's own name, never pledged; and
      the bank that registers the ODI converts and sends, with WeBank statements as proof the money is profit and
      savings. Say Singapore money comes only from spare cash, profit set aside and savings, and that the set-aside
      pauses if borrowing rises above usual, so the two never mix."
    must:
    - '{{fig:funding.webank.home_headroom}}'
  webank_yes:
    convey: "Say what WeBank does say yes to, from the WeBank cards: the savings pot as a deposit in the company's
      own name, never pledged; and the bank that registers the ODI converts and sends, with WeBank statements as
      proof the money is profit and savings. Say WeBank keeps lending to the home shops at their usual level (they
      are at it now, so there's no room shown), that Singapore money comes only from spare cash, profit set aside
      and savings, and that the set-aside pauses if borrowing rises above usual, so the two never mix."
  slider_intro:
    convey: 'Explain that the biggest lever is the share of monthly profit they set aside: dragging the slider moves
      the opening date and the home cash safety line together.'
  slider_set:
    convey: 'Summarise this setting: the monthly set-aside, the likely opening, the opening if things go badly,
      and the chance home cash dips below the safety line.'
    must:
    - '{{fig:plan.setaside_monthly}}'
    - '{{fig:plan.open_likely}}'
    - '{{fig:plan.open_p95}}'
    - '{{fig:plan.floor_risk}}'
  window_miss:
    convey: Say plainly that the likely opening is later than they hoped for (hoped_for). If the set-aside is
      already at the safe limit, say raising it isn't an option; then name what would bring it closer (their own
      savings, rent-free months from the landlord, a local partner), or accepting a later date.
  not_within_horizon:
    convey: Say at this share the shop doesn't reliably open within the plan's horizon; suggest a higher share or
      one of the other levers.
  levers_ask:
    convey: Ask whether they're happy with this or want to try another lever.
    ask: true
  ask_savings:
    convey: Ask how much of their own savings they could put in; it goes in as capital, never as a loan.
    ask: true
  ask_rent_free:
    convey: Ask how many rent-free fit-out months they'll ask the landlord for; it only counts once it's in the
      signed offer.
    ask: true
  alternative_later:
    convey: Say the option they picked from the rule card (option) belongs to the funding step, which comes once
      the costs are settled, and it will be there then; then go back to the question.
  mix_intro:
    convey: Say the card shows how the cost is covered.
  done:
    convey: Turn to laying out the plan.
labels:
  confirm_label:
    en: Make my plan
    zh: 生成计划
  edit_label:
    en: Keep adjusting
    zh: 继续调整
---
# Funding

1. `funding.gap` → say `gap_intro`. Show `funding_options` (open options, plus the WeBank and registering-bank cards, which are never counted in the plan) → say `webank_yes_home` if the WeBank home working-capital card is shown, else `webank_yes`. Show `closed_options` ("Why not my WeBank loan?"). Raise the WeBank-role topic.
2. Show `setaside_slider` at the default share (never above the wall). Raise the safety-line topic. Previews are computed live by code; the commit runs the full simulation. Under it, show `funding_compare` ("Compare funding plans"): set-aside only, plus savings, plus a local partner, each column a full solve at the slider's share; "Choose this funding" applies a column through `toggle_option`. It has no beat of its own.
3. Offer the levers one at a time, and only if the owner asks or the gap is large: own savings, rent-free months, a local partner.
4. Every plan is checked by every rule. A failing plan is never shown as a recommendation.
5. "Looks good" → rules check → `funding_mix` → hand off to `goal_plan` (the goal's approval card is the commitment).

`guard` handles "use my WeBank loan", "my company can guarantee it", "send it through Hong Kong" and the like. Each rule card offers that rule's own lawful alternatives (`rules/rules.yaml`); a pick that changes the plan applies here, or reopens this step from a later one, with the change applied; before this step it says `alternative_later`.
