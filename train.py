"""Train and evaluate three anomaly detectors on the same CRIA drawer recordings."""
from pathlib import Path
import argparse
import csv
import json
import random

import joblib
import numpy as np
import polars as pl
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_recall_curve, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "results"
SEED = 42
WINDOW_FRAMES = 30
STRIDE = 5
WRENCH = "observation.state.wrench_raw_chunk"
VALID = "observation.state.wrench_chunk_valid_len"
CHANNELS = ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")
DEMO_IDS = (149, 8, 17)


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_annotations():
    source = DATA / "meta" / "annotation.json"
    return list(json.loads(source.read_text(encoding="utf-8"))["episodes"].values())


def split_episodes(episodes):
    strata = np.array([
        (e["source"], bool(e["anomaly"]["manual"]["ranges"])) for e in episodes
    ], dtype=str)
    ids = np.arange(len(episodes))
    fit, test = train_test_split(ids, test_size=.2, random_state=SEED, stratify=strata)
    train, valid = train_test_split(fit, test_size=.25, random_state=SEED, stratify=strata[fit])
    return {
        name: [episodes[i]["episode_index"] for i in split]
        for name, split in [("train", train), ("validation", valid), ("test", test)]
    }


def read_episode(episode):
    return pl.read_parquet(DATA / episode["parquet_path"], columns=[
        "frame_index", "timestamp", "frame_label", "episode_label", WRENCH, VALID,
    ])


def make_windows(episode):
    table = read_episode(episode)
    wrench = np.asarray(table[WRENCH].to_list(), dtype=np.float32)
    valid = table[VALID].to_numpy()
    labels = (table["frame_label"].to_numpy() == 0).astype(np.int64)
    indices = np.array([
        end - 1 for end in range(WINDOW_FRAMES, len(table) + 1, STRIDE)
        if np.all(valid[end - WINDOW_FRAMES:end] == 4)
    ], dtype=np.int64)
    if len(indices):
        windows = np.stack([
            wrench[i + 1 - WINDOW_FRAMES:i + 1].reshape(-1, 6) for i in indices
        ])
    else:
        windows = np.empty((0, WINDOW_FRAMES * 4, 6), dtype=np.float32)
    return windows, labels[indices], table["frame_index"].to_numpy()[indices], table["timestamp"].to_numpy()[indices]


def summarize_windows(windows):
    return np.hstack([
        windows.mean(axis=1),
        windows.std(axis=1),
        np.abs(windows).max(axis=1),
        windows[:, -4:].mean(axis=1) - windows[:, :4].mean(axis=1),
    ])


def combine(episodes_by_id, ids):
    rows = [episodes_by_id[i] for i in ids]
    return tuple(np.concatenate(columns) for columns in zip(*rows))


class WrenchLSTM(nn.Module):
    def __init__(self, hidden_size=32):
        super().__init__()
        self.lstm = nn.LSTM(input_size=6, hidden_size=hidden_size, batch_first=True)
        self.output = nn.Linear(hidden_size, 1)

    def forward(self, windows):
        _, (hidden, _) = self.lstm(windows)
        return self.output(hidden[-1]).squeeze(-1)


@torch.inference_mode()
def lstm_scores(model, windows, mean, scale, device):
    model.eval()
    normalized = torch.from_numpy((windows - mean) / scale)
    return np.concatenate([
        torch.sigmoid(model(batch.to(device))).cpu().numpy()
        for batch in normalized.split(256)
    ])


def train_lstm(train, labels, validation, val_labels, device, max_epochs):
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if device.type == "cuda":
        torch.backends.cudnn.allow_tf32 = False
    else:
        torch.set_num_threads(min(torch.get_num_threads(), 4))

    mean = train.mean(axis=(0, 1))
    scale = train.std(axis=(0, 1)).clip(min=1e-6)
    x = torch.from_numpy((train - mean) / scale)
    y = torch.from_numpy(labels.astype(np.float32))
    batches = DataLoader(TensorDataset(x, y), batch_size=128, shuffle=True,
                         generator=torch.Generator().manual_seed(SEED))

    model = WrenchLSTM().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=.001)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(
        (len(labels) - labels.sum()) / labels.sum(), device=device, dtype=torch.float32
    ))

    best_ap = -1.0
    best_state = None
    history = []
    for epoch in range(1, max_epochs + 1):
        model.train()
        loss_sum = 0.0
        for windows, targets in batches:
            windows, targets = windows.to(device), targets.to(device)
            optimizer.zero_grad()
            loss = loss_fn(model(windows), targets)
            loss.backward()
            optimizer.step()
            loss_sum += loss.item() * len(targets)
        scores = lstm_scores(model, validation, mean, scale, device)
        ap = float(average_precision_score(val_labels, scores))
        history.append({"epoch": epoch, "train_loss": loss_sum / len(labels), "validation_ap": ap})
        print(f"LSTM epoch {epoch:02d}: loss={history[-1]['train_loss']:.4f} validation AP={ap:.4f}", flush=True)
        if ap > best_ap:
            best_ap = ap
            best_epoch = epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        if epoch - best_epoch >= 6:
            break
    model.load_state_dict(best_state)
    return model, mean, scale, history, best_epoch


