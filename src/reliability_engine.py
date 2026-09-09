"""
Reliability Engine: Main orchestrator for the reliability testing system.

This module ties together preference parsing, recommendation scoring, validation,
and iterative weight optimization. It's the core of the advanced AI feature.
"""

from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field
from copy import deepcopy
import csv
import os

from src.recommender import Song, UserProfile, recommend_songs, score_song
from src.validator import (validate_recommendations, ValidationResult, extract_keywords,
                           evaluate_song, rank_by_preferences, GENRE_KEYWORDS, MOOD_KEYWORDS)
from src.optimizer import WeightOptimizer


@dataclass
class PlaylistResult:
    """Result of processing a user request through the reliability engine."""
    recommendations: List[Tuple[Song, float, List[str]]]  # (song, score, reasons)
    validation: ValidationResult
    optimization_steps: List = None
    final_match_rate: float = 0.0
    confidence: float = 0.0  # Fraction of returned songs satisfying all explicit preferences.
    decision_log: List[str] = None  # Detailed log of all steps taken
    confidence_low_reason: str = None  # Explanation if confidence < 0.4
    best_attempt_used: bool = False  # Earlier round retained or low-confidence output.

    attempt_history: List[Dict] = field(default_factory=list)
    selected_iteration: int = 0

    def __post_init__(self):
        if self.optimization_steps is None:
            self.optimization_steps = []
        if self.decision_log is None:
            self.decision_log = []


class PreferenceParser:
    """Parses natural language user input into preference adjustments."""

    # Shared explicit vocabulary keeps parsing and validation aligned.
    MOOD_KEYWORDS = MOOD_KEYWORDS
    GENRE_KEYWORDS = GENRE_KEYWORDS

    def parse(self, user_input: str, default_profile: UserProfile = None) -> UserProfile:
        """
        Parse natural language input into a UserProfile with adjusted preferences.

        Args:
            user_input: User's natural language description
            default_profile: Base profile to modify (creates new one if None)

        Returns:
            UserProfile with preferences adjusted based on user input
        """
        user_input_lower = user_input.lower()

        # Use default profile or create a neutral one
        if default_profile:
            genre = default_profile.favorite_genre
            mood = default_profile.favorite_mood
            energy = default_profile.target_energy
            acoustic = default_profile.likes_acoustic
        else:
            genre = 'pop'
            mood = 'happy'
            energy = 0.5
            acoustic = False

        # Extract mood from input
        detected_mood = self._detect_mood(user_input_lower)
        if detected_mood:
            mood = detected_mood

        # Extract genre from input
        detected_genre = self._detect_genre(user_input_lower)
        if detected_genre:
            genre = detected_genre

        # Extract energy level
        detected_energy = self._detect_energy(user_input_lower)
        if detected_energy is not None:
            energy = detected_energy

        # Extract acoustic preference
        if 'acoustic' in user_input_lower or 'unplugged' in user_input_lower:
            acoustic = True
        elif 'electronic' in user_input_lower or 'synth' in user_input_lower or 'digital' in user_input_lower:
            acoustic = False

        return UserProfile(
            favorite_genre=genre,
            favorite_mood=mood,
            target_energy=energy,
            likes_acoustic=acoustic,
        )

    def _detect_mood(self, user_input_lower: str) -> Optional[str]:
        _, constraints = extract_keywords(user_input_lower)
        return constraints['mood'][0]['mood'] if constraints['mood'] else None

    def _detect_genre(self, user_input_lower: str) -> Optional[str]:
        _, constraints = extract_keywords(user_input_lower)
        return constraints['genre'][0]['genre'] if constraints['genre'] else None

    def _detect_energy(self, user_input_lower: str) -> Optional[float]:
        """Extract energy level from user input."""
        # High energy indicators
        if any(word in user_input_lower for word in ['upbeat', 'energetic', 'intense', 'fast', 'pumped', 'workout', 'gym']):
            return 0.80
        # Very low energy (sleepy)
        if 'sleepy' in user_input_lower:
            return 0.25
        # Low energy indicators (tired, exhausted, etc.)
        if any(word in user_input_lower for word in ['tired', 'exhausted', 'chill', 'relaxing', 'calm', 'slow']):
            return 0.40
        # Medium-high
        if any(word in user_input_lower for word in ['active', 'lively', 'bouncy']):
            return 0.65
        # Medium-low
        if any(word in user_input_lower for word in ['mellow', 'peaceful', 'gentle']):
            return 0.40
        return None


