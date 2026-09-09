# Song catalog

`songs.csv` contains 100 distinct real recordings, replacing the original 21 demonstration entries. The application schema and integer IDs are preserved; IDs 1–100 now refer to new tracks. Historical song IDs and demo rankings are not compatible with the previous catalog.

## Source and provenance

- Original dataset: [Spotify Tracks Dataset by Maharshi Pandya](https://www.kaggle.com/datasets/maharshipandya/-spotify-tracks-dataset).
- Downloaded copy: [CeliaPires/spotify-tracks raw CSV](https://github.com/CeliaPires/spotify-tracks/blob/main/data/01_spotify_raw_dataset.csv).
- Retrieval date: September 8, 2026.
- Downloaded file: 114,000 rows; SHA-256 `f3245c80cc55a2bef55659484ce0254aa2b5a0e9e113643527b7772e10c347d3`.

`song_sources.csv` maps every catalog ID to the source row, Spotify track ID, source genre, and album. A recording can be inspected at `https://open.spotify.com/track/` followed by its Spotify track ID. Track titles and artist credits are copied verbatim, including source punctuation and semicolon-separated credits.

Energy, tempo, valence, danceability, and acousticness are copied unchanged from the downloaded dataset. They are source-reported audio features, not measurements produced or independently verified by this project. Tempo is renamed to `tempo_bpm`. No numeric features were fabricated or adjusted to satisfy the recommender.

## Selection

The catalog contains ten tracks in each category: pop, rock, metal, jazz, classical, acoustic, country, electronic, hip-hop, and study. Artist pools were curated to avoid obvious cross-genre tagging errors. Within each pool, the highest source-popularity recording was selected, with track ID breaking ties. Acoustic selections additionally require source acousticness above 0.60.

Genre labels are broad catalog categories, not an exhaustive musical taxonomy. Most retain the source label; rock recordings by Foo Fighters, Guns N' Roses, Nirvana, Red Hot Chili Peppers, Radiohead, and Queen may come from other source categories and are assigned to rock. The original tag remains in `song_sources.csv`. Jazz includes vocal jazz and crossover recordings; classical includes contemporary piano. The source's `study` category is retained rather than assuming every recording is lofi. The current parser does not recognize `study` as a genre.

This is a curated demonstration subset, not a representative sample of music consumption or a recommendation-quality benchmark. Source popularity is used only for selection and is not a current popularity claim.

## Approximate mood labels

Mood labels are project annotations, not source-provided labels or verified listener judgments. They approximate musical style and audio affect, not lyrical sentiment. Initial rules are applied in this order:

1. Study → focused.
2. Classical → relaxed below energy 0.30; otherwise focused.
3. Metal → aggressive at energy 0.70 or above; otherwise melancholic.
4. Other genres → happy at valence 0.60 or above; otherwise energetic at energy 0.70 or above; otherwise melancholic below valence 0.35; otherwise chill.

A style review overrides these defaults for the following IDs to avoid treating numeric valence as definitive mood:

| IDs | Assigned mood |
| --- | --- |
| 10, 17, 29, 89 | aggressive |
| 16 | energetic |
| 20, 58, 85 | melancholic |
| 31, 51, 52, 57, 60, 70 | chill |
| 32, 33, 56 | happy |
| 81, 83, 86 | playful |
| 82, 84, 87, 88, 90 | intense |

These annotations can be revised independently of the original numeric features. Mood-dependent scoring and diagnostic results should be interpreted with that subjectivity in mind.

## Validation and test impact

The replacement was checked for exactly 100 rows, unique IDs, unique title/artist pairs, unique Spotify track IDs, required columns, positive tempo, and 0–1 feature ranges. Every numeric feature was compared with its source row. The existing loader successfully reads all 100 entries.

All 29 existing test functions passed when invoked directly. They construct independent fixtures rather than reading `songs.csv`; this check did not use the pytest runner. Catalog replacement changes CLI demonstrations and documented examples, which were rerun. Any future tests of catalog-specific IDs, titles, rankings, or confidence values must use the new catalog explicitly.

The catalog includes 50 recordings with energy at or below 0.45 and 29 at or below 0.30. Their presence does not guarantee that scoring places them in the top five. Adaptive retries now apply adjusted weights, but ranking still balances energy with other features.
