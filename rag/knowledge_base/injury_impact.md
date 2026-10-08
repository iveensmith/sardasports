# Injury Impact on Match Outcomes

The impact of a missing player on a football team's result probability
depends heavily on the player's role and how replaceable it is. Losing a
starting goalkeeper or a first-choice center-back tends to move a team's
expected goals conceded more than losing a squad-rotation winger, because
defensive positions are typically less deep in quality across a squad than
attacking ones. Losing a primary goalscorer has an outsized effect on
expected goals scored when the team lacks a comparable backup.

Quantifying this rigorously requires either detailed injury-adjusted rating
systems (tracking a team's rating with and without specific players over
many matches) or player-level statistical models that can be summed and
compared with and without a given lineup — both are substantially more data-
intensive than team-level modeling.

SARDASPORTS does not currently ingest an injury data source (see the
project roadmap), so its predictions reflect team-level historical form,
Elo, and goal-scoring tendencies only — they do not yet adjust for a specific
missing player. Where the AI analyst agent's `get_injuries` tool is called
and no data source is configured, it will say so explicitly rather than
guess at an impact, since an unverified injury claim could materially
mislead a prediction's users.
