from blind_assist.speech import Transcriber


def main() -> None:
    transcriber = Transcriber()
    print("Recording for 4 seconds...")
    text = transcriber.record_and_transcribe(duration=4.0)
    print(f"Heard: {text or '[nothing detected]'}")


if __name__ == "__main__":
    main()
