"""Tests for the validator module."""

from src.recommender import Song, UserProfile
from src.validator import extract_keywords, validate_recommendations, ValidationResult


def make_test_songs():
    """Create test songs for validation."""
    return [
        Song(
            id=1,
            title="Upbeat Pop",
            artist="Test",
            genre="pop",
            mood="happy",
            energy=0.85,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi",
            artist="Test",
            genre="lofi",
            mood="chill",
            energy=0.3,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.3,
            acousticness=0.85,
        ),
        Song(
            id=3,
            title="Acoustic Sad",
            artist="Test",
            genre="acoustic",
            mood="melancholic",
            energy=0.25,
            tempo_bpm=60,
            valence=0.3,
            danceability=0.2,
            acousticness=0.95,
        ),
    ]


def test_extract_keywords_upbeat():
    """Test extracting 'upbeat' keyword."""
    keywords, constraints = extract_keywords("I want upbeat music")
    assert "upbeat" in keywords
    assert len(constraints["energy"]) > 0
    assert constraints["energy"][0].get("energy_min") == 0.7


def test_extract_keywords_tired():
    """Test extracting 'tired' keyword."""
    keywords, constraints = extract_keywords("I'm tired and want relaxing music")
    assert "tired" in keywords or "relaxing" in keywords
    assert len(constraints["energy"]) > 0
    assert min(c["energy_max"] for c in constraints["energy"]) == 0.45


def test_extract_keywords_acoustic():
    """Test extracting acoustic preference."""
    keywords, constraints = extract_keywords("I want acoustic unplugged music")
    assert "acoustic" in keywords or "unplugged" in keywords
    assert len(constraints["acoustic"]) > 0


def test_extract_keywords_no_matches():
    """Test input with no recognizable keywords."""
    keywords, constraints = extract_keywords("I like music")
    assert len(keywords) == 0
    assert sum(len(v) for v in constraints.values()) == 0


def test_validate_recommendations_all_match():
    """Test validation when all songs match intent."""
    songs = make_test_songs()
    # Both low-energy songs must also satisfy the requested related mood.
    songs[2].mood = "relaxed"
    # Create recommendations: (song, score, reasons)
    recommendations = [
        (songs[1], 0.95, ["Chill lofi"]),  # Low energy
        (songs[2], 0.90, ["Chill acoustic"]),  # Low energy
    ]

    result = validate_recommendations("I want chill music", recommendations)

    assert result.match_rate == 1.0
    assert result.total_matches == 2
    assert result.total_songs == 2


def test_validate_recommendations_partial_match():
    """Test validation when some songs match intent."""
    songs = make_test_songs()
    # One high-energy, one low-energy
    recommendations = [
        (songs[0], 0.95, ["Upbeat pop"]),  # High energy (doesn't match "chill")
        (songs[1], 0.90, ["Chill lofi"]),  # Low energy (matches "chill")
    ]

    result = validate_recommendations("I want chill music", recommendations)

    assert result.match_rate == 0.5
    assert result.total_matches == 1
    assert result.total_songs == 2


def test_validate_recommendations_no_keywords():
    """Unrecognized requests cannot establish match quality."""
    songs = make_test_songs()
    recommendations = [
        (songs[0], 0.95, ["Song 1"]),
        (songs[1], 0.90, ["Song 2"]),
    ]

    result = validate_recommendations("Just give me some music", recommendations)

    assert result.match_rate is None
    assert result.preference_coverage is None
    assert result.evaluated is False
    assert result.total_matches == 0
    assert not any(check.complete for check in result.song_matches)


def test_validate_recommendations_conflicting_energy():
    """Test validation with conflicting energy preferences."""
    songs = make_test_songs()
    recommendations = [
        (songs[0], 0.95, ["Upbeat pop"]),  # High energy
        (songs[1], 0.90, ["Chill lofi"]),  # Low energy
    ]

    # User wants both upbeat AND relaxing (conflicting)
    result = validate_recommendations("I want upbeat but I'm tired", recommendations)

    # Should still match the ones that fit one or the other
    assert result.match_rate >= 0.0
    assert result.total_songs == 2


def test_validation_result_has_reasons():
    """Test that validation provides detailed reasons."""
    songs = make_test_songs()
    recommendations = [(songs[1], 0.95, ["Chill"])]

    result = validate_recommendations("I want chill low-energy music", recommendations)

    assert len(result.reasons) > 0
    assert any("Energy" in reason or "energy" in reason for reason in result.reasons)


