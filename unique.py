import os
import sys
from xml.etree import ElementTree
from xml.etree.ElementTree import ParseError

from decode import extract_tablet_lines, extract_tablet_words


class TLHdig:
    def __init__(self):
        self.total_words = 0
        self.broken_words = 0
        self.unique_words = set()

    def load_word(self, word_element):
        if word_element.text:
            result = "<i>" + word_element.text + "</i>"
        else:
            result = ""
        for child in word_element:
            if child.tag == 'd':
                result += "<sup>" + "".join(child.itertext()) + "</sup>"
            elif child.tag == 'sGr':
                result += "".join(child.itertext())
            elif child.tag == 'aGr':
                child_text = "".join(child.itertext())
                if child_text:
                    result += "<i>" + child_text + "</i>"
            elif child.tag == 'num':
                result += "".join(child.itertext())
            if child.tail:
                result += "<i>" + child.tail + "</i>"
        if not result:
            return None

        self.total_words += 1

        if 'x' in result or result.startswith('-') or result.endswith('-'):
            self.broken_words += 1
            return None

        return result.replace("</i><i>", "")

    def load_file(self, path):
        tree = ElementTree.parse(path)
        root = tree.getroot()
        for w in root.iter('w'):
            word = self.load_word(w)
            self.unique_words.add(word)

    def load(self, path):
        for subdir, dirs, files in os.walk(path):
            for file in files:
                filepath = subdir + os.sep + os.fsdecode(file)
                if filepath.endswith(".xml"):
                    try:
                        self.load_file(filepath)
                    except ParseError as e:
                        print("Error loading file: " + filepath + " " + str(e))
                        break

def is_broken_word(word):
    word = word.replace('<i>', '').replace('</i>', '')
    return (not word or 'x' in word or word.startswith(']') or word.endswith('[') or word.endswith('-') or word.startswith('-')
            or word.startswith('(-)') or word.endswith('(-)') or word.startswith('Or'))

english_words = ["'", '′', 'ii', 'iv', 'ab', 'to', 'the', 'obv', 'rev', 'u.e.', 'lo.e.', 'of', 'one', 'or',
                 'is', 'gap', 'few', 'end', 'due', 'are', 'Possibly']
garbage = [']', '[', '<sup></sup>', '<sup>?</sup>', '<sup>(?)</sup>', '?', '<i></i>', '</i><i>',
           '<sup>1</sup>', '<sup>2</sup>', '<sup>3</sup>', '<sup><i>1</sup></i>', '<sup>()<i>1</sup></i>']

def is_english_word(word):
    if any(w in word for w in english_words): return True
    word = word.replace('<i>', '').replace('</i>', '')
    if word.islower() and not '<sup>' in word:
        syllables = word.split('-')
        if any((len(s) > 3) for s in syllables):
            return True
    return False


def collect_unique_words(path):
    tlhdig = TLHdig()
    tlhdig.load(path)

    seen_words = set()
    total_words = 0
    broken_words = 0
    unique_words = []
    unique_word_attestations = {}
    files = list(filter(lambda f: f.endswith(".pdf") and f.startswith("Or"), os.listdir("pdfs")))
    for f in files:
        print("Processing " + f)
        lines = extract_tablet_lines("pdfs/" + f)
        base_height = lines[0]['chars'][0]['height']
        for l in lines[1:]:   # the first line is the tablet title
            words = extract_tablet_words(l, base_height)
            for word in words:
                if is_english_word(word): continue
                total_words += 1

                if word in seen_words: continue
                seen_words.add(word)   # we add both attested and cleaned version to seen words
                for x in garbage:
                    word = word.replace(x, '')
                if is_broken_word(word):
                    broken_words += 1
                    print("Skipping broken word: " + word + "")
                    continue
                if any(c.isdigit() for c in word):
                    continue

                if '<' not in word and all(c.islower() or c == '-' for c in word):
                    word = "<i>" + word + "</i>"
                if word in unique_words:
                    unique_word_attestations[word].append(f.removesuffix(".pdf"))
                elif word not in seen_words:
                    seen_words.add(word)
                    if word not in tlhdig.unique_words:
                        unique_words.append(word)
                        unique_word_attestations[word] = [f.removesuffix(".pdf")]

    unique_words.sort()

    html = open("uniques.html", "w", encoding="utf-8")
    html.write("<html><head><meta charset='utf-8'></head><body>")
    for unique_word in unique_words:
        html.write(unique_word + ": " + ", ".join(unique_word_attestations[unique_word]) + "<br/>\n")
    html.write("</body></html>")

    print("Total words: {0}".format(total_words))
    print("Broken words: {0}".format(broken_words))
    print("Total unique words: {0}".format(len(unique_words)))
    print("TLHdig total words: {0}".format(tlhdig.total_words))
    print("TLHdig broken words: {0}".format(tlhdig.broken_words))
    print("TLHdig unique words: {0}".format(len(tlhdig.unique_words)))

if __name__ == "__main__":
    collect_unique_words(sys.argv[1])
