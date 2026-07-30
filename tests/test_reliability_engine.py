"""Tests for the reliability engine."""

from src.recommender import Song, UserProfile
from src.reliability_engine import ReliabilityEngine, PreferenceParser, PlaylistResult


def make_test_songs():
    """Create diverse test songs."""
    return [
        Song(
            id=1, title="Happy Pop", artist="Artist A", genre="pop", mood="happy",
            energy=0.85, tempo_bpm=120, valence=0.9, danceability=0.8, acousticness=0.2,
        ),
        Song(
            id=2, title="Chill Lofi", artist="Artist B", genre="lofi", mood="chill",
            energy=0.3, tempo_bpm=80, valence=0.6, danceability=0.3, acousticness=0.85,
        ),
        Song(
            id=3, title="Aggressive Metal", artist="Artist C", genre="metal", mood="aggressive",
            energy=0.95, tempo_bpm=160, valence=0.2, danceability=0.2, acousticness=0.05,
        ),
        Song(
            id=4, title="Acoustic Sad", artist="Artist D", genre="acoustic", mood="melancholic",
            energy=0.25, tempo_bpm=60, valence=0.3, danceability=0.2, acousticness=0.95,
        ),
        Song(
            id=5, title="Electronic Upbeat", artist="Artist E", genre="electronic", mood="energetic",
            energy=0.88, tempo_bpm=130, valence=0.85, danceability=0.85, acousticness=0.1,
        ),
    ]


def test_preference_parser_detects_mood():
    """Test that parser detects mood from input."""
    parser = PreferenceParser()
    profile = parser.parse("I want happy music")

    assert profile.favorite_mood == "happy"


def test_preference_parser_detects_genre():
    """Test that parser detects genre from input."""
    parser = PreferenceParser()
    profile = parser.parse("I want to listen to lofi")

    assert profile.favorite_genre == "lofi"


def test_preference_parser_detects_energy():
    """Test that parser detects energy level."""
    parser = PreferenceParser()

    # High energy
    profile_high = parser.parse("I want upbeat music for my workout")
    assert profile_high.target_energy > 0.7

    # Low energy
    profile_low = parser.parse("I'm tired and want relaxing music")
    assert profile_low.target_energy <= 0.4


def test_preference_parser_detects_acoustic():
    """Test that parser detects acoustic preference."""
    parser = PreferenceParser()

    # Acoustic
    profile_acoustic = parser.parse("I want acoustic unplugged music")
    assert profile_acoustic.likes_acoustic is True

    # Electronic
    profile_electronic = parser.parse("I want electronic synth music")
    assert profile_electronic.likes_acoustic is False


def test_preference_parser_uses_defaults():
    """Test that parser uses default profile when provided."""
    parser = PreferenceParser()
    default = UserProfile(
        favorite_genre="jazz",
        favorite_mood="chill",
        target_energy=0.5,
        likes_acoustic=True,
    )

    # Input with no genre/mood/energy → keeps defaults
    profile = parser.parse("I like this style", default)

    assert profile.favorite_genre == "jazz"
    assert profile.favorite_mood == "chill"


def test_reliability_engine_process_request():
    """Test end-to-end request processing."""
    songs = make_test_songs()
    engine = ReliabilityEngine(songs)

    result = engine.process_user_request("I want happy pop music", k=3)

    assert isinstance(result, PlaylistResult)
    assert len(result.recommendations) <= 3
    assert result.final_match_rate >= 0.0
    assert result.confidence >= 0.0


def test_reliability_engine_creates_decision_log():
    """Test that engine produces detailed decision log."""
    songs = make_test_songs()
    engine = ReliabilityEngine(songs)

    result = engine.process_user_request("I want chill music")

    assert len(result.decision_log) > 0
    assert any("Parsing" in log or "parsing" in log.lower() for log in result.decision_log)
    assert any("Scoring" in log or "scoring" in log.lower() for log in result.decision_log)
    assert any("Validating" in log or "validating" in log.lower() for log in result.decision_log)


def test_reliability_engine_handles_conflicting_preferences():
    """Test handling of conflicting preferences (tired but upbeat)."""
    songs = make_test_songs()
    engine = ReliabilityEngine(songs)

    # This should trigger optimization since preferences conflict
    result = engine.process_user_request(
        "I want upbeat energetic music but I'm exhausted",
        k=3,
        min_match_rate=0.5,
    )

    assert isinstance(result, PlaylistResult)
    # Should have tried to optimize
    assert any("conflict" in log.lower() for log in result.decision_log)


def test_reliability_engine_respects_k():
    """Test that engine respects the k parameter."""
    songs = make_test_songs()
    engine = ReliabilityEngine(songs)

    result = engine.process_user_request("I want pop music", k=2)

    assert len(result.recommendations) <= 2


def test_reliability_engine_returns_formatted_log():
    """Test that engine can format results as readable log."""
    songs = make_test_songs()
    engine = ReliabilityEngine(songs)

    result = engine.process_user_request("I want happy music")
    log = engine.log_result(result)

    assert isinstance(log, str)
    assert len(log) > 0
    assert "Match Rate" in log or "Confidence" in log or "Final" in log