class ReliabilityEngine:
    """Main orchestrator for the reliability testing system."""

    def __init__(self, songs: List[Song]):
        self.songs = songs
        self.parser = PreferenceParser()
        self.optimizer = WeightOptimizer()

    def _diagnose_low_confidence(
        self, user_input: str, recommendations: List[Tuple[Song, float, List[str]]], validation: ValidationResult
    ) -> str:
        """Use the same predicate as ranking and validation for catalog diagnostics."""
        _, constraints = extract_keywords(user_input)
        matching = sum(evaluate_song(song, constraints).complete for song in self.songs)
        if not self.songs:
            return "The catalog is empty; no recommendations are available."
        return (
            f"{matching} of {len(self.songs)} catalog songs satisfy all recognized requested preferences. "
            f"Returning {validation.total_matches} complete matches and "
            f"{validation.total_songs - validation.total_matches} partial matches. "
            "Partial matches are ordered by preferences satisfied, then similarity; "
            "see each song's matched and missed preferences."
        )

    def process_user_request(
        self,
        user_input: str,
        base_profile: UserProfile = None,
        k: int = 5,
        min_match_rate: float = 0.7,
        min_acceptable_confidence: float = 0.4,
        max_iterations: int = 3,
    ) -> PlaylistResult:
        """Rank all songs by explicit preference coverage, then similarity.

        Retain every attempt. Compare rounds by complete matches, total boxes
        satisfied, then default-weight similarity on a common scoring scale.
        Exact ties keep the earlier attempt. Confidence is the full-match rate,
        not a probability. Parser defaults only influence similarity tie-breaks.
        """
        profile = self.parser.parse(user_input, base_profile)
        keywords, constraints = extract_keywords(user_input)
        current_weights = self.optimizer.DEFAULT_WEIGHTS.copy()
        decision_log = [
            f"User Input: {user_input!r}",
            f"Parsing: genre={profile.favorite_genre}, mood={profile.favorite_mood}, "
            f"energy={profile.target_energy:.2f}, acoustic={profile.likes_acoustic}",
            "Validating explicit preferences only; similarity defaults are not requirements.",
            f"Detected conflicts: {', '.join(self.optimizer.detect_conflicts(user_input)) or 'None'}",
        ]
        attempts = []
        optimization_steps = []

        def evaluate_attempt(iteration, weights):
            # Do not truncate by similarity before checking preference coverage.
            scored = recommend_songs(profile, self.songs, k=len(self.songs), weights=weights)
            recommendations = rank_by_preferences(scored, constraints, k)
            validation = validate_recommendations(user_input, recommendations, keywords, constraints)
            # Scores under different weights are not directly comparable. Use
            # the unchanged default weights only to break equal-quality round ties.
            baseline_similarity = sum(score_song(profile, song)[0] for song, _, _ in recommendations)
            quality = (validation.total_matches,
                       sum(check.matched_count for check in validation.song_matches),
                       baseline_similarity)
            attempt = deepcopy({
                'iteration': iteration, 'weights': weights,
                'recommendations': recommendations, 'validation': validation,
                'match_rate': validation.match_rate,
                'preference_coverage': validation.preference_coverage,
                'quality': quality,
            })
            attempts.append(attempt)
            decision_log.append(
                f"Scoring round {iteration}: complete matches {validation.total_matches}/{validation.total_songs} "
                f"({validation.match_rate:.1%}); preference coverage {validation.preference_coverage:.1%}"
            )
            return attempt

        current = evaluate_attempt(0, current_weights)
        best = current
        if current['match_rate'] < min_match_rate:
            for iteration in range(1, max_iterations + 1):
                current_weights = self.optimizer.suggest_weight_adjustments(
                    user_input, current_weights, current['match_rate']
                )
                current = evaluate_attempt(iteration, current_weights)
                optimization_steps.append(deepcopy({
                    'iteration': iteration, 'weights': current_weights,
                    'match_rate': current['match_rate'],
                    'preference_coverage': current['preference_coverage'],
                }))
                if current['quality'] > best['quality']:
                    best = current
                if current['match_rate'] >= min_match_rate:
                    break

        recommendations = best['recommendations']
        validation = best['validation']
        confidence = validation.match_rate
        low_confidence = confidence < min_acceptable_confidence
        best_attempt_used = best['iteration'] != current['iteration'] or low_confidence
        reason = self._diagnose_low_confidence(user_input, recommendations, validation) if low_confidence else None
        decision_log.append(f"Selected round {best['iteration']} of {len(attempts)} evaluated attempts.")
        decision_log.append(f"Final Match Rate: {confidence:.1%}; preference coverage: {validation.preference_coverage:.1%}")
        if reason:
            decision_log.append(reason)
        return PlaylistResult(
            recommendations=deepcopy(recommendations), validation=deepcopy(validation),
            optimization_steps=optimization_steps, final_match_rate=confidence,
            confidence=confidence, decision_log=decision_log,
            confidence_low_reason=reason, best_attempt_used=best_attempt_used,
            attempt_history=attempts, selected_iteration=best['iteration'],
        )

    def log_result(self, result: PlaylistResult) -> str:
        """Format result as readable log."""
        output = []
        output.extend(result.decision_log)

        output.append("\n" + "=" * 70)
        output.append("📋 Validation Details:")
        output.append("=" * 70)
        for reason in result.validation.reasons:
            output.append(f"   {reason}")

        output.append(f"\n📊 Final Confidence: {result.confidence:.1%}")
        output.append("=" * 70)

        return "\n".join(output)
