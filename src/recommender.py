from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import csv
import os

@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool


# Example taste profile for testing
EXAMPLE_USER = UserProfile(
    favorite_genre="lofi",
    favorite_mood="chill",
    target_energy=0.4,
    likes_acoustic=True
)

def load_songs(csv_path: str) -> List[Song]:
    """
    Loads songs from a CSV file and converts them to Song objects.
    Required by src/main.py
    """
    print(f"Loading songs from {csv_path}...")
    songs = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            song = Song(
                id=int(row['id']),
                title=row['title'],
                artist=row['artist'],
                genre=row['genre'],
                mood=row['mood'],
                energy=float(row['energy']),
                tempo_bpm=float(row['tempo_bpm']),
                valence=float(row['valence']),
                danceability=float(row['danceability']),
                acousticness=float(row['acousticness'])
            )
            songs.append(song)

    print(f"Loaded {len(songs)} songs.")
    return songs

def score_song(user_prefs: UserProfile, song: Song) -> Tuple[float, List[str]]:
    """
    Scores a single song against user preferences using the algorithm recipe.
    Returns (total_score, list_of_reasons_for_scoring).
    """
    reasons = []

    # Genre score (40% weight)
    if song.genre.lower() == user_prefs.favorite_genre.lower():
        genre_score = 1.0
        genre_contrib = genre_score * 0.40
        reasons.append(f"✓ Genre match: {song.genre} (+{genre_contrib:.2f})")
    else:
        genre_score = 0.0
        genre_contrib = 0.0
        reasons.append(f"✗ Genre mismatch: {song.genre} vs {user_prefs.favorite_genre} (+{genre_contrib:.2f})")

    # Mood score (30% weight)
    if song.mood.lower() == user_prefs.favorite_mood.lower():
        mood_score = 1.0
        mood_desc = "exact match"
    elif _similar_mood(song.mood, user_prefs.favorite_mood):
        mood_score = 0.5
        mood_desc = "similar"
    else:
        mood_score = 0.1
        mood_desc = "different"

    mood_contrib = mood_score * 0.30
    reasons.append(f"{'✓' if mood_score >= 0.5 else '~' if mood_score > 0.1 else '✗'} Mood {mood_desc}: {song.mood} (+{mood_contrib:.2f})")

    # Energy score (15% weight) - continuous distance score
    energy_score = 1.0 - abs(user_prefs.target_energy - song.energy)
    energy_contrib = energy_score * 0.15
    reasons.append(f"Energy closeness: {song.energy:.2f} vs target {user_prefs.target_energy:.2f} (+{energy_contrib:.2f})")

    # Acoustic score (10% weight)
    if user_prefs.likes_acoustic:
        acoustic_score = song.acousticness
        acoustic_label = "acoustic preference"
    else:
        acoustic_score = 1.0 - song.acousticness
        acoustic_label = "non-acoustic preference"

    acoustic_contrib = acoustic_score * 0.10
    reasons.append(f"Acoustic: {song.acousticness:.2f} ({acoustic_label}) (+{acoustic_contrib:.2f})")

    # Valence score (5% weight) - depends on mood
    if user_prefs.favorite_mood.lower() in ['happy', 'energetic', 'playful']:
        valence_score = song.valence
        valence_label = "bright/happy"
    elif user_prefs.favorite_mood.lower() in ['chill', 'relaxed', 'sad', 'melancholic']:
        valence_score = 1.0 - song.valence
        valence_label = "calm/sad"
    else:
        valence_score = 0.5
        valence_label = "neutral"

    valence_contrib = valence_score * 0.05
    reasons.append(f"Valence: {song.valence:.2f} ({valence_label} for {user_prefs.favorite_mood}) (+{valence_contrib:.2f})")

    # Weighted total score
    total_score = (
        (genre_score * 0.40) +
        (mood_score * 0.30) +
        (energy_score * 0.15) +
        (acoustic_score * 0.10) +
        (valence_score * 0.05)
    )

    return (total_score, reasons)


def _similar_mood(mood1: str, mood2: str) -> bool:
    """Helper function to determine if two moods are similar."""
    mood_groups = {
        'chill': ['relaxed', 'focused'],
        'happy': ['energetic', 'playful'],
        'intense': ['aggressive'],
        'melancholic': ['sad'],
    }

    mood1_lower = mood1.lower()
    mood2_lower = mood2.lower()

    if mood1_lower == mood2_lower:
        return False

    for key, similar_moods in mood_groups.items():
        if mood1_lower == key and mood2_lower in similar_moods:
            return True
        if mood2_lower == key and mood1_lower in similar_moods:
            return True

    return False

def recommend_songs(user_prefs: UserProfile, songs: List[Song], k: int = 5) -> List[Tuple[Song, float, List[str]]]:
    """
    Scores all songs and returns the top k recommendations sorted by score (highest first).
    Expected return format: [(song, score, reasons), ...]
    """
    scored_songs = [
        (song, *score_song(user_prefs, song))
        for song in songs
    ]

    return sorted(scored_songs, key=lambda x: x[1], reverse=True)[:k]
