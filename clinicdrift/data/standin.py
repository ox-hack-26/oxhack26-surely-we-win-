"""Stand-in referral model so the engine can run before Sarah's model lands.

A frozen ImageNet ResNet-50 turns each retina into 2048 numbers; a logistic regression trained
on EyePACS 'train' scans turns those into p_referable. It also measures image quality. Output
matches docs/handoffs.md, under processed/standin/:

    scans.parquet   the scans it scored, with the scans.parquet columns
    features.npy    float16 image features, same row order
    model.json      referral_threshold and validation scores

Scores only what the engine needs: every scan the replay uses (worn-camera copies included),
all of EyePACS 'val', and a sample of EyePACS 'train'. Runs on the GPU when there is one.
Re-running only embeds scans it hasn't seen, so a new replay clinic costs seconds.

    python -m clinicdrift.data.standin           # embed any new scans, then fit
    python -m clinicdrift.data.standin --refit   # fit again from saved features
"""
import argparse
import io
import json
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from PIL import Image
from scipy import ndimage

from clinicdrift.config import PROCESSED_DIR
from clinicdrift.data.degrade import degrade, split_id
from clinicdrift.data.sources import load_scans

OUT_DIR = PROCESSED_DIR / "standin"
SEED = 2026
TRAIN_SAMPLE = 8000
TARGET_SENSITIVITY = 0.90  # see docs/handoffs.md: pick the threshold that catches 90% on val
THUMB = 512                # quality is measured at this size so every camera is judged alike
SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]


def preprocess(item: tuple[bytes, float]) -> tuple[np.ndarray, dict]:
    """Apply any camera wear, crop to the retina, measure quality, and return a normalised 224x224 array."""
    blob, wear = item
    img = Image.open(io.BytesIO(blob))
    width, height = img.size
    img.draft("RGB", (THUMB, THUMB))  # JPEGs decode straight at reduced size
    img = degrade(img.convert("RGB"), wear)
    scale = THUMB / max(img.size)  # up or down, so a low-resolution camera reads as blurry
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.BILINEAR)
    rgb = np.asarray(img, dtype=np.float32) / 255
    gray = rgb.mean(axis=2)

    mask = gray > 0.04  # the retina, as opposed to the black border
    ys, xs = np.nonzero(mask)
    if len(xs) > 1000:
        rgb, gray, mask = (a[ys.min():ys.max() + 1, xs.min():xs.max() + 1] for a in (rgb, gray, mask))
    inner = ndimage.binary_erosion(mask, iterations=6)  # keep the rim out of the sharpness measure
    retina = gray[mask] if mask.any() else gray.ravel()
    stats = {
        "width": width,
        "height": height,
        "brightness": float(retina.mean()),
        "contrast": float(retina.std()),
        "sharpness": float(ndimage.laplace(gray)[inner].var()) if inner.any() else 0.0,
    }

    side = max(rgb.shape[:2])  # pad to a square so the retina keeps its shape
    square = np.zeros((side, side, 3), dtype=np.float32)
    y0, x0 = (side - rgb.shape[0]) // 2, (side - rgb.shape[1]) // 2
    square[y0:y0 + rgb.shape[0], x0:x0 + rgb.shape[1]] = rgb
    small = Image.fromarray((square * 255).astype(np.uint8)).resize((SIZE, SIZE), Image.BILINEAR)
    arr = (np.asarray(small, dtype=np.float32).transpose(2, 0, 1) / 255 - MEAN) / STD
    return arr.astype(np.float16), stats


def pick_scans() -> pd.DataFrame:
    """Every scan to score, one row each; worn-camera copies point at their original's file and row."""
    scans = load_scans()
    train = scans[(scans["source"] == "eyepacs") & (scans["split"] == "train")]
    plain = set(scans.loc[(scans["source"] == "eyepacs") & (scans["split"] == "val"), "scan_id"])
    plain |= set(train.sample(TRAIN_SAMPLE, random_state=SEED)["scan_id"])
    wanted = pd.DataFrame({"scan_id": sorted(plain)})
    stream_ids = pd.read_parquet(PROCESSED_DIR / "stream.parquet", columns=["scan_id"])["scan_id"]
    wanted = pd.concat([wanted, stream_ids.to_frame()]).drop_duplicates("scan_id", ignore_index=True)

    split = wanted["scan_id"].map(split_id)
    wanted["base_id"] = [base for base, _ in split]
    wanted["wear"] = [wear for _, wear in split]
    picked = wanted.merge(scans.rename(columns={"scan_id": "base_id"}), on="base_id", validate="many_to_one")
    return picked.drop(columns="base_id")


