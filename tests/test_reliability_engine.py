from tests.review_helpers import confirmed_request
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

    result = confirmed_request(engine, "I want happy pop music", k=3)

    assert isinstance(result, PlaylistResult)
    assert len(result.recommendations) <= 3
    assert result.final_match_rate >= 0.0
    assert result.confidence >= 0.0


def test_reliability_engine_creates_decision_log():
    """Test that engine produces detailed decision log."""
    songs = make_test_songs()
    engine = ReliabilityEngine(songs)

    result = confirmed_request(engine, "I want chill music")

    assert len(result.decision_log) > 0
    assert any("Parsing" in log or "parsing" in log.lower() for log in result.decision_log)
    assert any("Scoring" in log or "scoring" in log.lower() for log in result.decision_log)
    assert any("Validating" in log or "validating" in log.lower() for log in result.decision_log)


def test_reliability_engine_requires_clarification_for_conflicting_preferences():
    from src.preferences import PreferenceReviewRequired
    from unittest.mock import patch
    engine = ReliabilityEngine(make_test_songs())
    draft = engine.prepare_request("I want upbeat energetic music but I'm exhausted")
    with patch('src.reliability_engine.recommend_songs', side_effect=AssertionError('must not score')):
        try:
            draft.confirm()
        except PreferenceReviewRequired:
            assert 'energy' in draft.issues()
        else:
            raise AssertionError('Conflicting preferences were confirmed')


def test_reliability_engine_respects_k():
    """Test that engine respects the k parameter."""
    songs = make_test_songs()
    engine = ReliabilityEngine(songs)

    result = confirmed_request(engine, "I want pop music", k=2)

    assert len(result.recommendations) <= 2


def test_reliability_engine_returns_formatted_log():
    """Test that engine can format results as readable log."""
    songs = make_test_songs()
    engine = ReliabilityEngine(songs)

    result = confirmed_request(engine, "I want happy music")
    log = engine.log_result(result)

    assert isinstance(log, str)
    assert len(log) > 0
    assert "Complete-match rate:" in log
    assert "Preference coverage:" in log
    assert "Confidence" not in log


def test_retry_applies_weights_and_retains_earlier_partial_match():
    from math import isclose
    from src.recommender import score_song
    songs = [
        Song(1, "High-energy pop", "A", "pop", "happy", .9, 120, .8, .6, .2),
        Song(2, "Low-energy jazz", "B", "jazz", "happy", .4, 80, .8, .6, .2),
    ]
    request = "happy pop but tired"
    engine = ReliabilityEngine(songs)
    result = confirmed_request(engine, request, k=1)
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
    result = confirmed_request(engine, request, k=1)
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
    result = confirmed_request(engine, request, k=1)
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
    result = confirmed_request(engine, request, k=2)
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
    result = confirmed_request(ReliabilityEngine(songs), 'happy pop tired acoustic', k=5)
    assert len(result.recommendations) == 3
    assert [c.matched_count for c in result.validation.song_matches] == [4, 3, 0]
    assert result.validation.total_matches == 1
    assert result.final_match_rate == 1 / 3
    assert result.confidence_low_reason.startswith('1 of 3 catalog songs')


def test_unspecified_profile_defaults_are_not_requirements():
    song = Song(1, "Quiet jazz", "A", "jazz", "melancholic", .2, 70, .2, .2, .9)
    base = UserProfile('pop', 'happy', .8, False)
    result = confirmed_request(ReliabilityEngine([song]), 'tired', base_profile=base, k=1)
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
    result = confirmed_request(ReliabilityEngine(songs), 'happy pop tired', k=2)
    assert result.final_match_rate == .5
    assert result.confidence_low_reason is None
    assert result.selected_iteration == 0
    assert result.best_attempt_used
    assert [s.id for s, _, _ in result.recommendations] == [1, 2]
    assert [s.id for s, _, _ in result.attempt_history[-1]['recommendations']] == [1, 3]


def test_full_match_and_diagnostics_share_related_mood_policy():
    song = Song(1, "Quiet", "A", "jazz", "relaxed", .2, 70, .4, .3, .8)
    engine = ReliabilityEngine([song])
    result = confirmed_request(engine, 'chill jazz acoustic', k=1)
    assert result.final_match_rate == 1.
    assert engine._diagnose_low_confidence('chill jazz acoustic', result.recommendations, result.validation).startswith('1 of 1')


def test_empty_catalog_retains_an_evaluable_attempt():
    result = confirmed_request(ReliabilityEngine([]), 'happy jazz', max_iterations=0)
    assert result.recommendations == []
    assert result.final_match_rate == 0.
    assert len(result.attempt_history) == 1
    assert 'empty' in result.confidence_low_reason


def test_unrecognized_request_skips_retries_and_returns_none_metrics():
    from unittest.mock import patch
    from src.recommender import recommend_songs
    engine = ReliabilityEngine(make_test_songs())
    with patch.object(engine.optimizer, 'suggest_weight_adjustments', side_effect=AssertionError('must not retry')):
        result = confirmed_request(engine, 'surprise me', k=2)
    assert result.recommendations == recommend_songs(engine.parser.parse(''), engine.songs, k=2)
    assert result.confidence is None
    assert result.final_match_rate is None
    assert result.validation.match_rate is None
    assert result.validation.preference_coverage is None
    assert result.validation.total_matches == 0
    assert not result.validation.evaluated
    assert result.optimization_steps == []
    assert len(result.attempt_history) == 1
    attempt = result.attempt_history[0]
    assert attempt['evaluated'] is False
    assert attempt['match_rate'] is None
    assert attempt['preference_coverage'] is None
    assert attempt['quality'] is None
    assert result.confidence_low_reason is None
    assert result.best_attempt_used is False
    output = engine.log_result(result)
    assert 'Not evaluated' in output and '%' not in output


