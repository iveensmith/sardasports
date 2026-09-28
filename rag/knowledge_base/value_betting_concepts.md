# Value Detection: Model Probability vs. Market-Implied Probability

Bookmaker odds encode a probability estimate, but not directly — decimal
odds have to be converted first. A decimal odds of 2.00 corresponds to a raw
implied probability of 1 / 2.00 = 50%. Summing the raw implied probabilities
across all outcomes of a market (home win, draw, away win) will always come
out above 100%; that excess is the bookmaker's margin, often called the
"overround" or "vig." To get a fair comparison against a model's own
probabilities, the raw implied probabilities need to be divided by their sum
so they add up to exactly 100% — UniquePredict does this in
`ml.monitoring.value_detection` before comparing anything.

"Value" in this context means a percentage-point gap between a model's
probability for an outcome and the market's overround-adjusted implied
probability for the same outcome. A positive gap means the model is more
confident in that outcome than the market is; a negative gap means the
opposite. This is purely a mathematical comparison between two probability
estimates — it says nothing about whether either estimate is *correct*, and
it is not a profit guarantee. Markets are frequently more accurate than any
single model, especially for well-traded top-league matches where sharp
money has already pushed prices toward efficiency.

Because of this, UniquePredict's value-detection output always reports the
edge as a plain number alongside a disclaimer, and the AI analyst agent is
instructed never to describe a detected edge as a betting recommendation.
