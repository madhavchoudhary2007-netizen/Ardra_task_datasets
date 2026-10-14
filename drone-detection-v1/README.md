# Drone detection dataset v1

Four-class COCO object detection dataset: `marker_flag` (0), `instrument_box` (1), `hammer` (2), and `short_tripod` (3).

## What is included

- 3,360 clean canonical images and 20,885 distinct augmented images: 24,245 unique image files total.
- Train, validation, and test partitions. Every source scene and its variants stay in one partition (1,898 source groups).
- COCO `instances.json` annotations for each image split in the metadata release asset.
- `metadata/image_index.csv`: one row per image file, SHA-256, parent source, split, and class membership.
- `by_class/*.csv`: class and split views referencing those image paths. A multi-class image may appear in several CSVs, but its binary exists only once.

Download all assets from the [drone-detection-v1 release](https://github.com/madhavchoudhary2007-netizen/Ardra_task_datasets/releases/tag/drone-detection-v1.0-20261014). Extract every ZIP into the **same** empty directory. Each archive contains paths under `drone_dataset_final/`. Run `python3 scripts/verify_release.py /path/to/extraction/drone_dataset_final` from this directory to check all 24,245 image hashes and split separation.

The archived images include original clean images and their distinct augmented variants. The dataset intentionally omits redundant training materializations, QA backup images, and old combined packages. The class CSVs are indexes, not copies of images.

## Training and evaluation

Use `canonical/train` and `augmented/train` to train. Prefer `canonical/val_original` for model selection and keep `canonical/test_original` untouched for final assessment. The augmented validation/test sets are useful robustness checks, but are not independent scenes. Avoid interpreting their larger image counts as more independent validation or test evidence. See [TRAINING_GUIDE.md](TRAINING_GUIDE.md).

No data split or augmentation policy can guarantee the absence of overfitting or underfitting. The classes are imbalanced, and verified target-free scenes are limited. Current source QA records 3,210 fully verified annotations, 13,789 requiring further adjudication, 39 confirmed corrections, one pending fix, and 73 missing-instance exceptions. Confirmed missing objects without defensible exact boundaries are recorded as exceptions, not guessed training boxes. This is the best available frozen version, not an assertion that every label is perfect.

## Layout

`canonical/{train,val_original,test_original}/images` contains clean images. `augmented/{train,val_drone,test_drone}/images` contains variants. Matching `annotations/instances.json` files in the metadata asset are COCO format. `metadata/split_manifest.csv` and `metadata/validation_report.json` describe the source-group split checks.

