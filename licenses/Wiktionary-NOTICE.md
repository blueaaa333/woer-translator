# Wiktionary community data

This distribution includes an adapted database, `community.db`, derived from
Wiktionary contributors' content extracted by Wiktextract and published by Kaikki.org.

Sources:

- Chinese Wiktionary contributors: https://zh.wiktionary.org/
- Simple English Wiktionary contributors: https://simple.wiktionary.org/
- English Wiktionary contributors: https://en.wiktionary.org/
- Extraction project: https://github.com/tatuylonen/wiktextract
- Dataset downloads: https://kaikki.org/dictionary/rawdata.html
- English per-word JSONL downloads: https://kaikki.org/dictionary/English/index.html

Wiktionary text is reused under Creative Commons Attribution-ShareAlike 4.0
International (CC BY-SA 4.0). This adaptation of the data is distributed under
the same license: https://creativecommons.org/licenses/by-sa/4.0/
Legal text: https://creativecommons.org/licenses/by-sa/4.0/legalcode.en

Attribution: Wiktionary contributors, via the original page URLs stored in each
database entry and opened with the app's Source link. Contributor histories can
be accessed using the history tab on each source page (or `?action=history`).
No endorsement by Wikimedia, Wiktionary contributors or Kaikki.org is implied.

Changes made: retained English-language entries from Chinese and Simple English
editions; supplemented common words from English edition downloads; selected
glosses, contributed usage examples, forms and IPA; excluded examples marked as
quotations or carrying citation references; grouped Chinese translation hints by
their original sense labels; converted to an indexed SQLite database. English
translation labels are not machine-generated Chinese definitions.

Dataset retrieved on 2026-10-24. Raw dumps remain in the build workspace rather
than the runtime package. This notice applies to the community data, not as a
blanket license for other bundled dictionaries, application code or icon assets.
