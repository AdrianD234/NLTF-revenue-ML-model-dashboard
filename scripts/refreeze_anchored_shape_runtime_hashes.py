"""Re-freeze the pinned runtime artifact hashes after the promotion.

The pinned hashes in tests/test_revenue_outlook.py exist so a pack cannot
change silently. Promoting balanced_structural changes the pack deliberately,
so the pins move - but only for files whose change is already justified by the
promotion audit, and every move is recorded old -> new with its cause.

Run AFTER scripts/build_anchored_shape_promotion_audit.py has passed.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEST_FILE = REPO_ROOT / "tests" / "test_revenue_outlook.py"
PACK_DIR = REPO_ROOT / "data" / "current_revenue_outlook"
OUT = REPO_ROOT / "artifacts" / "anchored_structural_shape_transition"

ANCHOR = "def test_current_revenue_outlook_runtime_artifact_hashes_are_frozen"

CAUSE = (
    "balanced_structural promoted as the production long-run transition "
    "schedule; FY2031-FY2050 post-model rows rebuilt"
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    # Read as BYTES and remember the file's own line-ending convention. This
    # repo pins `* -text`, so endings are committed content: a read_text /
    # write_text round-trip silently rewrites every line and turns a 13-line
    # re-freeze into a 5,042-line diff.
    raw = TEST_FILE.read_bytes()
    was_crlf = b"\r\n" in raw
    source = raw.decode("utf-8")
    start = source.index(ANCHOR)
    block_start = source.index("expected_hashes = {", start)
    block_end = source.index("}", block_start)
    block = source[block_start:block_end]

    pinned = dict(re.findall(r"'([^']+)':\s*'([0-9a-f]{64})'", block))
    if not pinned:
        raise SystemExit("no pinned hashes found; refusing to rewrite the test")

    rows: list[dict[str, object]] = []
    updated = dict(pinned)
    for name, old in pinned.items():
        path = PACK_DIR / name
        if not path.exists():
            raise SystemExit(f"pinned artifact missing from the pack: {name}")
        new = sha256_of(path)
        if new != old:
            updated[name] = new
            rows.append(
                {
                    "artifact": name,
                    "old_sha256": old,
                    "new_sha256": new,
                    "cause": CAUSE,
                }
            )

    if not rows:
        print("no pinned hash changed; nothing to re-freeze")
        return 0

    rebuilt = block
    for row in rows:
        rebuilt = rebuilt.replace(
            f"'{row['artifact']}': '{row['old_sha256']}'",
            f"'{row['artifact']}': '{row['new_sha256']}'",
        )
    rewritten = source[:block_start] + rebuilt + source[block_end:]
    payload = rewritten.encode("utf-8")
    if was_crlf:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    TEST_FILE.write_bytes(payload)

    frame = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT / "runtime_hash_refreeze_audit.csv", index=False)
    print(frame[["artifact", "old_sha256", "new_sha256"]].to_string(index=False))
    print()
    print(f"re-froze {len(rows)} of {len(pinned)} pinned artifact hashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
