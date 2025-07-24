import os
import re
import datetime
import shutil
import json
import logging
import boto3
import time
import tempfile
from dotenv import load_dotenv

from ai_services import extract_chapter_from_pdf, extract_dialogue_from_pdf
from pdf_services import split_chapter_from_pdf
from tts_services import generate_voice

# --- Configuration ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "TTS_Jobs")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# --- AWS Clients ---
sqs = boto3.client("sqs", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# --- Helper Functions ---

def upload_directory_content_to_s3(local_folder_path: str, s3_prefix: str):
    """
    Uploads the content of a local folder to a specified S3 prefix,
    """
    print(f"Uploading contents of '{local_folder_path}' to 's3://{S3_BUCKET_NAME}/{s3_prefix}'")

    for root, _, files in os.walk(local_folder_path):
        for filename in files:
            # 1. Get the full local path
            local_path = os.path.join(root, filename)

            # 2. Get the relative path to maintain folder structure
            relative_path = os.path.relpath(local_path, local_folder_path)

            # 3. Construct the S3 key (ensure forward slashes for S3)
            s3_key = os.path.join(s3_prefix, relative_path).replace("\\", "/")

            # 4. Upload the file
            print(f"  Uploading {local_path} -> s3://{S3_BUCKET_NAME}/{s3_key}")
            s3.upload_file(local_path, S3_BUCKET_NAME, s3_key)

def is_valid_dialogue(text: str) -> bool:
    """Checks if a string is suitable for TTS."""
    return bool(text and re.search(r'[a-zA-Z0-9]', text))

def process_chapter_audio(chapter_dialogues: list, output_dir: str, job_id: str, chapter_title: str, ):
    """Generates audio for each dialogue and saves it along with metadata."""
    chapter_metadata = {
        "job_id": job_id,
        "title": chapter_title,
        "date_added": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dialogues": [],
    }

    for i, novel_dialogue in enumerate(chapter_dialogues):
        speaker = novel_dialogue.get("speaker")
        dialogue = novel_dialogue.get("dialogue")

        if not is_valid_dialogue(dialogue):
            continue
        
        audio_filename = f"dialogue_{i}.mp3"
        local_audio_path = os.path.join(output_dir, audio_filename)
        
        try:
            generate_voice(text=dialogue, dst_path=local_audio_path)

        except Exception as e:
            logger.error(f"[{job_id}] Voice gen FAILED for dialogue: '{dialogue[:50]}...'. Error: {e}")
            audio_filename = "ERROR"

        chapter_metadata['dialogues'].append({
            "speaker": speaker,
            "text": dialogue,
            "audio_file": audio_filename,
        })

    # Save the metadata for this chapter
    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(chapter_metadata, f, ensure_ascii=False, indent=2)

# --- Main Job Logic ---

def process_job(job_id: str):
    """Main function to process a single TTS job."""
    # Create a unique temporary directory for this specific job
    job_temp_dir = os.path.join(tempfile.gettempdir(), job_id)
    os.makedirs(job_temp_dir, exist_ok=True)
    local_pdf_path = os.path.join(job_temp_dir, "novel.pdf")

    try:
        logger.info(f"[{job_id}] - Starting job processing.")
        table.update_item(
            Key={"JobID": job_id},
            UpdateExpression="SET JobStatus = :status",
            ExpressionAttributeValues={":status": "PROCESSING"},
        )

        source_s3_key = f"sources/{job_id}/novel.pdf"
        logger.info(f"[{job_id}] - Downloading {source_s3_key}...")
        s3.download_file(S3_BUCKET_NAME, source_s3_key, local_pdf_path)

        # Step 1: Get chapter page ranges
        chapter_data = extract_chapter_from_pdf(local_pdf_path)

        # Step 2: Split original PDF into chapter PDFs in a temp sub-folder
        chapters_dir = os.path.join(job_temp_dir, "chapters")
        chapter_paths = split_chapter_from_pdf(src_path=local_pdf_path,  dst_path=chapters_dir, chapters_stem=chapter_data,)
        
        # Step 3: Process each chapter PDF
        generated_output_dir = os.path.join(job_temp_dir, "generated_output")
        os.makedirs(generated_output_dir, exist_ok=True)

        for i, chapter_path in enumerate(chapter_paths):
            print(f"Processing: {chapter_path}...")
            _filename = os.path.basename(chapter_path) #novelname.pdf
            chapter_title = os.path.splitext(_filename)[0] #novelname
            # Create a dedicated output folder for each chapter, use index to avoid same chapter name
            chapter_output_dir = os.path.join(generated_output_dir, f"{i}_{chapter_title}")
            os.makedirs(chapter_output_dir, exist_ok=True)

            dialogues = extract_dialogue_from_pdf(chapter_path)
            process_chapter_audio(chapter_dialogues=dialogues, output_dir=chapter_output_dir, job_id=job_id, chapter_title=chapter_title)
        
        # Step 4: Upload all generated files to S3
        logger.info(f"[{job_id}] - Uploading generated files to S3.")
        upload_directory_content_to_s3(generated_output_dir, f"generated/{job_id}")

        table.update_item(
            Key={"JobID": job_id},
            UpdateExpression="SET JobStatus = :status",
            ExpressionAttributeValues={":status": "COMPLETE"},
        )
        logger.info(f"[{job_id}] - Job completed successfully.")

    except Exception as e:
        logger.error(f"[{job_id}] - Job failed. Reason: {e}", exc_info=True)
        table.update_item(
            Key={"JobID": job_id},
            UpdateExpression="SET JobStatus = :status, ErrorMessage = :error",
            ExpressionAttributeValues={":status": "FAILED", ":error": str(e)},
        )
    finally:
        # Cleanup the job-specific temporary directory
        if os.path.exists(job_temp_dir):
            shutil.rmtree(job_temp_dir)
            logger.info(f"[{job_id}] - Cleaned up temporary directory.")

# --- Main Loop ---

if __name__ == "__main__":
    if not all([SQS_QUEUE_URL, DYNAMODB_TABLE_NAME, S3_BUCKET_NAME]):
        logger.critical("Missing required environment variables. Exiting.")
        exit(1)

    logger.info("TTS Worker started. Polling for jobs...")
    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20
            )

            if "Messages" in response:
                message = response["Messages"][0]
                receipt_handle = message["ReceiptHandle"]
                job_id = message["Body"]

                logger.info(f"Received job: {job_id}")
                process_job(job_id)

                sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
        except Exception as e:
            logger.critical(f"CRITICAL ERROR in main loop: {e}", exc_info=True)
            # Wait for a moment to prevent rapid-fire failures on a systemic issue
            time.sleep(10)