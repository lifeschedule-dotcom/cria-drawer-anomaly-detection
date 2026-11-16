"""Export the trusted, locally trained forest and raw episode for browser inference."""
import json
from pathlib import Path
import sys

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT
WEB = ROOT / "web"
sys.path.insert(0, str(PROJECT))

from train import CHANNELS, STRIDE, VALID, WINDOW_FRAMES, WRENCH, load_annotations, read_episode


def export_script(path, name, value):
    body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    path.write_text(f"const {name} = {body};\n", encoding="utf-8")


episode = next(row for row in load_annotations() if row["episode_index"] == 149)
table = read_episode(episode)
frames = []
for index, timestamp, count, chunk in zip(
    table["frame_index"], table["timestamp"], table[VALID], table[WRENCH].to_list()
):
    samples = np.asarray(chunk[:count], dtype=np.float32).ravel().tolist()
    frames.append([index, timestamp, count, *samples])

forest = joblib.load(PROJECT / "results/random_forest.joblib")
positive = list(forest.classes_).index(1)
comparison = json.loads((PROJECT / "results/model_comparison.json").read_text(encoding="utf-8"))
threshold = comparison["models"]["random_forest"]["threshold"]
trees = []
for estimator in forest.estimators_:
    tree = estimator.tree_
    nodes = []
    for node, feature in enumerate(tree.feature):
        if feature < 0:
            values = tree.value[node, 0]
            nodes.append([-1, float(values[positive] / values.sum())])
        else:
            nodes.append([
                int(feature), float(tree.threshold[node]),
                int(tree.children_left[node]), int(tree.children_right[node]),
            ])
    trees.append(nodes)

export_script(WEB / "live-model.js", "rollingForest", {
    "trees": trees, "threshold": threshold, "windowFrames": WINDOW_FRAMES, "stride": STRIDE,
})
export_script(WEB / "live-sensor.js", "liveInput", {"axes": CHANNELS, "frames": frames})
