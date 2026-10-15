# Plan: accounts, premium membership, payments and alerts

Status: **plan only, nothing built.** Written 12 Oct 2026.

The eight items in the brief:

1. Customer registration and login
2. Automated sports-data feeds
3. Prediction dashboards
4. Premium membership management
5. Payment integration
6. Automated email notifications
7. Performance statistics and reporting
8. Telegram notifications

---

## 1. Where the project is today

| Item | State now | What is missing |
|---|---|---|
| 1. Registration and login | **Nothing.** No user tables, no sessions. The site is public and free. | Everything. |
| 2. Sports-data feeds | **Mostly built.** API-Football (fixtures, odds, results, live, stats, injuries) on the Pro plan; basketball and tennis feeds; Football-Data history; scheduler with quota guard and a plan watcher. | Feed health monitoring and alerts; basketball on its own plan; the lower divisions, cups, UEFA and internationals (needs a retrain); running feeds outside the web process. |
| 3. Prediction dashboards | Public boards, match pages, bankers, slip builder, league and team pages. | Anything personal: a member's own dashboard, watchlist, saved slips, filters that persist. |
| 4. Premium membership | **Nothing.** No plans, no gating. | Plans, entitlements, subscription states, gating that cannot be bypassed. |
| 5. Payments | **Nothing.** | Provider, checkout, webhooks, receipts, refunds, tax. |
| 6. Email notifications | **Nothing outgoing.** The Contact form stores messages in the database; no mail is sent. | A sender domain, a provider, templates, queue, preferences, unsubscribe. |
| 7. Statistics and reporting | The public record (`/progress`, per-sport records, per-market tables). | Reporting for members (personal) and for the owner (revenue, members, feed health), scheduled reports. |
| 8. Telegram | **Nothing.** The footer has a "coming soon" row. | A bot, account linking, alert types, throttling. |

Things that constrain every choice below:

- **One 4 GB server, SQLite, one process for the engine.** It froze on 12 Oct (the weekly retrain ran inside the
  web process). Accounts and payments add write traffic and background work; the work has to leave the web
  process first (phase 0).
- **Pages are cached and shared** (ISR and a CDN). Anything member-specific must be fetched per request and
  never cached for everyone, or one member's data is served to another.
- **The site's argument is honesty:** every pick is stored before kick-off and graded, wins and losses alike.
  Premium must not break that (see section 6, "rules we keep").
- **No fabrication.** No invented testimonials, member counts, "guaranteed" wins or fake scarcity.

---

## 2. Decisions needed from the owner (these change what gets built)

| # | Decision | Why it matters | My recommendation |
|---|---|---|---|
| D1 | **What is free and what is premium?** | Defines the whole gating model and the revenue. | Keep the record, today's board and one pick per sport free. Premium: full markets and all leagues, alerts, saved slips and history export, early-access to the daily bankers card. |
| D2 | **Plans, prices, currency, billing periods** | Needed before payments. The mock-up's prices are not ours and must not be reused. | Monthly and yearly, one currency to start, a 7-day money-back window. |
| D3 | **Who pays, where?** UK, Nigeria, both? | Decides the payment provider(s). | Stripe for cards (UK and international); Paystack or Flutterwave added for Nigeria (bank transfer, USSD, NGN). |
| D4 | **Accounts: Supabase or self-hosted?** | Biggest architecture choice (section 3). | Supabase for accounts and email-link login; engine stays on SQLite. |
| D5 | **Legal entity and policies** | Terms, privacy policy, refund policy, VAT. Needs a real name and address. | Get a lawyer to review. Tipster services are advertised under gambling-adjacent rules. |
| D6 | **Email sender and domain** | Needs the domain (bought) to send from `@yourdomain`. | Resend or Postmark, with SPF, DKIM and DMARC set on the domain. |
| D7 | **Telegram: a public channel, private alerts, or both?** | Decides the bot design. | Public channel for free picks, private bot messages for premium alerts. |
| D8 | **Do odds ever become bookmaker referrals?** | Affiliate links carry licensing and age-gating duties. Still undecided. | No, until a lawyer says otherwise. |
| D9 | **Hosting capacity** | Accounts, queues and a database beside the engine need more than 4 GB. | Move to an 8 GB server, and split the web, worker and database. |

