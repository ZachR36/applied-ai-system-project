"""Evaluate explicit preferences independently of similarity scores."""

from typing import List, Tuple, Dict
from dataclasses import dataclass, field
import re
from src.recommender import Song, _similar_mood


@dataclass
class SongMatch:
    song_id: int
    matched_preferences: List[str]
    missed_preferences: List[str]
    details: List[str]

    @property
    def matched_count(self) -> int:
        return len(self.matched_preferences)

    @property
    def total_preferences(self) -> int:
        return self.matched_count + len(self.missed_preferences)

    @property
    def complete(self) -> bool:
        return not self.missed_preferences


@dataclass
class ValidationResult:
    match_rate: float  # Fraction of returned songs satisfying every explicit preference.
    total_matches: int
    total_songs: int
    reasons: List[str]
    keywords_found: List[str]
    song_matches: List[SongMatch] = field(default_factory=list)
    preference_coverage: float = 0.0  # Fraction of requested boxes satisfied across results.


# Acoustic/unplugged describes a feature, not a mandatory genre: acoustic jazz
# can satisfy both jazz and acousticness without being tagged "acoustic".
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
    'focused': ['focused', 'concentrating', 'productive'],
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


def _consolidate_constraints(constraints: Dict) -> Dict:
    """Keep the strictest energy bounds and deduplicate other constraints."""
    result = {key: [] for key in ['genre', 'mood', 'energy', 'acoustic']}
    energy = constraints.get('energy', [])
    lower = [c['energy_min'] for c in energy if 'energy_min' in c]
    upper = [c['energy_max'] for c in energy if 'energy_max' in c]
    if lower:
        result['energy'].append({'energy_min': max(lower), 'category': 'energy'})
    if upper:
        result['energy'].append({'energy_max': min(upper), 'category': 'energy'})
    for key in ['genre', 'mood', 'acoustic']:
        for constraint in constraints.get(key, []):
            if constraint not in result[key]:
                result[key].append(constraint.copy())
    return result


def _occurrences(text: str, phrase: str):
    return re.finditer(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text)


def extract_keywords(user_input: str) -> Tuple[List[str], Dict]:
    """Extract recognized, explicitly stated preferences; never add defaults.

    Negation and arbitrary natural-language reasoning remain unsupported.
    Longest genre phrases win overlaps ("indie pop" is not also "pop").
    """
    text = user_input.lower()
    constraints = {key: [] for key in ['genre', 'mood', 'energy', 'acoustic']}
    keywords = []
    occupied = set()
    genres = sorted(((word, genre) for genre, words in GENRE_KEYWORDS.items()
                     for word in words), key=lambda pair: -len(pair[0]))
    for word, genre in genres:
        for match in _occurrences(text, word):
            span = set(range(*match.span()))
            if span & occupied:
                continue
            occupied.update(span)
            constraints['genre'].append({'genre': genre, 'category': 'genre'})
            if word not in keywords:
                keywords.append(word)
    # Avoid interpreting the "chill" inside the genre alias "chill hop" as mood.
    mood_text = ''.join(' ' if i in occupied else char for i, char in enumerate(text))
    for mood, words in MOOD_KEYWORDS.items():
        for word in words:
            if next(_occurrences(mood_text, word), None):
                constraints['mood'].append({'mood': mood, 'category': 'mood'})
                if word not in keywords:
                    keywords.append(word)
    for word, constraint in INTENT_KEYWORDS.items():
        if constraint['category'] == 'mood':
            continue
        search_text = mood_text if constraint['category'] == 'energy' else text
        if next(_occurrences(search_text, word), None):
            constraints[constraint['category']].append(constraint.copy())
            if word not in keywords:
                keywords.append(word)
    return keywords, constraints


def evaluate_song(song: Song, constraints: Dict) -> SongMatch:
    """One equal-weight box per requested category, regardless of synonyms."""
    constraints = _consolidate_constraints(constraints)
    matched, missed, details = [], [], []
    for category, checks in constraints.items():
        if not checks:
            continue
        if category == 'genre':
            actual = song.genre.lower().replace('indie-pop', 'indie pop')
            passed = all(actual == c['genre'] for c in checks)
            detail = f"Genre {song.genre}; requested: {', '.join(c['genre'] for c in checks)}"
        elif category == 'mood':
            passed = all(song.mood.lower() == c['mood'] or _similar_mood(song.mood, c['mood']) for c in checks)
            detail = f"Mood {song.mood}; requested: {', '.join(c['mood'] for c in checks)} (related moods allowed)"
        elif category == 'energy':
            passed = all(song.energy >= c.get('energy_min', 0.) and song.energy <= c.get('energy_max', 1.) for c in checks)
            bounds = [f">= {c['energy_min']}" if 'energy_min' in c else f"<= {c['energy_max']}" for c in checks]
            detail = f"Energy {song.energy:.2f}; requested: {' and '.join(bounds)}"
        else:
            passed = all((song.acousticness > .6) == c['likes_acoustic'] for c in checks)
            targets = ['acoustic (> 0.60)' if c['likes_acoustic'] else 'non-acoustic (<= 0.60)' for c in checks]
            detail = f"Acousticness {song.acousticness:.2f}; requested: {', '.join(targets)}"
        (matched if passed else missed).append(category)
        details.append(f"{'✓' if passed else '✗'} {detail}")
    return SongMatch(song.id, matched, missed, details)


def rank_by_preferences(recommendations: List[Tuple], constraints: Dict, k: int) -> List[Tuple]:
    """Rank the entire scored catalog: boxes first, round similarity second."""
    return sorted(recommendations,
                  key=lambda item: (evaluate_song(item[0], constraints).matched_count, item[1]),
                  reverse=True)[:k]


def validate_recommendations(user_input: str, recommendations: List[Tuple],
                             keywords: List[str] = None, constraints: Dict = None) -> ValidationResult:
    if keywords is None or constraints is None:
        keywords, constraints = extract_keywords(user_input)
    checks = [evaluate_song(song, constraints) for song, _, _ in recommendations]
    total = len(checks)
    complete = sum(check.complete for check in checks)
    boxes = sum(check.total_preferences for check in checks)
    reasons = []
    for (song, _, _), check in zip(recommendations, checks):
        if not check.total_preferences:
            reasons.append(f"{song.title}: no recognized explicit preferences to check")
        else:
            reasons.append(f"{'✓' if check.complete else '✗'} {song.title}: "
                           f"{check.matched_count}/{check.total_preferences} preferences; " + '; '.join(check.details))
    return ValidationResult(
        match_rate=complete / total if total else 0., total_matches=complete,
        total_songs=total, reasons=reasons, keywords_found=keywords,
        song_matches=checks,
        preference_coverage=sum(c.matched_count for c in checks) / boxes if boxes else (1. if total else 0.),
    )


def log_validation(validation: ValidationResult) -> str:
    return '\n'.join([
        f"Complete matches: {validation.total_matches}/{validation.total_songs} ({validation.match_rate:.1%})",
        f"Preference coverage: {validation.preference_coverage:.1%}", *validation.reasons,
    ])
