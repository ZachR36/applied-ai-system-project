# GrooveMatch Model Card

## System overview

GrooveMatch is a deterministic content-based music recommender with a separate intent-validation and fallback pipeline. It uses manually specified scoring rules and keyword mappings; there is no trained model, LLM inference, or collaborative filtering.

Its intended use is local experimentation with recommendation scoring, explainability, and reliability mechanisms. Recommendations are generated from the included catalog rather than a streaming-service integration.

## Data

`data/songs.csv` contains 100 records with these fields:

- Identifiers and labels: `id`, `title`, `artist`, `genre`, `mood`.
- Numeric features: `energy`, `tempo_bpm`, `valence`, `danceability`, `acousticness`.

Scoring uses genre, mood, energy, acousticness, and valence. Tempo and danceability are loaded but do not affect ranking. The scoring formulas assume energy, valence, and acousticness are on a 0–1 scale; the loader converts numeric types without enforcing those ranges.

The catalog is a curated subset of the Spotify Tracks Dataset, with unchanged source-reported numeric features and approximate project-assigned mood labels. The [catalog notes](data/README.md) document the source, selection and annotation policies; `data/song_sources.csv` preserves recording identifiers and original genre tags. It is a demonstration catalog, not evidence of representative music coverage. There is no training/test split because the system does not train on these records.

## Scoring and parsing

The score combines genre (0.40), mood (0.30), energy (0.15), acousticness (0.10), and valence (0.05). Exact genre matches receive full genre credit; mood groups allow partial matches. Energy uses distance from the target, and acousticness and valence are mapped to preferences.

The parser uses substring matching. Without a supplied base profile, it defaults to pop, happy, energy 0.5, and a non-acoustic preference. These defaults can influence recommendations when a request is ambiguous or unsupported. Parsing does not reliably handle negation, artist similarity, or competing preferences.

## Validation metric

`match_rate = songs passing energy constraints / songs returned`

The API exposes this same value as `confidence`. It is a deterministic compliance measure and has not been calibrated against human judgments.

- Repeated energy constraints are consolidated to the strictest lower and upper bounds.
- Mood and acoustic checks produce feedback but do not change pass/fail status.
- Genre is not checked by the validator.
- Nonempty results without energy constraints pass these checks, even if other preferences are wrong.
- Empty recommendation lists have a match rate of zero.

Consequently, 100% confidence does not establish that all requested attributes are satisfied.

## Retry and fallback policy

The engine retries when match rate is below 0.70, for at most three iterations by default. Each retry applies normalized weight suggestions to scoring and records the attempt. The user profile remains unchanged. Weight adjustments can trade genre/mood similarity for better energy compliance. Calls that omit custom weights retain the original scoring behavior.

If the final match rate is strictly below 0.40, the engine returns the best recorded attempt and adds a diagnostic explanation. This is best-effort output, not a guarantee that the request is fulfilled.

Diagnostics count catalog matches using energy, exact mood, and acoustic constraints. This differs from the validator's energy-only pass/fail policy. The diagnostic branch can label a request as conflicting when at least three catalog matches exist; that message does not prove the constraints are contradictory. Diagnostic rules should be aligned with validation before treating their explanations as authoritative.

## Evaluation evidence

Four requests were executed against the included catalog with `k=5` and default thresholds:

| Request | Match rate | Retry count | Best-attempt fallback |
| --- | ---: | ---: | --- |
| I want lofi music that is chill and relaxing, I like acoustic sounds | 0.80 | 0 | No |
| I want happy music but I am tired and exhausted | 0.40 | 3 | No |
| I want upbeat energetic pop music for my workout | 0.80 | 2 | No |
| I want sleepy music | 0.40 | 3 | No |

The repository also includes 33 test functions across scoring, validation, optimization helpers, and orchestration. These checks do not constitute an evaluation of recommendation quality with real listeners. No measured quality uplift, latency benchmark, demographic fairness result, or production-scale evaluation is claimed.

## Reliability and coverage considerations

- **Catalog coverage:** A small catalog limits which requests can be fulfilled. Weight changes cannot create missing content.
- **Ranking bias:** Genre and mood initially account for 70% of the score, which can reduce cross-genre discovery. The magnitude of this effect has not been measured.
- **Metric scope:** Energy compliance can conceal unmet mood, acoustic, or genre preferences.
- **Observability:** Returned decision logs expose parsed preferences, attempts, and validation feedback. They are in-memory output rather than a persistent monitoring system.
- **Privacy:** The pipeline runs locally and contains no external API calls or persistent user-profile store. Decision logs include the user's raw request, which matters if callers later save or share them.
- **Personalization:** Requests are independent; the system does not learn from listening history, skips, or ratings.

## Improvement priorities

Broaden regression coverage for adaptive ranking; unify validation and diagnostic rules; improve unsupported-input handling; extend data coverage; and evaluate relevance, diversity, and coverage using a larger catalog and human judgments.