---

## 3. Architecture

### 3.1 The one real fork: where accounts live

| | **A. Supabase (managed Postgres + Auth)** | **B. Self-hosted (Postgres + auth in FastAPI)** |
|---|---|---|
| Effort | Lower (email verification, password reset, magic links, OAuth come ready) | Higher (build and secure all of it) |
| Server memory | None on your box | About 300 to 500 MB for Postgres |
| Control and data location | A third party holds user data | Everything on your server |
| Cost | Free tier pauses after a week idle, so plan on the paid tier (about $25 a month) | The server only |
| Risk | Vendor dependency and plan limits | You own every security bug |
| Fits today's setup | Yes: engine stays on SQLite, only member data goes out | Needs Postgres and a migration of the app's data layer |

**Recommendation: A.** The engine keeps its SQLite database untouched. Next.js signs members in through
Supabase; the engine checks the member's token when a gated endpoint is called and reads their plan from a
small `entitlements` table kept in Supabase. This leaves the proven prediction pipeline alone and adds the
member layer beside it.

If D4 is B, the same phases apply; phase 1 grows by about a week.

### 3.2 Process layout (phase 0)

```
Cloudflare  ->  web (Next.js, 512 MB)  ->  api (read-only requests, 1.5 GB)
                                       ->  worker (scheduler, feeds, training, notifications, 1.5 GB)
                                       ->  Supabase (members, plans)       <- external
```

The scheduler and every heavy job move out of the process that answers visitors. A job that misbehaves then
restarts the worker, and the site keeps serving.

### 3.3 Data model (members side)

- `profiles` (id, display name, country, over_18_confirmed_at, created_at)
- `plans` (id, name, interval, price, currency, provider_price_id, active)
- `subscriptions` (id, user_id, plan_id, status, current_period_end, cancel_at_period_end, provider_ref)
- `payments` (id, user_id, subscription_id, amount, currency, status, provider_ref, receipt_url)
- `webhook_events` (provider, event_id unique, payload, processed_at): makes webhooks idempotent
- `entitlements` view: user -> which features are on right now
- `notification_prefs` (user_id, channel, kind, enabled), `email_outbox`, `telegram_links`
- `watchlist` (user_id, team or league), `saved_slips`, `followed_picks`

---

## 4. The plan, by phase

Estimates are **working days for one developer**, including tests, and assume the decisions above are made.

### Phase 0: Foundations (4 to 6 days)
- Wire the domain through Cloudflare (permanent address, HTTPS, redirects).
- Split the process: `worker` container for the scheduler, feeds, training and notifications.
- Server to 8 GB; Postgres or Supabase connection; staging environment; secrets handling; encrypted
  off-server backups of every database, and a restore test.
- Error tracking and uptime alerts.
- **Done when:** a runaway job restarts the worker and leaves the site up; a restore from backup has been done.

### Phase 1: Registration and login (item 1) (5 to 7 days)
- Sign-up with email and password, magic link, optional Google sign-in; email verification; password reset.
- Over-18 confirmation at sign-up; Terms and Privacy acceptance recorded with a date.
- Bot protection (Cloudflare Turnstile), rate limits, lockout, session expiry, "log out everywhere".
- Account page: profile, change email and password, delete account, export my data.
- Pages: sign up, log in, forgot password, verify email, account.
- **Done when:** a new member can register, verify, log in on a phone, reset a password and delete their
  account, and none of the public pages slowed down.

