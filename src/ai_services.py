import os
import json
import pathlib
from tenacity import retry, stop_after_attempt, wait_fixed
from google import genai
from google.genai import types
from pydantic import BaseModel
from datatypes import NovelChapter, NovelDialogue
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv('GEMINI_KEY'))

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def extract_chapter_from_pdf(input_path):
  print(f"extract chapter from {input_path}...")

  filepath = pathlib.Path(input_path)
  prompt = "From the provided novel pdf file, extract the start and end page of each chapter in json format. Ignore the extra chapter that have to story in it e.g. Character_Pages, Other_Volumes, Appendix etc."
  response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(
          data=filepath.read_bytes(),
          mime_type='application/pdf',
        ),
        prompt],
      config= {
          'response_mime_type': "application/json",
          "response_schema": list[NovelChapter]
      })
  return json.loads(response.text)

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def extract_dialogue_from_pdf(input_path):
  print(f"extract dialogue from {input_path}...")

  filepath = pathlib.Path(input_path)
  prompt = """
  From the provided novel pdf file, I want you to extract the dialogue found in it in to json format.
  you must follow this instructions
    1. Visit all of the texts, understand it and think about who is the one owning each line of the text
    2. The character can be 'Unknown', 'Narrator', and the Character name itself
    3. Give response in JSON format with key of speaker and dialogue like example, e.g., [
        {
            "speaker": "Narrator",
            "dialogue": "Walking around in the middle of a seemingly never-ending darkness, at the end of his path.",
        },
        {
            "speaker": "Subaru",
            "dialogue": "So that's how, falling down after all sorts of things happened, and then walking around feeling hopeless and a little hungry, I stumbled into you... Satisfied?",
        }, 
        ]
  """
  response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(
          data=filepath.read_bytes(),
          mime_type='application/pdf',
        ),
        prompt],
      config= {
          'response_mime_type': "application/json",
          "response_schema": list[NovelDialogue]
      })
  return json.loads(response.text)