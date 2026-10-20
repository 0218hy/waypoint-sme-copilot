---
name: detour
version: 4
step: any
goal: Answer a side question briefly from the topic library, then return to the same step.
requires: []
produces: null
slots: []
tools:
- topics.lookup
widgets:
- topic_card
topics:
- T-RESIDENT-DIRECTOR
- T-EP-SALARY
- T-CPF-QUOTA
- T-GST
- T-GTO
- T-STATION-TRAFFIC
- T-NOT-YET-SIGN
- T-REINSTATEMENT
- T-WEBANK-ROLE
- T-LENDER-CONSENT
- T-ODI
- T-PRE-INVESTMENT
- T-SAFETY-FLOOR
- T-PARTNER
- T-HIRING-LOCALS
actions:
- show_topic
max_turns: 0
done_when: answered
next: null
beats:
  lead:
    convey: Acknowledge the question in a few words; the topic card that follows answers it.
  scope:
    convey: Say in a few words that you answer side questions only from the checked cards, so the card that follows
      says where to ask this one. Don't answer the question yourself.
---
# Detour

Answer side questions from the topic library only. Show the matching `topic_card` (short text, "Tell me more", source). If no topic fits, code shows the scope card (`T-SCOPE`: Waypoint answers side questions only from its checked cards, and a filing agent, accountant or the lender should answer this one). There is no free-form answer: you never write one, and you don't see the owner's typed words when you write. Then return to the pending question of the active step.
