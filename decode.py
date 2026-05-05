import os

import pdfplumber
from pdfplumber.utils import extract_words

superscript_prefixes = ['D', 'LÚ', 'GIŠ']
superscript_suffixes = ['ḪI.A', 'MEŠ']

def sort_key(item: str):
    base = item.removeprefix("Or. ").removesuffix(".pdf")
    (year, number) = base.split("_")
    year = int(year)
    while len(number) < 6: number = "0" + number
    return year + 100 if year < 90 else year, number


def extract_tablet_words(l, base_height):
    words = extract_words(l['chars'], return_chars=True)
    prev_word = {}
    result = [""]
    for w in words:
        if prev_word and prev_word['text'] not in superscript_prefixes and w['text'] not in superscript_suffixes:
            result.append("")
        prev_word = w
        italic = False
        superscript = False
        for c in w['chars']:
            new_italic = 'Italic' in c['fontname']
            new_superscript = base_height - c['height'] > 3

            if superscript and not new_superscript: result[-1] += "</sup>"
            if italic and not new_italic: result[-1] += "</i>"
            if not italic and new_italic: result[-1] += "<i>"
            if not superscript and new_superscript: result[-1] += "<sup>"
            italic = new_italic
            superscript = new_superscript

            result[-1] += c['text']

        if superscript: result[-1] += '</sup>'
        if italic: result[-1] += '</i>'
    return result


def extract_tablet_lines(path):
    lines = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.get_textmap()
            lines.extend(text.extract_text_lines())
    return lines

def convert_tablets():
    html = open("sapinuwa.html", "w", encoding="utf-8")
    html.write("<html><head><meta charset='utf-8'></head><body>")

    files = list(filter(lambda f: f.endswith(".pdf") and f.startswith("Or"), os.listdir("pdfs")))
    files.sort(key = sort_key)
    for f in files:
        html.write("<h1>" + f + "</h1>")
        lines = extract_tablet_lines("pdfs/" + f)
        base_height = lines[0]['chars'][0]['height']
        for l in lines:
            words = extract_tablet_words(l, base_height)
            html.write(" ".join(words))
            html.write("<br/>\n")

    html.write("</body></html>")

if __name__ == "__main__":
    convert_tablets()
