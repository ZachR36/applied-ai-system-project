"""
Validates whether recommendations match a user's stated intent.

This module extracts keywords from user input and checks if the recommended
songs actually match what the user asked for. Used by the reliability engine
to determine if weight adjustments are needed.
"""

from typing import List, Tuple, Dict
from dataclasses import dataclass
from src.recommender import Song


@dataclass
class ValidationResult:
    """Result of validating a set of recommendations."""
    match_rate: float  # 0.0 to 1.0: fraction of songs that match intent
    total_matches: int  # How many songs matched
    total_songs: int  # Total songs validated
    reasons: List[str]  # Detailed feedback on what matched/didn't
    keywords_found: List[str]  # Keywords extracted from user input


# Keyword mappings: user intent phrases → feature targets
INTENT_KEYWORDS = {
    # Energy level
    'upbeat': {'energy_min': 0.7, 'category': 'energy'},
    'energetic': {'energy_min': 0.7, 'category': 'energy'},
    'high energy': {'energy_min': 0.7, 'category': 'energy'},
    'intense': {'energy_min': 0.75, 'category': 'energy'},
    'fast': {'energy_min': 0.7, 'category': 'energy'},
    'pumped': {'energy_min': 0.75, 'category': 'energy'},

    'chill': {'energy_max': 0.5, 'category': 'energy'},
    'relaxing': {'energy_max': 0.4, 'category': 'energy'},
    'calm': {'energy_max': 0.5, 'category': 'energy'},
    'slow': {'energy_max': 0.45, 'category': 'energy'},
    'tired': {'energy_max': 0.4, 'category': 'energy'},
    'exhausted': {'energy_max': 0.3, 'category': 'energy'},
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


def extract_keywords(user_input: str) -> Tuple[List[str], Dict]:
    """
    Extract intent keywords from user input.

    Returns:
        (keywords_found, intent_constraints)
        keywords_found: list of matched keywords
        intent_constraints: dict of {category: [constraints]}
    """
    user_input_lower = user_input.lower()
    keywords_found = []
    intent_constraints = {'energy': [], 'mood': [], 'acoustic': []}

    for keyword, constraint in INTENT_KEYWORDS.items():
        if keyword in user_input_lower:
            keywords_found.append(keyword)
            category = constraint.get('category')
            if category in intent_constraints:
                intent_constraints[category].append(constraint)

    return keywords_found, intent_constraints


def validate_recommendations(
    user_input: str,
    recommendations: List[Tuple],  # [(song, score, reasons), ...]
    keywords: List[str] = None,
    constraints: Dict = None,
) -> ValidationResult:
    """
    Validate if recommendations match user's stated intent.

    Args:
        user_input: Original user input text
        recommendations: List of (song, score, reasons) tuples from recommend_songs()
        keywords: Pre-extracted keywords (optional, extracted if not provided)
        constraints: Pre-extracted constraints (optional, extracted if not provided)

    Returns:
        ValidationResult with match_rate, reasons, and detailed feedback
    """
    # Extract keywords if not provided
    if keywords is None or constraints is None:
        keywords, constraints = extract_keywords(user_input)

    # If no keywords found, consider all valid (match rate = 1.0)
    if not keywords:
        return ValidationResult(
            match_rate=1.0,
            total_matches=len(recommendations),
            total_songs=len(recommendations),
            reasons=["No specific intent keywords found; all recommendations valid"],
            keywords_found=keywords,
        )

    reasons = []
    matches = 0

    # Check each recommendation
    for song, score, song_reasons in recommendations:
        song_matches = True
        song_feedback = []

        # Check energy constraints
        for constraint in constraints.get('energy', []):
            if 'energy_min' in constraint:
                if song.energy < constraint['energy_min']:
                    song_matches = False
                    song_feedback.append(f"✗ Energy {song.energy:.2f} < {constraint['energy_min']} (user wants upbeat)")
                else:
                    song_feedback.append(f"✓ Energy {song.energy:.2f} ≥ {constraint['energy_min']}")

            if 'energy_max' in constraint:
                if song.energy > constraint['energy_max']:
                    song_matches = False
                    song_feedback.append(f"✗ Energy {song.energy:.2f} > {constraint['energy_max']} (user wants calm)")
                else:
                    song_feedback.append(f"✓ Energy {song.energy:.2f} ≤ {constraint['energy_max']}")

        # Check mood constraints
        for constraint in constraints.get('mood', []):
            if 'mood' in constraint:
                if song.mood.lower() == constraint['mood'].lower():
                    song_feedback.append(f"✓ Mood matches: {song.mood}")
                else:
                    # Don't hard-fail on mood mismatch; it's less critical
                    song_feedback.append(f"~ Mood {song.mood} vs preferred {constraint['mood']}")

        # Check acoustic constraints
        for constraint in constraints.get('acoustic', []):
            if 'likes_acoustic' in constraint:
                is_acoustic = song.acousticness > 0.6
                if constraint['likes_acoustic'] and not is_acoustic:
                    song_feedback.append(f"✗ Not acoustic enough ({song.acousticness:.2f})")
                elif not constraint['likes_acoustic'] and is_acoustic:
                    song_feedback.append(f"✗ Too acoustic ({song.acousticness:.2f})")
                else:
                    song_feedback.append(f"✓ Acoustic preference matched")

        if song_matches:
            matches += 1
            reason_str = f"✓ {song.title}: {', '.join(song_feedback)}"
        else:
            reason_str = f"✗ {song.title}: {', '.join(song_feedback)}"

        reasons.append(reason_str)

    match_rate = matches / len(recommendations) if recommendations else 0.0

    return ValidationResult(
        match_rate=match_rate,
        total_matches=matches,
        total_songs=len(recommendations),
        reasons=reasons,
        keywords_found=keywords,
    )


def log_validation(validation: ValidationResult) -> str:
    """Format validation result as readable log."""
    output = []
    output.append(f"\n🔍 Validation Report:")
    output.append(f"   Match Rate: {validation.match_rate:.1%} ({validation.total_matches}/{validation.total_songs})")
    output.append(f"   Keywords Found: {', '.join(validation.keywords_found) if validation.keywords_found else 'None'}")
    output.append(f"\n   Details:")
    for reason in validation.reasons:
        output.append(f"   {reason}")

    return "\n".join(output)
