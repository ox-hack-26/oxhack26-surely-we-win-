"""Download the four eye-scan datasets from Hugging Face into RAW_DIR/<source>/.

Stdlib only. Re-running skips finished files and resumes partial ones, so it is
safe to stop and start on flaky wifi.

    python scripts/download_data.py              # all four, smallest first
    python scripts/download_data.py aptos idrid  # just these
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clinicdrift.config import RAW_DIR  # noqa: E402

# Smallest first, so the deployment clinics are ready while EyePACS (training) is still coming.
SOURCES = {
    "idrid": "amin-nejad/idrid-disease-grading",
    "aptos": "bumbledeep/aptos",
    "messidor2": "sngsfydy/Messidor2",
    "eyepacs": "bumbledeep/eyepacs",
}
TREE_URL = "https://huggingface.co/api/datasets/{repo}/tree/main?recursive=true"
FILE_URL = "https://huggingface.co/datasets/{repo}/resolve/main/{path}"
CHUNK = 1 << 20
RETRIES = 10  # each retry resumes, so flaky wifi still makes progress


def list_files(repo: str) -> list[dict]:
    with urllib.request.urlopen(TREE_URL.format(repo=repo), timeout=60) as resp:
        return [f for f in json.load(resp) if f["type"] == "file"]


def fetch(url: str, dest: Path, size: int) -> None:
    """Download url to dest, resuming from whatever part is already on disk."""
    have = dest.stat().st_size if dest.exists() else 0
    if have > size:
        dest.unlink()
        have = 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
        with open(dest, "ab" if have else "wb") as out:
            if have and resp.status != 206:  # server ignored the range: start over
                out.truncate(0)
                have = 0
            start, done, next_report = time.time(), have, have + 100 * CHUNK
            while chunk := resp.read(CHUNK):
                out.write(chunk)
                done += len(chunk)
                if done >= next_report:
                    rate = (done - have) / max(time.time() - start, 1e-6) / 1e6
                    print(f"    {done / 1e6:,.0f} / {size / 1e6:,.0f} MB  ({rate:.1f} MB/s)", flush=True)
                    next_report += 100 * CHUNK
    if done != size:  # the server closed the connection early; the retry resumes from here
        raise ConnectionError(f"connection closed at {done / 1e6:,.0f} of {size / 1e6:,.0f} MB")


def download(name: str, repo: str) -> None:
    files = list_files(repo)
    total = sum(f.get("size", 0) for f in files)
    print(f"== {name} ({repo}): {len(files)} files, {total / 1e6:,.0f} MB", flush=True)
    for f in files:
        dest = RAW_DIR / name / f["path"]
        size = f.get("size", 0)
        if dest.exists() and dest.stat().st_size == size:
            print(f"  ok   {f['path']}", flush=True)
            continue
        print(f"  get  {f['path']} ({size / 1e6:,.1f} MB)", flush=True)
        for attempt in range(1, RETRIES + 1):
            try:
                fetch(FILE_URL.format(repo=repo, path=f["path"]), dest, size)
                break
            except OSError as err:  # covers URLError, timeouts, dropped connections
                print(f"    attempt {attempt} failed: {err}", flush=True)
                if attempt == RETRIES:
                    raise
                time.sleep(5 * attempt)
        if dest.stat().st_size != size:
            raise RuntimeError(f"{dest} is {dest.stat().st_size} bytes, expected {size}")
    print(f"== {name} done", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", help=f"any of {', '.join(SOURCES)} (default: all, smallest first)")
    names = parser.parse_args().sources or list(SOURCES)
    if unknown := [n for n in names if n not in SOURCES]:
        parser.error(f"unknown source(s): {', '.join(unknown)}")
    print(f"Saving to {RAW_DIR}", flush=True)
    for name in names:
        download(name, SOURCES[name])
    print("All downloads finished.", flush=True)


if __name__ == "__main__":
    main()
