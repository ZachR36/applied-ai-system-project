"""Users can bypass, leave, or complete the optional demo."""
from unittest.mock import patch
import pytest
from src.main import main, USER_REQUESTS
from src.recommender import Song

SONGS = [Song(1, 'Example', 'A', 'pop', 'happy', .4, 100, .5, .5, .2)]


@pytest.mark.parametrize('actions,expected_demos,interactive', [
    (['1'], 0, True),
    (['q'], 0, False),
    (['2', 'r'], 1, True),
    (['2', 'q'], 1, False),
    (['2', '', 'r'], 2, True),
    (['invalid', '', '1'], 0, True),
    (['2', 'invalid', 'r'], 1, True),
    (['2', *([''] * (len(USER_REQUESTS)-1)), 'r'], len(USER_REQUESTS), True),
])
def test_navigation_routes_without_unwanted_profiles(actions, expected_demos, interactive, capsys):
    with patch('src.main.load_songs', return_value=SONGS), \
         patch('builtins.input', side_effect=actions), \
         patch('src.main.display_recommendations_with_reliability') as demo, \
         patch('src.main.interactive_mode') as recommend:
        main()
    assert demo.call_count == expected_demos
    assert recommend.call_count == int(interactive)
    if interactive:
        recommend.assert_called_once_with(SONGS)


def test_cancel_current_demo_profile_then_skip_remaining_profiles(capsys):
    with patch('src.main.load_songs', return_value=SONGS), \
         patch('builtins.input', side_effect=['2', 'x', 'r']), \
         patch('src.main.interactive_mode') as recommend, \
         patch('src.reliability_engine.recommend_songs', side_effect=AssertionError('cancelled demo scored')):
        main()
    recommend.assert_called_once_with(SONGS)
    assert capsys.readouterr().out.count('Review preferences (nothing has been scored yet):') == 1


@pytest.mark.parametrize('interruption', [EOFError, KeyboardInterrupt])
def test_startup_interruption_exits_cleanly(interruption, capsys):
    with patch('src.main.load_songs', return_value=SONGS), \
         patch('builtins.input', side_effect=interruption), \
         patch('src.main.interactive_mode') as recommend:
        main()
    recommend.assert_not_called()
    assert 'Goodbye' in capsys.readouterr().out
