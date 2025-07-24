import unittest
from unittest.mock import patch, MagicMock

# Import the script you want to test
import worker

class TestWorkerUtils(unittest.TestCase):
    """Tests for simple, standalone helper functions."""

    def test_is_valid_dialogue(self):
        print("Running test: test_is_valid_dialogue")
        # Test cases that should return True
        self.assertTrue(worker.is_valid_dialogue("Hello world"))
        self.assertTrue(worker.is_valid_dialogue("This is test 1."))
        
        # Test cases that should return False
        self.assertFalse(worker.is_valid_dialogue(""))
        self.assertFalse(worker.is_valid_dialogue("..."))
        self.assertFalse(worker.is_valid_dialogue(" "))
        self.assertFalse(worker.is_valid_dialogue(None))


class TestProcessJob(unittest.TestCase):
    """Tests for the main process_job function, with dependencies mocked."""

    # We use @patch to replace external functions with "fakes" (Mocks) during the test.
    # The mocks are passed as arguments to the test method in reverse order of the decorators.
    @patch('worker.shutil.rmtree')
    @patch('worker.upload_folder_to_s3')
    @patch('worker.process_chapter_audio')
    @patch('worker.extract_dialogue_from_pdf')
    @patch('worker.split_chapter_from_pdf')
    @patch('worker.extract_chapter_from_pdf')
    @patch('worker.table')
    @patch('worker.s3')
    def test_successful_job(self, mock_s3, mock_table, mock_extract_chapter,
                            mock_split, mock_extract_dialogue, mock_process_voice,
                            mock_upload, mock_rmtree):

        print("\nRunning test: test_successful_job (Happy Path)")
        
        # --- ARRANGE (Setup our Mocks) ---
        # Configure the return values of our fake functions to simulate a successful run.
        mock_extract_chapter.return_value = [{"title": "Chapter 1", "start_page": 1, "end_page": 2}]
        mock_split.return_value = ["/tmp/test-job/chapter_1.pdf"]
        mock_extract_dialogue.return_value = [{"speaker": "Narrator", "dialogue": "It was a dark and stormy night."}]

        # --- ACT (Run the function we are testing) ---
        worker.process_job("test-job-id")

        # --- ASSERT (Check if our code behaved as expected) ---
        # Was the source file downloaded from S3?
        mock_s3.download_file.assert_called_once()
        
        # Was the status updated to PROCESSING at the start?
        first_update_call = mock_table.update_item.call_args_list[0]
        self.assertIn("PROCESSING", str(first_update_call))

        # Were all the processing steps called?
        mock_extract_chapter.assert_called_once()
        mock_split.assert_called_once()
        mock_extract_dialogue.assert_called_once()
        mock_process_voice.assert_called_once()
        mock_upload.assert_called_once()

        # Was the status updated to COMPLETE at the end?
        final_update_call = mock_table.update_item.call_args_list[-1]
        self.assertIn("COMPLETE", str(final_update_call))

        # Was the temporary directory cleaned up?
        mock_rmtree.assert_called_once()


    @patch('worker.shutil.rmtree')
    @patch('worker.table')
    @patch('worker.s3')
    @patch('worker.extract_chapter_from_pdf')
    def test_job_failure(self, mock_extract_chapter, mock_s3, mock_table, mock_rmtree):
        print("\nRunning test: test_job_failure (Error Path)")

        # --- ARRANGE ---
        # Simulate a failure from the Gemini API call
        mock_extract_chapter.side_effect = Exception("Gemini API rate limit exceeded")

        # --- ACT ---
        worker.process_job("failed-job-id")

        # --- ASSERT ---
        # Check that the status was updated to FAILED in DynamoDB
        final_update_call = mock_table.update_item.call_args_list[-1]
        self.assertIn("FAILED", str(final_update_call))
        self.assertIn("Gemini API rate limit exceeded", str(final_update_call))
        
        # Check that cleanup still happened even after failure
        mock_rmtree.assert_called_once()


if __name__ == '__main__':
    unittest.main()