def choose_threshold(labels, scores):
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    total = precision[:-1] + recall[:-1]
    f1 = np.divide(2 * precision[:-1] * recall[:-1], total, out=np.zeros_like(total), where=total > 0)
    return float(thresholds[f1.argmax()])


def evaluate(labels, scores, threshold):
    pred = scores >= threshold
    return {
        "ap": float(average_precision_score(labels, scores)),
        "precision": float(precision_score(labels, pred, zero_division=0)),
        "recall": float(recall_score(labels, pred, zero_division=0)),
        "f1": float(f1_score(labels, pred, zero_division=0)),
    }


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(fields)
        writer.writerows(rows)


def main(max_epochs):
    OUT.mkdir(exist_ok=True)
    episodes = load_annotations()
    split = split_episodes(episodes)
    assert len({i for ids in split.values() for i in ids}) == len(episodes) == 150
    assert set(DEMO_IDS) <= set(split["test"])
    save_json(OUT / "split.json", {"seed": SEED, **split})
    loaded = {e["episode_index"]: make_windows(e) for e in episodes}
    train_x, train_y, _, _ = combine(loaded, split["train"])
    val_x, val_y, _, _ = combine(loaded, split["validation"])
    test_x, test_y, _, _ = combine(loaded, split["test"])
    print("Windows:", len(train_y), len(val_y), len(test_y), flush=True)

    classic = {
        "logistic_regression": make_pipeline(
            StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000, random_state=SEED)
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=100, class_weight="balanced_subsample", n_jobs=4, random_state=SEED
        ),
    }
    for name, model in classic.items():
        model.fit(summarize_windows(train_x), train_y)
        joblib.dump(model, OUT / f"{name}.joblib")
        print("Trained", name, flush=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("LSTM device:", torch.cuda.get_device_name() if device.type == "cuda" else "CPU", flush=True)
    lstm, mean, scale, history, best = train_lstm(train_x, train_y, val_x, val_y, device, max_epochs)
    torch.save({
        "state_dict": {key: value.cpu() for key, value in lstm.state_dict().items()},
        "mean": torch.from_numpy(mean), "scale": torch.from_numpy(scale), "hidden_size": 32,
        "window_frames": WINDOW_FRAMES, "stride": STRIDE,
    }, OUT / "lstm.pt")
    write_csv(OUT / "lstm_history.csv", ("epoch", "train_loss", "validation_ap"),
              [(r["epoch"], r["train_loss"], r["validation_ap"]) for r in history])

    def all_scores(windows):
        features = summarize_windows(windows)
        scores = {name: m.predict_proba(features)[:, 1] for name, m in classic.items()}
        scores["lstm"] = lstm_scores(lstm, windows, mean, scale, device)
        return scores

    validation_scores = all_scores(val_x)
    test_scores = all_scores(test_x)
    metrics, thresholds = {}, {}
    for name, scores in validation_scores.items():
        threshold = choose_threshold(val_y, scores)
        thresholds[name] = threshold
        metrics[name] = {"threshold": threshold, "validation": evaluate(val_y, scores, threshold),
                         "test": evaluate(test_y, test_scores[name], threshold)}
    selected = max(metrics, key=lambda name: metrics[name]["validation"]["ap"])
    report = {
        "selected_by_validation_ap": selected,
        "window_frames_at_30hz": WINDOW_FRAMES, "window_force_samples_at_120hz": WINDOW_FRAMES * 4,
        "stride_frames": STRIDE, "seed": SEED, "device": device.type,
        "best_lstm_epoch": best, "windows": {"train": len(train_y), "validation": len(val_y), "test": len(test_y)},
        "positive_rate": {"validation": float(val_y.mean()), "test": float(test_y.mean())},
        "models": metrics,
    }
    save_json(OUT / "model_comparison.json", report)
    write_csv(OUT / "model_comparison.csv",
              ("model", "threshold", "validation_ap", "test_ap", "test_precision", "test_recall", "test_f1"),
              [(name, row["threshold"], row["validation"]["ap"], *row["test"].values()) for name, row in metrics.items()])

    for episode_id in DEMO_IDS:
        windows, labels, frames, times = loaded[episode_id]
        scores = all_scores(windows)
        columns = ["episode_id", "frame_index", "time_s", "actual_anomaly"]
        for name in scores:
            columns.extend([f"{name}_score", f"{name}_flag"])
        write_csv(OUT / f"episode_{episode_id:06}_scores.csv", columns, [
            [episode_id, int(frames[i]), float(times[i]), int(labels[i]), *[
                value for name, values in scores.items()
                for value in (float(values[i]), int(values[i] >= thresholds[name]))
            ]] for i in range(len(times))
        ])
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=24)
    main(parser.parse_args().epochs)
