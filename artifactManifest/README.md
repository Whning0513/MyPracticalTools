# artifactManifest

`artifact-manifest` creates a small, deterministic JSON inventory for a directory and checks it after a copy, upload, or handoff.

It records relative paths, byte sizes, SHA-256 hashes, and simple media types. The manifest is sorted and does not include itself when it lives inside the directory. Symlinks are rejected instead of being followed outside the root.

## Quick start

```bash
python -m pip install -e '.[test]'
artifact-manifest create ./artifact ./artifact.manifest.json --exclude '*.tmp'
artifact-manifest verify ./artifact ./artifact.manifest.json --exclude '*.tmp'
```

The verifier exits `0` when the directory matches, `1` when files are missing, changed, or unexpected, and `2` for an invalid input or manifest.

The format is intentionally plain JSON so it can be reviewed, archived, and used by another tool without this package.
