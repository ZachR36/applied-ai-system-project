"""Parsing, confirmation gates, and structured revision regression tests."""
from dataclasses import FrozenInstanceError
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
from src.preferences import parse_preferences, PreferenceReviewRequired
from src.preference_ui import review_preferences
from src.reliability_engine import ReliabilityEngine
from src.recommender import Song
from src.validator import evaluate_song


def songs():
    return [Song(1, 'Pop', 'A', 'pop', 'happy', .8, 120, .8, .5, .1),
            Song(2, 'Jazz', 'B', 'jazz', 'chill', .3, 80, .4, .5, .9),
            Song(3, 'Metal', 'C', 'metal', 'aggressive', .9, 130, .3, .5, .1)]


def must_clarify(draft):
    try:
        draft.confirm()
    except PreferenceReviewRequired:
        assert draft.issues()
    else:
        raise AssertionError('Unclear draft was confirmed')


def test_every_raw_request_requires_confirmation_before_scoring():
    engine = ReliabilityEngine(songs())
    for request in ['happy pop', 'pop or jazz', 'surprise me', 'high energy but low energy']:
        with patch('src.reliability_engine.recommend_songs', side_effect=AssertionError('scored too early')):
            try:
                engine.process_user_request(request)
            except PreferenceReviewRequired as error:
                assert error.draft.request == request
            else:
                raise AssertionError('Unconfirmed request reached scoring')


def test_negated_genre_and_or_alternatives():
    draft = parse_preferences('pop or jazz but no metal')
    assert not draft.issues()
    confirmed = draft.confirm()
    checks = [evaluate_song(song, confirmed.constraints) for song in songs()]
    assert [c.complete for c in checks] == [True, True, False]
    result = ReliabilityEngine(songs()).process_user_request(draft.request, confirmed_preferences=confirmed, k=5)
    assert {song.genre for song, _, _ in result.recommendations} == {'pop', 'jazz'}
    assert len(result.recommendations) == 2  # Do not fill with excluded metal.


def test_negation_applies_to_a_list_and_resets_after_but():
    draft = parse_preferences("I don't want metal or rock but I want jazz")
    assert draft.constraints['genre'][0]['genre_not'] == ['metal', 'rock']
    assert draft.constraints['genre'][0]['genre_any'] == ['jazz']
    assert not draft.issues()


def test_non_acoustic_synonyms_are_consistent_and_excluded_tracks_stay_out():
    for request in ['not acoustic', 'no acoustic', 'non-acoustic', 'without acoustic music']:
        draft = parse_preferences(request)
        assert not draft.issues()
        assert draft.constraints['acoustic'][0]['likes_acoustic'] is False
        engine = ReliabilityEngine(songs())
        result = engine.process_user_request(request, confirmed_preferences=draft.confirm(), k=5)
        assert all(song.acousticness <= .6 for song, _, _ in result.recommendations)
        assert result.validation.total_matches == 2


def test_negated_moods_use_related_mood_exclusions():
    draft = parse_preferences('not sad')
    confirmed = draft.confirm()
    sad = Song(4, 'Sad', 'D', 'pop', 'melancholic', .3, 70, .2, .4, .5)
    result = ReliabilityEngine([sad, *songs()]).process_user_request(draft.request, confirmed_preferences=confirmed)
    assert sad.id not in [song.id for song, _, _ in result.recommendations]


def test_contradictions_cannot_be_confirmed_until_field_is_fixed():
    draft = parse_preferences('happy jazz high energy but low energy')
    must_clarify(draft)
    before_genre, before_mood = draft.constraints['genre'].copy(), draft.constraints['mood'].copy()
    draft.set_energy(maximum=.45)
    assert not draft.issues()
    assert draft.constraints['genre'] == before_genre and draft.constraints['mood'] == before_mood
    assert draft.confirm().constraints['energy'][0]['energy_max'] == .45


def test_positive_and_negative_same_genre_require_clarification():
    draft = parse_preferences('pop but no pop')
    must_clarify(draft)
    draft.set_choices('genre', allowed=['jazz'], excluded=['pop'])
    assert not draft.issues()


def test_ambiguous_conjunction_and_cross_field_or_require_edits():
    for request in ['pop and jazz', 'pop or jazz and metal', 'happy or chill', 'pop or happy']:
        must_clarify(parse_preferences(request))


def test_unsupported_artist_and_unrecognized_words_are_not_silently_ignored():
    for request in ['music like Beyoncé', 'play tracks by Metallica', 'something wistful', 'perhaps pop']:
        draft = parse_preferences(request)
        must_clarify(draft)
        assert draft.unrecognized
    draft = parse_preferences('happy music like Beyoncé')
    draft.omit_unrecognized()  # Explicit user decision to omit artist similarity.
    confirmed = draft.confirm()
    assert confirmed.omitted_text
    assert confirmed.constraints['mood']


