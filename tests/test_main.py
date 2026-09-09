"""Verify metric presentation in both user-facing CLI modes."""

from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
from src.main import display_recommendations_with_reliability, interactive_mode
from src.recommender import Song


def capture_modes(request, songs):
    demo = StringIO()
    with redirect_stdout(demo):
        display_recommendations_with_reliability('Example', request, songs)
    interactive = StringIO()
    with patch('builtins.input', side_effect=[request, 'quit']), redirect_stdout(interactive):
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
