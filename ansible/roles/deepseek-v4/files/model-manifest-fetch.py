#!/usr/bin/env python3
"""Fetch an immutable Hugging Face LFS manifest for a pinned model commit."""

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    repository = urllib.parse.quote(args.repository, safe="/")
    url = f"https://huggingface.co/api/models/{repository}?blobs=true"
    with urllib.request.urlopen(url, timeout=60) as response:
        document = json.load(response)

    if document.get("sha") != args.revision:
        raise SystemExit(
            "Hugging Face API revision mismatch: "
            f"expected {args.revision}, received {document.get('sha')}"
        )

    files = []
    for sibling in document.get("siblings", []):
        lfs = sibling.get("lfs") or {}
        if lfs.get("sha256") and lfs.get("size"):
            files.append(
                {
                    "path": sibling["rfilename"],
                    "size": lfs["size"],
                    "sha256": lfs["sha256"],
                    "source": "huggingface-lfs",
                }
            )
        elif sibling.get("rfilename") == "model.safetensors.index.json":
            files.append(
                {
                    "path": sibling["rfilename"],
                    "size": sibling["size"],
                    "source": "huggingface-git-revision",
                }
            )

    if not files:
        raise SystemExit("No LFS artifacts were returned by the pinned repository")
    if not any(item["path"] == "model.safetensors.index.json" for item in files):
        raise SystemExit("Pinned repository did not return model.safetensors.index.json")

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(files, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
