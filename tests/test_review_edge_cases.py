"""Interrupted edits and confirmation must preserve explicit user intent."""
from copy import deepcopy
from unittest.mock import patch
import pytest
from src.preference_ui import review_preferences
from src.preferences import parse_preferences, PreferenceReviewRequired, GENRE_KEYWORDS
from src.recommender import Song
from src.validator import evaluate_song, is_excluded


@pytest.mark.parametrize('interruption', [EOFError, KeyboardInterrupt])
@pytest.mark.parametrize('prefix', [[], ['1'], ['3', '6', '.2'], ['4']])
def test_interrupted_review_does_not_confirm_or_partially_apply_edit(interruption, prefix, capsys):
    draft = parse_preferences('happy pop tired')
    before = deepcopy(draft.constraints)
    with patch('builtins.input', side_effect=[*prefix, interruption()]):
        assert review_preferences(draft) is None
    assert draft.constraints == before
    assert 'Request cancelled' in capsys.readouterr().out


@pytest.mark.parametrize('lower,upper', [('nan', '.5'), ('.9', '.1'), ('-.1', '.5'), ('.1', 'inf'), ('abc', '.5')])
def test_bad_custom_range_can_be_corrected_without_restarting(lower, upper, capsys):
    draft = parse_preferences('happy pop tired')
    with patch('builtins.input', side_effect=['3', '6', lower, upper, '3', '6', '.2', '.4', 'c']):
        confirmed = review_preferences(draft)
    assert 'Change not applied' in capsys.readouterr().out
    assert confirmed.constraints['genre'][0]['genre_any'] == ['pop']
    assert confirmed.constraints['mood'][0]['mood_any'] == ['happy']
    assert .2 <= confirmed.profile.target_energy <= .4
    song = Song(1, 'Example', 'A', 'pop', 'happy', .2, 100, .5, .5, .5)
    for energy, expected in [(.1999, False), (.2, True), (.4, True), (.4001, False)]:
        song.energy = energy
        assert evaluate_song(song, confirmed.constraints).complete is expected


def test_invalid_exclusion_choice_does_not_apply_pending_genre_change(capsys):
    draft = parse_preferences('pop')
    before = deepcopy(draft.constraints)
    jazz = str(list(GENRE_KEYWORDS).index('jazz') + 1)
    with patch('builtins.input', side_effect=['1', jazz, '999', 'c']):
        confirmed = review_preferences(draft)
    assert confirmed.constraints == before
    assert 'Change not applied' in capsys.readouterr().out


def test_omitting_unsupported_wording_does_not_clear_energy_conflict():
    draft = parse_preferences('high energy but low energy')
    draft.omit_unrecognized()
    with pytest.raises(PreferenceReviewRequired):
        draft.confirm()
    assert 'energy' in draft.issues()


def test_clearing_last_preference_requires_acceptance_of_unvalidated_suggestions():
    draft = parse_preferences('pop')
    draft.set_choices('genre')
    with pytest.raises(PreferenceReviewRequired):
        draft.confirm()
    draft.omit_unrecognized()
    assert not any(draft.confirm().constraints.values())


def test_mutating_snapshot_accessors_cannot_change_confirmed_preferences():
    confirmed = parse_preferences('happy pop').confirm()
    confirmed.constraints['genre'][0]['genre_any'].append('metal')
    confirmed.profile.favorite_genre = 'metal'
    assert confirmed.constraints['genre'][0]['genre_any'] == ['pop']
    assert confirmed.profile.favorite_genre == 'pop'


@pytest.mark.parametrize('acoustic,excluded', [(.6, False), (.600001, True)])
def test_hard_acoustic_exclusion_uses_same_boundary_as_validation(acoustic, excluded):
    draft = parse_preferences('pop')
    draft.set_acoustic(False, exclude_opposite=True)
    song = Song(1, 'Example', 'A', 'pop', 'happy', .5, 100, .5, .5, acoustic)
    constraints = draft.confirm().constraints
    assert is_excluded(song, constraints) is excluded
    assert evaluate_song(song, constraints).complete is (not excluded)