### Phase 2: Email notifications (item 6) (4 to 6 days)
- Sender domain authenticated (SPF, DKIM, DMARC); provider chosen (D6).
- Transactional first: verification, reset, welcome, receipts, payment failed, plan changed.
- Then product mail: daily picks digest, kick-off reminders for followed teams, weekly performance summary.
- An outbox table and a worker that sends with retries; bounce and complaint handling; per-kind preferences;
  one-click unsubscribe in every marketing mail; double opt-in for marketing.
- **Done when:** a test mail passes the spam checks (mail-tester style) and an unsubscribe takes effect at once.

### Phase 3: Telegram notifications (item 8) (3 to 5 days)
- A bot (BotFather); account linking by a one-time deep link from the dashboard, so no one can claim
  another member's alerts.
- Alert kinds: picks published, kick-off reminders, final result and whether the pick landed, daily summary.
- Throttling (Telegram allows about one message a second to a chat), quiet hours, stop and unlink commands.
- A public channel for free picks; premium alerts only to linked, active members.
- **Done when:** link, receive, mute and unlink all work, and a lapsed premium member stops receiving premium
  alerts within minutes.

### Phase 4: Prediction dashboards (item 3) (6 to 9 days)
- **Member dashboard:** today's picks filtered to followed teams and leagues, saved slips, followed picks and
  how each ended, notification settings.
- **Premium dashboard:** full market view, all competitions, confidence breakdown and calibration charts,
  history export (CSV).
- Per-member data is fetched fresh and never cached for others; public pages stay cached.
- **Done when:** two members with different watchlists see different data, a signed-out visitor sees none of
  it, and the public home page is as fast as before.

### Phase 5: Premium membership management (item 4) (5 to 7 days)
- Plans and entitlements; subscription states (trialing, active, past due, cancelled, expired); a grace
  period; cancel and resume.
- **Gating enforced in the engine, not only the page:** a premium endpoint refuses without a valid
  entitlement, and responses for premium data are never publicly cached.
- Admin screen for the owner: find a member, grant or revoke access, comp codes, see their history.
- **Done when:** a downgraded member loses access immediately, and calling a premium endpoint directly with a
  free account is refused.

### Phase 6: Payment integration (item 5) (6 to 9 days)
- Hosted checkout only, so card details never touch your server.
- Webhooks with signature checks, idempotency (the `webhook_events` table), retries, and a nightly
  reconcile job that compares provider and database.
- Customer portal (update card, cancel, invoices), receipts, refunds, failed-payment retries and emails.
- Tax and VAT handling, test mode all the way, then a live-mode checklist.
- **Done when:** a test payment, a failed payment, a refund and a cancellation each leave the database and the
  member's access in the right state, with nothing double-counted when a webhook arrives twice.

### Phase 7: Sports-data feeds hardening (item 2) (4 to 6 days, in parallel with 4 to 6)
- A **data health** page for the owner: when each feed last ran, what it fetched, quota left today, failures.
- Alerts (email and Telegram to the owner) when a feed is late, a job fails twice, or quota is short.
- Basketball on its own paid plan if wanted; the expansion (lower divisions, cups, UEFA, internationals) only
  after a retrain and a before and after accuracy check.
- Every job idempotent, with retries and a clear dead-letter log.
- **Done when:** a feed outage is noticed by the owner within minutes, before a visitor reports it.

### Phase 8: Performance statistics and reporting (item 7) (4 to 6 days)
- **Public:** keep the record as is; add per-league and per-period views, calibration, streaks, definitions.
- **Member:** personal results for followed picks and saved slips.
- **Owner:** revenue and members (new, active, churned, conversion), notification delivery, feed health;
  a scheduled weekly report by email.
- Anything that shows profit uses real prices, a stated flat stake and a clear "illustration, not a promise".
- **Done when:** every number on a report can be traced back to graded picks, and the owner gets the weekly
  report without asking.

### Phase 9: Legal, QA and launch (3 to 5 days)
- Terms, Privacy, Cookies, Refunds and Responsible-gambling pages updated and reviewed.
- Security review (see section 5), load test with a realistic crowd, accessibility pass.
- A staged launch: invite-only, then public; rollback plan.

