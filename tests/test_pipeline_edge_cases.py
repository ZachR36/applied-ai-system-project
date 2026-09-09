"""Boundary, exclusion, and state isolation contracts for orchestration."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch
import pytest
from src.recommender import Song, recommend_songs
from src.reliability_engine import ReliabilityEngine
from src.main import main
from tests.review_helpers import confirmed_request

BASE = Song(1, 'Example', 'A', 'pop', 'happy', .4, 100, .5, .5, .2)


def test_exact_retry_target_does_not_retry_but_lower_rate_does():
    songs = [replace(BASE, id=i, genre='pop' if i < 7 else 'jazz') for i in range(10)]
    engine = ReliabilityEngine(songs)
    at_target = confirmed_request(engine, 'pop', k=10, min_match_rate=.7)
    assert at_target.final_match_rate == .7
    assert len(at_target.attempt_history) == 1
    assert at_target.optimization_steps == []
    below_target = confirmed_request(engine, 'pop', k=10, min_match_rate=.71, max_iterations=2)
    assert len(below_target.attempt_history) == 3
    assert len(below_target.optimization_steps) == 2


def test_zero_retry_budget_still_scores_validates_and_explains_once():
    engine = ReliabilityEngine([BASE])
    with patch.object(engine.optimizer, 'suggest_weight_adjustments', side_effect=AssertionError('retry forbidden')):
        result = confirmed_request(engine, 'jazz', max_iterations=0)
    assert len(result.attempt_history) == 1
    assert len(result.recommendations) == 1
    assert result.selected_iteration == 0
    assert result.final_match_rate == 0
    assert 'No complete matches' in result.confidence_low_reason


def test_equal_quality_rounds_keep_first_attempt():
    result = confirmed_request(ReliabilityEngine([BASE]), 'jazz', max_iterations=2)
    assert len(result.attempt_history) == 3
    assert all(a['quality'] == result.attempt_history[0]['quality'] for a in result.attempt_history)
    assert result.selected_iteration == 0


def test_all_excluded_catalog_returns_empty_results_without_relaxing_exclusions():
    engine = ReliabilityEngine([BASE])
    with patch('src.reliability_engine.recommend_songs', wraps=recommend_songs) as scorer:
        result = confirmed_request(engine, 'no pop', max_iterations=2)
    assert result.recommendations == []
    assert result.validation.evaluated and result.final_match_rate == 0
    assert len(result.attempt_history) == 3
    assert all(call.args[1] == [] for call in scorer.call_args_list)
    assert '1 catalog songs were omitted' in result.confidence_low_reason
    assert 'Returning 0 of 5' in result.confidence_low_reason
    assert 'catalog is empty' not in result.confidence_low_reason


def test_exclusions_remain_enforced_during_every_retry():
    excluded = replace(BASE, id=2, genre='metal', energy=.2)
    engine = ReliabilityEngine([replace(BASE, energy=.9), excluded])
    with patch('src.reliability_engine.recommend_songs', wraps=recommend_songs) as scorer:
        result = confirmed_request(engine, 'tired but no metal', k=5)
    assert len(result.optimization_steps) == 3
    for call in scorer.call_args_list:
        assert [s.id for s in call.args[1]] == [1]
    for attempt in result.attempt_history:
        assert [s.id for s, _, _ in attempt['recommendations']] == [1]


def test_returned_history_and_validation_are_independent_of_catalog_and_other_requests():
    catalog = [replace(BASE, energy=.9)]
    original = deepcopy(catalog)
    engine = ReliabilityEngine(catalog)
    first = confirmed_request(engine, 'happy pop tired')
    preserved_round = deepcopy(first.attempt_history[1])
    first.validation.reasons.append('external mutation')
    first.attempt_history[0]['validation'].reasons.append('different mutation')
    first.attempt_history[0]['weights']['energy'] = 999
    first.recommendations[0][0].title = 'Changed'
    assert first.attempt_history[1] == preserved_round
    assert catalog == original
    second = confirmed_request(engine, 'happy pop', k=1)
    assert second.final_match_rate == 1
    assert second.optimization_steps == []
    assert second.attempt_history[0]['weights'] == engine.optimizer.DEFAULT_WEIGHTS
    assert second.recommendations[0][0].title == 'Example'
    assert all('mutation' not in reason for reason in second.validation.reasons)


@pytest.mark.parametrize('failure,expected', [
    (FileNotFoundError('missing'), 'data/songs.csv not found'),
    (ValueError("CSV row 3: energy='2'; expected a finite number between 0 and 1."), "CSV row 3: energy='2'"),
])
def test_cli_load_failure_is_actionable_and_never_starts_review(failure, expected, capsys):
    with patch('src.main.load_songs', side_effect=failure), \
         patch('builtins.input', side_effect=AssertionError('must not ask for preferences')):
        main()
    assert expected in capsys.readouterr().out


def test_cli_empty_catalog_stops_before_review(capsys):
    with patch('src.main.load_songs', return_value=[]), \
         patch('builtins.input', side_effect=AssertionError('must not ask for preferences')):
        main()
    assert 'No songs loaded' in capsys.readouterr().out
