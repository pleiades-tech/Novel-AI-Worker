from pydantic import BaseModel

class NovelChapter(BaseModel):
    title: str
    start_page: int
    end_page: int

class NovelDialogue(BaseModel):
  speaker: str
  dialogue: str