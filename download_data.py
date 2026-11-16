"""Download the pinned CRIA drawer subset into the local data directory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.request import urlopen


REPO = "Joringell/CRIA"
REVISION = "af288f2a470189c3991db73873f9d64171620a43"
SUBSET = "articulated/pull_drawer"
FOLDERS = ("data/chunk-000", "meta", "videos/wrist/chunk-000")
DEMO_IDS = (8, 17, 149)


def read_url(url):
    for retry in range(3):
        try:
            with urlopen(url, timeout=45) as response:
                return response.read()
        except OSError:
            if retry == 2:
                raise


def fetch_data(destination, demo_only):
    tree_url = f"https://huggingface.co/api/datasets/{REPO}/tree/{REVISION}/{SUBSET}"
    file_url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{SUBSET}"
    demo_stems = {f"episode_{index:06}" for index in DEMO_IDS}
    files = {}
    for folder in FOLDERS:
        for entry in json.loads(read_url(f"{tree_url}/{folder}")):
            if entry["type"] != "file":
                continue
            path = entry["path"].removeprefix(f"{SUBSET}/")
            download_all = folder == "meta" or (folder.startswith("data/") and not demo_only)
            if download_all or Path(path).stem in demo_stems:
                files[path] = entry["size"]

    def save(item):
        path, size = item
        local = destination / path
        if local.exists() and local.stat().st_size == size:
            return
        contents = read_url(f"{file_url}/{path}")
        if len(contents) != size:
            raise ValueError(f"{path}: expected {size} bytes, received {len(contents)}")
        local.parent.mkdir(parents=True, exist_ok=True)
        partial = local.with_name(local.name + ".part")
        partial.write_bytes(contents)
        partial.replace(local)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for index, _ in enumerate(pool.map(save, files.items()), 1):
            if index % 30 == 0 or index == len(files):
                print(f"{index}/{len(files)} files ready", flush=True)
    metadata = {
        "repo": REPO, "revision": REVISION, "subset": SUBSET,
        "license": "CC BY 4.0", "files": files,
    }
    (destination / "source.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-only", action="store_true", help="Get only episodes 8, 17, 149.")
    args = parser.parse_args()
    fetch_data(Path(__file__).resolve().parent / "data", args.demo_only)
