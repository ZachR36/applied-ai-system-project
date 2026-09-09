"""Verify metric presentation in both user-facing CLI modes."""

from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
from src.main import display_recommendations_with_reliability, interactive_mode
from src.recommender import Song


def capture_modes(request, songs):
    demo = StringIO()
    review_actions = ['5', '1', 'c'] if request == 'surprise me' else ['c']
    with patch('builtins.input', side_effect=review_actions), redirect_stdout(demo):
        display_recommendations_with_reliability('Example', request, songs)
    interactive = StringIO()
    with patch('builtins.input', side_effect=[request, *review_actions, 'quit']), redirect_stdout(interactive):
        interactive_mode(songs)
    return demo.getvalue(), interactive.getvalue()


def test_cli_unknown_request_labels_unvalidated_suggestions():
    song = Song(1, 'Example Song', 'A', 'pop', 'happy', .8, 100, .8, .5, .2)
    for output in capture_modes('surprise me', [song]):
        assert 'Example Song' in output
        assert 'Not evaluated—no supported preferences recognized' in output
        assert 'Unvalidated suggestions' in output
        assert '%' not in output
        assert 'confidence' not in output.lower()
        assert 'Error processing request' not in output


def test_cli_reports_complete_match_and_partial_coverage_separately():
    song = Song(1, 'Three boxes', 'A', 'jazz', 'happy', .4, 80, .7, .5, .8)
    for output in capture_modes('happy pop tired acoustic', [song]):
        assert 'Complete-match rate: 0.0%' in output
        assert 'Preference coverage: 75.0%' in output
        assert '0 of 1 songs match all recognized preferences' in output
        assert 'Similarity score:' in output
        assert 'confidence' not in output.lower()
        assert 'Error processing request' not in output


def test_both_cli_modes_show_no_match_catalog_explanation():
    song = Song(1, 'Partial', 'A', 'jazz', 'happy', .4, 80, .7, .5, .8)
    for output in capture_modes('happy pop tired acoustic', [song]):
        assert 'No complete matches are available in this catalog.' in output
        assert 'Returning 1 of 5 requested recommendations' in output
        assert 'Complete matches: 0; partial matches: 1' in output
        assert 'Error processing request' not in output


def test_both_cli_modes_show_empty_catalog_diagnostic():
    for output in capture_modes('happy jazz', []):
        assert 'The catalog is empty; no recommendations are available.' in output
        assert '0 of 0 songs match' in output
        assert 'Error processing request' not in output


def test_full_demo_requires_confirmation_for_each_request():
    from src.main import main, USER_REQUESTS
    song = Song(1, 'Demo', 'A', 'pop', 'happy', .4, 80, .7, .5, .8)
    output = StringIO()
    actions = [action for _ in USER_REQUESTS for action in ['c', '']] + ['n']
    with patch('src.main.load_songs', return_value=[song]), \
         patch('builtins.input', side_effect=actions), redirect_stdout(output):
        main()
    assert output.getvalue().count('Review preferences (nothing has been scored yet):') == len(USER_REQUESTS)
    assert output.getvalue().count('TOP RECOMMENDATIONS:') == len(USER_REQUESTS)


def test_cancelling_one_request_does_not_score_it_or_block_the_next():
    from src.recommender import recommend_songs
    song = Song(1, 'Demo', 'A', 'pop', 'happy', .4, 80, .7, .5, .8)
    with patch('builtins.input', side_effect=['happy jazz', 'x', 'happy pop', 'c', 'quit']), \
         patch('src.reliability_engine.recommend_songs', wraps=recommend_songs) as scorer, \
         redirect_stdout(StringIO()):
        interactive_mode([song])
    assert scorer.call_count == 1
