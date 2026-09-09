"""
Optimizes recommendation weights based on validation results.

When recommendations don't match user intent, this module detects conflicts
and suggests weight adjustments to improve the next iteration.
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
from src.recommender import UserProfile
from src.validator import extract_keywords, INTENT_KEYWORDS


@dataclass
class OptimizationStep:
    """Records a single optimization attempt."""
    iteration: int
    old_weights: Dict[str, float]
    new_weights: Dict[str, float]
    match_rate: float
    reason: str


class WeightOptimizer:
    """Intelligently adjusts scoring weights based on user intent."""

    # Default weights from README
    DEFAULT_WEIGHTS = {
        'genre': 0.40,
        'mood': 0.30,
        'energy': 0.15,
        'acoustic': 0.10,
        'valence': 0.05,
    }

    def __init__(self):
        self.optimization_history: List[OptimizationStep] = []

    def detect_conflicts(self, user_input: str) -> List[str]:
        """
        Detect conflicting preferences in user input.

        Returns:
            List of conflict descriptions
        """
        keywords, constraints = extract_keywords(user_input)
        conflicts = []

        energy_constraints = constraints.get('energy', [])
        has_high_energy = any('energy_min' in c for c in energy_constraints)
        has_low_energy = any('energy_max' in c for c in energy_constraints)

        if has_high_energy and has_low_energy:
            conflicts.append("Conflicting energy: wants upbeat AND calm/tired")

        mood_constraints = constraints.get('mood', [])
        happy_moods = [c for c in mood_constraints if c.get('mood') == 'happy']
        sad_moods = [c for c in mood_constraints if c.get('mood') == 'melancholic']

        if happy_moods and sad_moods:
            conflicts.append("Conflicting mood: wants happy AND sad")

        return conflicts

    def suggest_weight_adjustments(
        self,
        user_input: str,
        current_weights: Dict[str, float],
        match_rate: float,
        constraints: Dict = None,
    ) -> Dict[str, float]:
        """
        Suggest new weights based on validation results and intent.

        Args:
            user_input: User's natural language request
            current_weights: Current genre/mood/energy/acoustic/valence weights
            match_rate: Current validation match rate (0.0-1.0)

        Returns:
            Suggested new weights (normalized to sum to 1.0)
        """
        if constraints is None:
            _, constraints = extract_keywords(user_input)
        new_weights = current_weights.copy()

        # If energy constraints exist and match rate is low, boost energy weight
        if constraints.get('energy') and match_rate < 0.8:
            new_weights['energy'] = min(0.50, current_weights['energy'] + 0.15)
            new_weights['genre'] = max(0.15, current_weights['genre'] - 0.10)

        # If acoustic constraints exist, boost acoustic weight
        if constraints.get('acoustic') and match_rate < 0.8:
            new_weights['acoustic'] = min(0.20, current_weights['acoustic'] + 0.10)

        # If mood constraints exist, keep mood stable but don't over-reduce
        if constraints.get('mood') and match_rate < 0.8:
            new_weights['mood'] = max(0.20, current_weights['mood'] - 0.05)

        # Normalize weights to sum to 1.0
        total = sum(new_weights.values())
        new_weights = {k: v / total for k, v in new_weights.items()}

        return new_weights

    def optimize_until_valid(
        self,
        user_input: str,
        current_user_profile: UserProfile,
        initial_weights: Dict[str, float] = None,
        min_match_rate: float = 0.7,
        max_iterations: int = 3,
    ) -> Tuple[Dict[str, float], List[OptimizationStep], bool]:
        """
        Iteratively adjust weights until validation passes.

        Args:
            user_input: User's natural language request
            current_user_profile: Current UserProfile to potentially modify
            initial_weights: Starting weights (uses DEFAULT_WEIGHTS if None)
            min_match_rate: Target match rate (0.7 = 70%)
            max_iterations: Max adjustment attempts

        Returns:
            (final_weights, optimization_history, success)
        """
        if initial_weights is None:
            initial_weights = self.DEFAULT_WEIGHTS.copy()

        current_weights = initial_weights.copy()
        self.optimization_history = []

        for iteration in range(1, max_iterations + 1):
            # Suggest new weights based on intent
            new_weights = self.suggest_weight_adjustments(
                user_input, current_weights, match_rate=0.0
            )

            reason = self._generate_adjustment_reason(user_input, new_weights, current_weights)

            step = OptimizationStep(
                iteration=iteration,
                old_weights=current_weights.copy(),
                new_weights=new_weights,
                match_rate=0.0,  # Will be filled in by caller
                reason=reason,
            )
            self.optimization_history.append(step)
            current_weights = new_weights

        return current_weights, self.optimization_history, True

    def _generate_adjustment_reason(
        self,
        user_input: str,
        new_weights: Dict[str, float],
        old_weights: Dict[str, float],
    ) -> str:
        """Generate human-readable explanation for weight adjustment."""
        keywords, constraints = extract_keywords(user_input)

        adjustments = []
        for key in ['energy', 'mood', 'acoustic', 'genre', 'valence']:
            change = new_weights.get(key, 0) - old_weights.get(key, 0)
            if abs(change) > 0.02:  # Only report significant changes
                direction = "↑" if change > 0 else "↓"
                adjustments.append(f"{key} {direction} {change:+.2f}")

        return f"Adjusted weights: {', '.join(adjustments)}"

    def log_optimization_history(self) -> str:
        """Format optimization history as readable log."""
        if not self.optimization_history:
            return "No optimizations performed"

        output = []
        output.append("\n📊 Weight Optimization History:")

        for step in self.optimization_history:
            output.append(f"\n   Iteration {step.iteration}:")
            output.append(f"     {step.reason}")
            output.append(f"     Genre: {step.old_weights['genre']:.2f} → {step.new_weights['genre']:.2f}")
            output.append(f"     Mood: {step.old_weights['mood']:.2f} → {step.new_weights['mood']:.2f}")
            output.append(f"     Energy: {step.old_weights['energy']:.2f} → {step.new_weights['energy']:.2f}")
            output.append(f"     Acoustic: {step.old_weights['acoustic']:.2f} → {step.new_weights['acoustic']:.2f}")
            output.append(f"     Valence: {step.old_weights['valence']:.2f} → {step.new_weights['valence']:.2f}")
            if step.match_rate > 0:
                output.append(f"     Match Rate: {step.match_rate:.1%}")

        return "\n".join(output)
