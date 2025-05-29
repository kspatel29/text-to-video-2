from manim import config
from manim_voiceover.services.gtts import GTTSSpeechService

# Configure manim-voiceover to use the built-in GTTSSpeechService
config.voiceover_defaults = {
    "service": GTTSSpeechService(language="en", tld="com"),
    "transcription_model": "tiny",  # Whisper for word-timings
}

# Set a random seed for stable randomness across runs
config.random_seed = 42
