import os
import re
import shutil
import json
import logging
import boto3
from dotenv import load_dotenv
from ai_services import extract_chapter_from_pdf, extract_dialogue_from_pdf
from pdf_services import split_chapter_from_pdf
from tts_services import generate_voice
from types import NovelDialogue
from config import TEMP_DIR, TEMP_GENERATED

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AWS_REGION = "ap-southeast-1"
SQS_QUEUE_URL = "https://sqs.ap-southeast-1.amazonaws.com/331225031913/novel-ai-tts-jobs-queue"
DYNAMODB_TABLE_NAME = "TTS_Jobs"
S3_BUCKET_NAME = "novel-ai-storage"

sqs = boto3.client("sqs", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

def upload_folder_to_s3(job_id: str, local_folder_path: str):
    """
    Uploads the entire content of a local folder to a specified S3 prefix.
    """

    # Walk through the local folder
    for root, dirs, files in os.walk(local_folder_path):
        for filename in files:
            # Construct the full local path
            local_path = os.path.join(root, filename)

            # Construct the relative path for S3
            relative_path = os.path.relpath(local_path, local_folder_path)
            s3_key = os.path.join(job_id, relative_path)

            print(f"Uploading {local_path} to s3://{S3_BUCKET_NAME}/{s3_key}")
            s3.upload_file(local_path, S3_BUCKET_NAME, s3_key)

def is_valid_dialogue(text: str) -> bool:
    """
    Checks if a string is suitable for TTS.

    Returns True if the string contains at least one letter or number,
    False otherwise.
    """
    return bool(text and re.search(r'[a-zA-Z0-9]', text))


def process_voice_from_dialogue(chapter_dialogues: list[NovelDialogue], full_output_path: str):
    chapter_metadata = []
    audio_url = ""
    for novel_dialogue in chapter_dialogues:
        speaker = novel_dialogue.get("speaker")
        dialogue = novel_dialogue.get("dialogue")

        if not is_valid_dialogue:
            continue

        try: 
            generate_voice(dialogue)
        except Exception as e:
            logger.error(f"[{job_id}] Voice gen FAILED for dialogue: {dialogue}. Error: {e}")

        chapter_metadata.append({
            "speaker": speaker,
            "text": dialogue,
            "audio_url": audio_url,
        })

    with full_output_path.open("w", encoding="utf-8") as f:
        json.dump(chapter_metadata, f, ensure_ascii=False, indent=2)

def process_job(job_id: str):
    source_s3_key = f"sources/{job_id}/novel.pdf"
    local_pdf_path = f"/tmp/{job_id}.pdf"


    print(f"Downloading {source_s3_key}...")
    s3.download_file(S3_BUCKET_NAME, source_s3_key, local_pdf_path)

    try:
        table.update_item(
            Key={"JobID": job_id},
            UpdateExpression="SET JobStatus = :status",
            ExpressionAttributeValues={":status": "PROCESSING"},
        )

        # Extract PDF
        chapter_stem = extract_chapter_from_pdf(local_pdf_path)
        
        # Split PDF to chapter chunks
        chapter_list = split_chapter_from_pdf(chapter_stem)
        
        # Extract text
        for index, chapter_path in enumerate(chapter_list):

            local_output_path = os.path.join(TEMP_GENERATED, f"{index}_", os.path.basename(chapter_path))
            os.makedirs(local_output_path, exist_ok=True)

            chapter_dialogues = extract_dialogue_from_pdf(chapter_path)

            # Extract Voice
            process_voice_from_dialogue(chapter_dialogues=chapter_dialogues, full_output_path=local_output_path)
        
        upload_folder_to_s3(TEMP_GENERATED)

    except Exception as e:
        logger.error(f"Job {job_id} failed. Reason: {e}")
        table.update_item(
            Key={"JobID": job_id},
            UpdateExpression="SET JobStatus = :status, ErrorMessage = :error",
            ExpressionAttributeValues={":status": "FAILED", ":error": str(e)},
        )
    
    finally:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            logger.info(f"Cleaned up temporary directory: {TEMP_DIR}")


if __name__ == "__main__":
    logger.info("TTS Worker started. Polling for jobs...")
    response = sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20  # Long polling
        )
    if "Messages" in response:
        message = response["Messages"][0]
        receipt_handle = message["ReceiptHandle"]
        job_id = message["Body"]

        process_job(job_id)
        sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)



# Create temp folders

