"""Evaluate explicit preferences independently of similarity scores."""

from typing import List, Tuple, Dict, Optional
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
        return self.total_preferences > 0 and not self.missed_preferences


@dataclass
class ValidationResult:
    match_rate: Optional[float]  # None when no supported preferences were recognized; otherwise fraction of returned songs satisfying every explicit preference.
    total_matches: int
    total_songs: int
    reasons: List[str]
    keywords_found: List[str]
    song_matches: List[SongMatch] = field(default_factory=list)
    preference_coverage: Optional[float] = None  # None when unevaluated.

    @property
    def evaluated(self) -> bool:
        return self.match_rate is not None


from src.preferences import GENRE_KEYWORDS, MOOD_KEYWORDS, INTENT_KEYWORDS, parse_preferences


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


def extract_keywords(user_input: str) -> Tuple[List[str], Dict]:
    """Low-level extraction; callers must review parse issues before scoring."""
    draft = parse_preferences(user_input)
    return draft.keywords, draft.constraints


def is_excluded(song: Song, constraints: Dict) -> bool:
    """Explicit exclusions are never relaxed to fill a playlist."""
    for category in ['genre', 'mood']:
        actual = getattr(song, category).lower().replace('indie-pop', 'indie pop')
        for check in constraints.get(category, []):
            for excluded in check.get(f'{category}_not', []):
                if actual == excluded or (category == 'mood' and _similar_mood(actual, excluded)):
                    return True
    return any(check.get('hard') and (song.acousticness > .6) != check['likes_acoustic']
               for check in constraints.get('acoustic', []))


def evaluate_song(song: Song, constraints: Dict) -> SongMatch:
    """One equal-weight box per requested category, regardless of synonyms."""
    constraints = _consolidate_constraints(constraints)
    matched, missed, details = [], [], []
    for category, checks in constraints.items():
        if not checks:
            continue
        if category in ['genre', 'mood']:
            actual = getattr(song, category).lower().replace('indie-pop', 'indie pop')
            def matches(target):
                return actual == target or (category == 'mood' and _similar_mood(actual, target))
            passed = True
            labels = []
            for check in checks:
                allowed = check.get(f'{category}_any', [check[category]] if category in check else [])
                excluded = check.get(f'{category}_not', [])
                passed = passed and (not allowed or any(matches(v) for v in allowed)) and not any(matches(v) for v in excluded)
                labels.append(f"allowed: {' OR '.join(allowed) or 'any'}; excluded: {', '.join(excluded) or 'none'}")
            detail = f"{category.title()} {actual}; " + '; '.join(labels)
            if category == 'mood': detail += ' (related moods allowed)'
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
    evaluated = any(_consolidate_constraints(constraints).values())
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
        match_rate=(complete / total if total else 0.) if evaluated else None, total_matches=complete,
        total_songs=total, reasons=reasons, keywords_found=keywords,
        song_matches=checks,
        preference_coverage=(sum(c.matched_count for c in checks) / boxes if boxes else 0.) if evaluated else None,
    )


def format_validation_summary(validation: ValidationResult) -> str:
    """Shared user-facing metrics; never imply a satisfaction probability."""
    if not validation.evaluated:
        return ("Not evaluated—no supported preferences recognized.\n"
                "Unvalidated suggestions based on the default or supplied profile.")
    return (
        f"Complete-match rate: {validation.match_rate:.1%} "
        f"({validation.total_matches} of {validation.total_songs} songs match all recognized preferences).\n"
        f"Preference coverage: {validation.preference_coverage:.1%} of requested preferences satisfied."
    )


def log_validation(validation: ValidationResult) -> str:
    return '\n'.join([format_validation_summary(validation), *validation.reasons])
