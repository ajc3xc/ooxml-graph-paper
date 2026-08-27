# Execution checkpoint — 2026-08-25

## Confirmed

- Child Meridian project: `OOXML-Graph Paper`.
- Parent project: `meridian-build`.
- Code/data roots have been created but are empty.
- C: free space: approximately 243.91 GB.
- E: free space: approximately 185.01 GB.
- Pixi is available locally.
- GPU: NVIDIA GeForce RTX 3080, 20,480 MiB VRAM, driver 591.86.
- Existing DocBank scoring code is present in the parent repository; the real corpus is not present.

## Next executable wave

1. Verify official DocBank index and preview/sample layout.
2. Produce a local dataset manifest without downloading the full corpus.
3. Freeze the native-OOXML versus parser comparator and graph/gold schema.
4. Run a tiny end-to-end smoke slice locally.
5. Add GPU baselines only where their memory/runtime requirements fit the 20 GB card.
6. Scale only after smoke outputs pass structural, metric, provenance, and render-receipt gates.

## Explicit non-goals for this checkpoint

- No full DocBank download.
- No untracked OneDrive artifacts.
- No RunPod allocation.
- No claim that a model baseline is comparable until its input representation and token/cost accounting are recorded.

