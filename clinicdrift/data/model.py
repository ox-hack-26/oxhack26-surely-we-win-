"""The referral classifier: an ImageNet-pretrained ConvNeXt fine-tuned on EyePACS crops.

It has two outputs: a logit for "needs referral" (grade >= 2), which becomes p_referable, and a
regression on the 0-4 grade that only helps training. Its pooled features are the image features
the engine uses to tell how different a clinic's scans look from training.
"""
import math
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import timm
import torch
import torch.nn.functional as F

from clinicdrift.config import DATA_DIR
from clinicdrift.data.prepare import open_cache

ARCH = "convnext_tiny.in12k_ft_in1k_384"
MODEL_FILE = DATA_DIR / "models" / "referral.pt"
BATCH = 48
PREFETCH = 4  # batches read ahead while the GPU works


def build_model(pretrained: bool) -> torch.nn.Module:
    return timm.create_model(ARCH, pretrained=pretrained, num_classes=2, drop_path_rate=0.1)


def load_model(device: str = "cuda") -> torch.nn.Module:
    model = build_model(pretrained=False)
    model.load_state_dict(torch.load(MODEL_FILE, map_location="cpu")["state_dict"])
    return model.to(device).eval().to(memory_format=torch.channels_last)


def batches(n_rows: int, rows: np.ndarray, *targets: np.ndarray, shuffle_seed: int | None = None):
    """Batches of (uint8 crops (B, H, W, 3), *targets) for these cache rows, read ahead on threads.

    targets are per cache row (length n_rows), so they are indexed the same way as the cache.

    In order, every row, unless shuffle_seed is given: then shuffled, dropping the last partial batch.
    Threads, not DataLoader worker processes: on Windows each worker takes ~20 s to start, and the
    cache is a memmap the OS already holds in RAM, so reading it is a memcpy.
    """
    cache = open_cache(n_rows)
    if shuffle_seed is None:
        order, stops = np.arange(len(rows)), range(BATCH, len(rows) + BATCH, BATCH)
    else:
        order, stops = np.random.default_rng(shuffle_seed).permutation(len(rows)), range(BATCH, len(rows) + 1, BATCH)

    def load(pick: np.ndarray):
        idx = rows[pick]
        by_file = np.argsort(idx)  # read the memmap front to back
        crops = np.empty((len(idx), *cache.shape[1:]), np.uint8)
        crops[by_file] = cache[idx[by_file]]
        return (torch.from_numpy(crops).pin_memory(), *(torch.from_numpy(t[idx]) for t in targets))

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = deque()
        for stop in stops:
            pending.append(pool.submit(load, order[stop - BATCH:stop]))
            if len(pending) > PREFETCH:
                yield pending.popleft().result()
        while pending:
            yield pending.popleft().result()


def n_batches(n: int, shuffle: bool) -> int:
    return n // BATCH if shuffle else -(-n // BATCH)


def to_input(crops: torch.Tensor, model: torch.nn.Module, augment: bool = False) -> torch.Tensor:
    """uint8 (B, H, W, 3) crops on the GPU -> normalised float (B, 3, H, W), randomly augmented if asked."""
    x = crops.permute(0, 3, 1, 2).float() / 255
    if augment:
        x = _augment(x)
    cfg = model.pretrained_cfg
    mean = torch.tensor(cfg["mean"], device=x.device).view(1, 3, 1, 1)
    std = torch.tensor(cfg["std"], device=x.device).view(1, 3, 1, 1)
    return ((x - mean) / std).contiguous(memory_format=torch.channels_last)


def _augment(x: torch.Tensor) -> torch.Tensor:
    """Random rotation, flip, zoom, shift, brightness and contrast, done on the GPU in one pass."""
    b, device = x.shape[0], x.device
    angle = torch.rand(b, device=device) * 2 * math.pi
    scale = 1 + (torch.rand(b, device=device) * 2 - 1) * 0.1
    flip = torch.where(torch.rand(b, device=device) < 0.5, -1.0, 1.0)
    shift = (torch.rand(b, 2, device=device) * 2 - 1) * 0.05
    cos, sin = torch.cos(angle) / scale, torch.sin(angle) / scale
    theta = torch.stack([torch.stack([cos * flip, -sin, shift[:, 0]], 1),
                         torch.stack([sin * flip, cos, shift[:, 1]], 1)], 1)
    x = F.grid_sample(x, F.affine_grid(theta, list(x.shape), align_corners=False), align_corners=False)
    brightness = 1 + (torch.rand(b, 1, 1, 1, device=device) - 0.5) * 0.3
    contrast = 1 + (torch.rand(b, 1, 1, 1, device=device) - 0.5) * 0.3
    mean = x.mean(dim=(1, 2, 3), keepdim=True)
    return (((x - mean) * contrast + mean) * brightness).clamp(0, 1)


@torch.no_grad()
def predict(model: torch.nn.Module, n_scans: int, rows: np.ndarray, features: bool = False):
    """Referral logits for these cache rows, averaged over the scan and its mirror image.

    With features=True also returns the pooled image features, shape (len(rows), d), float32.
    """
    logits, feats = [], []
    for (crops,) in batches(n_scans, rows):
        x = to_input(crops.cuda(non_blocking=True), model)
        out_logit, out_feat = 0, 0
        for view in (x, x.flip(3)):
            with torch.autocast("cuda", dtype=torch.bfloat16):
                pooled = model.forward_head(model.forward_features(view), pre_logits=True)
                out = model.get_classifier()(pooled)
            out_logit = out_logit + out[:, 0].float() / 2
            out_feat = out_feat + pooled.float() / 2
        logits.append(out_logit.cpu())
        if features:
            feats.append(out_feat.cpu())
    logits = torch.cat(logits).numpy()
    return (logits, torch.cat(feats).numpy().astype(np.float32)) if features else logits