**Total: about 45 to 65 working days** for one person, depending on D4 and how many payment providers.

---

## 5. Cross-cutting requirements

**Security:** sessions in secure, HTTP-only cookies; passwords never stored by us (A) or hashed with argon2 (B);
every gated endpoint checks entitlement server-side; rate limits on login, reset and notification endpoints;
secrets only in the environment; admin actions audited; webhook signatures verified; dependency updates.

**Privacy:** collect the minimum; consent recorded; export and delete work; email and Telegram are opt-in per
kind; a data-processing list for the Privacy page; cookie banner only if a non-essential cookie is added.

**Reliability:** a member database backup that is tested; a queue for mail and Telegram so a provider outage
does not lose messages; graceful degradation (the public site works when members are down).

**Observability:** error tracking, uptime checks, a status of every scheduled job, structured logs.

**Testing:** unit tests for entitlement and subscription state changes; integration tests with the payment
provider's test mode and webhook replay; end-to-end sign-up to payment to access; abuse tests (cross-account
access, replayed webhooks).

---

## 6. Rules we keep (so the premium layer does not damage the product)

1. **Premium picks are stored before kick-off and graded the same way**, and appear in the public record
   afterwards, losses included. Nothing is hidden behind the paywall and then only shown if it won.
2. **No guarantees, no "sure wins", no invented reviews or member counts.**
3. **Probabilities, not advice:** every page keeps the 18+ and responsible-gambling notices.
4. **Free stays genuinely useful:** the daily board, the record and the glossary stay open.
5. **A refund path that works:** stated in the Terms and tested.

---

## 7. Suggested order

| Milestone | Contains | Why this order |
|---|---|---|
| M1 | Phase 0 and 1 | Safe base, then members exist. Free sign-ups start building an audience. |
| M2 | Phases 2, 3 and 4 | Free members get email and Telegram alerts and a dashboard: value before money. |
| M3 | Phases 5 and 6 | Premium and payments, the highest-risk part, built on a base that already works. |
| M4 | Phases 7, 8 and 9 | Reporting, feed hardening, legal and launch. |

**A faster path if revenue is urgent:** ship a thin slice after M1 (Stripe or Paystack payment link, access
granted by the owner in an admin screen, no self-service). About 3 to 4 days, and replaced by phases 5 and 6.

---

## 8. Rough running costs (verify before relying on them)

| Item | About |
|---|---|
| Server, 8 GB | roughly double today's |
| Supabase (paid tier) | about $25 a month |
| Email provider | free tier first, then about $20 a month |
| Payments | a percentage of each charge (cards roughly 1.5% to 3% plus a fixed fee; Paystack differs for Nigeria) |
| Telegram, Cloudflare, Turnstile | free |
| API-Football Pro | what you already pay; basketball is a separate plan |
| Error tracking | free tier first |

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Regulation of tips and gambling-adjacent services differs by country | Legal review (D5) before charging; age gate; no referral links without advice (D8) |
| A paywall that looks like cherry-picking | Rule 1 above; premium picks graded publicly |
| Payment bugs charge or fail to grant access | Idempotent webhooks, nightly reconcile, test mode first, small beta |
| The server freezes again | Phase 0 split, memory caps, swap, alerts |
| Member data leak | Server-side gating, row-level security (A), pen test before launch |
| Email lands in spam | Authenticated domain, warm-up, honest content, easy unsubscribe |
| Scope grows | Fixed milestones; each phase has a "done when" |

---

## 10. What I need to start

1. Answers to D1 to D9 (or "your recommendation" on any).
2. The legal name, address and contact email for the Terms and Privacy pages.
3. Accounts to be created: Supabase project (or the go-ahead for self-hosting), Stripe and/or Paystack,
   an email provider, a Telegram bot token.
4. A server upgrade to 8 GB.
