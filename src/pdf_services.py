import os
import shutil
from PyPDF2 import PdfReader, PdfWriter
from datatypes import NovelChapter

def split_chapter_from_pdf(input_pdf_path: str, chapters_stem: list[NovelChapter], output_dir: str):
    """
    Splits a single PDF into multiple chapter-based PDFs based on JSON data.
    """

    print("split chapter from pdf..")

    os.makedirs(output_dir, exist_ok=True)

    reader = PdfReader(input_pdf_path)

    if len(chapters_stem) == 1:
        title = chapters_stem[0].get("title")

        filename_safe_title = title.strip()
        filename_safe_title = "".join(c if c.isalnum() or c in (' ', '-') else '_' for c in filename_safe_title)
        filename_safe_title = filename_safe_title.replace(' ', '_')
        filename_safe_title = filename_safe_title.rstrip('._')
        filename_safe_title = filename_safe_title.replace('__', '_')

        output_filename = os.path.join(output_dir, f"{filename_safe_title}.pdf")
        shutil.copy2(input_pdf_path, output_filename)

        return [output_filename]

    for chapter_info in chapters_stem:
        title = chapter_info["title"]
        start_page = chapter_info["start_page"]
        end_page = chapter_info["end_page"]

        writer = PdfWriter()

        output_file_list=[]

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

        output_filename = os.path.join(output_dir, f"{filename_safe_title}.pdf")

        output_file_list.append(output_filename)

        with open(output_filename, "wb") as output_pdf:
            writer.write(output_pdf)
        print(f"Created: {output_filename} (Pages {start_page}-{end_page})")

    return output_file_list