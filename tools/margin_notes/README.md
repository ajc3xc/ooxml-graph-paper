# Margin Notes

Manuscript-review tool for this paper (`paper/main.tex`), adapted from the
same tool built for a sibling project's PLOS paper. A reviewer opens the
published page, reads the paper block by block, and can select text to leave
a comment/suggestion, or click directly into a paragraph (`contenteditable`)
to retype it inline -- edits are tracked as word-diffs against the original
per block.

- **`margin_notes.html`** -- one ordinary, complete HTML file (open it
  directly in a browser) containing the CSS, the render/edit/comment logic,
  and the manuscript itself. The manuscript part -- `CITES`, `cite()`,
  `SECTIONS` and the `DOC` block array, between the `// BEGIN GENERATED` and
  `// END GENERATED` markers -- is **generated from `paper/main.tex`**. Never
  edit that region by hand (a Claude Code hook in this repo blocks it); edit
  `main.tex` and regenerate. Everything outside the markers (`META`, UI, app
  code) is hand-authored as before.

- **`build_doc_from_tex.py`** -- the generator. It parses `main.tex` (with
  `main.aux` for `\ref` numbers, `refs.bib` for citation names, and
  `paper/numbers.json` for `\val{key}` values), carries every existing block
  id forward by matching blocks against the current file (reviewer comments
  are keyed by block id, so ids must survive regeneration), and keeps figure
  images from the current file. Its module docstring lists the conventions.

      python tools/margin_notes/build_doc_from_tex.py            # report: matched/new/dropped ids + text diffs
      python tools/margin_notes/build_doc_from_tex.py --write    # regenerate the region in margin_notes.html
      python tools/margin_notes/build_doc_from_tex.py --check    # exit 1 if the region is stale (pre-commit)

  `--write` refuses if any existing block id would be dropped, unless each is
  named with `--allow-drop`. Build the PDF first so `main.aux` is current.

- **`build_chunks.js`** -- publish step. The Claude Artifact publish pipeline
  stalls on uploads above roughly 300-500KB; `margin_notes.html` (~530KB with
  embedded figures) is over that, so run `node build_chunks.js` and publish
  `dist/index.html` plus `dist/chunks/*.js` (as `files`) instead of the plain
  file.

## To change the paper's content in the tool

1. Edit `paper/main.tex` (numbers go in `paper/numbers.json`; see
   `paper/consistency.py`), build the PDF.
2. `python tools/margin_notes/build_doc_from_tex.py --write`
3. `node tools/margin_notes/build_chunks.js`, then publish `dist/`.

## Data model note

Comments, suggestions, and paragraph edits made by reviewers in the live
tool are **not** stored in these files -- they live in the artifact's own
realtime database (`db` capability), keyed by manuscript block id (or
`localStorage` when opened as a plain local file, single-browser only).
Nothing here needs to change for reviewer activity to be preserved across
publishes, as long as block ids are preserved -- which is why the generator
refuses to drop one silently.