def test_unrecognized_request_preserves_supplied_profile_without_claiming_match():
    from src.recommender import recommend_songs
    engine = ReliabilityEngine(make_test_songs())
    profile = UserProfile('lofi', 'chill', .3, True)
    result = confirmed_request(engine, 'surprise me', base_profile=profile, k=1)
    assert result.recommendations == recommend_songs(profile, engine.songs, k=1)
    assert result.confidence is None
    assert not result.validation.evaluated


def test_unrecognized_empty_catalog_is_unevaluated_without_retries():
    result = confirmed_request(ReliabilityEngine([]), 'surprise me')
    assert result.recommendations == []
    assert result.confidence is None
    assert result.optimization_steps == []
    assert not result.validation.evaluated


def test_recognized_unmet_request_remains_evaluated_zero_and_retries():
    song = Song(1, 'Other', 'A', 'rock', 'melancholic', .8, 100, .3, .3, .1)
    engine = ReliabilityEngine([song])
    result = confirmed_request(engine, 'happy jazz acoustic tired')
    assert result.validation.evaluated
    assert result.final_match_rate == result.confidence == 0.
    assert result.validation.preference_coverage == 0.
    assert len(result.optimization_steps) == 3
    assert result.confidence_low_reason is not None
    # Existing configurable thresholds still control evaluated requests.
    without_retries = confirmed_request(engine, 'happy jazz', min_match_rate=0.)
    assert without_retries.optimization_steps == []


def test_diagnostics_distinguish_no_complete_matches_and_zero_box_alternatives():
    songs = [
        Song(1, 'Some boxes', 'A', 'jazz', 'happy', .4, 80, .8, .5, .8),
        Song(2, 'No boxes', 'B', 'metal', 'melancholic', .9, 100, .2, .5, .1),
    ]
    result = confirmed_request(ReliabilityEngine(songs), 'happy pop tired acoustic', k=5)
    reason = result.confidence_low_reason
    assert 'No complete matches are available in this catalog.' in reason
    assert '0 of 2 catalog songs' in reason
    assert 'Returning 2 of 5 requested recommendations' in reason
    assert 'Complete matches: 0; partial matches: 1' in reason
    assert 'alternatives matching none of the requested preferences: 1' in reason
    assert 'conflict' not in reason.lower()


def test_diagnostics_compare_available_matches_with_requested_count():
    songs = [
        Song(1, 'Complete', 'A', 'jazz', 'relaxed', .3, 80, .4, .5, .8),
        Song(2, 'Partial', 'B', 'jazz', 'melancholic', .3, 80, .4, .5, .8),
        Song(3, 'Another partial', 'C', 'pop', 'relaxed', .3, 80, .4, .5, .8),
    ]
    result = confirmed_request(ReliabilityEngine(songs), 'chill jazz acoustic', k=5)
    reason = result.confidence_low_reason
    assert '1 of 3 catalog songs' in reason
    assert 'Too few complete matches' in reason
    assert 'requested 5 recommendations' in reason
    assert 'Returning 3 of 5 requested recommendations' in reason
    assert 'Complete matches: 1; partial matches: 2' in reason
    assert 'conflict' not in reason.lower()


def test_diagnostics_count_all_four_preferences_and_related_moods():
    from dataclasses import replace
    full = Song(1, 'Full', 'A', 'jazz', 'relaxed', .3, 80, .5, .5, .8)
    songs = [full, replace(full, id=2, genre='pop'), replace(full, id=3, mood='melancholic'),
             replace(full, id=4, energy=.9), replace(full, id=5, acousticness=.2)]
    result = confirmed_request(ReliabilityEngine(songs), 'chill jazz acoustic')
    assert result.validation.total_matches == 1
    assert '1 of 5 catalog songs' in result.confidence_low_reason
    assert 'Complete matches: 1; partial matches: 4' in result.confidence_low_reason


def test_three_matching_songs_are_not_mislabeled_conflicting():
    from dataclasses import replace
    full = Song(1, 'Full', 'A', 'jazz', 'relaxed', .3, 80, .5, .5, .8)
    songs = [replace(full, id=i) for i in range(3)]
    engine = ReliabilityEngine(songs)
    result = confirmed_request(engine, 'chill jazz acoustic', k=2)
    assert result.confidence_low_reason is None
    reason = engine._diagnose_low_confidence('chill jazz acoustic', result.recommendations,
                                            result.validation, requested_count=2)
    assert '3 of 3 catalog songs' in reason
    assert 'enough complete matches' in reason
    assert 'Complete matches: 2; partial matches: 0' in reason
    assert 'conflict' not in reason.lower()


def test_diagnostic_threshold_is_still_strictly_below_point_four():
    from dataclasses import replace
    full = Song(1, 'Full', 'A', 'jazz', 'happy', .4, 80, .8, .5, .8)
    songs = [replace(full, id=i, genre='jazz' if i < 2 else 'pop') for i in range(5)]
    engine = ReliabilityEngine(songs)
    boundary = confirmed_request(engine, 'happy jazz', k=5)
    assert boundary.final_match_rate == .4
    assert boundary.confidence_low_reason is None
    custom = confirmed_request(engine, 'happy jazz', k=5, min_acceptable_confidence=.41)
    assert custom.final_match_rate == .4
    assert 'Too few complete matches' in custom.confidence_low_reason
    assert 'Complete matches: 2; partial matches: 3' in custom.confidence_low_reason
