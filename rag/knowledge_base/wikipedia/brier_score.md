# Brier score

Source: Wikipedia, "Brier score" (https://en.wikipedia.org/wiki/Brier_score), retrieved 2026-09-22. Text licensed under CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/); this excerpt is trimmed to its most substantive introductory paragraphs.

The Brier score is a strictly proper scoring rule that measures the accuracy of probabilistic predictions. For unidimensional predictions, it is strictly equivalent to the mean squared error as applied to predicted probabilities.

The Brier score is applicable to tasks in which predictions must assign probabilities to a set of mutually exclusive discrete outcomes or classes. The set of possible outcomes can be either binary or categorical in nature, and the probabilities assigned to this set of outcomes must sum to one (where each individual probability is in the range of 0 to 1). It was proposed by Glenn W. Brier in 1950.

The Brier score can be thought of as a cost function. More precisely, across all items

in a set of N predictions, the Brier score measures the mean squared difference between:

Therefore, the lower the Brier score is for a set of predictions, the better the predictions are calibrated. Note that the Brier score, in its most common formulation, takes on a value between zero and one, since this is the square of the largest possible difference between a predicted probability (which must be between zero and one) and the actual outcome (which can take on values of only 0 or 1).  In the original (1950) formulation of the Brier score, the range is double, from zero to two.

The Brier score is appropriate for binary and categorical outcomes that can be structured as true or false, but it is inappropriate for ordinal variables which can take on three or more values.

is the number of forecasting instances. In effect, it is the mean squared error of the forecast. This formulation is mostly used for binary events (for example "rain" or "no rain"). The above equation is a proper scoring rule only for binary events; if a multi-category forecast is to be evaluated, then the original definition given by Brier below should be used.

that it will rain on a given day. Then the Brier score is calculated as follows:
