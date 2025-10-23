# Relation Type Normalization Hardening

## Background
Recent fixes canonicalize edge relation names by trimming, uppercasing, and swapping literal spaces for underscores. This eliminates the most common duplicate causes (e.g. `"Works With"` vs `"WORKS_WITH"`), but the approach still misses:
- Non-breaking spaces, tabs, and other Unicode whitespace.
- Punctuation variants (`"works-with"`, `"works/with"`, `"works.with"`).
- Accented or compatibility characters that render identically but compare differently.

Because the ingestion pipeline relies on string equality to dedupe edges, the normalization step must collapse all “visually identical” relation labels to a single canonical key.

## Objectives
1. Normalize arbitrary Unicode relation labels into a stable ASCII identifier.
2. Prevent duplicate edge records that differ only by whitespace, punctuation, diacritics, or Unicode compatibility forms.
3. Keep the implementation testable and dependency-light, while allowing an optional library-based alternative if we need broader transliteration support.

## Recommended Approach
### 1. Canonicalize Unicode Input
- Apply [Unicode NFKC normalization](https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize) to fold compatibility characters (e.g. full-width letters, smart quotes) into their canonical forms.
- Use `str.casefold()` instead of `str.upper()` for the initial transformation; case folding handles locale-insensitive comparisons correctly.

### 2. Map Common Punctuation to Underscores
- Transliterate characters we consider separators—dash (`-`), slash (`/`), dot (`.`), colon (`:`), etc.—to underscores before collapsing whitespace. This keeps relation name semantics while avoiding duplicate keys.

### 3. Collapse Whitespace Robustly
- Replace every run of whitespace (matching `\s` so tabs, NBSP, etc.) with a single underscore via `re.sub(r'\s+', '_', …)`.
- After punctuation substitution and whitespace collapse, replace multi-underscore runs with a single underscore to avoid `WORKS__WITH`.

### 4. Strip Non-Alphanumeric Residue
- Optionally remove any character outside `[A-Z0-9_]` after the previous steps. This prevents stray symbols from generating distinct identifiers.

### 5. Final Formatting
- Convert to uppercase (`.upper()`) to stay consistent with existing storage.
- Emit a debug log when the canonical value differs from the trimmed input to aid observability.

### Example Implementation
```python
import re
import unicodedata

SEPARATOR_TRANSLATION = str.maketrans({
    '-': '_',
    '/': '_',
    '.': '_',
    ':': '_',
})

def normalize_relation_type(raw: str) -> str:
    if not raw:
        return ''

    normalized = unicodedata.normalize('NFKC', raw).casefold()
    normalized = normalized.translate(SEPARATOR_TRANSLATION)
    normalized = re.sub(r'\s+', '_', normalized.strip())
    normalized = re.sub(r'_+', '_', normalized)
    normalized = re.sub(r'[^0-9a-z_]', '', normalized)
    normalized = normalized.upper()

    if normalized != raw.strip():
        logger.debug('Normalized relation type: "%s" -> "%s"', raw, normalized)

    return normalized
```

### Optional Library Support
If we prefer not to maintain the transliteration logic ourselves, [`python-slugify`](https://github.com/un33k/python-slugify) (MIT licensed) wraps [text-unidecode](https://pypi.org/project/text-unidecode/) and handles:
- Unicode normalization and ASCII transliteration.
- Whitespace collapse.
- Configurable separators.

Usage:
```python
from slugify import slugify

def normalize_relation_type(raw: str) -> str:
    if not raw:
        return ''
    slug = slugify(raw, separator='_', lowercase=True)
    normalized = slug.upper()
    if normalized != raw.strip():
        logger.debug('Normalized relation type: "%s" -> "%s"', raw, normalized)
    return normalized
```

Dependencies:
- `python-slugify` 8.0+ (supports custom separator, lowercase, Unicode normalization)
- `text-unidecode` (pulled in automatically)

## Testing Strategy
Add regression tests covering the following inputs → outputs:
| Input | Expected Output |
| --- | --- |
| `"Works With"` | `WORKS_WITH` |
| `"works-with"` | `WORKS_WITH` |
| `"works/with"` | `WORKS_WITH` |
| `"works\twith"` | `WORKS_WITH` |
| `"works\u00a0with"` (NBSP) | `WORKS_WITH` |
| `"WÖRKS WITH"` | `WORKS_WITH` |
| `"  works__with  "` | `WORKS_WITH` |

## References
- Python `unicodedata` normalization docs: <https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize>
- Python `re` module (whitespace classes, substitution): <https://docs.python.org/3/library/re.html>
- python-slugify project: <https://github.com/un33k/python-slugify>
- text-unidecode project: <https://pypi.org/project/text-unidecode/>

