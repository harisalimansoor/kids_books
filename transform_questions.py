"""
Transform questions: very conservative pattern replacement.
Only changes phrases that are clearly identifiable.
"""
import re

INPUT = "extracted_bank/grade_1_uk_year_1_templated_final_categories_visual_updated.txt"
OUTPUT = INPUT

# Container words
CONTAINERS = r'(?:basket|bowl|jar|box|bag|bucket|bunch|bundle|pack|pile|heap)'

# Patterns: (regex, replacement) — applied in order
PATTERNS = [

    # ─── Replace "in {adj} container" → "in front of them" ───
    (rf"\bin (?:a|an|the|her|his|their)\s+(?:\w+\s+){{{0,3}}}{CONTAINERS}\b",
     "in front of them"),

    # ─── Replace "on {adj} container" → "in front of them" ───
    (rf"\bon (?:a|an|the|her|his|their)\s+(?:\w+\s+){{{0,3}}}{CONTAINERS}\b",
     "in front of them"),

    # ─── Replace "into the/their container" → "" (remove) ───
    (rf"\binto (?:the|their|a|an)\s+(?:\w+\s+){{{0,3}}}{CONTAINERS}\b",
     ""),

    # ─── Replace "out of the/their container" → "" (remove) ───
    (rf"\bout of (?:the|their|a|an)\s+(?:\w+\s+){{{0,3}}}{CONTAINERS}\b",
     ""),

    # ─── Replace "inside" when container-related → "in front of them" ───
    (r"\binside,?\s*(?:and|with)?",
     "in front of them "),

    # ─── "in her lap" → "in front of her" ───
    (r"\bin (?:his|her|their) (?:lap|hands?|pocket)",
     "in front of them"),

    # ─── "in his/her basket" (possessive) → "in front of them" ───
    (rf"\bin (?:his|her|their) {CONTAINERS}\b",
     "in front of them"),

    # ─── "onto the table" → "in front of them" ───
    (r"\bonto the (?:table|floor|ground)\b",
     "in front of them"),

    # ─── Remove "If they pour/put/add/empty..." conditional clauses ───
    (r"\s*If (?:they|he|she|you|we|someone) (?:pour|put|add|empty|pour all|put all|add all|empty all) .+?\.",
     ""),

    # ─── "N are being taken/carried/given away" → "N have a red X on them" ───
    (r"(\d+)\s+\w+(?:\s+\w+)?\s+are being (?:taken|carried|given|swept) away",
     r"\1 of them have a red X on them"),

    # ─── "N have/has been taken/sold/eaten" → "N have a red X on them" ───
    (r"(\d+)\s+\w+(?:\s+\w+)?\s+(?:have|has) been (?:taken|sold|eaten|given|lost|removed)",
     r"\1 of them have a red X on them"),

    # ─── "N have fallen out/down" → "N have a red X on them" ───
    (r"(\d+)\s+\w+(?:\s+\w+)?\s+(?:have|has) fallen (?:out|down|off)",
     r"\1 of them have a red X on them"),

    # ─── "are left" → "are not crossed out" ───
    (r"\bare left\b", "are not crossed out"),

    # ─── "left in" → "not crossed out in" ───
    (r"\bleft (?:in|on|with|inside|the)\b",
     "not crossed out \g<0>"),

    # ─── Remove "But, oh no!" / "Then," / "After that," / "Now," sequences ───
    (r"\s*(?:But,?\s*oh no!?\s*|Then,?\s*|After that,?\s*|Now,?\s*)(?:look\s*[:,])?\s*",
     " "),

    # ─── Remove "that {role} has left / still" ───
    (r",?\s*(?:that|which)\s+[\w{}]+\s+(?:has|had)\s+(?:left|still)\b",
     ""),

    # ─── "with a X marked through them" → "have a red X on them" ───
    (r"with (?:a|an)\s+\w+\s+X (?:marked|drawn) through (?:them|it)",
     "have a red X on them"),

    # ─── Cleanup ───
    (r"\s+in front of them\s+in front of them", " in front of them "),
    (r"\s{2,}", " "),
    (r"\s+\.", "."),
    (r"\s+\?", "?"),
    (r"\s+,", ","),
    (r",\s*,", ","),
    (r"\. \.", "."),
    (r"\s*;\s*", "; "),
    (r"\s+$", ""),
    (r"^\s+", ""),
]


def transform(line: str) -> str:
    if line.startswith("===") or not line.strip():
        return line
    if not line.startswith("Look at the picture"):
        return line

    for pattern, replacement in PATTERNS:
        line = re.sub(pattern, replacement, line, flags=re.IGNORECASE)

    # Capitalize first letter after "!" if needed
    line = re.sub(r'!\s*[a-z]', lambda m: m.group(0).upper(), line)

    return line


def main():
    with open(INPUT, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    result = [transform(l) for l in lines]

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.writelines(result)

    print(f"Transformed {len(lines)} lines")


if __name__ == '__main__':
    main()
