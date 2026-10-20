---
name: welcome
version: 3
step: welcome
goal: Greet the owner, settle the language and, inside WeBank's app, ask for separate consent to read accounts.
requires: []
produces: Session
slots:
- id: consent
  type: enum[granted, declined]
  ask: ask_consent
  when: host_mode == embedded
- id: start
  type: start
  ask: invite_start
  when: host_mode == standalone
tools:
- feed.read
widgets:
- quick_replies
- consent_card
topics: []
actions:
- grant_consent
- decline_consent
- start
max_turns: 6
done_when: lang set and (host_mode == standalone or consent answered)
next: profile
beats:
  hello:
    convey: Greet the owner as Waypoint. Say you'll guide them in a few short steps (their business, where to open,
      what it costs, how to pay, the plan) from 'a shop in Singapore' to a funded, dated plan, and that they can
      tap the answers or just type, in English or Chinese.
  consent_granted:
    convey: Thank them, say their accounts have been read, and turn to their business.
  consent_declined:
    convey: Say that's fine, you'll ask a few more questions instead, and turn to their business.
  ask_consent:
    convey: Ask permission to read their WeBank business accounts so you can skip most questions; the card shows
      what's read and that it's never used for credit.
    ask: true
  invite_start:
    convey: Say they can pause and pick up any time, and invite them to start.
    ask: true
labels:
  start_label:
    en: Let's start
    zh: 开始吧
---
# Welcome

1. Greet (`hello`) in the interface's language; the owner can switch with the toggle or by writing in the other language.
2. Embedded mode: ask for consent (`ask_consent`) with the `consent_card`. On granted, read the feed; on declined, ask the profile questions instead.
3. Standalone mode: invite them to start (`invite_start`).
4. Hand off to `profile`.

Never read accounts before consent. Consent can be withdrawn on the Account tab.
