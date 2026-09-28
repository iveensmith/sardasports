# Home Advantage in Football

Home advantage is one of the most consistent effects in football analytics:
across most leagues and seasons, home teams win more often than a
strength-neutral model would predict. Commonly cited contributing factors
include crowd support affecting refereeing decisions and player adrenaline,
travel fatigue for the away side, and familiarity with pitch dimensions and
surroundings.

The size of the effect varies by league, by team, and over time — some
analyses found it shrank measurably during periods when matches were played
without crowds, which is consistent with crowd presence being a real
contributor rather than pure home-tactical familiarity. It also tends to be
larger for mid-table and smaller clubs than for the very biggest teams, whose
quality gap over most opponents already dominates the result regardless of
venue.

In UniquePredict, home advantage is represented in two independent places:
as a fixed points bonus added to the home team's effective Elo rating before
computing win probability, and as a multiplier on expected goals in the
Poisson model (so the home side's expected goals are scaled up and the away
side's are not). Because both estimates come from real historical results
rather than a single assumed constant, they can and do differ slightly
between leagues if trained separately per competition.
