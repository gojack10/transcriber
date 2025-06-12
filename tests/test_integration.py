import os
from pathlib import Path
import pytest
from transcriber import transcribe_files

@pytest.mark.integration
def test_transcribe_files_whisper_model_integration():
    """
    integration test to verify that the real transcribe_files function can
    load the tiny.en whisper model and produce a correct transcription.
    this test is marked as 'integration' and should be run selectively.
    """
    # path to the sample audio file
    sample_file = Path(__file__).parent / "samples/youtube_sample.wav"
    assert sample_file.exists(), "sample audio file not found!"

    # expected transcription text
    expected_text = "He's got content creator, y'all. You gotta be tough to get to the room. Terrible defense."

    # run the real transcribe_files function
    (
        successfully_transcribed,
        failed_transcriptions,
        transcription_results,
    ) = transcribe_files(model_name="tiny.en", file_paths=[sample_file])

    # assert that the transcription was successful
    assert len(successfully_transcribed) == 1
    assert not failed_transcriptions
    assert str(sample_file) in transcription_results

    # clean up the transcribed text for comparison
    # lowercasing and removing punctuation for a more robust check
    transcribed_text = transcription_results[str(sample_file)].strip().lower()
    cleaned_expected_text = expected_text.strip().lower()

    # check that the core message is present
    assert cleaned_expected_text in transcribed_text