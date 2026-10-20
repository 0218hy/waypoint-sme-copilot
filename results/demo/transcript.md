# Waypoint demo transcript (simulated)

Model: claude_code:claude-haiku-5-5 · seed 20261019 · company fictional · WeBank feed mocked · units simulated

## 1. Hello

**Waypoint:** Hi, I'm Waypoint. I'll guide you in a few short steps: your business, where to open, what it costs, how to pay, and your plan. Together we'll go from 'a shop in Singapore' to a funded plan with dates. Tap the answers or just type, in English or Chinese.
**Waypoint:** I can skip most questions by reading your WeBank business accounts. The card shows exactly what I'd read, and it's never used for credit. May I read your accounts?
`[consent_card]` 

> **Joon Rui taps:** Agree
**Waypoint:** Thank you. I've read your accounts, so let's start with your business.
`[profile_card]` 
**Waypoint:** The card above shows what I found in your accounts. Is this right? Tap any line to fix it.
`[business_glance]` Operating margin, last 12 months 19.2% | Margin, last 3 months 17% (Same months a year earlier 19%) | Revenue per shop a month RMB 36k | Cash runway 4 months | Debt-service coverage 4.7x (After your drawings 2.9x)
**Waypoint:** The next card works out some ratios from the same accounts: your margin over the past year, 19.2%, and recent months set against the same months a year earlier, since sales are seasonal. It also shows revenue per shop and how well profit covers your loan repayments. Your cash runway shows 4 months, but that reads high because your home rent isn't in the feed.
**Waypoint:** Who buys from you most?
`[quick_replies]` Young adults · Students · Office workers · Families · Tourists

> **Joon Rui taps:** Young adults
**Waypoint:** Next, let's talk money for the new shop. Do you have a rough budget in mind for it?
`[quick_replies]` S$200,000–S$300,000 · S$300,000–S$450,000 · S$450,000–S$600,000 · Not sure yet

> **Joon Rui taps:** S$300,000–S$450,000
**Waypoint:** Let's start with timing. When are you hoping to open?
`[quick_replies]` Within a year · In a year to eighteen months · In about two years · No rush

> **Joon Rui taps:** In a year to eighteen months
**Waypoint:** The summary card above sums up your business as I understand it. Shall we start looking for places?
`[confirm_card]` 

> **Joon Rui taps:** That's right
**Waypoint:** Thanks, that gives me a clear picture of your business. Now let's look at where your first shop could go.
**Waypoint:** What matters most to you for this first shop?
`[quick_replies]` Being near my kind of customer · Lots of foot traffic · Low rent

## 2. Where

> **Joon Rui taps:** Being near my kind of customer
**Waypoint:** The map shows the areas that suit your business best. Tap one to see why it made the list and which units are free there.
`[area_map]` top: Downtown Core (A big daytime crowd of workers and visitors; A busy food scene (more competition too)), Tampines (Rents fit your budget; A busy food scene (more competition too)), Woodlands (Rents fit your budget)
`[quick_replies]` Downtown Core · Tampines · Woodlands

> **Joon Rui taps:** Tampines
`[area_card]` 
`[topic_card]` Station traffic isn't footfall
**Waypoint:** Here's Tampines. The area card shows why it fits your shop, and below it are the units within your budget, each with the cups a day it needs to break even.
`[unit_compare]` Tampines 1 #01-K12: S$8,820/month, break-even 264 cups a day | Tampines Mall #B1-S03: S$10,600/month, break-even 281 cups a day | Century Square #B1-S11: S$10,600/month, break-even 282 cups a day
**Waypoint:** Just so you know, the unit listings in this demo are simulated.
`[topic_card]` Rent tied to sales (GTO)
**Waypoint:** Which unit would you like me to cost?
`[quick_replies]` Tampines 1 #01-K12 · Tampines Mall #B1-S03 · Century Square #B1-S11

