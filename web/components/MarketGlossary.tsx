/**
 * What each column on the board means.
 *
 * Plain definitions of the markets the board actually prices, so a reader who
 * has never placed a bet can still read a row. Only markets the engine
 * produces are listed: the reference site also explains a "team goals" market,
 * which this engine does not price, so it is left out rather than described
 * and then missing from every row.
 */

const ITEMS: Array<{ term: string; body: string }> = [
  {
    term: "Match result (1X2)",
    body: "Who wins after 90 minutes: 1 is the home side, X a draw, 2 the away side. The three probabilities add to 100%, and the pick is the likeliest of them.",
  },
  {
    term: "Double chance",
    body: "Two of the three results at once: 1X is home win or draw, X2 is draw or away win, 12 is either side winning. It is likelier than a single result by construction, so its price is shorter.",
  },
  {
    term: "Over / under goals",
    body: "Whether the match produces more or fewer goals than a line, counted in normal time. Over 2.5 needs three or more goals; under 2.5 needs two or fewer. The half-goal means there is never a push.",
  },
  {
    term: "Both teams to score (BTTS)",
    body: "Yes if each side scores at least once, no if either keeps a clean sheet. The final score does not matter, only that both goal counts are above zero.",
  },
  {
    term: "Best tip",
    body: "The single pick the engine leads with for the fixture, chosen from every market it priced: the likeliest call among those that beat how often their market lands anyway, or simply the likeliest where none do.",
  },
  {
    term: "Confidence",
    body: "A score out of ten for how closely the engine's independent estimators agree on the fixture. It describes agreement, not the chance of winning, which is what the percentage on each pick says.",
  },
  {
    term: "Prices and the ≈ mark",
    body: "A price is a bookmaker's where one was quoted. Where none was, the cell shows the pick's own fair price, 100 divided by its probability, marked ≈. A fair price has no bookmaker margin, so it is not a price you can bet at.",
  },
];

export function MarketGlossary({ heading = "How to read the board" }) {
  return (
    <section className="mt-14 max-w-[72ch]" aria-label={heading}>
      <h2 className="text-[18px] font-bold tracking-[-0.015em]">{heading}</h2>
      <dl className="mt-4 space-y-4">
        {ITEMS.map((item) => (
          <div key={item.term}>
            <dt className="text-[14px] font-semibold">{item.term}</dt>
            <dd className="mt-1 text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
              {item.body}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
