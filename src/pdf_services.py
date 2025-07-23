import os
from PyPDF2 import PdfReader, PdfWriter
from config import TEMP_NOVEL
from types import NovelChapter

def split_chapter_from_pdf(input_pdf_path: str, chapters_stem: list[NovelChapter]):
    """
    Splits a single PDF into multiple chapter-based PDFs based on JSON data.
    """
    reader = PdfReader(input_pdf_path)

    for chapter_info in chapters_stem:
        title = chapter_info["title"]
        start_page = chapter_info["start_page"]
        end_page = chapter_info["end_page"]

        output_file_list = []

        writer = PdfWriter()

        for page_num in range(start_page - 1, end_page):
            if page_num < len(reader.pages):
                writer.add_page(reader.pages[page_num])
            else:
                print(f"Warning: Page {page_num + 1} for '{title}' is out of bounds for the input PDF. Skipping.")
                break

        # Sanitize the title to create a safe filename
        filename_safe_title = title.strip()
        filename_safe_title = "".join(c if c.isalnum() or c in (' ', '-') else '_' for c in filename_safe_title)
        filename_safe_title = filename_safe_title.replace(' ', '_')
        filename_safe_title = filename_safe_title.rstrip('._')
        filename_safe_title = filename_safe_title.replace('__', '_')

        output_filename = os.path.join(TEMP_NOVEL, f"{filename_safe_title}.pdf")

        output_file_list.append(output_filename)

        with open(output_filename, "wb") as output_pdf:
            writer.write(output_pdf)
        print(f"Created: {output_filename} (Pages {start_page}-{end_page})")

    return output_filename