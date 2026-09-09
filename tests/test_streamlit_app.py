"""Exercise the web UI through Streamlit's real session and widget runner."""
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from src.recommender import Song

APP = Path(__file__).resolve().parents[1] / 'app.py'
SONGS = [Song(1, 'Quiet pop', 'A', 'pop', 'happy', .3, 100, .7, .5, .2),
         Song(2, 'Loud jazz', 'B', 'jazz', 'chill', .8, 100, .4, .5, .9)]


def start():
    return AppTest.from_file(str(APP), default_timeout=20).run()


def test_web_starts_without_scoring_and_demo_is_optional():
    with patch('src.reliability_engine.recommend_songs', side_effect=AssertionError('scored early')):
        app = start()
    assert not app.exception
    assert app.title[0].value == 'Find music for your moment.'
    assert not app.metric
    assert app.expander[0].label == 'See how it works · optional demo'


def test_form_confirmation_displays_matches_and_hides_stale_results():
    with patch('src.recommender.load_songs', return_value=SONGS):
        app = start()
        app.radio[0].set_value('Pick preferences').run()
        assert app.button(key='form:submit').disabled
        app.multiselect(key='form:genre').set_value(['pop']).run()
        assert not app.metric
        app.button(key='form:submit').click().run()
        assert not app.exception
        assert app.metric[0].value == '50%'
        assert any(s.value == '1. Quiet pop' for s in app.subheader)
        app.multiselect(key='form:genre').set_value(['jazz']).run()
        assert not app.metric
        assert any('Preferences changed' in i.value for i in app.info)


def test_text_can_be_edited_before_confirmation_without_reparsing():
    with patch('src.recommender.load_songs', return_value=SONGS):
        app = start()
        app.text_area[0].set_value('pop').run()
        app.button(key='parse_request').click().run()
        app.multiselect(key='text:genre').set_value(['jazz']).run()
        app.slider(key='text:count').set_value(1).run()
        assert not app.metric
        app.button(key='text:submit').click().run()
        assert not app.exception
        assert app.metric[0].value == '100%'
        assert any(s.value == '1. Loud jazz' for s in app.subheader)
        app.text_area[0].set_value('metal').run()
        assert not app.metric


def test_conflicting_energy_requires_explicit_resolution():
    app = start()
    app.text_area[0].set_value('high energy but low energy').run()
    app.button(key='parse_request').click().run()
    assert app.button(key='text:submit').disabled
    app.slider(key='text:energy').set_value((.2, .4)).run()
    assert app.button(key='text:submit').disabled
    app.checkbox(key='text:resolve_energy').check().run()
    assert not app.button(key='text:submit').disabled
    app.button(key='text:submit').click().run()
    assert not app.exception
    assert app.metric


def test_unsupported_text_requires_explicit_omission():
    app = start()
    app.text_area[0].set_value('happy music like Beyonce').run()
    app.button(key='parse_request').click().run()
    assert app.button(key='text:submit').disabled
    app.checkbox(key='text:omit').check().run()
    assert not app.button(key='text:submit').disabled


def test_demo_loads_only_when_requested_and_requires_confirmation():
    with patch('src.reliability_engine.recommend_songs', side_effect=AssertionError('scored early')):
        app = start()
        app.button(key='load_demo').click().run()
    assert not app.exception
    assert app.button(key='demo:submit')
    assert not app.metric


def test_empty_and_invalid_catalog_are_reported():
    for response in [[], ValueError('CSV row 2: energy out of range')]:
        kwargs = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
        with patch('src.recommender.load_songs', **kwargs):
            app = start()
        assert not app.exception
        assert app.error
        assert not app.radio


def test_no_preferences_need_explicit_acceptance_and_are_ungraded():
    app = start()
    app.radio[0].set_value('Pick preferences').run()
    app.checkbox(key='form:defaults').check().run()
    app.button(key='form:submit').click().run()
    assert not app.exception
    assert app.metric[0].value == 'Not evaluated'
    assert any('Unvalidated suggestions' in i.value for i in app.info)


def test_switching_input_modes_preserves_field_edits():
    app = start()
    app.radio[0].set_value('Pick preferences').run()
    app.multiselect(key='form:genre').set_value(['jazz']).run()
    app.checkbox(key='form:energy_enabled').check().run()
    app.slider(key='form:energy').set_value((.2, .4)).run()
    app.radio[0].set_value('Describe in words').run()
    app.radio[0].set_value('Pick preferences').run()
    assert not app.exception
    assert app.multiselect(key='form:genre').value == ['jazz']
    assert app.slider(key='form:energy').value == (.2, .4)


def test_exclusions_can_leave_no_results_and_show_diagnostics():
    with patch('src.recommender.load_songs', return_value=SONGS):
        app = start()
        app.radio[0].set_value('Pick preferences').run()
        app.multiselect(key='form:exclude_genre').set_value(['pop', 'jazz']).run()
        app.button(key='form:submit').click().run()
        assert not app.exception
        assert app.metric[2].value == '0'
        assert any('explicit exclusions' in w.value for w in app.warning)


def test_overlapping_allowed_and_excluded_genre_blocks_submission():
    app = start()
    app.radio[0].set_value('Pick preferences').run()
    app.multiselect(key='form:genre').set_value(['pop']).run()
    app.multiselect(key='form:exclude_genre').set_value(['pop']).run()
    assert app.button(key='form:submit').disabled
    assert app.error
    app.multiselect(key='form:exclude_genre').set_value([]).run()
    assert not app.button(key='form:submit').disabled


def test_demo_results_do_not_replace_personal_recommendations():
    with patch('src.recommender.load_songs', return_value=SONGS):
        app = start()
        app.radio[0].set_value('Pick preferences').run()
        app.multiselect(key='form:genre').set_value(['pop']).run()
        app.button(key='form:submit').click().run()
        saved = app.session_state['form:result']
        app.button(key='load_demo').click().run()
        app.button(key='demo:submit').click().run()
        assert not app.exception
        assert app.session_state['form:result'] == saved
        assert 'demo:result' in app.session_state
