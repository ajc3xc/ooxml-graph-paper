# Margin Notes

Manuscript-review tool for this paper (`paper/main.tex`), adapted from the
same tool built for a sibling project's PLOS paper. A reviewer opens the
published page, reads the paper block by block, and can select text to leave
a threaded comment/suggestion, or click directly into a paragraph
(`contenteditable`) to retype it inline -- edits are tracked as word-diffs
against the original per block.

- **`margin_notes.html`** -- the real source. One ordinary, complete HTML
  file (open it directly in a browser) containing the CSS, the render/edit/
  comment logic (unchanged from the sibling project -- that part is generic),
  and a `const DOC = [...]` array with this paper's own 46 manuscript blocks
  (paragraphs, footnotes, and 4 tables; no embedded figures yet, since the
  paper itself has none -- see its own `\todo` about generating real figures).
  Edit this file for any change to the tool's UI/behavior or this paper's
  content.

- **`build_chunks.js`** -- build step, NOT currently needed. The Claude
  Artifact publish pipeline stalls on any single upload above roughly
  300-500KB; this paper's `margin_notes.html` is ~146KB with no embedded
  images, comfortably under that, so it publishes directly as one file. Kept
  here, unmodified from the sibling project, so it's ready the moment this
  paper's real figures get embedded and push the file over that threshold --
  run with `node build_chunks.js` if/when that happens; see its own header
  comment for the full mechanism.

## Regenerating the DOC block from main.tex

The DOC array was generated, not hand-typed, via a one-off script (kept for
reference, not committed as project tooling since it's tied to this specific
paper's exact prose): a small LaTeX-to-HTML converter handling `\citep`,
`\emph`/`\textbf`/`\texttt`, `--`/`---`, `\%`/`\_`, bare `$...$` math-mode
stripping, and `\todo`/`\pending` markers, fed hand-transcribed
(id, section, heading, raw-tex) tuples in main.tex's own order. If main.tex
changes substantially, re-transcribing and re-running that pattern is more
reliable than hand-editing the generated `DOC` array directly, since the
array's `tex:`/`text:` fields must stay in sync with each other and with
`\ref{}`/`\Cref{}` targets resolved to their actual numbers.

## To make a content/code change

1. Edit `margin_notes.html` directly (or regenerate its `DOC` array as above
   if main.tex changed).
2. If it's grown past ~250KB (check with `ls -la`), run `node build_chunks.js`
   and publish `dist/index.html` + `dist/chunks/*.js` instead of the plain
   file. Otherwise just publish `margin_notes.html` itself directly.

## Data model note

Comments, suggestions, and paragraph edits made by reviewers in the live
tool are **not** stored in these files -- they live in the artifact's own
realtime database (`db` capability), keyed by manuscript block id (or
`localStorage` when opened as a plain local file, single-browser only).
Nothing here needs to change for reviewer activity to be preserved across
publishes.