> **Joon Rui taps:** Tampines 1 #01-K12
**Waypoint:** Good choice: Tampines 1 #01-K12. Next, let's work out what opening it would cost. You can come back to compare other units any time from the steps.
**Waypoint:** Opening Tampines 1 #01-K12 is likely to cost S$311,600, and up to S$337,800 if things go badly. This assumes a standard fit-out and a manager hired in Singapore. Open any group on the card to see its lines and sources.
`[cost_breakdown]` likely S$311,600, if things go badly S$337,800 (RMB 1.64m)
`[unit_economics]` Break-even (a month's EBITDA is zero): 264 cups a day; To pay back within the lease: 331 cups a day; To pay back within the lease, if things go badly: 357 cups a day; At the lower menu price: 445 cups a day; Your best shop at home: 178 cups a day || 250 cups a day: EBITDA -S$1,512/month, payback not within the lease (badly not within the lease), NPV -S$284,100 | 300 cups a day: EBITDA S$4,029/month, payback not within the lease (badly not within the lease), NPV -S$123,400 | 350 cups a day: EBITDA S$9,571/month, payback 29 months (badly not within the lease), NPV S$30,700 | 400 cups a day: EBITDA S$15,100/month, payback 19 months (badly 26 months), NPV S$178,800 | 450 cups a day: EBITDA S$20,700/month, payback 15 months (badly 20 months), NPV S$326,500
**Waypoint:** The next card shows whether the shop at Tampines 1 #01-K12 pays back. It needs 264 cups a day to break even, and 331 cups a day to pay back the investment within the lease, or 357 cups a day if things go badly. These rest on estimates for ramp-up, delivery share and price, shown on the card. You can type your own cups-a-day figure to see its row.
`[topic_card]` You'll need a resident director
**Waypoint:** Should anything change, like the fit-out level, sending your own manager, or adding a contractor quote? If it all looks right, you can carry on.
`[quick_replies]` Looks right · Basic fit-out · Premium fit-out · Send my own manager · Add a contractor quote

## 3. What it costs

> **Joon Rui taps:** Add a contractor quote
**Waypoint:** Do you have any quotes from contractors or suppliers yet? You can take a photo or upload them, and I'll read the lines for you.
`[upload_prompt]` upload
`[quick_replies]` Use the sample quote (demo) · No quotes yet

> **Joon Rui taps:** Use the sample quote (demo)
**Waypoint:** The card shows what I read from your contractor's quote. Please accept or reject each line there. A quote line replaces my estimate only when it covers that whole cost. If a line prices just part of a cost, my estimate stays, since demolition is only part of fit-out, for example. On the card you can mark a line as covering the whole cost, or pick which cost an unmatched line belongs to.
`[upload_prompt]` 5 lines read (model); excluded: 拆除另计 Demolition extra, GST 另计 GST not included

> **Joon Rui taps:** Accept 隔墙及天花 Partition + ceiling

> **Joon Rui taps:** Accept 地面 Flooring (vinyl)

> **Joon Rui taps:** Accept 水电 Electrical + plumbing

> **Joon Rui taps:** Accept 吧台及柜体 Counter + cabinets

> **Joon Rui taps:** Accept 招牌 Signage
**Waypoint:** I've updated the cost card for Tampines 1 #01-K12. With a standard fit-out and a manager hired in Singapore, the likely total is now S$312,400.
`[cost_breakdown]` likely S$312,400, if things go badly S$337,700 (RMB 1.64m)
`[unit_economics]` Break-even (a month's EBITDA is zero): 264 cups a day; To pay back within the lease: 331 cups a day; To pay back within the lease, if things go badly: 357 cups a day; At the lower menu price: 445 cups a day; Your best shop at home: 178 cups a day || 250 cups a day: EBITDA -S$1,512/month, payback not within the lease (badly not within the lease), NPV -S$284,900 | 300 cups a day: EBITDA S$4,029/month, payback not within the lease (badly not within the lease), NPV -S$124,200 | 350 cups a day: EBITDA S$9,571/month, payback 29 months (badly not within the lease), NPV S$30,000 | 400 cups a day: EBITDA S$15,100/month, payback 19 months (badly 26 months), NPV S$178,000 | 450 cups a day: EBITDA S$20,700/month, payback 15 months (badly 20 months), NPV S$325,800
**Waypoint:** You can try a different fit-out, send your own manager or add a contractor quote. If the card looks right, you can carry on. Is there anything you'd like to change?
`[quick_replies]` Looks right · Basic fit-out · Premium fit-out · Send my own manager · Add a contractor quote

> **Joon Rui taps:** This quote covers all of Fit-out
**Waypoint:** The cost card for Tampines 1 #01-K12 is updated, with a standard fit-out and a manager hired in Singapore. The likely total is now S$312,500.
`[cost_breakdown]` likely S$312,500, if things go badly S$330,600 (RMB 1.64m)
`[unit_economics]` Break-even (a month's EBITDA is zero): 264 cups a day; To pay back within the lease: 331 cups a day; To pay back within the lease, if things go badly: 355 cups a day; At the lower menu price: 445 cups a day; Your best shop at home: 178 cups a day || 250 cups a day: EBITDA -S$1,512/month, payback not within the lease (badly not within the lease), NPV -S$285,000 | 300 cups a day: EBITDA S$4,029/month, payback not within the lease (badly not within the lease), NPV -S$124,200 | 350 cups a day: EBITDA S$9,571/month, payback 29 months (badly not within the lease), NPV S$29,900 | 400 cups a day: EBITDA S$15,100/month, payback 19 months (badly 26 months), NPV S$178,000 | 450 cups a day: EBITDA S$20,700/month, payback 15 months (badly 19 months), NPV S$325,800
**Waypoint:** You can switch the fit-out level, send your own manager, or add a contractor quote. If it looks right, you can carry on. Would you like to change anything?
`[quick_replies]` Looks right · Basic fit-out · Premium fit-out · Send my own manager · Add a contractor quote

> **Joon Rui taps:** Looks right
**Waypoint:** A few costs don't have a quote yet, or have one worth a second look. The cost card marks them, and they're worth raising with your contractor.
`[missing_items]` 
`[topic_card]` You'll need to hire locally first
**Waypoint:** Now let's look at how to pay for it all.
**Waypoint:** You need RMB 1.14m more than your spare cash of RMB 500k. The cards list every lawful way to cover it.
`[funding_options]` 
**Waypoint:** Here's what WeBank does say yes to. Your savings pot can sit as a deposit in the company's own name, and it is never pledged. The bank that registers the ODI changes the money and sends it, and your WeBank statements show it comes from profit and savings. WeBank keeps lending to the home shops at their usual level. They're at that level now, so the card shows no extra room. Money for Singapore comes only from spare cash, profit you set aside and savings. If home borrowing goes above usual, the set-aside pauses, so the loan money and the Singapore money stay apart.
`[closed_options]` 
`[topic_card]` WeBank's role in this move
**Waypoint:** Your biggest lever is the share of monthly profit you set aside. Drag the slider and you'll see the opening date and your home cash safety line move together.
`[setaside_slider]` share 40% (wall 100%): likely month 14.5 (Jan 2028), badly month 18.5 (May 2028), floor risk 2.6%, RMB 85k/month
`[funding_compare]` 
`[topic_card]` Your safety line
**Waypoint:** At this setting you put aside RMB 85k a month. You'd likely open month 14.5 (Jan 2028), or month 18.5 (May 2028) if things go badly. The chance home cash dips below the safety line is 2.6%.
**Waypoint:** Are you happy with this, or would you like to try another lever?
`[quick_replies]` Looks good · Add my savings · Ask for rent-free months · A local partner?

## 4. How to pay

> **Joon Rui:** Just use my WeBank line for now
**Waypoint:** I'm sorry, that route isn't one we can plan with. The card below explains why and shows what can work instead.
`[rule_card]` R1: Loan money stays home — Your WeBank loan can't pay for Singapore: not the shop, the savings pot or the Singapore company.
**Waypoint:** Now, back to where we were with your funding plan.
**Waypoint:** Are you happy with this plan, or would you like to try another lever?
`[quick_replies]` Looks good · Add my savings · Ask for rent-free months · A local partner?

> **Joon Rui taps:** Slide to 30%
`[setaside_slider]` share 30% (wall 100%): likely month 18.5 (May 2028), badly month 22.5 (Sep 2028), floor risk 1.4%, RMB 64k/month
`[funding_compare]` 
**Waypoint:** At this setting you'd put aside RMB 64k each month. The likely opening is month 18.5 (May 2028), or month 22.5 (Sep 2028) if things go badly. The chance your home cash dips below the safety line is 1.4%.
**Waypoint:** Are you happy with this, or would you like to try another lever, like adding savings or rent-free months?
`[quick_replies]` Looks good · Add my savings · Ask for rent-free months · A local partner?

> **Joon Rui taps:** Slide to 50%
`[setaside_slider]` share 50% (wall 100%): likely month 12.5 (Nov 2027), badly month 17.5 (Apr 2028), floor risk 3.1%, RMB 106k/month
`[funding_compare]` 
**Waypoint:** At this setting you put aside RMB 106k each month. Your likely opening is month 12.5 (Nov 2027), or month 17.5 (Apr 2028) if things go badly. The chance your home cash dips below the safety line is 3.1%.
**Waypoint:** Are you happy with this, or would you like to try another lever?
`[quick_replies]` Looks good · Add my savings · Ask for rent-free months · A local partner?

> **Joon Rui taps:** Slide to 40%
`[setaside_slider]` share 40% (wall 100%): likely month 14.5 (Jan 2028), badly month 18.5 (May 2028), floor risk 2.6%, RMB 85k/month
`[funding_compare]` 
**Waypoint:** At this setting you put aside RMB 85k each month. Your likely opening is month 14.5 (Jan 2028), or month 18.5 (May 2028) if things go badly. The chance your home cash dips below the safety line is 2.6%.
**Waypoint:** Are you happy with this, or would you like to try another lever?
`[quick_replies]` Looks good · Add my savings · Ask for rent-free months · A local partner?

> **Joon Rui taps:** Looks good
**Waypoint:** The card above shows how the cost will be covered, from your spare cash and your monthly set-aside.
`[funding_mix]` Spare cash RMB 500k, Monthly set-aside RMB 1.14m
**Waypoint:** With the money side clear, let's lay out your plan.
**Waypoint:** The timeline shows every step in the order the law requires. It shows when each step is likely to happen and the latest it can safely happen.
`[milestone_timeline]` WeBank's consent as lender (Nov 2026) → ODI filing (DRC and Commerce Bureau) (Jan 2027) → Bank ODI registration (Feb 2027) → Incorporate and open the Singapore account (May 2027) → Setup transfer (May 2027) → First main transfer (May 2027) → Accept the offer and sign the lease (May 2027) → Hire and train local staff (Jul 2027) → Fit-out (Aug 2027) → Food shop licence (Sep 2027) → Opening (Jan 2028)
`[topic_card]` Ask WeBank first
**Waypoint:** Here is your plan in a single line: likely opening around month 14.5 (Jan 2028), or month 18.5 (May 2028) if things go badly, setting aside RMB 85k each month.
`[goal_summary]` Open at Tampines 1 #01-K12 around month 14.5 (Jan 2028); if things go badly, by month 18.5 (May 2028). Set aside RMB 85k a month.
**Waypoint:** Your plan is ready, and nothing starts until you approve it. Reminders come by email monthly, without amounts, and there is no automatic monthly transfer; you can change these with the chips below.
`[approval_card]` Start my goal: Unit: Tampines 1 #01-K12; Total likely cost: S$312,500 (RMB 1.64m); Funding mix: Spare cash RMB 500k · Monthly set-aside RMB 1.14m; Likely opening: month 14.5 (Jan 2028); If things go badly: month 18.5 (May 2028); Monthly set-aside: RMB 85k; Chance home cash dips below the floor: 2.6%; Check-ins: Monthly; Note: Waypoint never moves money
`[quick_replies]` Change reminders · Show amounts in emails · Also set up the monthly transfer

## 5. Your plan

> **Joon Rui taps:** Start my goal
**Waypoint:** Your goal is set. You'll find it on the Goal tab, a welcome email is on its way to you, and I'll check in with you as we agreed.
**Waypoint:** Your goal is now active. Tap any step on the timeline to see what to prepare or to mark it done. You can also ask me anything about the plan, or change part of it. What would you like to do first?
`[milestone_timeline]` WeBank's consent as lender (Nov 2026) → ODI filing (DRC and Commerce Bureau) (Jan 2027) → Bank ODI registration (Feb 2027) → Incorporate and open the Singapore account (May 2027) → Setup transfer (May 2027) → First main transfer (May 2027) → Accept the offer and sign the lease (May 2027) → Hire and train local staff (Jul 2027) → Fit-out (Aug 2027) → Food shop licence (Sep 2027) → Opening (Jan 2028)

## 6. 4 weeks later

_(clock moved to 2026-11-16; weekly check ran; simulated four-shop sales dip started)_

> **Joon Rui taps:** Open the alert email link
**Waypoint:** Something has shifted in your plan. The card above shows what changed.
`[alert_card]` Your plan has slipped from the goal
**Waypoint:** Each of these fixes works, and each one shows its new dates. Pick the one that suits you and I'll get it ready for you to approve.
`[repair_options]` Set aside a bit more → month 14.5 (Jan 2028) | Add some of your savings → month 14.5 (Jan 2028) | Ask for more rent-free months → month 16.5 (Mar 2028)

> **Joon Rui taps:** Set aside a bit more
`[milestone_timeline]` WeBank's consent as lender (Dec 2026) → ODI filing (DRC and Commerce Bureau) (Feb 2027) → Bank ODI registration (Mar 2027) → Incorporate and open the Singapore account (May 2027) → Setup transfer (May 2027) → First main transfer (Jul 2027) → Accept the offer and sign the lease (Jul 2027) → Hire and train local staff (Sep 2027) → Fit-out (Oct 2027) → Food shop licence (Nov 2027) → Opening (Jan 2028)
**Waypoint:** Your plan is ready. Nothing starts until you approve it. Reminders will come by email once a month, the emails won't show amounts, and there's no monthly transfer set up. You can change any of these with the chips below.
`[approval_card]` Update my goal: Unit: Tampines 1 #01-K12; Total likely cost: S$312,500 (RMB 1.64m); Funding mix: Monthly set-aside RMB 1.64m; Likely opening: month 14.5 (Jan 2028); If things go badly: month 23.5 (Oct 2028); Monthly set-aside: RMB 187k; Chance home cash dips below the floor: 3.3%; Check-ins: Monthly; Note: Waypoint never moves money

> **Joon Rui taps:** Update my goal
**Waypoint:** Your goal is updated. The Goal tab now shows the new dates for each step.
**Waypoint:** Your goal is active. Tap any step on the timeline to see what to prepare or to mark it done, ask me anything about it, or change part of the plan. What would you like to look at first?
`[milestone_timeline]` WeBank's consent as lender (Dec 2026) → ODI filing (DRC and Commerce Bureau) (Feb 2027) → Bank ODI registration (Mar 2027) → Incorporate and open the Singapore account (May 2027) → Setup transfer (May 2027) → First main transfer (Jul 2027) → Accept the offer and sign the lease (Jul 2027) → Hire and train local staff (Sep 2027) → Fit-out (Oct 2027) → Food shop licence (Nov 2027) → Opening (Jan 2028)

