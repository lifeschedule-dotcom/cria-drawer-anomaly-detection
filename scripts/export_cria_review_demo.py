"""Export the notebook's episode 149 results for the offline browser demo."""
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT
DESTINATION = ROOT / "web"
sys.path.insert(0, str(PROJECT))

from safety_report import SITE_SCENARIOS, prepare_site_review, read_detection, render_site_review
from train import CHANNELS, VALID, WRENCH, load_annotations, read_episode

episode = next(item for item in load_annotations() if item["episode_index"] == 149)
evidence = read_detection(149, "random_forest")
sensor = read_episode(episode)
waveform = []
for timestamp, chunk, count in zip(sensor["timestamp"], sensor[WRENCH], sensor[VALID]):
    averages = np.asarray(chunk[:count]).mean(axis=0).round(4).tolist() if count else [None] * 6
    waveform.append([round(timestamp, 4), *averages])

with (PROJECT / "results/episode_000149_scores.csv").open(encoding="utf-8", newline="") as stream:
    scores = [[round(float(row["time_s"]), 4), float(row["random_forest_score"]),
               int(row["random_forest_flag"])] for row in csv.DictReader(stream)]

cases = {}
for key in SITE_SCENARIOS:
    review = prepare_site_review(evidence, key)
    cases[key] = {**review, "report": render_site_review(review)}

data = dict(
    manual=evidence["manual_times_s"], alerts=evidence["flagged_times_s"],
    threshold=evidence["threshold"], scores=scores, waveform=waveform, axes=CHANNELS,
    cases=cases,
)
DESTINATION.mkdir(parents=True, exist_ok=True)
(DESTINATION / "episode.js").write_text(
    "const episode = " + json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + ";\n",
    encoding="utf-8",
)
