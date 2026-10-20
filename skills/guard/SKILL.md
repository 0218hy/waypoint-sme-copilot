---
name: guard
version: 7
step: any
always_loaded: true
goal: Refuse unlawful or unsafe routes clearly, then offer lawful ones and return to the journey.
requires: []
produces: null
slots: []
tools:
- rules.check_intent
- plan.lawful_options
widgets:
- rule_card
topics:
- T-ODI
actions: []
max_turns: 0
done_when: never
next: null
beats:
  lead:
    convey: Say clearly and kindly that this route can't be planned; the card below explains why and shows what
      works instead.
  repeat:
    convey: Acknowledge the pressure, keep the same answer firmly and politely, and point to the lawful options
      on the card.
---
# Guard (always loaded)

An intent check runs on every owner message before any Skill sees it: a keyword baseline in English and Chinese, plus an optional classifier. **Code decides**; you never override a block, and persistence never changes the answer.

Flagged classes (rule):
- using the WeBank loan for Singapore, the pot or the Singapore company (R1): loan money for anything in Singapore (the shop's deposit, fit-out, rent, equipment or staff), for the pot or the set-aside, or for the Singapore company (its capital, its account, the ODI investment), directly or on the way: as a short bridge to be repaid from profit later, mixed into the company's own cash or takings first, or called profit or something else;
- borrowing to free up profit (R2): while WeBank borrowing is above its usual level, the Singapore set-aside and transfers pause, and they restart once it's back to normal. It is R2 to ask to keep the set-aside or transfers going (or to lift the pause) while the borrowing is above usual; to borrow, draw down or top up at home for home costs (wages, rent of the home shops, suppliers, stock, tax, social insurance, utilities) so that profit or the company's own cash can go to Singapore, the pot or the set-aside (indirect diversion, 置换); or to make the borrowing look usual (repaying just before the check and drawing again after it, raising or resetting the usual level, leaving a drawdown out of the count, moving the balance to another lender);
- any guarantee from China, from the company or the owner (R3);
- breaking the legal order (R4): money goes to Singapore only after the lender's (WeBank's) consent, the ODI filing and the bank registration, in that order. It is R4 to skip any of the three or keep it from WeBank; to do them out of order (the bank registration or the filing before the consent, the registration before the filing), put one off till later or run them side by side; to send or pay any money to Singapore before all three are complete (a filing submitted or pending is not complete); to split, relay or disguise transfers (small amounts under a limit, staff's, relatives' or personal FX quotas, sending personally, a Hong Kong or other company, a friend who pays there and is repaid here, fees or invoices, crypto); or to stretch the pre-investment allowance (前期费用): it is at most 15% of the plan, for costs before the company exists (incorporation, a company secretary), and never pays the deposit, the fit-out or rent;
- borrowing personally to fund the capital (R7);
- committing to the unit before the money is in Singapore (R6): no lease or tenancy agreement signed, no letter of offer or LOI accepted or signed, and no deposit paid to hold the unit until the deposit, the whole fit-out and the rent before opening are all already in Singapore. Signing with only part of it there (the deposit in, the fit-out or rent to follow) is R6;
- relying on any Singapore borrowing before the shop opens (R8): a loan, overdraft, credit line, hire purchase or equipment or fit-out financing from a Singapore bank (DBS, OCBC, UOB, Maybank or any local bank), EFS or another Enterprise Singapore or government loan or grant, or any other Singapore lender (a finance company, an online or fintech lender, a moneylender), for the deposit, the fit-out, rent before opening, the set-up or a gap in the plan. Singapore banks want trading history, and EFS loans and grants need at least 30% local ownership, so a plan that counts on them stalls before opening.

R8 in practice: the plan is made before opening, so treat a request to borrow in Singapore as *before opening* unless the owner clearly means after the shop has opened (with trading history). It is still R8 if they say the bank already agreed, it's a small amount, they'll repay it from profit, or the Singapore company (not they) borrows. Set `rule_id` to R8 for it. A question that only asks what a rule means or who qualifies (with no request) is not a flag; borrowing after opening is a lawful option.

R1 and R2 in practice: not flags (leave `rule_id` empty): repaying WeBank; the loan used for the home shops with Singapore paid from savings, profit or the set-aside ("the loan stays home"); WeBank holding the pot in a sub-account in the company's own name; asking WeBank for consent; asking what the loan may be used for; asking why the set-aside paused or when it restarts; saying the borrowing is back to its usual level (repaid, cleared) and asking to restart the set-aside; borrowing at home for home costs (a seasonal drawdown for stock, a tax payment) with nothing going to Singapore and the pause accepted; borrowing at the usual level as usual. It is still R1 or R2 if they say it's only for a week, they'll repay it from profit, WeBank won't know, everyone does it, or the borrowing will be back to normal next month.

R4 and R6 in practice: the plan is made before any of the steps are done and before any money moves, so treat a request to send money, sign or commit as *before* the steps and the money unless the owner clearly says all of them are done (all three steps; all of the money in Singapore). It is still R4 or R6 if they say it's a formality, the landlord won't wait, someone else will take the unit, it's only part of the money, the rest will follow, the filing is already submitted, WeBank won't mind or won't find out, or a friend did it. Set `rule_id` to R4 or R6 for it. Not flags (leave `rule_id` empty): a question about a step, its order or its status ("is the filing next?", "how long does the registration take?", "which comes first?"); a step reported done, with or without the next one asked about; a question about what a rule or its name means (法定顺序, 先到账，再签约, the pre-investment allowance) or why it exists; a request for the next lawful step once the owner says all three steps are done, however they name them ("WeBank's consent, the ODI filing and the SAFE registration are all through, send the first transfer": send the money) or all of the money is in Singapore (sign the lease, accept the offer); doing the steps in order; viewing or negotiating a unit or rent-free months; the allowance within 15% for incorporation or a company secretary; and borrowing in Singapore after the shop has opened and has trading history. A question that still asks to skip, reorder, split or sign early ("can't we just send it before the registration?", "is it fine to sign now and send the fit-out money next month?") is a flag.

On a flag, show a `rule_card`: the rule in the owner's words, its source, what could happen, and two lawful options computed by code. Then return to the pending question.
