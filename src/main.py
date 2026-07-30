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
    result = engine.process_user_request(
        user_request,
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

    print(f"\n✨ Final Confidence: {result.confidence:.1%}")
    print(f"   (How confident the system is that these match your request)")

    # Display low-confidence explanation if applicable
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
        print(f"   ⭐ Score: {score:.3f} / 1.000")
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

        # Check if input is too short or just nonsense
        if len(user_input.split()) < 2:
            print("   ❌ Please be more specific about what kind of music you want\n")
            continue

        try:
            print()
            result = engine.process_user_request(user_input, k=5, min_match_rate=0.7)

            # Simplified output for interactive mode
            print("\n📝 Your Request: " + user_input)
            print("=" * 70)
            print("\n🎵 Top 5 Recommendations:\n")

            for rank, (song, score, reasons) in enumerate(result.recommendations, 1):
                print(f"{rank}. {song.title} by {song.artist}")
                print(f"   Genre: {song.genre} | Mood: {song.mood} | Energy: {song.energy:.2f}")
                print(f"   ⭐ Score: {score:.3f} / 1.000")
                print(f"   Why: {reasons[0] if reasons else 'Good match!'}")
                print()

            print(f"Confidence Level: {result.confidence:.1%}")
            print("=" * 70)
            print()
        except Exception as e:
            print(f"   ❌ Error processing request: {str(e)}")
            print("   Please try rephrasing your request.\n")


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

    # Test with predefined profiles using natural language requests
    print("\n\n📌 DEMO MODE: Testing with predefined user profiles\n")
    for profile_name, user_request in USER_REQUESTS.items():
        display_recommendations_with_reliability(profile_name, user_request, songs, k=5)
        input("\n(Press Enter to see next user profile...)")

    # Ask if user wants to try interactive mode
    print("\n" + "=" * 70)
    response = input("\nWould you like to try interactive mode? (y/n) > ").strip().lower()
    if response in ['y', 'yes']:
        interactive_mode(songs)


if __name__ == "__main__":
    main()
