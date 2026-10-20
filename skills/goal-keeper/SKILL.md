---
name: goal-keeper
version: 5
step: goal_keeper
goal: Keep the owner on the goal; alert on the plan, not on noise; re-plan only with approval.
requires:
- goal.exists
produces: GoalRevision
slots:
- id: checkin
  type: money_cny pair
  ask: checkin_ask
- id: repair
  type: repair_id
  ask: repairs_intro
- id: milestone_done
  type: yes_no
  ask: confirm_done
tools:
- goalkeeper.check
- repairs.find
- approval.prepare_revise_goal
- goal.revise
- timeline.build
- goal.mark_milestone_done
- drafts.consent_request
- drafts.checklist
- approval.prepare_recurring_setaside
- webank.prepare_setaside
widgets:
- checkin_form
- status_card
- alert_card
- repair_options
- approval_card
- quick_replies
- milestone_timeline
- draft_card
topics:
- T-LENDER-CONSENT
- T-ODI
actions:
- submit_checkin
- see_repairs
- select_repair
- approve
- cancel
- reopen_step
- mark_milestone_done
max_turns: 0
done_when: never
next: null
beats:
  hello:
    convey: 'Say the goal is active: they can tap a step on the timeline for what to prepare or to mark it done,
      ask you anything about it, or change part of the plan.'
    ask: true
  checkin_ask:
    convey: Ask how last month went (the form takes profit and the amount set aside).
    ask: true
  on_track:
    convey: Say they're on track and give the likely opening.
    must:
    - '{{fig:goal.open_likely}}'
  at_risk:
    convey: Say the plan has slipped a little and give the new likely opening.
    must:
    - '{{fig:goal.open_likely}}'
  off_track:
    convey: Say the plan is off track, give the new likely opening, and offer to look at fixes.
    must:
    - '{{fig:goal.open_likely}}'
  r2_pause:
    convey: Explain that the set-aside is paused while their WeBank borrowing is above its usual level, and restarts
      once it's back to normal.
  alert_intro:
    convey: Say something moved in their plan; the card shows what.
  repairs_intro:
    convey: Say these fixes work, each with its new dates; they can pick one and you'll prepare it for their approval.
  no_repairs:
    convey: Say none of the standard fixes keeps the plan within the rules right now; moving the target date is
      the safe option.
  revised:
    convey: Say the goal is updated; the Goal tab shows the new dates.
  milestone_done:
    convey: Acknowledge {{step}} as done (the timeline shows it ticked) and say the next step is {{next_step}}.
  milestone_done_last:
    convey: Acknowledge {{step}} as done; every step of the plan is now done.
  milestone_not_yet:
    convey: Say that's fine, {{step}} stays open; they can mark it done from the timeline once it is.
  milestone_already_done:
    convey: Say {{step}} is already marked done; the timeline shows where things stand.
  milestone_out_of_order:
    convey: Say {{step}} can't be marked done yet because {{before}} comes first in the legal order and isn't
      done; the timeline shows the order.
  confirm_done:
    convey: Ask them to confirm {{step}} is done before you record it.
    ask: true
  confirm_money_done:
    convey: Ask them to confirm they released the money for {{step}} themselves, in their own bank, before you
      record it as done. Waypoint never moves money.
    ask: true
  consent_draft_intro:
    convey: Say the consent request to WeBank is drafted from their approved plan; they check it, then copy or
      download it and send it themselves. Waypoint never sends it.
  consent_letter:
    convey: 'Write the body of the consent request, in the owner''s voice as the borrower company, to WeBank:
      they plan one leased tea shop in Singapore through a new Singapore company owned by the Shenzhen company,
      give the planned investment and the monthly set-aside, say it is funded only from the company''s own profit
      and savings and never from the WeBank loan, that nothing in China guarantees the Singapore company, and
      that no money leaves before the ODI filing and bank registration; then ask for WeBank''s consent as lender
      and offer to provide documents. No greeting line, no sign-off, no headings: the card adds them.'
    must:
    - '{{fig:draft.invest_total}}'
    - '{{fig:draft.setaside_monthly}}'
  checklist_intro:
    convey: Say the card lists what to prepare for {{step}}, each item with its source; their agent or provider
      does the filing, and Waypoint never files anything.
  setaside_intro:
    convey: Say one more card prepares the monthly transfer they chose, into their company's own savings sub-account
      in WeBank. Approving it only prepares it; nothing moves until they sign it in WeBank's own app, and it pauses
      by itself while their borrowing is above its usual level or home cash would fall below the safety floor.
  setaside_prepared:
    convey: Say the monthly transfer is prepared in WeBank and is waiting for their signature there; it starts only
      once they sign it in WeBank's own app. Waypoint never moves money.
  setaside_held:
    convey: 'Say the monthly transfer isn''t prepared today because of this rule (held_by): while their WeBank borrowing
      is above its usual level set-asides pause, and home cash must stay above the safety floor. Say they can add
      it again when they next update the goal, once that has passed.'
  setaside_refused:
    convey: Say something changed since the transfer card was prepared, so nothing was prepared; an updated card
      follows.
  setaside_cancelled:
    convey: Say nothing was prepared; their goal is unchanged, and they can still set aside each month themselves.
labels:
  revise_title:
    en: Update my goal
    zh: 更新我的目标
  setaside_title:
    en: Prepare my monthly transfer
    zh: 准备每月自动转存
---
# Goal Keeper

- **From a check-in** (standalone mode): `checkin_form` asks for last month's profit and amount set aside. The weekly check runs and a `status_card` is shown.
- **From an email link** (read once by the web app): the check-in email's "Something changed" opens `checkin_form` for that goal and period (the signed token is checked first); the alert email's link opens that `alert_card` and its `repair_options`. An invalid or expired link shows a plain notice.
- **The monthly set-aside** (embedded mode, if chosen): after the goal is approved, one `approval_card` (`recurring_setaside`) prepares it, lines built by code. Approving records it in WeBank "pending your signature"; the owner signs it in WeBank's own flow. R2's pause or R5's floor holds it back (`setaside_held`).
- **From an alert:** `alert_card` (what moved, by how much, the act-by date), then `repair_options` computed by code. The owner picks one → `approval_card` → a goal revision.
- **Changing the plan:** a "Change in chat" from the Goal tab reopens that step's Skill with the current plan loaded. The rebuilt goal needs approval.
- **Milestones:** a tap on a step (`open_milestone`) explains it and, for lender consent, shows the consent request (`draft_card`: facts from code, the letter body from the `consent_letter` beat); for the ODI filing and incorporation, a checklist from `data/milestone_checklists.yaml`. Waypoint drafts; the owner sends.
- **Marking a step done** (`mark_milestone_done`, from the timeline or typed): code checks it is one of this goal's steps and that every earlier step in legal order is done. A money step, or anything typed, is recorded only after the owner confirms. Then the timeline shows it ticked and the status and next step are recomputed.

Never invent a fix. A slow week alone is never an alert.