def test_each_explicit_category_can_fail_independently():
    from dataclasses import replace
    song = Song(10, "Complete", "A", "jazz", "happy", .4, 80, .8, .5, .8)
    request = "happy jazz acoustic tired"
    assert validate_recommendations(request, [(song, .1, [])]).match_rate == 1.
    for category, changed in [
        ('genre', replace(song, genre='pop')),
        ('mood', replace(song, mood='melancholic')),
        ('energy', replace(song, energy=.9)),
        ('acoustic', replace(song, acousticness=.2)),
    ]:
        validation = validate_recommendations(request, [(changed, .99, [])])
        check = validation.song_matches[0]
        assert validation.match_rate == 0.
        assert check.matched_count == 3
        assert check.missed_preferences == [category]
        assert validation.preference_coverage == .75
        assert '✗' in validation.reasons[0]


def test_related_moods_count_as_satisfied():
    from src.validator import evaluate_song
    _, constraints = extract_keywords('chill')
    song = make_test_songs()[1]
    song.mood = 'relaxed'
    assert evaluate_song(song, constraints).complete
    song.mood = 'melancholic'
    assert not evaluate_song(song, constraints).complete


def test_synonyms_do_not_add_extra_boxes():
    from src.validator import evaluate_song
    song = make_test_songs()[1]
    _, simple = extract_keywords('tired acoustic')
    _, repeated = extract_keywords('tired exhausted acoustic unplugged')
    a, b = evaluate_song(song, simple), evaluate_song(song, repeated)
    assert a.matched_count == b.matched_count == 2
    assert a.total_preferences == b.total_preferences == 2


def test_genre_extraction_handles_catalog_and_longest_phrases():
    for phrase, target in [('country', 'country'), ('hip hop', 'hip-hop'),
                           ('study', 'study'), ('indie pop', 'indie pop'), ('heavy metal', 'metal')]:
        _, constraints = extract_keywords(phrase)
        assert {v for c in constraints['genre'] for v in c['genre_any']} == {target}
    _, constraints = extract_keywords('acoustic jazz')
    assert {v for c in constraints['genre'] for v in c['genre_any']} == {'jazz'}
    assert constraints['acoustic']


def test_contradictory_energy_is_one_unsatisfied_box():
    result = validate_recommendations('high energy but tired', [(make_test_songs()[0], .99, [])])
    check = result.song_matches[0]
    assert check.total_preferences == 1
    assert check.missed_preferences == ['energy']
    assert result.match_rate == 0.


def test_empty_results_distinguish_known_and_unknown_preferences():
    known = validate_recommendations('happy jazz', [])
    assert known.match_rate == 0.
    assert known.preference_coverage == 0.
    assert known.evaluated is True
    unknown = validate_recommendations('some music', [])
    assert unknown.match_rate is None
    assert unknown.preference_coverage is None
    assert unknown.evaluated is False


def test_acoustic_threshold_and_non_acoustic_request():
    song = make_test_songs()[0]
    song.acousticness = .6
    assert validate_recommendations('acoustic', [(song, .8, [])]).match_rate == 0.
    assert validate_recommendations('digital', [(song, .8, [])]).match_rate == 1.
    song.acousticness = .60001
    assert validate_recommendations('acoustic', [(song, .8, [])]).match_rate == 1.


def test_summary_distinguishes_partial_coverage_from_complete_matches():
    from src.validator import format_validation_summary
    songs = [(Song(i, str(i), 'A', 'jazz', 'happy', .4, 80, .7, .4, .8), .8, [])
             for i in range(5)]
    result = validate_recommendations('happy pop tired acoustic', songs)
    summary = format_validation_summary(result)
    assert 'Complete-match rate: 0.0%' in summary
    assert '0 of 5 songs match all recognized preferences' in summary
    assert 'Preference coverage: 75.0%' in summary
    assert 'confidence' not in summary.lower()


def test_unevaluated_summary_has_no_percentage_even_with_suggestions():
    from src.validator import log_validation
    for recommendations in [[], [(make_test_songs()[0], .99, [])]]:
        result = validate_recommendations('surprise me', recommendations)
        output = log_validation(result)
        assert 'Not evaluated—no supported preferences recognized' in output
        assert 'Unvalidated suggestions' in output
        assert '%' not in output
