# SEO plan

This is the working plan for ranking the site once it is hosted. It has four parts:
what people search for and which page answers it, what is already built, what has to
happen on launch day, and what to measure afterwards.

One rule runs through all of it. **Nothing here may be invented or overstated.** No
search volumes are quoted, because none have been measured; the keyword choices
below come from search *intent* and have to be validated in Search Console once the
site has impressions. No page may promise wins, "sure" tips or an accuracy figure the
public record does not back. For a site in the betting-adjacent space that is the
difference between being treated as a trustworthy publisher and being treated as
spam, and it is also simply the site's argument: every pick is graded in public.

## 1. Keywords, by intent, mapped to pages

Each page targets one primary phrase and a few close variants, and no two pages
target the same phrase. Competing with yourself splits the ranking signal.

| Intent | Primary phrase | Page | Notes |
| --- | --- | --- | --- |
| Daily tips | football predictions today | `/` (H1, title) and `/matches` | Home owns the brand-level phrase; `/matches` owns "today's football predictions & betting tips". |
| Daily tips, other days | football predictions for [date] | `/matches?date=…` | Dated titles, self-canonical. A dedicated `/football-predictions-tomorrow` route is the obvious next step (see section 5). |
| AI angle | AI football predictions | `/` description and hero copy, `/how-it-works` | "AI" is a differentiator searchers use; it appears where it is true. |
| Goals market | over 2.5 goals predictions today | `/over-2-5-goals-predictions-today` | Has a 30-day record, a base rate and an FAQ. |
| Both teams to score | both teams to score predictions today, BTTS tips | `/both-teams-to-score-predictions-today` | Added in this pass; same structure as over 2.5. |
| Exact score | correct score predictions today | `/correct-score-predictions-today` | Reports the real, low hit rate on purpose. |
| Safe picks | football banker tips today | `/bankers` | The page states the 80% threshold and the record. |
| Accumulators | accumulator builder, bet slip generator | `/slip` | A tool page, which attracts links and repeat visits. |
| Match previews | [home] vs [away] prediction | `/match/[slug]` | The long tail. Unique title, description, H1 and `SportsEvent` data per fixture. |
| League tips | [league] predictions, [league] tips | `/leagues/[slug]` | 43 competitions. |
| Team form | [team] predictions, [team] form | `/teams/[slug]` | 843 active teams; thin ones are not indexed. |
| Comparison ("best") | best AI prediction site, best football prediction site, best prediction site | Home title tag, description, hero, home section "The best AI prediction site for football", home FAQ, footer, `/best-football-prediction-site` | **Owner's decision: the site states that it is the best AI prediction site.** Every statement of it is paired with grounds a visitor can verify (the 8-point checklist and the self-assessment, including a "where it falls short" section), so it reads as a position, not an empty boast. No competitor is named. If any ground stops being true, change the ground; do not drop the verifiability. |
| Free / accuracy | free football predictions, most accurate football predictions | home FAQ, `/best-football-prediction-site` FAQ | Answered honestly: free is not the test, verifiability is. |
| Trust | football prediction accuracy, are football predictions accurate | `/progress` | The page most competitors cannot build, because it needs a real record. |
| How it works | how AI football predictions work | `/how-it-works` | Also feeds the FAQ rich-result markup. |

**Words to avoid.** "Sure wins", "guaranteed", "fixed matches", "100% accurate",
"safe bets" as a promise. They are untrue, they attract the wrong audience, and they
are the vocabulary of the sites search engines distrust most. "Banker" is used because
it is a standard term, always defined on the page as a probability, not a promise.

## 2. What is built

**Crawlability.** `robots.txt` and `sitemap.xml` are generated. The sitemap lists the
fixed pages, every league with data, every team that has played in the last year, and
fixtures from a fortnight back to a week ahead, each with a *real* last-modified date
taken from the matches themselves (a lastmod that is always "today" teaches a crawler
to ignore the field). If the engine is unreachable the sitemap falls back to the fixed
pages for that one request and retries on the next, so a transient failure cannot pin a
shrunken sitemap.

**Staging safeguard.** Until `NEXT_PUBLIC_SITE_URL` is set to a real public address,
every page is `noindex, nofollow` and `robots.txt` disallows everything. A staging copy
cannot be indexed by accident. Setting the variable flips both.

