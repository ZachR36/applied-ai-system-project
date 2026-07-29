"""Tests for the optimizer module."""

from src.recommender import UserProfile
from src.optimizer import WeightOptimizer


def test_detect_conflicts_energy():
    """Test detecting conflicting energy preferences."""
    optimizer = WeightOptimizer()
    conflicts = optimizer.detect_conflicts("I want upbeat music but I'm tired")

    assert len(conflicts) > 0
    assert any("energy" in c.lower() for c in conflicts)


def test_detect_conflicts_no_conflicts():
    """Test when there are no conflicts."""
    optimizer = WeightOptimizer()
    conflicts = optimizer.detect_conflicts("I want happy pop music")

    assert len(conflicts) == 0


def test_suggest_weight_adjustments_boosts_energy():
    """Test that energy constraints boost energy weight."""
    optimizer = WeightOptimizer()
    current_weights = {
        'genre': 0.40,
        'mood': 0.30,
        'energy': 0.15,
        'acoustic': 0.10,
        'valence': 0.05,
    }

    # Low match rate with energy constraint → should boost energy
    new_weights = optimizer.suggest_weight_adjustments(
        "I want relaxing music",
        current_weights,
        match_rate=0.3,
    )

    # Energy weight should increase
    assert new_weights['energy'] > current_weights['energy']
    # Genre weight should decrease
    assert new_weights['genre'] < current_weights['genre']
    # Weights should still sum to 1.0
    assert abs(sum(new_weights.values()) - 1.0) < 0.01


def test_suggest_weight_adjustments_boosts_acoustic():
    """Test that acoustic constraints boost acoustic weight."""
    optimizer = WeightOptimizer()
    current_weights = {
        'genre': 0.40,
        'mood': 0.30,
        'energy': 0.15,
        'acoustic': 0.10,
        'valence': 0.05,
    }

    # Low match rate with acoustic constraint → should boost acoustic
    new_weights = optimizer.suggest_weight_adjustments(
        "I want unplugged acoustic music",
        current_weights,
        match_rate=0.3,
    )

    # Acoustic weight should increase
    assert new_weights['acoustic'] > current_weights['acoustic']
    # Weights should sum to 1.0
    assert abs(sum(new_weights.values()) - 1.0) < 0.01


def test_optimize_until_valid_returns_weights():
    """Test that optimization returns valid weight dict."""
    optimizer = WeightOptimizer()
    profile = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.5,
        likes_acoustic=False,
    )

    final_weights, history, success = optimizer.optimize_until_valid(
        "I want chill happy music",
        profile,
        max_iterations=2,
    )

    assert isinstance(final_weights, dict)
    assert all(k in final_weights for k in ['genre', 'mood', 'energy', 'acoustic', 'valence'])
    assert abs(sum(final_weights.values()) - 1.0) < 0.01
    assert success


def test_optimize_until_valid_respects_max_iterations():
    """Test that optimization respects max_iterations."""
    optimizer = WeightOptimizer()
    profile = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.5,
        likes_acoustic=False,
    )

    _, history, _ = optimizer.optimize_until_valid(
        "I want chill happy music",
        profile,
        max_iterations=2,
    )

    assert len(history) <= 2


def test_weight_optimization_normalizes():
    """Test that weights are normalized after adjustment."""
    optimizer = WeightOptimizer()
    current_weights = {
        'genre': 0.40,
        'mood': 0.30,
        'energy': 0.15,
        'acoustic': 0.10,
        'valence': 0.05,
    }

    new_weights = optimizer.suggest_weight_adjustments(
        "I want upbeat acoustic music",
        current_weights,
        match_rate=0.2,
    )

    # Weights must sum to 1.0
    assert abs(sum(new_weights.values()) - 1.0) < 0.001
    # All weights must be non-negative
    assert all(w >= 0 for w in new_weights.values())


def test_adjustment_reason_generation():
    """Test that adjustment reasons are generated."""
    optimizer = WeightOptimizer()
    old_weights = {
        'genre': 0.40,
        'mood': 0.30,
        'energy': 0.15,
        'acoustic': 0.10,
        'valence': 0.05,
    }
    new_weights = {
        'genre': 0.30,
        'mood': 0.25,
        'energy': 0.30,
        'acoustic': 0.10,
        'valence': 0.05,
    }

    reason = optimizer._generate_adjustment_reason(
        "I want chill music",
        new_weights,
        old_weights,
    )

    assert isinstance(reason, str)
    assert len(reason) > 0
    # Should mention some weight changes
    assert "↑" in reason or "↓" in reason
