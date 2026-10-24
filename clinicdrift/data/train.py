"""Fine-tune the referral classifier on the EyePACS training scans; keep the epoch with the best val AUC.

    python -m clinicdrift.data.train            # ~15 min on an RTX 5090 laptop
    python -m clinicdrift.data.train --epochs 1 # quick check that everything runs

Needs processed/scans.parquet and the crop cache from `python -m clinicdrift.data.prepare`.
Writes models/referral.pt and models/train_log.csv under CLINICDRIFT_DATA.
"""
import argparse
import csv
import math
import time

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score

from clinicdrift.data.model import ARCH, MODEL_FILE, Crops, build_model, loader, predict, to_input
from clinicdrift.data.prepare import SCANS
from clinicdrift.data.sources import TRAINING_SOURCE

SEED = 2026
EPOCHS = 10
LR = 1.5e-4
WEIGHT_DECAY = 0.05
WARMUP_STEPS = 300
GRADE_WEIGHT = 0.5  # weight of the auxiliary grade regression in the loss


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    args = parser.parse_args()
    torch.manual_seed(SEED)
    torch.backends.cudnn.benchmark = True

    scans = pd.read_parquet(SCANS, columns=["source", "split", "grade", "referable"])
    eyepacs = scans["source"] == TRAINING_SOURCE
    train = np.flatnonzero(eyepacs & (scans["split"] == "train"))
    val = np.flatnonzero(eyepacs & (scans["split"] == "val"))
    referable = scans["referable"].to_numpy(np.float32)
    grade = scans["grade"].to_numpy(np.float32)
    print(f"train {len(train):,} scans ({referable[train].mean():.1%} referable), val {len(val):,}")

    data = loader(Crops(len(scans), train, referable[train], grade[train]), shuffle=True)
    model = build_model(pretrained=True).cuda().to(memory_format=torch.channels_last)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    total = args.epochs * len(data)
    schedule = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda step: min(
        (step + 1) / WARMUP_STEPS, 0.5 * (1 + math.cos(math.pi * min(step, total) / total))))

    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_path = MODEL_FILE.parent / "train_log.csv"
    with open(log_path, "w", newline="") as f:
        csv.writer(f).writerow(["epoch", "train_loss", "val_auc", "seconds"])
    best_auc = -1.0
    for epoch in range(1, args.epochs + 1):
        model.train()
        start, losses = time.time(), []
        for step, (crops, y, g) in enumerate(data, 1):
            x = to_input(crops.cuda(non_blocking=True), model, augment=True)
            y, g = y.cuda(non_blocking=True), g.cuda(non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out = model(x).float()
            loss = F.binary_cross_entropy_with_logits(out[:, 0], y) + GRADE_WEIGHT * F.smooth_l1_loss(out[:, 1], g)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            schedule.step()
            losses.append(loss.item())
            if step % 100 == 0:
                print(f"  epoch {epoch} step {step}/{len(data)} loss {np.mean(losses[-100:]):.4f} "
                      f"({step * data.batch_size / (time.time() - start):.0f} scans/s)", flush=True)

        model.eval()
        auc = roc_auc_score(referable[val], predict(model, len(scans), val))
        seconds = time.time() - start
        print(f"epoch {epoch}: train loss {np.mean(losses):.4f}, val AUC {auc:.4f}, {seconds:.0f} s", flush=True)
        with open(log_path, "a", newline="") as f:
            csv.writer(f).writerow([epoch, round(float(np.mean(losses)), 5), round(auc, 5), round(seconds)])
        if auc > best_auc:
            best_auc = auc
            torch.save({"state_dict": model.state_dict(), "arch": ARCH, "epoch": epoch, "val_auc": auc,
                        "n_train": len(train), "epochs": args.epochs}, MODEL_FILE)
    print(f"Best val AUC {best_auc:.4f}; saved {MODEL_FILE}")


if __name__ == "__main__":
    main()