**On-page.** One shared builder (`web/lib/seo.ts`) produces every title, description,
canonical, Open Graph and Twitter card, so no page can forget one. It enforces the
limits: titles drop the brand rather than be cut off past about 62 characters, and
descriptions are trimmed at a word boundary at 155. Every page has exactly one H1, and
the H1s now say what the page is (previously several said only "Bankers" or "Leagues",
and the matches page's H1 was just a date). The home H1 is "Football predictions, every
one graded", where it used to be "Every prediction, graded".

**Match pages.** These were the largest gap: every fixture shared one generic title and
had no H1. Each now has a unique title ("Arsenal vs Chelsea Prediction & Betting
Tips"), a description with competition and date, a visible H1, a canonical on the
readable URL (so `/match/144414` and the long form do not compete), a breadcrumb trail,
and `SportsEvent` structured data.

**Structured data** (JSON-LD, all describing content actually on the page):
`Organization` and `WebSite` site-wide; `FAQPage` on the home page, how-it-works and the
three market pages; `BreadcrumbList` on every league, team, match and market page;
`SportsEvent` on football fixtures; `Dataset` on the track record, pointing at the two
real CSV downloads (this can surface the record in Google Dataset Search). Google now
limits FAQ rich results to a few kinds of site, so do not expect expanding FAQs in the
results; the markup is still valid and still helps machines read the page.

**Social sharing.** A generated 1200 x 630 share image carries the brand and the
one-line promise, with no statistic that could go stale.

**Thin pages.** A team with fewer than three recorded matches is `noindex` (still
reachable, not offered to search engines). The legacy prediction board and model
analytics views are `noindex`.

## 3. Launch checklist

1. **Set `NEXT_PUBLIC_SITE_URL`** to the real address (for example
   `https://www.yourdomain.com`, no trailing slash) in the production environment, then
   rebuild. Check `/robots.txt` says `Allow: /` and the page source says
   `index, follow`.
2. **HTTPS everywhere, one hostname.** Redirect `http` to `https` and the non-preferred
   of `www` / non-`www` to the preferred, with a 301. Two reachable hostnames split
   every signal in half.
3. **Search Console.** Add the site as a *domain property* (DNS verification), submit
   `https://…/sitemap.xml`, and check Coverage after a few days. Do the same in Bing
   Webmaster Tools.
4. **Analytics.** Add a privacy-respecting analytics tool before launch so the first
   weeks of data are not lost. (Not installed yet; it needs your choice and, depending
   on where visitors are, a consent notice.)
5. **Make the engine crawl-safe.** A crawler will request hundreds of pages in a burst.
   The engine currently runs a full day of predictions per request, and a burst has
   been seen to exhaust its database connections and return errors. That has to be fixed
   (it is queued as its own task) and the site served from a cache or CDN, before
   inviting Google in. A crawler that meets 500 errors reduces how often it comes back.
6. **Core Web Vitals.** Run PageSpeed Insights on the home page, a match page and a
   league page against the live address. Watch LCP on the home hero and the weight of
   the first board.
7. **Trust pages.** About, Contact and Privacy now exist (with a responsible-gambling
   section on About and a dated corrections list), and are linked from the footer and in
   the sitemap. What is still needed from you before launch: set
   `NEXT_PUBLIC_OPERATOR_NAME` and, if you want one shown, `NEXT_PUBLIC_CONTACT_EMAIL`, so
   the pages name who runs the site (they say "the site's operator" until you do); have
   someone qualified read the Privacy policy; and add Terms of use if you want them. Add a
   `sameAs` list to the `Organization` data once real social profiles exist.

## 4. Measuring it

After two to four weeks of impressions, in Search Console:

- **Queries.** Which of the phrases in section 1 actually appear, and at what position?
  Re-write titles for queries where impressions are high and click-through is low.
- **Pages.** Which match, league and team pages are indexed? "Crawled, currently not
  indexed" on team pages means they are too thin; raise the `noindex` threshold.
- **Indexed vs submitted.** The sitemap carries about a thousand URLs. If far fewer are
  indexed after a month, the cause is almost always speed or thin content, not the
  sitemap.
- **Track record page.** This is the one with a real chance at links and press, because
  it holds something others do not: every loss on the record, downloadable. Watch its
  referrers.

## 5. What to build next (in order of likely return)

1. **Dedicated day pages.** `/football-predictions-tomorrow` and
   `/football-predictions-today` as stable, indexable addresses, instead of a query
   string on `/matches`. People search "tomorrow" far more than "4 October".
2. **More markets in the same pattern** the market pages already follow: under 2.5, over
   1.5, double chance, draw predictions. Each reuses the existing service and record.
3. **League x market pages** ("Premier League BTTS tips"), generated from data, only
   where there is enough history to be non-trivial.
4. **A glossary.** "What is BTTS", "what is double chance", "what does 1X2 mean". These
   are the informational queries that bring people who have not decided where to look
   yet. The explanatory text already exists on the board and market pages and can be
   given addresses of its own.
5. **Team and league pages with more depth** once more is stored: head-to-head
   summaries, home and away splits. Depth, not volume, is what keeps these indexed.
6. **Links.** Publish the open dataset prominently, write up the corrected track-record
   finding (a prediction site that publishes its own error is a story), and submit to
   football-data communities. Do not buy links.

## 6. Do not

- Add keywords to pages in hidden text, or repeat a phrase for its own sake.
- Mark up content that is not visible on the page.
- Publish a page per team-versus-team combination or per date that has nothing on it.
- Copy another site's prediction text. Everything here is generated from this engine's
  own numbers, which is the reason it can be distinctive.
