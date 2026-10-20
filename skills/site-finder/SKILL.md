---
name: site-finder
version: 4
step: site
goal: Help the owner pick one unit to cost.
requires:
- profile.confirmed
produces: Shortlist
slots:
- id: priority
  type: enum[foot_traffic, low_rent, near_customers]
  default: near_customers
  ask: ask_priority
- id: area
  type: area_id
  ask: map_intro
- id: unit
  type: unit_id
  ask: units_intro
tools:
- sites.rank_areas
- sites.area_profile
- sites.list_units
- sites.compare_units
- sites.break_even
widgets:
- quick_replies
- area_map
- area_card
- unit_compare
- confirm_card
topics:
- T-STATION-TRAFFIC
- T-GTO
- T-NOT-YET-SIGN
actions:
- set_priority
- select_area
- select_unit
- confirm
- rule_out_area
max_turns: 12
confirms:
- unit
- confirm_unit
done_when: shortlist.chosen_unit is set and owner confirmed
next: cost
beats:
  ask_priority:
    convey: Ask what matters most for their first shop.
    ask: true
  map_intro:
    convey: Say the map highlights the areas that fit them best; invite them to tap one to see why and the units
      there.
  area_intro:
    convey: 'Introduce {{area}}: the area card shows why it fits; below are units within their budget with the cups
      a day each needs to break even.'
  over_budget:
    convey: Say nothing in {{area}} fits their budget right now, so the closest units are shown to make the gap
      visible.
  no_units:
    convey: Say there are no listed units in {{area}} right now and suggest looking at another area.
  units_intro:
    convey: Ask which unit they'd like you to cost.
    ask: true
  done:
    convey: Turn to what it will cost.
  simulated_note:
    convey: Note plainly that unit listings in this demo are simulated.
  unit_chosen:
    convey: Confirm they picked {{unit}} and say you'll now work out what opening it would cost; they can come back
      to compare others any time from the steps.
labels:
  confirm_label:
    en: Cost this unit
    zh: 算算这个铺位
  edit_label:
    en: Look at others
    zh: 看看别的
---
# Site finder

1. Ask `priority` with quick replies.
2. `sites.rank_areas` → `area_map` with the top three areas. Each gets up to three short reasons, taken from the tool's reason codes.
3. When the owner taps an area → `area_card` (residents, customer-group share, station traffic, food outlets, rent) and `unit_compare` for units there within budget, with break-even cups a day next to their best Shenzhen shop.
4. The owner picks a unit; that's the confirmation (going back is one tap) → hand off to `cost`.

Bring up when relevant: station traffic isn't footfall (first area card); turnover rent (a unit has GTO terms); "you can't sign yet" (the owner asks about making an offer).

Never rank areas yourself, mention a rent the tool didn't return, or predict sales.
