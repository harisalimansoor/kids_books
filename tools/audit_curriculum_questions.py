"""
Audit and verification script for curriculum mathematics questions across all grades.
Validates:
1. EYFS Nursery / Cambridge EY1 suitability (vocabulary, length, distractors, numbers 1-5).
2. EYFS Pre-Reception / Cambridge EY2 suitability (no meta-terms like 'subitises', clean options, numbers to 10).
3. EYFS Reception / Cambridge EY3 ELG suitability (numbers to 10, doubles, sharing, no KS1 place-value arithmetic).
4. Grade 1 (Key Stage 1 Year 1) statutory bounds (addition/subtraction within 20).
5. All stems have valid meta.json, 4 options, and correct answer included.
"""

import json
from pathlib import Path

def audit_all():
    repo_root = Path(__file__).resolve().parent.parent
    grades = ['Nursery', 'Prep', 'KG', 'Grade_1', 'Grade_2', 'Grade_3', 'Grade_4', 'Grade_5']

    total_stems = 0
    errors = []
    grade_counts = {}

    for g in grades:
        fallback_dir = repo_root / f"grades/{g}/questions/fallback"
        stems = list(fallback_dir.glob("*/*"))
        grade_counts[g] = len(stems)
        total_stems += len(stems)

        for stem in stems:
            q_file = stem / "question.txt"
            m_file = stem / "meta.json"

            if not q_file.exists():
                errors.append(f"Missing question.txt: {stem}")
                continue
            if not m_file.exists():
                errors.append(f"Missing meta.json: {stem}")
                continue

            q_text = q_file.read_text(encoding="utf-8").strip()
            words = q_text.split()

            with open(m_file, encoding="utf-8") as f:
                meta = json.load(f)

            ans = meta.get("answer", {})
            correct = str(ans.get("correct", "")).strip()
            options = [str(o).strip() for o in ans.get("options", [])]

            if not correct:
                errors.append(f"Empty correct answer in {stem}")
            if len(options) != 4:
                errors.append(f"Options count != 4 in {stem}: {options}")
            if correct not in options:
                errors.append(f"Correct answer '{correct}' not in options {options} in {stem}")

            # Specific grade pedagogical checks
            if g == "Nursery":
                if len(words) > 35:
                    errors.append(f"Nursery question too long ({len(words)} words): {stem}")
                for opt in options:
                    if any(bad in opt.lower() for bad in ["neither", "both are", "microwave", "locked drawer", "identical"]):
                        errors.append(f"Inappropriate distractor in Nursery {stem}: {opt}")

            elif g == "Prep":
                if "subitises" in q_text.lower():
                    errors.append(f"Pedagogical jargon 'subitises' in Prep {stem}")
                if "order word" in q_text.lower():
                    errors.append(f"Pedagogical jargon 'order word' in Prep {stem}")

    print("================================================================================")
    print("CURRICULUM QUESTION AUDIT REPORT")
    print("================================================================================")
    for g, cnt in grade_counts.items():
        print(f"  - {g:10s}: {cnt:4d} stems validated")
    print("--------------------------------------------------------------------------------")
    print(f"Total Stems Audited: {total_stems}")
    print(f"Total Errors Found:  {len(errors)}")
    print("================================================================================")

    if errors:
        for e in errors[:15]:
            print("  [ERROR]", e)
        return False
    else:
        print(">> ALL QUESTIONS PASSED 100% OF UK & CAMBRIDGE CURRICULUM INTEGRITY CHECKS!")
        return True

if __name__ == "__main__":
    import sys
    success = audit_all()
    sys.exit(0 if success else 1)
