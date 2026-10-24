# Sources, data licenses and rebuild instructions

The application code is MIT. Source datasets are not relicensed to MIT.

## Public dictionary archives

`data/words.db.gz` contains an empty compatibility schema authored by this project. It deliberately contains no ECDICT entries or personal exam tags.

`data/extended.db.gz` combines WordNet 3.0 English senses, examples, lemmas and exception forms with Chinese Open Wordnet lemma mappings, plus structured inflection indexes from Wiktionary. Original WordNet and COW material retains the upstream licenses below. This project's adapted indexing and compilation contributions are provided under CC BY-SA 4.0; retain the upstream notices as well.

`data/community.db.gz` is an adaptation of English-language entries extracted from Chinese, Simple English and selected English Wiktionary pages. Wiktionary contributors are the authors; Wiktextract / Kaikki.org provides the extraction. This database and our adaptations are CC BY-SA 4.0. Every entry preserves its original page URL for attribution; follow its History tab for contributors. No Wikimedia, Kaikki or contributor endorsement is implied. See `licenses/Wiktionary-NOTICE.md` and `licenses/CC-BY-SA-4.0.html`.

Inputs retrieved during development on 2026-10-23/24:

| Local build input | Upstream | Applicable terms |
|---|---|---|
| wordnet.zip | [NLTK distribution of WordNet 3.0](https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip), [upstream licensing](https://wordnet.princeton.edu/license-and-commercial-use) | licenses/WordNet-LICENSE.txt |
| cmn.tab | [Chinese Open Wordnet data](https://raw.githubusercontent.com/omwn/omw-data/main/wns/cow/wn-data-cmn.tab) | [COW license](https://github.com/omwn/omw-data/blob/main/wns/cow/LICENSE), licenses/COW-LICENSE.txt |
| simple-extract.jsonl.gz | [Kaikki raw downloads](https://kaikki.org/dictionary/rawdata.html), Simple English edition | Wiktionary contributors, CC BY-SA 4.0 |
| zh-extract.jsonl.gz | [Kaikki raw downloads](https://kaikki.org/dictionary/rawdata.html), Chinese edition | Wiktionary contributors, CC BY-SA 4.0 |
| common_wiki/WORD.jsonl | `https://kaikki.org/dictionary/English/meaning/FIRST/FIRST_TWO/WORD.jsonl` | English Wiktionary contributors, CC BY-SA 4.0 |

`data/manifest.json` records the exact filenames, SHA-256 hashes and build statistics for the snapshot used here. Kaikki downloads change over time; the builder accepts local copies and does not silently replace them from a moving URL. It can build a new snapshot, but matching this release requires the recorded input hashes. Original raw dumps are not bundled; the processed, attributed adaptation is included.

To rebuild in an empty directory, obtain the listed inputs, retain their licenses, arrange them using the local input names above, and run:

```powershell
python scripts/build_open_data.py --inputs PATH_TO_INPUT_DIRECTORY --output PATH_TO_EMPTY_OUTPUT_DIRECTORY
```

The optional `common_wiki/` folder can contain additional English JSONL files from the same documented source. The builder excludes example quotations and records with explicit reference, author, title, year, source or URL fields, retains sense grouping, creates SQLite indexes, and writes deterministic gzip headers. There may still be upstream data errors; report a concrete source URL when requesting correction.

To unpack the included snapshot for the application:

```powershell
python scripts/prepare_data.py
```

## Code dependencies and artwork

- OpenCC Python 0.1.7: [PyPI](https://pypi.org/project/opencc-python-reimplemented/0.1.7/), [source](https://github.com/yichen0831/opencc-python), [OpenCC data source](https://github.com/BYVoid/OpenCC). Apache-2.0; license and NOTICE retained, package installed separately.
- App icon: [Lucide languages](https://lucide.dev/icons/languages), [original SVG](https://github.com/lucide-icons/lucide/blob/main/icons/languages.svg). ISC; adapted palette, rounded background and rasterization. Full notice in `assets/Lucide-LICENSE.txt`.
- Optional speech: pinned upstream downloads in `scripts/speech-downloads.json`; model cards and upstream terms in `licenses/`; details in `docs/SPEECH.md`. No speech binary or model weights are included.
- Promotional poster: generated for this project with the built-in image generation tool, using the licensed app icon. Prompt and provenance in `docs/PROMO.md`. The displayed interface is illustrative.

## Not included

ECDICT, exam PDFs, PDF-derived entries, legacy private API integrations, browser screenshots containing third-party documents, personal vocabulary lists, settings, logs, audio caches, credentials and third-party binary distributions are absent from this source release. Their absence is intentional and does not modify the user's separate local installation.
