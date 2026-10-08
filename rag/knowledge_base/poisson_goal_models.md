# Poisson Goal Models

Goals in football are relatively rare, independent-ish events, which makes
the Poisson distribution a natural fit for modeling how many goals a team
will score in a match. The Poisson approach (originally popularized in
football analytics by Maher in 1982, and refined by Dixon and Coles) assigns
each team two numbers: an attack strength and a defense strength, both
measured relative to the league average.

A team's expected goals in a given fixture come from multiplying the league's
average goals-per-game by its attack strength and the opponent's defense
weakness, with a home-advantage multiplier applied to the home side. Once you
have expected goals for both teams, treating each as an independent Poisson
random variable produces a full matrix of scoreline probabilities — P(0-0),
P(1-0), P(2-1), and so on, for every plausible scoreline.

This scoreline matrix is unusually versatile: summing the diagonal gives the
draw probability, summing everything below the diagonal gives the home-win
probability, and the matrix directly answers questions like "P(both teams
score)" or "P(more than 2.5 total goals)" without needing separate models.
SARDASPORTS uses exactly this property — its Poisson model derives the
correct-score, over/under, and BTTS baselines, which dedicated machine
learning models are then blended with once enough training data exists.

The main limitation of a pure Poisson model is that it assumes home and away
goals are independent of each other, which isn't perfectly true (teams
sometimes adjust tactics once a game state is established), and it has no
concept of current form, injuries, or fixture congestion — all reasons to
combine it with Elo and feature-based ML models rather than use it alone.
