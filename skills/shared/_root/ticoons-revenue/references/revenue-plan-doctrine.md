---
name: revenue-plan-doctrine
description: The conceptual doctrine behind revenue plan items - the ladder, the five-question test, and the traps. From ticoons-libre-agents/skills/revenue-plan.
---

# Revenue plan doctrine

A revenue plan is not a forecast and not a work list. It is the venture's honest answer to
one question: **what will a customer be able to do, that they cannot do today, and would
confirm out loud?**

Revenue is the proxy we use because we usually cannot measure real customer value directly.
The proxy only works if each item is anchored to something the customer would recognise as
value. An item that is true because we were busy is a broken proxy, and a broken proxy funds
the wrong ventures.

Hold this posture: you are writing something the customer could be shown without
embarrassment, and something a customer could mark yes or no without asking you what you
meant. Approved items are immutable.

## The ladder

Between our work and the customer's fortunes there are four rungs.

1. **Activity** - *we built the export.* Ours. True because we were busy.
2. **Capability** - *the customer can export a CSV.* A user's. A feature now exists; the
  business is exactly where it was.
3. **Standing** - *the customer closes month-end in two days instead of nine.* The
  customer's, and changed by us. Standing is any change in what the business is or can do:
  time recovered, cost avoided, scale reached, a market they can now enter, a certification
  they can now hold, IP they now own, a reputation they can now claim, an option they did
  not previously have.
4. **Fortune** - *the customer's revenue increases by X.* The world's. Real value, but
  produced by their sales team, their market, their pricing, their timing, and us.

**Every revenue plan item lives on rung 3.** Write the furthest-out change in the customer's
standing that our work is still substantially responsible for.

Rung 2 fails because nothing about the business changed - a capability was added, nothing was
gained. Rung 4 fails for the opposite reason: it is a genuine gain, but so much of it is
decided elsewhere that when it does not happen, nobody learns whether this venture did its
job. Rung 3 is the last place we can be held to account.

## Rung 4 is not taboo

Rung 3 is a proxy for rung 4, and a proxy is only worth holding if it still moves the needle
the customer actually cares about. So rung 4 is not something we avoid discussing - it is the
thing the whole plan is aimed at, and both CEO and Investor are expected to keep it in view.

The Investor owns the final sign-off on the revenue plan and therefore owns the judgement that
the proxy is valid. The CEO cannot hide behind that. When the link from an item to the
customer's fortunes weakens - the market moved, the customer's priorities changed, the
assumed causation was wrong - the CEO is responsible for saying so and proposing the change.
Silence is not neutrality; a CEO who lets a stale proxy stand has chosen it.

## Customer, not user

Say *customer*: the party whose business result changes and whose money is at stake. A user
clicking a new button is rung 2. Ask who signs off on the invoice and what changes for them.
If an item's only beneficiary is an internal team or an end user's convenience, keep climbing
until you reach the change in the customer's standing that the convenience causes.

## The five-question test

Every item must pass all five. If you cannot answer instantly, the item is not ready.

1. **Binary** - can it be answered with a yes/no.
2. **Customer-verifiable** - would the paying customer themselves confirm it, from evidence
  they hold? Not our dashboard, not our sprint board, not our belief about them.
3. **Enablement, not activity** - is it off rung 1? "We built / shipped / integrated /
  migrated" is activity. "The customer can / receives / no longer has to" is enablement. Not
  to be confused with user enablement via product capabilities; those are milestones that
  help get us to the revenue goal.
4. **Ours to move** - is it on rung 3 rather than 2 or 4? If it comes out false, does that
  tell the Investor something about *this venture*, or only about the customer's market?
5. **Clarity** - does the item stand alone? Anybody in the company should be able to read the
  item itself and know what is being claimed and how it will be settled, without the team,
  the customer, or the surrounding narrative to interpret it.

## Where verification detail lives

If an item is settled by a survey, an approval, or a threshold, the specifics belong in the
item's own text: who is asked, the exact question or decision, and the bar that counts as a
pass. The Trilovation description and narrative fields exist to give background, not to hold
the definition - an item whose meaning is only recoverable from the narrative does not stand
alone, and the narrative is not what gets marked yes or no at the end of the quarter.

This is detail about *settlement*, never about *mechanism*. "Confirmed by the customer's
finance lead in the quarterly review" is settlement. "Confirmed after we ship the new
dashboard" is mechanism, and it drags the item back to rung 1.

## No feature checklists

Clarity is not satisfied by listing features or workflow steps. When an item is challenged as
unclear, the response is to state who confirms it and against what bar - not to append a list
of what the product will do. A checklist reads as precision while quietly converting a rung-3
item back into rung-1 activity we can mark done by ourselves, and it puts the mechanism back
in the plan. What we build and in what order is Kanban's job; the revenue plan does not
duplicate it.

We want to uphold the "We are flexible and will do what it take to create value" mindset, and shun the "we built what we agreed on, not our fault that it didn't work out" mindset.

## Rewriting an item

When an item fails, do not soften it - climb. Ask "so that what?" until you reach the
customer's standing, then write that answer as the item and throw the original away. If you
climb past it into their fortunes, step back down one rung.

| Not this                      | This                                                                |
| ----------------------------- | ------------------------------------------------------------------- |
| Build the reconciliation API  | Customer closes month-end without manual spreadsheet reconciliation |
| Improve onboarding UX         | A new customer team is live and transacting on day one, unassisted  |
| Partner integration delivered | Customer settles partner invoices without leaving their own system  |

Notice what disappears: the mechanism. How we do it is our problem, and stating it in the
plan quietly converts the item into something we can mark done by ourselves.

## Traps that look like good items

- **Compound items.** "Customer can do X and Y" is two items pretending to be one so that
  half-done can be reported as progress. Split them.
- **Vanity thresholds.** Counts of features, tickets, or releases measure us, not them.
- **Perpetual items.** If it can never be false, it can never be evidence. If it can never be
  true this quarter, it is a strategy statement, not a plan item.
- **Proxy of a proxy.** "Customer is satisfied" is unverifiable. "Customer renewed" is not.
- **Retrofitting.** Writing the item after the work, shaped to what the work happened to
  produce. The plan comes first; that is the entire point of it.

## Milestones and revenue plan items

Milestones are ours: dated commitments about work, and it is fine for them to be about
mechanism - rung 1 is where milestones belong. Revenue plan items are the customer's. Link a
milestone to the item it unlocks so the chain from our effort to their standing is visible -
and if a milestone links to nothing, be suspicious of why we are doing it.

The revenue plan comes first. Milestones are how we work out a route to items that have
already been agreed, so at plan review time there may be no milestones yet - that is the
expected order, not a gap, and reviewers should not treat missing milestones as an incomplete
plan. A plan built around milestones that already exist is retrofitting.