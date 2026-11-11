# How The Guild would work legally

The demo runs on PayPal sandbox money, so none of this applies yet. Before real money moves, these are the questions a guild has to answer, and the plan for each. This is a plan to take to a lawyer, not legal advice. The rules differ by country and, in the US, by state.

## 1. The safety pool looks like insurance

**The question.** Members pay in every month, and the pool pays when a client never pays. Many places regulate "you pay a premium, we pay your loss" as insurance.

**What the design already does to stay on the mutual-aid side:**
- Only members pay in, and only members can be covered. No outsiders, no profit.
- A payout is never promised. An admin decides every claim, and the AI only recommends.
- Payouts are capped at 50% of the invoice and need a real, sent, overdue PayPal invoice.
- If the client pays later, the money goes back to the pool.

**The plan.** Write the pool rules down as a members' agreement that says payouts are discretionary. Many mutual-aid and "sharing" funds work this way. A lawyer in the launch state confirms it doesn't count as insurance there. If it does, partner with a licensed insurer for the cover and keep the guild as the group that buys it.

## 2. Early pay looks like a loan

**The question.** "Paid on day one" pays part of an invoice now and takes it back plus a 2% fee when the client pays. That is close to invoice factoring, or a small loan.

**What the design already does:** the fee is fixed and shown before anyone accepts, the advance is capped (70% of the invoice, $1,000, and half the pool), and one advance per member at a time.

**The plan.** Either make early pay fee-free (a member benefit, which is usually simpler), or offer it through a licensed lending or factoring partner, with the disclosures they require.

## 3. Who holds the money

**The question.** In the demo, the pool is a balance in our database, and PayPal Payouts sends money from one account.

**The plan.** Each guild becomes a legal entity (an LLC or a co-op) with its own PayPal business account and a written operating agreement. PayPal handles identity checks and moving money. The Guild's software keeps the rules and the record, and never holds funds itself. A lawyer checks whether paying members their split from that account needs a money-transmission licence, or whether PayPal's role covers it.

## 4. Taxes

Referral fees and claim payouts are income for the member. The guild entity would issue the tax forms its country requires (in the US, 1099s) and keep the money trail as its record, which the app already does for every dollar.

## 5. Agreements and privacy

- The client work agreement is a template. A lawyer reviews it once per country, and the app keeps its "fingerprint" (SHA-256) of the exact text each client accepted.
- The app stores the IP address and browser of whoever accepts an agreement, as proof. That needs a privacy policy, a retention period, and a way to delete data on request.

## Order of work before real money

1. Pick one launch state or country and get one lawyer review of points 1 to 3.
2. Form the first guild's entity and open its PayPal business account.
3. Publish terms of service, the pool rules and a privacy policy.
4. Start with early pay off, and turn it on once point 2 is settled.
