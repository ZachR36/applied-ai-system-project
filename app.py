"""Streamlit entry point for GrooveMatch: streamlit run app.py."""
from copy import deepcopy
from pathlib import Path
import json

import streamlit as st
from src.main import USER_REQUESTS
from src.preferences import PreferenceDraft, GENRE_KEYWORDS, MOOD_KEYWORDS, parse_preferences
from src.recommender import load_songs
from src.reliability_engine import ReliabilityEngine

CATALOG_PATH = Path(__file__).resolve().parent / 'data' / 'songs.csv'
ACOUSTIC_OPTIONS = {
    'Any': (None, False),
    'Prefer acoustic': (True, False),
    'Prefer non-acoustic': (False, False),
    'Exclude acoustic': (False, True),
    'Exclude non-acoustic': (True, True),
}


def clear_editor(prefix):
    for key in list(st.session_state):
        if key.startswith(prefix + ':'):
            del st.session_state[key]


def preference_editor(original, prefix):
    """Build a candidate from visible controls; unresolved questions block scoring."""
    draft = deepcopy(original)
    st.caption('Leave selections empty for any. Multiple selections mean OR. Related moods count as matches.')
    columns = st.columns(2)
    for column, category, vocabulary in zip(columns, ['genre', 'mood'], [GENRE_KEYWORDS, MOOD_KEYWORDS]):
        with column:
            checks = original.constraints[category]
            allowed = [v for c in checks for v in c.get(category + '_any', [])]
            excluded = [v for c in checks for v in c.get(category + '_not', [])]
            selected = st.multiselect(category.title(), list(vocabulary), default=allowed, key=f'{prefix}:{category}')
            avoided = st.multiselect('Exclude ' + category, list(vocabulary), default=excluded, key=f'{prefix}:exclude_{category}')
            try:
                draft.set_choices(category, selected, avoided)
            except ValueError as error:
                draft.questions[category] = str(error)
    energy_checks = original.constraints['energy']
    lower = max((c.get('energy_min', 0.) for c in energy_checks), default=0.)
    upper = min((c.get('energy_max', 1.) for c in energy_checks), default=1.)
    if lower > upper:
        lower, upper = 0., 1.
    energy_enabled = st.checkbox('Set an energy range', value=bool(energy_checks), key=f'{prefix}:energy_enabled')
    bounds = st.slider('Energy · gentle to intense', 0., 1., (float(lower), float(upper)), .01,
                       key=f'{prefix}:energy', disabled=not energy_enabled)
    st.caption('The range is inclusive. Energy measures intensity; it is not tempo in BPM.')
    if energy_enabled:
        draft.set_energy(*bounds)
    else:
        draft.set_energy()
    acoustic_checks = original.constraints['acoustic']
    acoustic_value = ((acoustic_checks[0]['likes_acoustic'], bool(acoustic_checks[0].get('hard')))
                      if acoustic_checks else (None, False))
    acoustic_default = list(ACOUSTIC_OPTIONS.values()).index(acoustic_value)
    acoustic = st.selectbox('Acousticness', list(ACOUSTIC_OPTIONS), index=acoustic_default, key=f'{prefix}:acoustic')
    draft.set_acoustic(*ACOUSTIC_OPTIONS[acoustic])
    st.caption('Acoustic means acousticness above 0.60. Preferences can have partial-match alternatives; exclusions are never relaxed.')

    # Parsing ambiguities need explicit resolution, even when defaults look plausible.
    for category, question in original.issues().items():
        if category in ['genre', 'mood', 'energy', 'acoustic']:
            st.warning(question)
            if not st.checkbox(f'Use the displayed {category} choices to resolve this question', key=f'{prefix}:resolve_{category}'):
                draft.questions[category] = question
    if original.unrecognized:
        st.warning('Some wording needs your decision: ' + '; '.join(original.unrecognized))
        if st.checkbox('Omit this unsupported wording; use only the preferences shown above', key=f'{prefix}:omit'):
            draft.omit_unrecognized()
    if not any(draft.constraints.values()):
        if st.checkbox('I accept unvalidated suggestions with no preference requirements', key=f'{prefix}:defaults'):
            draft.defaults_accepted = True
    return draft


def show_results(result):
    st.subheader('Your recommendations')
    a, b, c = st.columns(3)
    a.metric('Complete-match rate', f'{result.final_match_rate:.0%}' if result.validation.evaluated else 'Not evaluated')
    b.metric('Preference coverage', f'{result.validation.preference_coverage:.0%}' if result.validation.evaluated else 'Not evaluated')
    c.metric('Songs returned', len(result.recommendations))
    st.caption('Complete-match rate: songs meeting every preference. Coverage: requested categories satisfied across songs. Neither is a probability of satisfaction.')
    if not result.validation.evaluated:
        st.info('Unvalidated suggestions based on the default or supplied profile. No supported preferences were confirmed.')
    if result.confidence_low_reason:
        st.warning(result.confidence_low_reason)
    if not result.recommendations:
        st.info('No eligible songs to display. You can revise your preferences above; explicit exclusions are never relaxed.')
    for rank, ((song, score, reasons), check) in enumerate(zip(result.recommendations, result.validation.song_matches), 1):
        with st.container(border=True):
            st.subheader(f'{rank}. {song.title}')
            st.write(song.artist)
            st.caption(f'{song.genre} · {song.mood} · Energy {song.energy:.2f} · Acousticness {song.acousticness:.2f}')
            if not result.validation.evaluated:
                st.info('Not graded — no confirmed preference requirements')
            elif check.complete:
                st.success(f'Complete match · {check.matched_count}/{check.total_preferences} preferences')
            else:
                st.warning(f'Partial match · {check.matched_count}/{check.total_preferences} preferences' if check.matched_count else
                           f'No preferences matched · 0/{check.total_preferences}')
            for detail in check.details:
                st.write(detail)
            with st.expander(f'Why this song? Similarity score: {score:.3f} / 1.000'):
                for reason in reasons:
                    st.write(reason)
    with st.expander('How this playlist was selected'):
        st.write(f"Selected round {result.selected_iteration}; {len(result.optimization_steps)} re-scoring attempts.")
        st.caption('Complete matches rank first, then the number of preferences met, then similarity. Earlier attempts are retained when they are better.')
        st.dataframe([{'Round': a['iteration'], 'Complete-match rate': a['match_rate'],
                       'Preference coverage': a['preference_coverage'], 'Selected': a['iteration'] == result.selected_iteration}
                      for a in result.attempt_history], hide_index=True)
        st.text('\n'.join(result.decision_log))


