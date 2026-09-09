# GrooveMatch Model Card

## System overview

GrooveMatch is a deterministic content-based music recommender with a separate intent-validation and fallback pipeline. It uses manually specified scoring rules and keyword mappings; there is no trained model, LLM inference, or collaborative filtering.

Its intended use is local experimentation with recommendation scoring, explainability, and reliability mechanisms. Recommendations are generated from the included catalog rather than a streaming-service integration.

## Data

`data/songs.csv` contains 100 records with these fields:

- Identifiers and labels: `id`, `title`, `artist`, `genre`, `mood`.
- Numeric features: `energy`, `tempo_bpm`, `valence`, `danceability`, `acousticness`.

Scoring uses genre, mood, energy, acousticness, and valence. Tempo and danceability are loaded but do not affect ranking. The CSV loader requires finite energy, valence, danceability, and acousticness values in the inclusive 0–1 range, and finite tempo greater than zero. Missing, nonnumeric, or out-of-range numeric cells stop loading with a CSV row, field, value, and expected-domain error; no partial catalog is returned and values are never silently corrected. Missing numeric columns are reported at the header. Row numbers count CSV records, with the header as row 1. These checks apply at CSV ingestion; directly constructed `Song` objects are not validated by the loader.

The catalog is a curated subset of the Spotify Tracks Dataset, with unchanged source-reported numeric features and approximate project-assigned mood labels. The [catalog notes](data/README.md) document the source, selection and annotation policies; `data/song_sources.csv` preserves recording identifiers and original genre tags. It is a demonstration catalog, not evidence of representative music coverage. There is no training/test split because the system does not train on these records.

## Scoring and parsing

The score combines genre (0.40), mood (0.30), energy (0.15), acousticness (0.10), and valence (0.05). Exact genre matches receive full genre credit; mood groups allow partial matches. Energy uses distance from the target, and acousticness and valence are mapped to preferences.

## Parsing, clarification, and confirmation

Text seeds an editable draft; it never directly triggers scoring. The parser uses a shared phrase vocabulary and word boundaries for genre, mood, energy, and acousticness. Longest phrases win overlaps. Supported negation includes no/not/without/avoid and common “don't want” forms. Genre and mood exclusions are explicit; “not acoustic” excludes acoustic recordings. “Pop or jazz” becomes allowed genre alternatives.

Contradictory energy bounds, simultaneous inclusion/exclusion, ambiguous conjunctions, mixed-field negation/OR, unsupported vocabulary, and artist-reference requests require clarification. This is a conservative rule-based parser, not general language understanding. Conditional language, complex boolean expressions, cultural references, artist similarity, and free-text importance rules are not reliably interpreted; users must use the structured editors or explicitly omit unsupported wording.

Every request, even an unambiguous one, must be confirmed. The CLI exposes numbered editors for each field and preserves the rest of the draft. Unresolved questions block confirmation. The API raises `PreferenceReviewRequired` when no confirmation is supplied. `draft.confirm()` creates an immutable snapshot only after unresolved issues are cleared; callers should invoke it only in response to explicit user confirmation. This is an application workflow contract, not an authentication mechanism.

Scoring and retries use the confirmed snapshot. Allowed alternatives influence similarity through the first selected value; validation accepts any allowed alternative, and the review displays their order. Energy targets are clamped within the confirmed range. Unspecified similarity fields use the supplied profile or the existing defaults; they do not become requirements. Explicit exclusions filter candidates before scoring and are never relaxed, even to fill the requested count.

## Validation metrics and ranking

`match_rate = songs satisfying every recognized requested category / songs returned`

`preference_coverage = satisfied category boxes / requested category boxes across returned songs`

The API temporarily exposes `match_rate` as `confidence` for compatibility. User-facing output uses “Complete-match rate” and “Preference coverage”; neither is calibrated against human judgments. With no recognized constraints, both rates and the compatibility `confidence` field are `None`, `validation.evaluated` is false, and no song is counted as a complete match. After explicit acceptance of no preferences and confirmation, the system labels suggestions as unvalidated and based on the default or supplied profile, with no validation retries. This also applies to an empty catalog with an unrecognized request. Recognized requests with empty results retain zero match rate and coverage.

