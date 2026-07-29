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
    assert constraints["energy"][0].get("energy_max") == 0.4


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
    """Test validation with no keywords (should match all)."""
    songs = make_test_songs()
    recommendations = [
        (songs[0], 0.95, ["Song 1"]),
        (songs[1], 0.90, ["Song 2"]),
    ]

    result = validate_recommendations("Just give me some music", recommendations)

    assert result.match_rate == 1.0
    assert result.total_matches == 2


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