def review_and_recommend(original, prefix, engine):
    st.markdown('#### Review your preferences')
    draft = preference_editor(original, prefix)
    count = st.slider('Number of recommendations', 1, 10, 5, key=f'{prefix}:count')
    issues = draft.issues()
    for message in issues.values():
        st.error(message)
    signature = json.dumps({'constraints': draft.constraints, 'issues': issues, 'omitted': draft.omitted_text,
                            'defaults': draft.defaults_accepted, 'request': draft.request, 'count': count}, sort_keys=True)
    st.caption('Clicking Enter confirms the preferences displayed above and starts scoring.')
    if st.button('Enter · get recommendations', type='primary', key=f'{prefix}:submit', disabled=bool(issues)):
        confirmed = draft.confirm()
        with st.spinner('Finding and checking your matches…'):
            result = engine.process_user_request(draft.request, k=count, confirmed_preferences=confirmed)
        st.session_state[f'{prefix}:result'] = (signature, result)
    saved = st.session_state.get(f'{prefix}:result')
    if saved:
        if saved[0] == signature:
            show_results(saved[1])
        else:
            st.info('Preferences changed. Click Enter to confirm and update your recommendations.')


def main():
    st.set_page_config(page_title='GrooveMatch · Music for your moment', page_icon='🎧', layout='centered')
    # Preserve field edits when switching input modes or demo examples.
    # Reassigning non-button widget values detaches them from widget cleanup.
    for key in list(st.session_state):
        if key.startswith(('text:', 'form:', 'demo:')) and not key.endswith(':submit'):
            st.session_state[key] = st.session_state[key]
    st.caption('GROOVEMATCH / EXPLAINABLE MUSIC DISCOVERY')
    st.title('Find music for your moment.')
    st.write('Welcome to GrooveMatch, a content-based music recommender that checks how well each song fits what you asked for. Explore a curated catalog of 100 real recordings, with clear explanations of the matches and compromises.')
    st.write('Describe what you want or choose preferences below. Review your choices, then press Enter to get a playlist. Open the demo first if you’d like a guided example.')
    try:
        songs = load_songs(CATALOG_PATH)
    except (OSError, ValueError, KeyError) as error:
        st.error(f'Unable to load the song catalog: {error}')
        st.stop()
    if not songs:
        st.error('The song catalog is empty. Add songs before requesting recommendations.')
        st.stop()
    engine = ReliabilityEngine(songs)
    with st.expander('See how it works · optional demo', expanded=False):
        example = st.selectbox('Choose an example', list(USER_REQUESTS), key='demo_example')
        st.write(USER_REQUESTS[example])
        st.caption('Load an example, inspect its preferences, then confirm to see its recommendations. You can edit it just like your own request.')
        if st.button('Load this example', key='load_demo'):
            clear_editor('demo')
            st.session_state['demo_draft'] = parse_preferences(USER_REQUESTS[example])
        if 'demo_draft' in st.session_state:
            if st.session_state['demo_draft'].request == USER_REQUESTS[example]:
                review_and_recommend(st.session_state['demo_draft'], 'demo', engine)
            else:
                st.info('Load the selected example to review it.')
    st.divider()
    st.header('Make it yours')
    mode = st.radio('How would you like to choose?', ['Describe in words', 'Pick preferences'], horizontal=True)
    if mode == 'Describe in words':
        text = st.text_area('What do you feel like listening to?', placeholder='For example: happy pop with low energy', key='request_text')
        if st.button('Review my request', key='parse_request'):
            if not text.strip():
                st.warning('Describe what you want to hear first.')
            else:
                clear_editor('text')
                st.session_state['text_draft'] = parse_preferences(text.strip())
        if 'text_draft' in st.session_state:
            if st.session_state['text_draft'].request == text.strip():
                review_and_recommend(st.session_state['text_draft'], 'text', engine)
            else:
                st.info('Your wording changed. Choose Review my request to update the preferences.')
    else:
        review_and_recommend(PreferenceDraft('Preferences selected in the form'), 'form', engine)
    st.divider()
    st.caption('A local recommendation prototype, built with Claude Code. Mood labels are approximate; recommendations come from the bundled catalog. No account or API key required.')


if __name__ == '__main__':
    main()
