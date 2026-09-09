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
                           evaluate_song, rank_by_preferences, GENRE_KEYWORDS, MOOD_KEYWORDS,
                           format_validation_summary, is_excluded)
from src.optimizer import WeightOptimizer
from src.preferences import parse_preferences, ConfirmedPreferences, PreferenceReviewRequired


@dataclass
class PlaylistResult:
    """Result of processing a user request through the reliability engine."""
    recommendations: List[Tuple[Song, float, List[str]]]  # (song, score, reasons)
    validation: ValidationResult
    optimization_steps: List = None
    final_match_rate: Optional[float] = None
    confidence: Optional[float] = None  # Compatibility alias for final_match_rate; not probability.
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
    """Compatibility helper: derive a profile from the shared phrase parser."""
    MOOD_KEYWORDS = MOOD_KEYWORDS
    GENRE_KEYWORDS = GENRE_KEYWORDS

    def parse(self, user_input: str, default_profile: UserProfile = None) -> UserProfile:
        return parse_preferences(user_input, default_profile).similarity_profile()


class ReliabilityEngine:
    """Main orchestrator for the reliability testing system."""

    def __init__(self, songs: List[Song]):
        self.songs = songs
        self.parser = PreferenceParser()
        self.optimizer = WeightOptimizer()

    def _diagnose_low_confidence(
        self, user_input: str, recommendations: List[Tuple[Song, float, List[str]]],
        validation: ValidationResult, requested_count: Optional[int] = None, constraints: Optional[Dict] = None,
    ) -> str:
        """Explain catalog coverage without inferring contradictory preferences.

        Count complete, partial, and zero-preference matches using exactly the
        same predicate as ranking. Requested count distinguishes catalog scarcity
        from the number of results actually returned.
        """
        if not self.songs:
            return "The catalog is empty; no recommendations are available."
        if not validation.evaluated:
            return "Not evaluated—no supported preferences recognized."
        if constraints is None:
            _, constraints = extract_keywords(user_input)
        matching = sum(evaluate_song(song, constraints).complete for song in self.songs)
        requested = len(recommendations) if requested_count is None else requested_count
        coverage = f"{matching} of {len(self.songs)} catalog songs satisfy all recognized requested preferences. "
        if matching == 0:
            explanation = "No complete matches are available in this catalog. "
        elif matching < requested:
            explanation = f"Too few complete matches are available to fill the requested {requested} recommendations. "
        else:
            explanation = f"The catalog has enough complete matches for the requested {requested} recommendations. "

        checks = [evaluate_song(song, constraints) for song, _, _ in recommendations]
        complete = sum(check.complete for check in checks)
        partial = sum(not check.complete and check.matched_count > 0 for check in checks)
        unmatched = sum(check.matched_count == 0 for check in checks)
        returned = f"Returning {len(recommendations)} of {requested} requested recommendations. "
        returned += f"Complete matches: {complete}; partial matches: {partial}"
        if unmatched:
            returned += f"; alternatives matching none of the requested preferences: {unmatched}"
        returned += "."
        if partial or unmatched:
            returned += (" Alternatives are ordered by preferences satisfied, then similarity. "
                         "See each song's matched and missed preferences to assess the compromises.")
        excluded = sum(is_excluded(song, constraints) for song in self.songs)
        exclusion_note = f"{excluded} catalog songs were omitted because of your explicit exclusions. " if excluded else ""
        return coverage + exclusion_note + explanation + returned

    def prepare_request(self, user_input: str, base_profile: UserProfile = None):
        """Build an editable draft without scoring any songs."""
        return parse_preferences(user_input, base_profile)

    def process_user_request(
        self,
        user_input: str,
        base_profile: UserProfile = None,
        k: int = 5,
        min_match_rate: float = 0.7,
        min_acceptable_confidence: float = 0.4,
        max_iterations: int = 3,
        confirmed_preferences: Optional[ConfirmedPreferences] = None,
    ) -> PlaylistResult:
        """Score only an explicitly confirmed snapshot, never raw text alone.

        Rank eligible songs by preference coverage, then similarity.

        Retain every attempt. Compare rounds by complete matches, total boxes
        satisfied, then default-weight similarity on a common scoring scale.
        Exact ties keep the earlier attempt. The compatibility confidence field
        aliases the complete-match rate (None if unevaluated). Unrecognized
        requests return profile-based suggestions without validation retries.
        Parser defaults only influence similarity tie-breaks.
        """
        if confirmed_preferences is None:
            raise PreferenceReviewRequired(self.prepare_request(user_input, base_profile))
        if not isinstance(confirmed_preferences, ConfirmedPreferences) or confirmed_preferences.request != user_input:
            raise ValueError('Confirmation must belong to this request.')
        constraints = confirmed_preferences.constraints
        profile = confirmed_preferences.profile
        keywords = [category for category, checks in constraints.items() if checks]
        eligible_songs = [song for song in self.songs if not is_excluded(song, constraints)]
        current_weights = self.optimizer.DEFAULT_WEIGHTS.copy()
        decision_log = [
            f"User Input: {user_input!r}",
            f"Parsing: genre={profile.favorite_genre}, mood={profile.favorite_mood}, "
            f"energy={profile.target_energy:.2f}, acoustic={profile.likes_acoustic}",
            "Validating explicit preferences only; similarity defaults are not requirements.",
            f"Preferences explicitly confirmed; {len(self.songs) - len(eligible_songs)} songs excluded.",
            f"Confirmed constraints: {constraints}",
            f"Explicitly omitted wording: {list(confirmed_preferences.omitted_text)}",
        ]
        attempts = []
        optimization_steps = []

        def evaluate_attempt(iteration, weights):
            # Do not truncate by similarity before checking preference coverage.
            scored = recommend_songs(profile, eligible_songs, k=len(eligible_songs), weights=weights)
            recommendations = rank_by_preferences(scored, constraints, k)
            validation = validate_recommendations(user_input, recommendations, keywords, constraints)
            # Scores under different weights are not directly comparable. Use
            # the unchanged default weights only to break equal-quality round ties.
            baseline_similarity = sum(score_song(profile, song)[0] for song, _, _ in recommendations)
            quality = (validation.total_matches,
                       sum(check.matched_count for check in validation.song_matches),
                       baseline_similarity) if validation.evaluated else None
            attempt = deepcopy({
                'iteration': iteration, 'weights': weights,
                'recommendations': recommendations, 'validation': validation,
                'match_rate': validation.match_rate, 'evaluated': validation.evaluated,
                'preference_coverage': validation.preference_coverage,
                'quality': quality,
            })
            attempts.append(attempt)
            decision_log.append(
                f"Scoring round {iteration}: " + format_validation_summary(validation)
            )
            return attempt

        current = evaluate_attempt(0, current_weights)
        best = current
        if current['evaluated'] and current['match_rate'] < min_match_rate:
            for iteration in range(1, max_iterations + 1):
                current_weights = self.optimizer.suggest_weight_adjustments(
                    user_input, current_weights, current['match_rate'], constraints=constraints
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
        match_rate = validation.match_rate
        low_match_rate = validation.evaluated and match_rate < min_acceptable_confidence
        best_attempt_used = best['iteration'] != current['iteration'] or low_match_rate
        reason = self._diagnose_low_confidence(user_input, recommendations, validation, requested_count=k, constraints=constraints) if low_match_rate else None
        decision_log.append(f"Selected round {best['iteration']} of {len(attempts)} recorded attempts.")
        decision_log.append(format_validation_summary(validation))
        if reason:
            decision_log.append(reason)
        return PlaylistResult(
            recommendations=deepcopy(recommendations), validation=deepcopy(validation),
            optimization_steps=optimization_steps, final_match_rate=match_rate,
            confidence=match_rate, decision_log=decision_log,
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

        output.append("\n" + format_validation_summary(result.validation))
        output.append("=" * 70)

        return "\n".join(output)
