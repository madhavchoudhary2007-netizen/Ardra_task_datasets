# Training guide

1. Train only on `canonical/train` and `augmented/train`. Keep every variant in the same partition as its source scene. Do not randomly re-split images.
2. Monitor loss and per-class precision/recall/AP on **clean** `canonical/val_original`. Use early stopping or regularization when validation quality worsens while training quality improves.
3. Check each class separately. `marker_flag` has far more labeled instances than `short_tripod`; use class-aware sampling or loss weighting if the rare classes underperform. Do not infer performance from overall AP alone.
4. Evaluate once on untouched `canonical/test_original`. Use `augmented/val_drone` and `augmented/test_drone` to measure transformation robustness separately; their images are variants of existing source scenes.
5. Examine false positives on verified target-free images and collect more independent hard negatives if deployment backgrounds differ. Do not label unreviewed or quarantined images as target-free by assumption.
6. Review the remaining QA exceptions before using this dataset for safety-critical claims. A known missing object without exact boundaries is left unboxed instead of assigning guessed geometry.

No dataset can eliminate overfitting or underfitting by itself. Check learning curves, per-class errors, source-scene generalization, and performance on new independent scenes.

