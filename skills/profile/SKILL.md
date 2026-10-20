---
name: profile
version: 4
step: profile
goal: Know the business well enough to search and plan, asking only what isn't already known.
requires:
- session.ready
produces: Profile
slots:
- id: shops
  type: count
  ask: ask_shops
  skip_if: feed
- id: monthly_profit
  type: money_range_cny
  ask: ask_profit
  skip_if: feed
- id: spare_cash
  type: money_cny
  ask: ask_spare
  skip_if: feed
- id: customers
  type: enum[students, office_workers, young_adults, families, tourists]
  ask: ask_customers
- id: budget
  type: money_range_sgd | not_sure
  ask: ask_budget
- id: window
  type: enum[6_12, 12_18, 18_24, no_rush]
  ask: ask_window
tools:
- feed.read
- profile.from_feed
- profile.floor
- ratios.chain
widgets:
- profile_card
- business_glance
- quick_replies
- confirm_card
topics: []
actions:
- answer_slot
- edit_field
- confirm
max_turns: 14
done_when: every slot filled (ranges allowed) and owner confirmed
next: site
beats:
  card_intro_feed:
    convey: Say the card shows what you found in their accounts; ask if it's right (they can tap a line to fix it).
    ask: true
  glance_intro:
    convey: Say the next card works out a few ratios from the same accounts (margin over the last year, the last
      few months against the same months a year earlier because sales are seasonal, revenue per shop, how long
      the cash would last and how well profit covers the loan repayments); the cash runway reads high because
      home rent isn't in the feed. Don't judge the numbers.
    must:
    - '{{fig:ratio.op_margin_ttm}}'
    - '{{fig:ratio.cash_runway}}'
  ask_shops:
    convey: Ask how many shops they run today.
    ask: true
  ask_profit:
    convey: Ask roughly how much operating profit the whole business makes in a month.
    ask: true
  ask_spare:
    convey: Ask how much cash they could spare today without touching payroll or loan repayments.
    ask: true
  ask_customers:
    convey: Ask who buys from them most.
    ask: true
  ask_budget:
    convey: Ask whether they have a rough budget for the Singapore shop.
    ask: true
  ask_window:
    convey: Ask when they're hoping to open.
    ask: true
  confirm_intro:
    convey: Say the summary card sums up their business as you understand it, and ask whether to start looking for places.
    ask: true
  done:
    convey: Acknowledge, and turn to where their first shop should be.
labels:
  confirm_label:
    en: That's right
    zh: 没错
  edit_label:
    en: Change something
    zh: 修改
---
# Profile

1. Embedded mode with consent: build the profile from the feed and show `profile_card` with each field's source. Ask "Is this right?" Then `ratios.chain` → `business_glance`: ratios worked out from the same feed (trend against the same months last year, never month on month; the runway is labelled overstated). Only ask the slots that are still missing.
2. Standalone mode: ask the slots one by one, in order, with ranges as quick replies and the option to type a number. A range is stored as a range; narrow it later only if it matters.
3. Spare cash is computed by code (cash minus the safety floor minus a payroll buffer) whenever the feed allows. Show it; don't ask for it.
4. Finish with `confirm_card`. On confirm, hand off to `site`.

Never ask two things in one message. Never comment on whether the numbers are good or bad.
