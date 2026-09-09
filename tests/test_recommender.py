from src.recommender import Song, UserProfile, recommend_songs, score_song

def make_test_songs():
    return [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]


def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    songs = make_test_songs()
    results = recommend_songs(user, songs, k=2)

    assert len(results) == 2
    # The pop, happy, high energy song should score higher
    assert results[0][0].genre == "pop"
    assert results[0][0].mood == "happy"


def test_score_song_returns_tuple():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    song = make_test_songs()[0]

    score, reasons = score_song(user, song)
    assert isinstance(score, float)
    assert isinstance(reasons, list)
    assert len(reasons) > 0
    assert 0.0 <= score <= 1.0


def test_default_weights_preserve_original_score():
    from math import isclose
    user = UserProfile("pop", "happy", 0.8, False)
    song = make_test_songs()[0]
    score, reasons = score_song(user, song)
    assert isclose(score, 0.975)
    explicit = {"genre": .4, "mood": .3, "energy": .15, "acoustic": .1, "valence": .05}
    assert score_song(user, song, weights=explicit) == (score, reasons)


def test_custom_weights_change_ranking_and_explanations():
    from math import isclose
    import re
    user = UserProfile("pop", "happy", 0.4, False)
    songs = make_test_songs()
    weights = {"genre": 0., "mood": 0., "energy": 1., "acoustic": 0., "valence": 0.}
    original_weights = weights.copy()
    assert recommend_songs(user, songs, k=1)[0][0].id == 1
    result = recommend_songs(user, songs, k=1, weights=weights)
    song, score, reasons = result[0]
    assert song.id == 2
    assert isclose(score, 1.0)
    contributions = [float(re.search(r"\(\+([0-9.]+)\)", reason).group(1)) for reason in reasons]
    assert contributions == [0., 0., 1., 0., 0.]
    assert isclose(sum(contributions), score)
    assert weights == original_weights
    # A custom call must not change subsequent default scoring.
    assert recommend_songs(user, songs, k=1)[0][0].id == 1
