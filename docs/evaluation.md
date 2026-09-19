# Small Evaluation Set

`data/evaluation/review_annotations.csv` contains one human-authored expected
theme and stance label for each of the 30 synthetic demo reviews in
`data/sample_reviews.csv`.

The set exists to catch functional regressions in review validation, evidence
linking and support-versus-contradiction handling. It is deliberately small,
synthetic and category-specific. It is not evidence of production model
accuracy, statistical calibration or performance on live Amazon reviews.

## Labels

- `support`: the review supports the pain point represented by the theme.
- `contradict`: the review provides counter-evidence or a positive experience.
- `neutral`: reserved for reviews that mention a theme without taking a clear
  position. The current fixture uses paired support and contradiction examples.

## Intended Checks

1. Every annotation references an existing review ID exactly once.
2. Evidence links always resolve back to the original review text.
3. Both supporting and contradicting evidence remain visible.
4. Low-coverage themes are downgraded to `unknown` rather than promoted to a
   confident recommendation.

Evaluation results should always be reported with the fixture size and its
synthetic-data limitation.
