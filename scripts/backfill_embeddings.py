#!/usr/bin/env python3
"""
Backfill semantic embeddings for all existing Open Brain thoughts.

Run once after installing sentence-transformers, or after importing
thoughts from another source (Mac Mini migration, bulk import, etc.).

Usage:
    cd /path/to/Johnny
    python scripts/backfill_embeddings.py

Takes ~30 seconds for 56 thoughts on a laptop CPU.
On Mac Mini M-series: ~5 seconds.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.thoughts import _load as load_thoughts
from agents.embeddings import _load_embeddings, embed_and_store, _get_model


def main():
    print("Loading embedding model (downloads ~80 MB on first run)...")
    model = _get_model()
    if model is None:
        print("ERROR: sentence-transformers not installed.")
        print("Run: pip install sentence-transformers")
        sys.exit(1)
    print("Model loaded.")

    thoughts = load_thoughts()
    if not thoughts:
        print("No thoughts found in storage/thoughts/thoughts.json")
        sys.exit(0)

    existing = _load_embeddings()
    to_embed = [t for t in thoughts if t["id"] not in existing]

    if not to_embed:
        print(f"All {len(thoughts)} thoughts already have embeddings. Nothing to do.")
        return

    print(f"Found {len(thoughts)} thoughts, {len(to_embed)} need embeddings.")
    print()

    success = 0
    for i, t in enumerate(to_embed, 1):
        ok = embed_and_store(t["id"], t["thought"])
        status = "OK" if ok else "SKIP"
        print(f"  [{i:3d}/{len(to_embed)}] {status}  {t['id']}  {t['thought'][:70]}...")
        if ok:
            success += 1

    print()
    print(f"Done. {success}/{len(to_embed)} thoughts embedded.")
    print(f"Total embeddings stored: {len(_load_embeddings())}")


if __name__ == "__main__":
    main()