def iter_blobs(picked: pd.DataFrame):
    """(row index in picked, (image bytes, wear)), one parquet row group at a time to keep memory low."""
    for path, rows in picked.groupby("file"):
        pf = pq.ParquetFile(path)
        wanted: dict[int, list[int]] = {}
        for row_in_file, index in zip(rows["row_in_file"], rows.index):
            wanted.setdefault(row_in_file, []).append(index)
        start = 0
        for group in range(pf.num_row_groups):
            n = pf.metadata.row_group(group).num_rows
            hits = [r for r in range(start, start + n) if r in wanted]
            if hits:
                images = pf.read_row_group(group, columns=["image"]).column("image")
                yield [(index, (images[r - start].as_py()["bytes"], picked.at[index, "wear"]))
                       for r in hits for index in wanted[r]]
            start += n


def embed(picked: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    import torch
    from torchvision.models import ResNet50_Weights, resnet50

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)
    model.fc = torch.nn.Identity()
    model = model.eval().to(device)
    print(f"Embedding {len(picked):,} scans on {device}", flush=True)

    features = np.zeros((len(picked), 2048), dtype=np.float16)
    stats = [None] * len(picked)
    done, started = 0, time.time()
    with Pool(6) as pool, torch.inference_mode():
        for batch in iter_blobs(picked):
            index, blobs = zip(*batch)
            results = pool.map(preprocess, blobs, chunksize=4)
            x = torch.from_numpy(np.stack([arr for arr, _ in results])).to(device)
            with torch.autocast(device, enabled=device == "cuda"):
                out = model(x.float()).float().cpu().numpy()
            features[list(index)] = out.astype(np.float16)
            for i, (_, s) in zip(index, results):
                stats[i] = s
            done += len(batch)
            if done % 1000 < len(batch):
                rate = done / (time.time() - started)
                print(f"  {done:,}/{len(picked):,}  ({rate:.0f} scans/s)", flush=True)
    return features, pd.DataFrame(stats)


def fit(scored: pd.DataFrame, features: np.ndarray) -> tuple[pd.DataFrame, dict]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    x = features.astype(np.float32)
    train = (scored["split"] == "train").to_numpy()
    val = (scored["split"] == "val").to_numpy()
    y = scored["referable"].to_numpy()

    best = None
    for c in (0.003, 0.01, 0.03, 0.1):
        clf = make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=3000))
        clf.fit(x[train], y[train])
        auc = roc_auc_score(y[val], clf.predict_proba(x[val])[:, 1])
        print(f"  C={c}: val AUC {auc:.3f}", flush=True)
        if best is None or auc > best[0]:
            best = (auc, c, clf)
    auc, c, clf = best

    scored = scored.copy()
    scored["p_referable"] = clf.predict_proba(x)[:, 1]
    p_val, y_val = scored.loc[val, "p_referable"].to_numpy(), y[val]
    threshold = float(np.quantile(p_val[y_val], 1 - TARGET_SENSITIVITY))
    refer = p_val >= threshold
    model_info = {
        "model": "stand-in: ImageNet ResNet-50 features + logistic regression",
        "C": c,
        "referral_threshold": threshold,
        "val_auc": float(auc),
        "val_sensitivity": float(refer[y_val].mean()),
        "val_specificity": float((~refer[~y_val]).mean()),
    }

    # Crude quality: how a scan's sharpness and contrast rank against the training scans.
    ref = scored[train]
    for col in ("sharpness", "contrast"):
        scored[f"_{col}_rank"] = np.searchsorted(np.sort(ref[col]), scored[col]) / len(ref)
    scored["quality"] = (scored["_sharpness_rank"] + scored["_contrast_rank"]) / 2
    scored = scored.drop(columns=["_sharpness_rank", "_contrast_rank"])
    return scored, model_info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refit", action="store_true", help="skip embedding; fit from saved features")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    measured = ["scan_id", "source", "split", "grade", "referable", "wear",
                "brightness", "contrast", "sharpness", "width", "height"]
    have = OUT_DIR / "scans.parquet"
    scored = pd.read_parquet(have) if have.exists() else pd.DataFrame(columns=measured)
    features = np.load(OUT_DIR / "features.npy") if have.exists() else np.zeros((0, 2048), np.float16)
    if "wear" not in scored:  # files from before camera wear existed
        scored["wear"] = 0.0
    scored = scored[measured]

    if not args.refit:
        picked = pick_scans()
        new = picked[~picked["scan_id"].isin(scored["scan_id"])].reset_index(drop=True)
        if len(new):
            new_features, stats = embed(new)
            scored = pd.concat([scored, pd.concat([new, stats], axis=1)[measured]], ignore_index=True)
            features = np.vstack([features, new_features])
            np.save(OUT_DIR / "features.npy", features)
        else:
            print("No new scans to embed", flush=True)

    scored, model_info = fit(scored, features)
    columns = measured[:5] + ["p_referable", "quality"] + measured[5:]
    scored[columns].to_parquet(OUT_DIR / "scans.parquet", index=False)
    (OUT_DIR / "model.json").write_text(json.dumps(model_info, indent=2), encoding="utf-8")
    print(json.dumps(model_info, indent=2))


if __name__ == "__main__":
    main()
