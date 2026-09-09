"""
Command line runner for the Music Recommender Simulation with Reliability Testing.

The main recommender now uses a reliability engine that:
1. Parses natural language input into user preferences
2. Scores recommendations
3. Validates whether they match user intent
4. Iteratively adjusts weights if validation fails
5. Explains all decisions to the user
"""

from src.recommender import load_songs, UserProfile, EXAMPLE_USER
from src.reliability_engine import ReliabilityEngine
from src.validator import format_validation_summary
from src.preference_ui import review_preferences


# Define distinct user preference profiles for testing
USER_PROFILES = {
    "Chill Lofi Lover": EXAMPLE_USER,

    "High-Energy Pop Fan": UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.85,
        likes_acoustic=False
    ),

    "Intense Metal Head": UserProfile(
        favorite_genre="metal",
        favorite_mood="aggressive",
        target_energy=0.95,
        likes_acoustic=False
    ),

    "Happy but Exhausted": UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.2,
        likes_acoustic=True
    ),

    "Loud & Acoustic Metal": UserProfile(
        favorite_genre="metal",
        favorite_mood="aggressive",
        target_energy=0.9,
        likes_acoustic=True
    ),

    "Genre Agnostic Mediator": UserProfile(
        favorite_genre="jazz",
        favorite_mood="focused",
        target_energy=0.5,
        likes_acoustic=True
    ),
}

# Natural language descriptions that get parsed by the reliability engine
USER_REQUESTS = {
    "Chill Lofi Lover": "I want lofi music that's chill and relaxing, I like acoustic sounds",
    "High-Energy Pop Fan": "I'm in the mood for upbeat happy pop music, high energy please",
    "Intense Metal Head": "I want aggressive metal music, loud and intense, no acoustic stuff",
    "Happy but Exhausted": "I want happy music but I'm really tired and exhausted right now",
    "Loud & Acoustic Metal": "I want metal that's aggressive and loud but also acoustic and unplugged",
    "Genre Agnostic Mediator": "I need focused jazz music, acoustic and medium energy for concentration",
}


def display_recommendations_with_reliability(
    user_name: str, user_request: str, songs, k: int = 5
) -> None:
    """
    Display recommendations using the reliability engine.

    The engine parses natural language, validates recommendations,
    and explains its reasoning process.
    """
    print(f"\n{'='*70}")
    print(f"🎵 Music Recommender for: {user_name}")
    print(f"{'='*70}")
    print(f"User Request: \"{user_request}\"")
    print(f"{'='*70}\n")

    # Create reliability engine and process request
    engine = ReliabilityEngine(songs)
    confirmed = review_preferences(engine.prepare_request(user_request))
    if confirmed is None:
        return
    result = engine.process_user_request(
        user_request,
        confirmed_preferences=confirmed,
        base_profile=None,
        k=k,
        min_match_rate=0.7,
        max_iterations=3,
    )

    # Display decision log (shows parsing, scoring, validation, optimization)
    print("🔍 DECISION LOG:")
    print("=" * 70)
    for log_entry in result.decision_log:
        print(log_entry)

    # Display validation details
    print("\n📊 VALIDATION DETAILS:")
    print("=" * 70)
    for reason in result.validation.reasons:
        print(f"  {reason}")

    print("\n" + format_validation_summary(result.validation))

    # Display catalog coverage explanation below the configured match-rate threshold
    if result.best_attempt_used and result.confidence_low_reason:
        print("\n⚠️  NOTE ON THESE RECOMMENDATIONS:")
        print("=" * 70)
        print(result.confidence_low_reason)

    # Display the actual recommendations
    print("\n🎵 TOP RECOMMENDATIONS:")
    print("=" * 70)
    for rank, (song, score, reasons) in enumerate(result.recommendations, 1):
        print(f"\n{rank}. {song.title} by {song.artist}")
        print(f"   Genre: {song.genre} | Mood: {song.mood} | Energy: {song.energy:.2f}")
        print(f"   Similarity score: {score:.3f} / 1.000")
        print(f"   Why this song:")
        for reason in reasons:
            print(f"     • {reason}")


