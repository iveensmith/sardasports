# Elo Ratings in Football

The Elo rating system was originally designed for chess by Arpad Elo, and
adapted for football by tracking a single number per team that represents
relative strength. Every team starts at a baseline rating (UniquePredict
defaults to 1500) and that number moves up after wins and down after losses,
with the size of the movement controlled by a K-factor.

The core idea is the expected score: given two ratings, Elo computes a
logistic-curve probability that the higher-rated side wins. If the actual
result matches that expectation, the rating barely moves; if a big underdog
wins, both ratings move sharply, because the system was "surprised."

Home advantage is modeled as a fixed bonus added to the home team's rating
before computing the expected score — UniquePredict uses roughly 60 points
by default, tuned via the ELO_HOME_ADVANTAGE setting. Margin of victory also
matters in football-adapted Elo: a 3-0 win moves ratings more than a 1-0 win,
since it's stronger evidence of a quality gap between the sides.

Elo's strength is that it requires no training data beyond match results and
updates automatically after every game — no retraining pipeline needed. Its
weakness is that it only captures overall win/loss strength, not *why* a team
is strong (attack vs. defense, home vs. away form, injuries), which is why
UniquePredict combines it with a Poisson goal model and a machine-learned
model rather than relying on Elo alone.
