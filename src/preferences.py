"""Parse text into an editable draft; scoring requires an explicit confirmation."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from copy import deepcopy
import json
import math
import re
from src.recommender import UserProfile, _similar_mood

GENRE_KEYWORDS = {
    'pop': ['pop', 'mainstream'],
    'indie pop': ['indie pop', 'indie-pop'],
    'lofi': ['lofi', 'lo-fi', 'chill hop'],
    'rock': ['rock', 'hard rock'],
    'metal': ['metal', 'heavy metal'],
    'jazz': ['jazz', 'smooth jazz'],
    'electronic': ['electronic', 'edm', 'synth'],
    'classical': ['classical', 'orchestral'],
    'country': ['country'],
    'hip-hop': ['hip-hop', 'hip hop', 'rap'],
    'study': ['study'],
}
MOOD_KEYWORDS = {
    'happy': ['happy', 'cheerful', 'joyful', 'upbeat'],
    'chill': ['chill', 'relaxing', 'relaxed', 'calm', 'mellow', 'peaceful', 'gentle'],
    'aggressive': ['aggressive', 'intense', 'angry'],
    'melancholic': ['sad', 'melancholic', 'depressed'],
    'focused': ['focused', 'concentrating', 'productive', 'concentration'],
    'energetic': ['energetic', 'pumped', 'excited', 'active', 'lively', 'bouncy'],
    'playful': ['playful'],
}
INTENT_KEYWORDS = {
    # Energy level
    'upbeat': {'energy_min': 0.7, 'category': 'energy'},
    'energetic': {'energy_min': 0.7, 'category': 'energy'},
    'high energy': {'energy_min': 0.7, 'category': 'energy'},
    'intense': {'energy_min': 0.75, 'category': 'energy'},
    'fast': {'energy_min': 0.7, 'category': 'energy'},
    'pumped': {'energy_min': 0.75, 'category': 'energy'},

    'chill': {'energy_max': 0.5, 'category': 'energy'},
    'relaxing': {'energy_max': 0.5, 'category': 'energy'},
    'calm': {'energy_max': 0.5, 'category': 'energy'},
    'slow': {'energy_max': 0.45, 'category': 'energy'},
    'tired': {'energy_max': 0.45, 'category': 'energy'},
    'exhausted': {'energy_max': 0.45, 'category': 'energy'},
    'sleepy': {'energy_max': 0.3, 'category': 'energy'},
    'mellow': {'energy_max': 0.5, 'category': 'energy'},

    # Mood
    'happy': {'mood': 'happy', 'category': 'mood'},
    'cheerful': {'mood': 'happy', 'category': 'mood'},
    'joyful': {'mood': 'happy', 'category': 'mood'},
    'sad': {'mood': 'melancholic', 'category': 'mood'},
    'melancholic': {'mood': 'melancholic', 'category': 'mood'},
    'aggressive': {'mood': 'aggressive', 'category': 'mood'},
    'intense mood': {'mood': 'aggressive', 'category': 'mood'},

    # Acoustic preference
    'acoustic': {'likes_acoustic': True, 'category': 'acoustic'},
    'unplugged': {'likes_acoustic': True, 'category': 'acoustic'},
    'natural': {'likes_acoustic': True, 'category': 'acoustic'},
    'electronic': {'likes_acoustic': False, 'category': 'acoustic'},
    'synth': {'likes_acoustic': False, 'category': 'acoustic'},
    'digital': {'likes_acoustic': False, 'category': 'acoustic'},
}

# Include energy vocabulary already supported by the preference parser.
for word in ['workout', 'gym']:
    INTENT_KEYWORDS[word] = {'energy_min': .7, 'category': 'energy'}
for word in ['low energy', 'low-energy']:
    INTENT_KEYWORDS[word] = {'energy_max': .45, 'category': 'energy'}
for word in ['peaceful', 'gentle']:
    INTENT_KEYWORDS[word] = {'energy_max': .5, 'category': 'energy'}
for word in ['active', 'lively', 'bouncy']:
    INTENT_KEYWORDS[word] = {'energy_min': .6, 'category': 'energy'}

GENRE_KEYWORDS['acoustic'] = []  # Selectable explicitly; the adjective is a feature.
INTENT_KEYWORDS.update({
    'high-energy': {'energy_min': .7, 'category': 'energy'},
    'medium energy': {'energy_min': .45, 'energy_max': .7, 'category': 'energy'},
    'medium-energy': {'energy_min': .45, 'energy_max': .7, 'category': 'energy'},
    'loud': {'energy_min': .7, 'category': 'energy'},
    'non-acoustic': {'likes_acoustic': False, 'hard': True, 'category': 'acoustic'},
    'non acoustic': {'likes_acoustic': False, 'hard': True, 'category': 'acoustic'},
})


def empty_constraints():
    return {name: [] for name in ['genre', 'mood', 'energy', 'acoustic']}


class PreferenceReviewRequired(ValueError):
    def __init__(self, draft):
        self.draft = draft
        super().__init__('Review, clarify, and explicitly confirm preferences before scoring.')


@dataclass(frozen=True)
class ConfirmedPreferences:
    request: str
    constraints_json: str
    profile_values: Tuple[str, str, float, bool]
    omitted_text: Tuple[str, ...] = ()

    @property
    def constraints(self):
        return json.loads(self.constraints_json)

    @property
    def profile(self):
        return UserProfile(*self.profile_values)


@dataclass
class PreferenceDraft:
    request: str
    constraints: Dict = field(default_factory=empty_constraints)
    keywords: List[str] = field(default_factory=list)
    questions: Dict[str, str] = field(default_factory=dict)
    unrecognized: List[str] = field(default_factory=list)
    omitted_text: List[str] = field(default_factory=list)
    default_profile: Optional[UserProfile] = None
    defaults_accepted: bool = False

    def set_choices(self, category, allowed=(), excluded=()):
        vocabulary = GENRE_KEYWORDS if category == 'genre' else MOOD_KEYWORDS if category == 'mood' else None
        if vocabulary is None:
            raise ValueError('Choose genre or mood.')
        allowed, excluded = list(dict.fromkeys(allowed)), list(dict.fromkeys(excluded))
        if any(value not in vocabulary for value in allowed + excluded):
            raise ValueError('Select values from the displayed choices.')
        if set(allowed) & set(excluded):
            raise ValueError('The same preference cannot be allowed and excluded.')
        self.constraints[category] = ([{f'{category}_any': allowed, f'{category}_not': excluded,
                                      'category': category}] if allowed or excluded else [])
        self.questions.pop(category, None)

    def set_energy(self, minimum=None, maximum=None):
        bounds = [value for value in [minimum, maximum] if value is not None]
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in bounds):
            raise ValueError('Energy bounds must be finite numbers between 0 and 1.')
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError('Minimum energy cannot exceed maximum energy.')
        self.constraints['energy'] = []
        if minimum is not None:
            self.constraints['energy'].append({'energy_min': minimum, 'category': 'energy'})
        if maximum is not None:
            self.constraints['energy'].append({'energy_max': maximum, 'category': 'energy'})
        self.questions.pop('energy', None)

    def set_acoustic(self, preference=None, exclude_opposite=False):
        if preference is not None and not isinstance(preference, bool):
            raise ValueError('Choose any, acoustic, or non-acoustic.')
        self.constraints['acoustic'] = ([] if preference is None else
            [{'likes_acoustic': preference, 'hard': bool(exclude_opposite), 'category': 'acoustic'}])
        self.questions.pop('acoustic', None)

    def omit_unrecognized(self):
        """Explicit user choice; never silently discard unsupported parts."""
        self.omitted_text.extend(self.unrecognized)
        self.unrecognized.clear()
        self.questions.pop('wording', None)
        self.questions.pop('unspecified', None)
        self.defaults_accepted = True

    def issues(self):
        issues = dict(self.questions)
        energy = self.constraints['energy']
        low = max((c.get('energy_min', 0.) for c in energy), default=0.)
        high = min((c.get('energy_max', 1.) for c in energy), default=1.)
        if low > high:
            issues['energy'] = 'High and low energy bounds conflict. Choose an energy range.'
        for category in ['genre', 'mood']:
            checks = self.constraints[category]
            allowed = [v for c in checks for v in c.get(f'{category}_any', [])]
            excluded = [v for c in checks for v in c.get(f'{category}_not', [])]
            if set(allowed) & set(excluded):
                issues[category] = 'An option is both allowed and excluded. Edit this field.'
            if allowed and category == 'mood' and all(
                any(a == e or _similar_mood(a, e) for e in excluded) for a in allowed
            ):
                issues[category] = 'All allowed moods are excluded by related mood rules. Edit this field.'
        if len({c['likes_acoustic'] for c in self.constraints['acoustic']}) > 1:
            issues['acoustic'] = 'Acoustic and non-acoustic requirements conflict. Choose one or any.'
        if self.unrecognized:
            issues['wording'] = 'Unsupported or unclear wording: ' + '; '.join(self.unrecognized)
        if not any(self.constraints.values()) and not self.defaults_accepted:
            issues['unspecified'] = 'Choose preferences, or explicitly accept unvalidated profile-based suggestions.'
        return issues

    def similarity_profile(self):
        base = self.default_profile or UserProfile('pop', 'happy', .5, False)
        genre, mood = base.favorite_genre, base.favorite_mood
        for category in ['genre', 'mood']:
            allowed = [v for c in self.constraints[category] for v in c.get(f'{category}_any', [])]
            if allowed:
                if category == 'genre': genre = allowed[0]
                else: mood = allowed[0]
        energy = base.target_energy
        lower = max((c.get('energy_min', 0.) for c in self.constraints['energy']), default=0.)
        upper = min((c.get('energy_max', 1.) for c in self.constraints['energy']), default=1.)
        if self.constraints['energy']:
            # Clamp the existing target into the confirmed range.
            if upper <= .3: energy = min(.25, upper)
            elif upper <= .5: energy = min(.4, upper)
            elif lower >= .6: energy = max(.8, lower)
            energy = min(upper, max(lower, energy))
        acoustic = self.constraints['acoustic'][0]['likes_acoustic'] if self.constraints['acoustic'] else base.likes_acoustic
        return UserProfile(genre, mood, energy, acoustic)

    def confirm(self):
        if self.issues():
            raise PreferenceReviewRequired(self)
        profile = self.similarity_profile()
        return ConfirmedPreferences(self.request, json.dumps(self.constraints, sort_keys=True),
                                    (profile.favorite_genre, profile.favorite_mood, profile.target_energy,
                                     profile.likes_acoustic), tuple(self.omitted_text))

    def summary(self):
        lines = ['Review preferences (nothing has been scored yet):']
        for number, category in enumerate(['genre', 'mood'], 1):
            allowed = [v for c in self.constraints[category] for v in c.get(f'{category}_any', [])]
            excluded = [v for c in self.constraints[category] for v in c.get(f'{category}_not', [])]
            lines.append(f"{number}. {category.title()}: {' OR '.join(allowed) or 'any'}; exclude: {', '.join(excluded) or 'none'}")
        energy = self.constraints['energy']
        lower = max((c.get('energy_min', 0.) for c in energy), default=0.)
        upper = min((c.get('energy_max', 1.) for c in energy), default=1.)
        lines.append(f"3. Energy: {f'{lower:.2f}–{upper:.2f}' if energy else 'any'}")
        acoustic = self.constraints['acoustic']
        options = [('acoustic' if c['likes_acoustic'] else 'non-acoustic') +
                   (' only (exclude opposite)' if c.get('hard') else ' preferred') for c in acoustic]
        lines.append('4. Acousticness: ' + (' AND '.join(options) or 'any'))
        lines.append('Related moods count as matches. Explicit exclusions are never recommended.')
        if self.omitted_text:
            lines.append('Explicitly omitted: ' + '; '.join(self.omitted_text))
        for key, message in self.issues().items():
            lines.append(f'Clarify {key}: {message}')
        if not any(self.constraints.values()):
            lines.append('No requirements: any suggestions would be unvalidated and profile-based.')
        return '\n'.join(lines)


def parse_preferences(text, default_profile=None):
    """Conservative phrase parser. Unsupported scope/words require review."""
    draft = PreferenceDraft(text, default_profile=deepcopy(default_profile))
    normalized = text.lower().replace('’', "'")
    rules = {}
    for category, mapping in [('genre', GENRE_KEYWORDS), ('mood', MOOD_KEYWORDS)]:
        for target, phrases in mapping.items():
            for phrase in phrases:
                rules.setdefault(phrase, []).append((category, target))
    for phrase, check in INTENT_KEYWORDS.items():
        if check['category'] != 'mood':
            rules.setdefault(phrase, []).append((check['category'], check))
    pattern = r'(?<!\w)(?:' + '|'.join(re.escape(p) for p in sorted(rules, key=len, reverse=True)) + r')(?!\w)'
    matches = list(re.finditer(pattern, normalized))
    positives = {'genre': [], 'mood': []}; negatives = {'genre': [], 'mood': []}
    occurrences = {'genre': [], 'mood': []}
    negated = False; previous_end = 0; previous_categories = set(); previously_negated = False
    for match in matches:
        gap = normalized[previous_end:match.start()]
        resets_scope = bool(re.search(r'\bbut\b|[.;!?]|\b(?:i want|i like|i need)\b', gap))
        if resets_scope:
            negated = False
        explicit_negation = bool(re.search(r"\b(?:no|not|without|avoid|except|don't want|don't like|do not want|do not like)\b|anything but", gap))
        if explicit_negation:
            negated = True
        phrase = match.group()
        categories = {category for category, _ in rules[phrase]}
        if negated and previously_negated and not resets_scope and not explicit_negation and categories != previous_categories:
            for category in categories | previous_categories:
                draft.questions[category] = 'Negation spans different fields; clarify each affected field.'
        draft.keywords.append(phrase)
        for category, value in rules[phrase]:
            if category in positives:
                (negatives if negated else positives)[category].append(value)
                if not negated: occurrences[category].append(match.span())
            elif category == 'acoustic':
                # Excluding a genre doesn't imply a preference for acoustic music.
                if negated and any(c == 'genre' for c, _ in rules[phrase]):
                    continue
                check = value.copy()
                if negated:
                    check['likes_acoustic'] = not check['likes_acoustic']
                    check['hard'] = True
                draft.constraints['acoustic'].append(check)
            elif negated:
                draft.questions['energy'] = 'Negated energy is ambiguous. Choose a range in Energy.'
            else:
                draft.constraints['energy'].append(value.copy())
        previous_end = match.end()
        previous_categories = categories
        previously_negated = negated
    for category in positives:
        allowed = list(dict.fromkeys(positives[category])); excluded = list(dict.fromkeys(negatives[category]))
        if allowed or excluded:
            draft.constraints[category] = [{f'{category}_any': allowed, f'{category}_not': excluded, 'category': category}]
        if len(allowed) > 1:
            spans = occurrences[category]
            between = normalized[spans[0][1]:spans[-1][0]]
            compatible = category == 'mood' and all(a == b or _similar_mood(a, b) for a in allowed for b in allowed)
            if (not re.search(r'\bor\b', between) and not compatible) or (re.search(r'\bor\b', between) and re.search(r'\band\b', between)):
                draft.questions[category] = 'Multiple values were mentioned. Choose allowed alternatives explicitly.'
    # An OR spanning categories cannot be represented as independent fields.
    for first, second in zip(matches, matches[1:]):
        if re.search(r'\bor\b', normalized[first.end():second.start()]):
            first_categories = {c for c, _ in rules[first.group()]}
            second_categories = {c for c, _ in rules[second.group()]}
            if first_categories != second_categories:
                for category in first_categories | second_categories:
                    draft.questions[category] = 'An OR spans different fields. Choose this field explicitly.'
    if re.search(r'\b(?:not only|not necessarily|maybe|perhaps|unless|rather than|more than|less than)\b', normalized):
        draft.unrecognized.append('Conditional, uncertain, or comparative wording needs explicit field choices.')
    if re.search(r'\b(?:music|songs?|tracks?)\s+(?:like|by)\b|\bsounds? like\b', normalized):
        draft.unrecognized.append('Artist/reference matching is unsupported; choose style fields or explicitly omit it.')
    consumed = set(i for match in matches for i in range(*match.span()))
    remainder = ''.join(' ' if i in consumed else c for i, c in enumerate(normalized))
    scaffolding = set("any mood i i'm im am want wants would could can you me my some music song songs track tracks playlist please like likes need prefer listen listening to for the a an that's that is are and or but also with sounds stuff right now really very in of it do don't not no without avoid except anything give get make play this style feel feeling today thank thanks more as".split())
    unknown = sorted(set(re.findall(r"[\w]+(?:'[\w]+)?", remainder)) - scaffolding)
    if unknown:
        draft.unrecognized.append('Unrecognized words: ' + ', '.join(unknown))
    return draft
