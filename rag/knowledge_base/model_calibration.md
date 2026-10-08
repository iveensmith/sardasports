# Model Calibration and the Brier Score

A prediction model is "well calibrated" if, among all the times it says an
outcome has a 70% chance, that outcome actually happens about 70% of the
time — no more, no less. Calibration is a distinct property from accuracy: a
model can correctly pick the most likely outcome most of the time while still
being badly calibrated (for example, consistently saying 90% when the true
rate is closer to 65%), which matters a lot if the probabilities themselves
are going to be read or acted on, not just the single most-likely pick.

The Brier score is a standard way to measure this: for each prediction, take
the squared difference between the predicted probability and the actual
outcome (1 if it happened, 0 if it didn't), summed across all possible
outcomes, then averaged across every prediction. A Brier score of 0 is a
perfect, always-certain-and-always-right model; guessing a flat 1/3 chance
for every outcome in a three-way market gives a Brier score around 0.67. A
well-calibrated, reasonably skillful match-result model typically lands
somewhere between 0.20 and 0.25.

SARDASPORTS tracks this in `ml.monitoring.calibration`, which buckets past
predictions by the probability assigned to their predicted outcome and
compares each bucket's average confidence against how often predictions in
that bucket were actually correct — the closer those two numbers are for
every bucket, the better calibrated the ensemble is. This can only be
computed once enough completed matches have accumulated real evaluated
predictions; a handful of predictions produce a noisy, not-yet-meaningful
curve.