def test_keyword_boundaries_do_not_match_inside_words():
    draft = parse_preferences('metallic popular fastidious')
    assert not any(draft.constraints.values())
    must_clarify(draft)


def test_negated_energy_requires_an_explicit_range():
    draft = parse_preferences('not high energy')
    assert 'energy' in draft.issues()
    must_clarify(draft)
    draft.set_energy(maximum=.45)
    assert draft.confirm().profile.target_energy <= .45


def test_confirmation_is_a_snapshot_and_does_not_reparse_original_text():
    engine = ReliabilityEngine(songs())
    draft = engine.prepare_request('pop')
    draft.set_choices('genre', allowed=['jazz'])
    confirmed = draft.confirm()
    draft.set_choices('genre', allowed=['metal'])
    assert confirmed.constraints['genre'][0]['genre_any'] == ['jazz']
    result = engine.process_user_request('pop', confirmed_preferences=confirmed, k=1)
    assert result.recommendations[0][0].genre == 'jazz'
    assert result.validation.total_matches == 1
    assert result.confidence_low_reason is None
    try:
        confirmed.request = 'metal'
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError('Confirmation is mutable')


def test_confirmation_from_another_request_is_rejected():
    engine = ReliabilityEngine(songs())
    confirmed = engine.prepare_request('pop').confirm()
    with patch('src.reliability_engine.recommend_songs', side_effect=AssertionError('scored too early')):
        try:
            engine.process_user_request('jazz', confirmed_preferences=confirmed)
        except ValueError:
            pass
        else:
            raise AssertionError('Wrong request confirmation accepted')


def test_edited_constraints_are_used_by_optimizer_and_diagnostics():
    engine = ReliabilityEngine(songs())
    draft = engine.prepare_request('pop')
    draft.set_choices('genre', allowed=['classical'])
    draft.set_acoustic(True)
    confirmed = draft.confirm()
    with patch.object(engine.optimizer, 'suggest_weight_adjustments', wraps=engine.optimizer.suggest_weight_adjustments) as spy:
        result = engine.process_user_request('pop', confirmed_preferences=confirmed, k=3)
    assert spy.call_args.kwargs['constraints'] == confirmed.constraints
    assert result.confidence_low_reason.startswith('0 of 3 catalog songs')
    assert all('classical' in reason for reason in result.validation.reasons)


def test_no_preferences_requires_explicit_choice_before_confirmation():
    draft = parse_preferences('surprise me')
    must_clarify(draft)
    draft.omit_unrecognized()
    result = ReliabilityEngine(songs()).process_user_request('surprise me', confirmed_preferences=draft.confirm())
    assert result.final_match_rate is None and result.optimization_steps == []


def test_review_ui_does_not_score_until_confirmed_and_preserves_other_fields():
    engine = ReliabilityEngine(songs())
    draft = engine.prepare_request('happy pop high energy but low energy')
    output = StringIO()
    # Attempt confirm, edit only energy to low, then confirm again.
    with patch('builtins.input', side_effect=['c', '3', '3', 'c']), redirect_stdout(output), \
         patch('src.reliability_engine.recommend_songs', side_effect=AssertionError('review scored songs')):
        confirmed = review_preferences(draft)
    assert confirmed is not None
    assert confirmed.constraints['genre'][0]['genre_any'] == ['pop']
    assert confirmed.constraints['mood'][0]['mood_any'] == ['happy']
    assert confirmed.constraints['energy'][0]['energy_max'] == .45
    assert 'resolve the clarification items' in output.getvalue()


def test_review_cancellation_and_empty_enter_never_confirm():
    for actions in [['x'], ['', 'x'], ['3', 'cancel']]:
        draft = parse_preferences('happy pop')
        with patch('builtins.input', side_effect=actions), redirect_stdout(StringIO()):
            assert review_preferences(draft) is None


def test_invalid_field_edit_leaves_previous_values_unchanged():
    draft = parse_preferences('happy pop tired')
    before = draft.confirm().constraints
    for action in [lambda: draft.set_energy(float('nan'), .5),
                   lambda: draft.set_energy(.9, .1),
                   lambda: draft.set_choices('genre', allowed=['unknown']),
                   lambda: draft.set_choices('genre', allowed=['pop'], excluded=['pop'])]:
        try: action()
        except ValueError: pass
        else: raise AssertionError('Invalid edit accepted')
        assert draft.constraints == before


def test_negation_across_different_fields_is_not_guessed():
    draft = parse_preferences('no acoustic jazz')
    must_clarify(draft)
    assert 'acoustic' in draft.issues() and 'genre' in draft.issues()
    draft.set_choices('genre', allowed=['jazz'])
    draft.set_acoustic(False, exclude_opposite=True)
    assert not draft.issues()
