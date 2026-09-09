"""Field-by-field CLI review; never call the scorer from this module."""
from src.preferences import GENRE_KEYWORDS, MOOD_KEYWORDS, PreferenceReviewRequired


class ReviewCancelled(Exception):
    pass


def ask(prompt):
    value = input(prompt).strip().lower()
    if value in ['cancel', 'quit', 'x']:
        raise ReviewCancelled()
    return value


def pick_values(label, options, current):
    value = ask(f'{label}: comma-separated numbers; any/none to clear; Enter to keep > ')
    if not value:
        return current
    if value in ['any', 'none']:
        return []
    try:
        indices = [int(part.strip()) for part in value.split(',')]
        if not indices or any(i < 1 or i > len(options) for i in indices):
            raise ValueError()
        return list(dict.fromkeys(options[i - 1] for i in indices))
    except ValueError:
        raise ValueError('Use only the numbered choices shown above.')


def edit_choices(draft, category):
    options = list(GENRE_KEYWORDS if category == 'genre' else MOOD_KEYWORDS)
    print('Choices: ' + '; '.join(f'{i}. {v}' for i, v in enumerate(options, 1)))
    checks = draft.constraints[category]
    allowed = [v for c in checks for v in c.get(f'{category}_any', [])]
    excluded = [v for c in checks for v in c.get(f'{category}_not', [])]
    allowed = pick_values('Allowed alternatives (OR)', options, allowed)
    excluded = pick_values('Excluded values (never recommended)', options, excluded)
    draft.set_choices(category, allowed, excluded)


def edit_energy(draft):
    print('1. Any  2. Sleepy (0–0.30)  3. Low (0–0.45)  4. Medium (0.45–0.70)  5. High (0.70–1)  6. Custom range')
    choice = ask('Energy choice > ')
    ranges = {'1': (None, None), '2': (None, .3), '3': (None, .45), '4': (.45, .7), '5': (.7, None)}
    if choice == '6':
        lower = ask('Minimum 0–1 (Enter for no minimum) > ')
        upper = ask('Maximum 0–1 (Enter for no maximum) > ')
        draft.set_energy(float(lower) if lower else None, float(upper) if upper else None)
    elif choice in ranges:
        draft.set_energy(*ranges[choice])
    else:
        raise ValueError('Choose an energy option from 1 through 6.')


def review_preferences(draft):
    """Return an immutable confirmation only after explicit user confirmation."""
    try:
        while True:
            print('\n' + draft.summary())
            print('Edit: 1 genre, 2 mood, 3 energy, 4 acousticness; 5 clarify unsupported wording/no preferences; c confirm; x cancel')
            choice = ask('Review action > ')
            try:
                if choice in ['1', '2']:
                    edit_choices(draft, 'genre' if choice == '1' else 'mood')
                elif choice == '3':
                    edit_energy(draft)
                elif choice == '4':
                    print('1. Any  2. Prefer acoustic  3. Prefer non-acoustic  4. Exclude acoustic  5. Exclude non-acoustic')
                    value = ask('Acousticness choice > ')
                    options = {'1': (None, False), '2': (True, False), '3': (False, False), '4': (False, True), '5': (True, True)}
                    if value not in options: raise ValueError('Choose 1 through 5.')
                    draft.set_acoustic(*options[value])
                elif choice == '5':
                    print('Unsupported wording cannot be interpreted automatically. You can edit fields 1–4 to express what you want.')
                    for message in draft.unrecognized: print(message)
                    print('1. Explicitly omit unsupported wording and accept the displayed fields (profile-based suggestions if all are any)')
                    print('2. Return to field editing')
                    value = ask('Clarification choice > ')
                    if value == '1': draft.omit_unrecognized()
                    elif value != '2': raise ValueError('Choose 1 or 2.')
                elif choice == 'c':
                    try:
                        return draft.confirm()
                    except PreferenceReviewRequired:
                        print('Please resolve the clarification items before confirming. Use the numbered editors; your other choices are saved.')
                else:
                    print('Choose an editor, c to confirm, or x to cancel. Enter alone does not confirm.')
            except ValueError as error:
                print(f'Change not applied: {error}')
    except (ReviewCancelled, EOFError, KeyboardInterrupt):
        print('\nRequest cancelled. No songs were scored.')
        return None
