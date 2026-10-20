---
name: goal-plan
version: 3
step: goal_plan
goal: Turn the agreed plan into a dated goal the owner approves.
requires:
- funding_plan.confirmed
produces: Goal
slots:
- id: extras
  type: enum[change_reminders, amounts_on, add_transfer, no_transfer]
  optional: true
  ask: extras_ask
- id: checkin_frequency
  type: enum[weekly, fortnightly, monthly]
  default: monthly
  ask: ask_frequency
  optional: true
tools:
- timeline.build
- goal.summary
- approval.prepare_create_goal
- goal.create
- email.send
widgets:
- milestone_timeline
- goal_summary
- quick_replies
- approval_card
topics:
- T-LENDER-CONSENT
- T-ODI
- T-PRE-INVESTMENT
actions:
- set_frequency
- set_amounts
- set_recurring
- approve
- cancel
max_turns: 10
done_when: goal created after approval
next: goal_keeper
beats:
  timeline_intro:
    convey: Say the timeline shows every step in the order the law requires, when each is likely, and the latest
      it can safely happen.
  summary_intro:
    convey: 'Introduce the goal card: their plan in one line.'
  ask_frequency:
    convey: Ask how often you should check in with them by email.
    ask: true
  approve_intro:
    convey: Say the plan is ready and nothing starts until they approve. Say how often reminders will come by email
      (reminders), whether they show amounts (amounts_in_emails) and, if set, the monthly transfer (monthly_transfer),
      exactly as in these facts; they can change these with the chips below.
  created:
    convey: 'Say the goal is set: it''s on the Goal tab, a welcome email has gone out, and you''ll check in as agreed.'
  refused:
    convey: Say something changed since the card was prepared, so it couldn't start; an updated card follows.
  cancelled:
    convey: Say nothing has started; they can change anything, or approve when they're ready.
  extras_ask:
    convey: Offer the optional changes on the chips (reminder frequency, amounts in emails, a monthly transfer inside
      WeBank) without pushing them.
    ask: true
labels:
  approve_title:
    en: Start my goal
    zh: 开始我的目标
---
# Goal plan

1. `timeline.build` → `milestone_timeline` in legal order: lender consent, ODI filing, bank registration, company and bank account, setup transfer, first main transfer, lease, fit-out, licence, opening. Raise the lender-consent topic.
2. `goal_summary`: one sentence with the likely and if-things-go-badly opening dates and the monthly set-aside.
3. Show the `approval_card` "Start my goal" straight away, with the defaults on it (monthly email check-ins, no amounts; no automatic transfer). Optional chips change them; each change re-issues the card.
4. On approve, On approve, the server re-checks everything, creates the goal, sends the welcome email and opens the Goal tab.

Waypoint drafts; the owner sends. Nothing moves money.