Each explicitly requested genre, mood, energy, or acoustic category contributes one equally weighted box. Genre accepts any allowed alternative; mood accepts exact or related matches to any allowed alternative. Explicitly excluded genres/moods and excluded acoustic styles are removed before scoring. Energy constraints use the strictest bounds. Acousticness above 0.60 satisfies an acoustic request; 0.60 or below satisfies a non-acoustic request. Allowed values within genre or mood are alternatives (OR); exclusions all apply. Energy bounds define one range. Duplicates do not increase a category’s weight. Acoustic wording alone is treated as a feature requirement, not a mandatory acoustic genre label.

All eligible catalog songs are checked before truncating to top-k; explicitly excluded tracks cannot enter partial-match fallback. Complete matches rank first; remaining songs rank by boxes satisfied, then the current similarity score. Returned validation records expose every matched and missed category. A lower similarity score cannot displace a song satisfying more preferences.

## Retry and best-attempt policy

For evaluated requests, the engine retries below a complete-match rate of 0.70, for at most three iterations by default. Every round scores the full eligible catalog with its applied weights and uses the same preference-first ordering. It retains recommendations, weights, validation, and quality metadata for all rounds, including round zero.

The final selection compares complete-match count, total satisfied boxes, and default-weight similarity, in that order. An unevaluated request records one scoring attempt with `evaluated=False` and `quality=None`; it is never compared as a validated candidate. The fixed comparison weights prevent a score increase caused solely by changing weights from being mistaken for an improvement. Exact ties preserve the earlier attempt. Best-attempt selection is unconditional; below 0.40, diagnostic context is attached as well. The selected round is available as `selected_iteration`.

Full-catalog preference ranking already finds the maximum available complete matches and category coverage. Weight adjustment only affects similarity tie-breaks and cannot create missing content. The existing optimizer policy is retained. Diagnostics use the same per-song predicate as validation. They distinguish an empty catalog, zero complete matches, and fewer complete matches than the requested result count. Returned counts separately report complete matches, partial matches satisfying at least one category, and alternatives satisfying none. A small catalog or scarce matches does not establish that the request is contradictory. These explanations are shown in both CLI modes only under the existing diagnostic policy; the 0.40 boundary remains strict.

## Evaluation evidence

Four requests were executed against the included catalog with `k=5` and default thresholds:

| Request | Complete-match rate | Preference coverage | Retries | Selected round |
| --- | ---: | ---: | ---: | ---: |
| I want lofi music that is chill and relaxing, I like acoustic sounds | 0.00 | 0.750 | 3 | 0 |
| I want happy music but I am tired and exhausted | 0.80 | 0.900 | 0 | 0 |
| I want upbeat energetic pop music for my workout | 0.60 | 0.867 | 3 | 0 |
| I want sleepy music | 1.00 | 1.000 | 0 | 0 |

The repository also includes 83 test functions across scoring, validation, optimization helpers, and orchestration. These checks do not constitute an evaluation of recommendation quality with real listeners. No measured quality uplift, latency benchmark, demographic fairness result, or production-scale evaluation is claimed.

## Reliability and coverage considerations

- **Catalog coverage:** A small catalog limits which requests can be fulfilled. Weight changes cannot create missing content.
- **Ranking bias:** Genre and mood initially account for 70% of similarity, affecting tie-breaks among equally compliant songs. Explicit preferences take precedence over this score.
- **Metric scope:** Complete-match rate covers recognized categories, not arbitrary language or subjective musical taste. Approximate mood annotations and rigid energy thresholds remain limitations. Common exclusions are supported, while artist similarity, complex language, and explicit importance instructions still require structured clarification or explicit omission.
- **Observability:** Returned decision logs expose parsed preferences, attempts, and validation feedback. They are in-memory output rather than a persistent monitoring system.
- **Privacy:** The pipeline runs locally and contains no external API calls or persistent user-profile store. Decision logs include the user's raw request, which matters if callers later save or share them.
- **Personalization:** Requests are independent; the system does not learn from listening history, skips, or ratings.

## Improvement priorities

Evaluate the equal-category ranking policy with users; improve unsupported-input handling; extend data coverage; and evaluate relevance, diversity, and coverage using a larger catalog and human judgments.
