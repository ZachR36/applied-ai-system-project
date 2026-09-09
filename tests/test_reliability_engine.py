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


def test_retry_applies_weights_and_retains_earlier_partial_match():
    from math import isclose
    from src.recommender import score_song
    songs = [
        Song(1, "High-energy pop", "A", "pop", "happy", .9, 120, .8, .6, .2),
        Song(2, "Low-energy jazz", "B", "jazz", "happy", .4, 80, .8, .6, .2),
    ]
    request = "happy pop but tired"
    engine = ReliabilityEngine(songs)
    result = engine.process_user_request(request, k=1)
    assert len(result.attempt_history) == 4
    assert result.attempt_history[0]['recommendations'][0][0].id == 1
    assert result.attempt_history[-1]['recommendations'][0][0].id == 2
    # Both satisfy two of three preferences. Neither is a complete match.
    assert all(a['match_rate'] == 0. for a in result.attempt_history)
    assert all(isclose(a['preference_coverage'], 2 / 3) for a in result.attempt_history)
    assert result.selected_iteration == 0
    assert result.recommendations[0][0].id == 1
    for attempt in result.attempt_history:
        song, score, reasons = attempt['recommendations'][0]
        expected, expected_reasons = score_song(engine.parser.parse(request), song, weights=attempt['weights'])
        assert isclose(score, expected)
        assert reasons == expected_reasons
    # Mutating the returned result must not overwrite historical evidence.
    result.recommendations[0][2].append("external change")
    assert "external change" not in result.attempt_history[0]['recommendations'][0][2]
    assert result.attempt_history[0]['weights'] != result.attempt_history[-1]['weights']


def test_passing_validation_does_not_adjust_weights():
    from src.recommender import recommend_songs
    engine = ReliabilityEngine(make_test_songs())
    request = "happy pop"
    result = engine.process_user_request(request, k=1)
    assert result.optimization_steps == []
    assert result.recommendations == recommend_songs(engine.parser.parse(request), engine.songs, k=1)


def test_complete_match_outside_similarity_top_k_is_selected():
    from src.recommender import recommend_songs
    songs = [
        Song(1, "Nearly acoustic", "A", "pop", "happy", .4, 80, 1., .5, .59),
        Song(2, "All preferences", "B", "pop", "happy", .1, 80, 0., .5, .61),
    ]
    request = 'happy pop tired acoustic'
    engine = ReliabilityEngine(songs)
    assert recommend_songs(engine.parser.parse(request), songs, k=1)[0][0].id == 1
    result = engine.process_user_request(request, k=1)
    assert result.recommendations[0][0].id == 2
    assert result.final_match_rate == 1.
    assert result.optimization_steps == []


def test_partial_matches_rank_by_boxes_before_similarity():
    from src.recommender import recommend_songs
    songs = [
        Song(1, "Two boxes", "A", "pop", "happy", .8, 100, 1., .5, .59),
        Song(2, "Three boxes", "B", "jazz", "happy", .4, 80, 0., .5, .61),
    ]
    engine = ReliabilityEngine(songs)
    request = 'happy pop tired acoustic'
    assert recommend_songs(engine.parser.parse(request), songs, k=1)[0][0].id == 1
    result = engine.process_user_request(request, k=2)
    assert [song.id for song, _, _ in result.recommendations] == [2, 1]
    assert [c.matched_count for c in result.validation.song_matches] == [3, 2]
    assert result.validation.preference_coverage == 5 / 8
    assert result.final_match_rate == 0.


def test_complete_matches_then_partial_fill_when_fewer_than_k_exist():
    songs = [
        Song(1, "Full", "A", "pop", "happy", .4, 80, .8, .5, .8),
        Song(2, "Partial", "B", "pop", "happy", .9, 100, .8, .5, .8),
        Song(3, "Other", "C", "jazz", "melancholic", .9, 100, .1, .5, .1),
    ]
    result = ReliabilityEngine(songs).process_user_request('happy pop tired acoustic', k=5)
    assert len(result.recommendations) == 3
    assert [c.matched_count for c in result.validation.song_matches] == [4, 3, 0]
    assert result.validation.total_matches == 1
    assert result.final_match_rate == 1 / 3
    assert result.confidence_low_reason.startswith('1 of 3 catalog songs')


def test_unspecified_profile_defaults_are_not_requirements():
    song = Song(1, "Quiet jazz", "A", "jazz", "melancholic", .2, 70, .2, .2, .9)
    base = UserProfile('pop', 'happy', .8, False)
    result = ReliabilityEngine([song]).process_user_request('tired', base_profile=base, k=1)
    check = result.validation.song_matches[0]
    assert check.matched_preferences == ['energy']
    assert check.total_preferences == 1
    assert result.final_match_rate == 1.


def test_earlier_round_can_win_even_above_fallback_threshold():
    songs = [
        Song(1, "Full", "A", "pop", "happy", .4, 80, .8, .5, .2),
        Song(2, "Loud pop", "B", "pop", "happy", .9, 100, .8, .5, .2),
        Song(3, "Quiet jazz", "C", "jazz", "happy", .4, 80, .8, .5, .2),
    ]
    result = ReliabilityEngine(songs).process_user_request('happy pop tired', k=2)
    assert result.final_match_rate == .5
    assert result.confidence_low_reason is None
    assert result.selected_iteration == 0
    assert result.best_attempt_used
    assert [s.id for s, _, _ in result.recommendations] == [1, 2]
    assert [s.id for s, _, _ in result.attempt_history[-1]['recommendations']] == [1, 3]


def test_full_match_and_diagnostics_share_related_mood_policy():
    song = Song(1, "Quiet", "A", "jazz", "relaxed", .2, 70, .4, .3, .8)
    engine = ReliabilityEngine([song])
    result = engine.process_user_request('chill jazz acoustic', k=1)
    assert result.final_match_rate == 1.
    assert engine._diagnose_low_confidence('chill jazz acoustic', result.recommendations, result.validation).startswith('1 of 1')


def test_empty_catalog_retains_an_evaluable_attempt():
    result = ReliabilityEngine([]).process_user_request('happy jazz', max_iterations=0)
    assert result.recommendations == []
    assert result.final_match_rate == 0.
    assert len(result.attempt_history) == 1
    assert 'empty' in result.confidence_low_reason
