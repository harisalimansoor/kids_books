import re

INPUT = "extracted_bank/grade_1_uk_year_1_templated_final_categories_visual_updated.txt"
OUTPUT = "extracted_bank/grade_1_uk_year_1_templated_final_categories_visual_static.txt"

PRONOUN = {
    "grandmother_name": "her",
    "grandfather_name": "him",
    "mother_name": "her",
    "father_name": "him",
    "sibling_name": "him",
    "user_name": "{user_name}",
}

def _replace_action_verbs(text: str) -> str:
    # Pattern 1: {role} is/are [verb-ing] [number] [object]
    # Verbs: holding, showing, reading, sitting with, adding
    pat = re.compile(
        r'\{(\w+)\}\s+(?:is|are)\s+'
        r'(?:(?:sitting\s+with)\s+|holding\s+|showing\s+|reading\s+|adding\s+)'
        r'(\d+\s+\w+(?:\s+\w+)*?(?=\s*[,\.;!?]|\s+and\s+|\s+or\s+|\s+but\s+|$))',
        re.IGNORECASE
    )

    def repl(m):
        role = m.group(1)
        obj_part = m.group(2)
        pronoun = PRONOUN.get(role, "him")
        if role == "user_name":
            return f"{{{role}}} has {obj_part} in front of {{{role}}}"
        return f"{{{role}}} has {obj_part} in front of {pronoun}"

    text = pat.sub(repl, text)

    # Pattern 2: {role} is/are [verb-ing] a/an [object] (no number)
    pat_a = re.compile(
        r'\{(\w+)\}\s+(?:is|are)\s+'
        r'(?:holding\s+|showing\s+|reading\s+)'
        r'(a|an)\s+(\w+(?:\s+\w+)*?(?=\s*[,\.;!?]|\s+and\s+|\s+or\s+|\s+but\s+|$))',
        re.IGNORECASE
    )

    def repl_a(m):
        role = m.group(1)
        article = m.group(2).lower()
        obj_part = f"{article} {m.group(3)}"
        pronoun = PRONOUN.get(role, "him")
        if role == "user_name":
            return f"{{{role}}} has {obj_part} in front of {{{role}}}"
        return f"{{{role}}} has {obj_part} in front of {pronoun}"

    text = pat_a.sub(repl_a, text)

    # Pattern 3: someone is giving {role} [count] [object]
    pat2 = re.compile(
        r'someone\s+is\s+giving\s+(?:\{(\w+)\}|them)\s+(\d+\s+\w+(?:\s+\w+)*?(?=\s*[,\.;!?]|\s+and\s+|\s+or\s+|\s+but\s+|$))',
        re.IGNORECASE
    )

    def repl2(m):
        role = m.group(1) if m.group(1) else "sibling_name"
        obj_part = m.group(2)
        pronoun = PRONOUN.get(role, "him")
        if role == "user_name":
            return f"{{{role}}} has {obj_part} in front of {{{role}}}"
        return f"{{{role}}} has {obj_part} in front of {pronoun}"

    text = pat2.sub(repl2, text)

    return text


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        lines = f.readlines()

    transformed = [_replace_action_verbs(line.rstrip()) for line in lines]

    with open(OUTPUT, "w", encoding="utf-8") as f:
        for line in transformed:
            f.write(line + "\n")

    print(f"Transformed {len(transformed)} lines")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
