#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ARCHIVES="$ROOT/archives"
MANIFEST="$ROOT/SHA256SUMS"
OUT="$ROOT/IPFS_CIDS.tsv"
IPFS_BIN=${IPFS_BIN:-ipfs}

if ! command -v "$IPFS_BIN" >/dev/null 2>&1; then
    echo "error: cannot find $IPFS_BIN" >&2
    exit 1
fi
if ! "$IPFS_BIN" id >/dev/null 2>&1; then
    echo "error: Kubo daemon is not reachable; start 'ipfs daemon' first" >&2
    exit 1
fi
if [ ! -f "$MANIFEST" ]; then
    echo "error: missing $MANIFEST" >&2
    exit 1
fi

printf 'filename\tcid\tsha256\n' > "$OUT"
for archive in "$ARCHIVES"/*.tar.zst; do
    [ -f "$archive" ] || continue
    name=$(basename "$archive")
    expected=$(awk -v n="$name" '$2 == n { print $1 }' "$MANIFEST")
    actual=$(shasum -a 256 "$archive" | awk '{ print $1 }')
    if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
        echo "error: SHA-256 mismatch for $name" >&2
        exit 1
    fi

    echo "adding and pinning $name"
    result=$($IPFS_BIN add --cid-version=1 --raw-leaves \
        --chunker=size-1048576 --pin=true "$archive")
    printf '%s\n' "$result"
    cid=$(printf '%s\n' "$result" | awk '/^added / { print $2 }' | tail -n 1)
    if [ -z "$cid" ]; then
        echo "error: could not parse CID for $name" >&2
        exit 1
    fi
    printf '%s\t%s\t%s\n' "$name" "$cid" "$actual" >> "$OUT"
done

echo "wrote $OUT"
cat "$OUT"
