"""Module entry point for both source and packaged builds."""
import sys

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--verify-voice-assets":
        from aura.packaging_check import write_voice_check_report
        sys.exit(write_voice_check_report(sys.argv[2]))
    else:
        from aura.main import main
        main()
