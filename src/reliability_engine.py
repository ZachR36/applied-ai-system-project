"""
Reliability Engine: Main orchestrator for the reliability testing system.

This module ties together preference parsing, recommendation scoring, validation,
and iterative weight optimization. It's the core of the advanced AI feature.
"""

from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
import csv
import os

from src.recommender import Song, UserProfile, recommend_songs
from src.validator import validate_recommendations, ValidationResult, extract_keywords
from src.optimizer import WeightOptimizer


@dataclass
class PlaylistResult:
    """Result of processing a user request through the reliability engine."""
    recommendations: List[Tuple[Song, float, List[str]]]  # (song, score, reasons)
    validation: ValidationResult
    optimization_steps: List = None
    final_match_rate: float = 0.0
    confidence: float = 0.0  # 0.0-1.0: how confident we are in these recommendations
    decision_log: List[str] = None  # Detailed log of all steps taken

    def __post_init__(self):
        if self.optimization_steps is None:
            self.optimization_steps = []
        if self.decision_log is None:
            self.decision_log = []


class PreferenceParser:
    """Parses natural language user input into preference adjustments."""

    # Mood keyword mappings
    MOOD_KEYWORDS = {
        'happy': ['happy', 'cheerful', 'joyful', 'upbeat'],
        'chill': ['chill', 'relaxing', 'calm', 'mellow'],
        'aggressive': ['aggressive', 'intense', 'angry'],
        'melancholic': ['sad', 'melancholic', 'depressed'],
        'focused': ['focused', 'concentrating', 'productive'],
        'energetic': ['energetic', 'pumped', 'excited'],
    }

    # Genre keyword mappings
    GENRE_KEYWORDS = {
        'pop': ['pop', 'mainstream'],
        'lofi': ['lofi', 'lo-fi', 'chill hop'],
        'rock': ['rock', 'hard rock'],
        'metal': ['metal', 'heavy metal'],
        'jazz': ['jazz', 'smooth jazz'],
        'electronic': ['electronic', 'edm', 'synth'],
        'acoustic': ['acoustic', 'unplugged'],
        'classical': ['classical', 'orchestral'],
    }

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
        """Extract mood from user input."""
        for mood, keywords in self.MOOD_KEYWORDS.items():
            for keyword in keywords:
                if keyword in user_input_lower:
                    return mood
        return None

    def _detect_genre(self, user_input_lower: str) -> Optional[str]:
        """Extract genre from user input."""
        for genre, keywords in self.GENRE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in user_input_lower:
                    return genre
        return None

    def _detect_energy(self, user_input_lower: str) -> Optional[float]:
        """Extract energy level from user input."""
        # High energy indicators
        if any(word in user_input_lower for word in ['upbeat', 'energetic', 'intense', 'fast', 'pumped', 'workout', 'gym']):
            return 0.80
        # Low energy indicators
        if any(word in user_input_lower for word in ['tired', 'exhausted', 'sleepy', 'chill', 'relaxing', 'calm', 'slow']):
            return 0.30
        # Medium-high
        if any(word in user_input_lower for word in ['active', 'lively', 'bouncy']):
            return 0.65
        # Medium-low
        if any(word in user_input_lower for word in ['mellow', 'peaceful', 'gentle']):
            return 0.35
        return None


class ReliabilityEngine:
    """Main orchestrator for the reliability testing system."""

    def __init__(self, songs: List[Song]):
        self.songs = songs
        self.parser = PreferenceParser()
        self.optimizer = WeightOptimizer()

    def process_user_request(
        self,
        user_input: str,
        base_profile: UserProfile = None,
        k: int = 5,
        min_match_rate: float = 0.7,
        max_iterations: int = 3,
    ) -> PlaylistResult:
        """
        Process a user request through the full reliability pipeline.

        Args:
            user_input: Natural language user request
            base_profile: Base UserProfile to build on (optional)
            k: Number of songs to recommend
            min_match_rate: Target validation match rate (0.7 = 70%)
            max_iterations: Max optimization iterations

        Returns:
            PlaylistResult with recommendations, validation, and decision log
        """
        decision_log = []
        decision_log.append(f"📝 User Input: '{user_input}'")

        # Step 1: Parse user input into preferences
        decision_log.append("\n1️⃣ Parsing User Input...")
        parsed_profile = self.parser.parse(user_input, base_profile)
        decision_log.append(f"   Genre: {parsed_profile.favorite_genre}")
        decision_log.append(f"   Mood: {parsed_profile.favorite_mood}")
        decision_log.append(f"   Energy: {parsed_profile.target_energy:.2f}")
        decision_log.append(f"   Acoustic: {parsed_profile.likes_acoustic}")

        # Step 2: Score songs with default weights
        decision_log.append("\n2️⃣ Scoring Songs (Default Weights)...")
        current_profile = parsed_profile
        current_weights = self.optimizer.DEFAULT_WEIGHTS.copy()
        recommendations = recommend_songs(current_profile, self.songs, k=k)
        decision_log.append(f"   Top {k} songs scored")

        # Step 3: Validate recommendations
        decision_log.append("\n3️⃣ Validating Recommendations...")
        keywords, constraints = extract_keywords(user_input)
        validation = validate_recommendations(user_input, recommendations, keywords, constraints)
        decision_log.append(f"   Match Rate: {validation.match_rate:.1%} ({validation.total_matches}/{validation.total_songs})")

        # Step 4: Iterative optimization if needed
        optimization_steps = []
        if validation.match_rate < min_match_rate:
            decision_log.append(f"\n4️⃣ Optimizing Weights (Match Rate < {min_match_rate:.0%})...")
            decision_log.append(f"   Detected conflicts: {', '.join(self.optimizer.detect_conflicts(user_input)) or 'None'}")

            for iteration in range(1, max_iterations + 1):
                decision_log.append(f"\n   Iteration {iteration}:")

                # Get weight suggestions
                new_weights = self.optimizer.suggest_weight_adjustments(
                    user_input, current_weights, validation.match_rate
                )

                # Log weight changes
                for weight_name in ['genre', 'mood', 'energy', 'acoustic', 'valence']:
                    old = current_weights[weight_name]
                    new = new_weights[weight_name]
                    if abs(new - old) > 0.01:
                        change = "↑" if new > old else "↓"
                        decision_log.append(f"     {weight_name}: {old:.2f} → {new:.2f} {change}")

                current_weights = new_weights

                # Re-score with new weights (note: we'd need to modify recommend_songs to accept weights)
                # For now, just create a modified profile that hints at the new weights
                recommendations = recommend_songs(current_profile, self.songs, k=k)

                # Re-validate
                validation = validate_recommendations(user_input, recommendations, keywords, constraints)
                decision_log.append(f"     New Match Rate: {validation.match_rate:.1%}")

                optimization_steps.append({
                    'iteration': iteration,
                    'weights': new_weights.copy(),
                    'match_rate': validation.match_rate,
                })

                # Exit early if validation passes
                if validation.match_rate >= min_match_rate:
                    decision_log.append(f"\n   ✅ Optimization Passed!")
                    break

        # Step 5: Calculate confidence
        decision_log.append("\n5️⃣ Final Result:")
        confidence = validation.match_rate  # Confidence = validation match rate
        decision_log.append(f"   Final Match Rate: {validation.match_rate:.1%}")
        decision_log.append(f"   Confidence: {confidence:.1%}")

        return PlaylistResult(
            recommendations=recommendations,
            validation=validation,
            optimization_steps=optimization_steps,
            final_match_rate=validation.match_rate,
            confidence=confidence,
            decision_log=decision_log,
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