def interactive_mode(songs) -> None:
    """Allow user to input natural language requests."""
    print("\n" + "=" * 70)
    print("🎵 INTERACTIVE MODE - Natural Language Music Recommender")
    print("=" * 70)
    print("\nTell the recommender what kind of music you want!")
    print("Examples:")
    print("  - 'I want upbeat energetic pop music for my workout'")
    print("  - 'I'm tired and want chill acoustic music'")
    print("  - 'I want aggressive metal but I'm exhausted'")
    print("\nType 'quit' to exit.\n")

    engine = ReliabilityEngine(songs)

    while True:
        user_input = input("📝 What kind of music do you want? > ").strip()

        if user_input.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Thanks for using the Music Recommender!")
            break

        if not user_input:
            print("   ❌ Please describe what you want to listen to (e.g., 'happy pop music')\n")
            continue

        try:
            print()
            confirmed = review_preferences(engine.prepare_request(user_input))
            if confirmed is None:
                continue
            result = engine.process_user_request(user_input, k=5, min_match_rate=0.7, confirmed_preferences=confirmed)

            # Simplified output for interactive mode
            print("\n📝 Your Request: " + user_input)
            print("=" * 70)
            print("\n🎵 Top 5 Recommendations:\n")

            for rank, (song, score, reasons) in enumerate(result.recommendations, 1):
                print(f"{rank}. {song.title} by {song.artist}")
                print(f"   Genre: {song.genre} | Mood: {song.mood} | Energy: {song.energy:.2f}")
                print(f"   Similarity score: {score:.3f} / 1.000")
                print(f"   Preference checks: {result.validation.reasons[rank - 1]}")
                print()

            print(format_validation_summary(result.validation))
            if result.confidence_low_reason:
                print(result.confidence_low_reason)
            print("=" * 70)
            print()
        except Exception as e:
            print(f"   ❌ Error processing request: {str(e)}")
            print("   You can submit the request again and use the numbered preference editors.\n")


def main() -> None:
    # Load songs with error handling
    try:
        songs = load_songs("data/songs.csv")
    except FileNotFoundError:
        print("\n❌ ERROR: data/songs.csv not found")
        print("   Make sure you're running this from the project root directory")
        print("   and that data/songs.csv exists.")
        return
    except Exception as e:
        print(f"\n❌ ERROR loading songs: {str(e)}")
        print("   The CSV file may be malformed or missing required columns:")
        print("   (id, title, artist, genre, mood, energy, tempo_bpm, valence, danceability, acousticness)")
        return

    if not songs:
        print("\n❌ ERROR: No songs loaded from data/songs.csv")
        print("   The CSV file appears to be empty.")
        return

    print("\n" + "=" * 70)
    print("🎵 MUSIC RECOMMENDER WITH RELIABILITY TESTING")
    print("=" * 70)
    print("\nThis recommender uses an AI reliability system that:")
    print("  1. Parses your musical preferences from natural language")
    print("  2. Generates song recommendations")
    print("  3. Validates that recommendations match your intent")
    print("  4. Adjusts weights if recommendations don't match well")
    print("  5. Explains its reasoning transparently")
    print("=" * 70)

    try:
        while True:
            choice = input("\nStart: 1 get recommendations, 2 view demo, q quit > ").strip().lower()
            if choice in ['q', 'quit', 'exit']:
                return
            if choice == '1':
                interactive_mode(songs)
                return
            if choice == '2':
                break
            print("Choose 1 for recommendations, 2 for the demo, or q to quit.")

        print("\n📌 DEMO MODE")
        print("After each profile: r leaves the demo for recommendations; q quits.")
        print("During preference review, x cancels the current profile and opens those options.")
        profiles = list(USER_REQUESTS.items())
        for index, (profile_name, user_request) in enumerate(profiles):
            display_recommendations_with_reliability(profile_name, user_request, songs, k=5)
            last_profile = index == len(profiles) - 1
            while True:
                prompt = ("\nDemo complete: r get recommendations, q quit > " if last_profile else
                          "\nEnter for next profile, r get recommendations, q quit > ")
                choice = input(prompt).strip().lower()
                if choice in ['q', 'quit', 'exit']:
                    return
                if choice == 'r':
                    interactive_mode(songs)
                    return
                if not choice and not last_profile:
                    break
                print("Choose r for recommendations or q to quit." if last_profile else
                      "Press Enter for the next profile, r for recommendations, or q to quit.")
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
