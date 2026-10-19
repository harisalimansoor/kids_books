from pathlib import Path
import json

root = Path("grades")
for g in ["Grade_1", "Grade_2", "Grade_3", "Grade_4", "Grade_5"]:
    print(f"================== {g} ==================")
    for bank in ["primary", "fallback"]:
        b_dir = root / g / "questions" / bank
        if not b_dir.exists():
            continue
        topics = sorted([d.name for d in b_dir.iterdir() if d.is_dir()])
        print(f"Bank: {bank}, Topics: {topics}")
        for t in topics:
            stems = sorted(list((b_dir / t).iterdir()))
            print(f"  Topic {t}: {len(stems)} stems")
            # Let's inspect unique questions
            questions = set()
            for s in stems:
                qf = s / "question.txt"
                if qf.exists():
                    questions.add(qf.read_text(encoding="utf-8").strip())
            print(f"    Unique question texts: {len(questions)} / {len(stems)}")
            # print first 2 question texts
            sample_stems = stems[:2]
            for s in sample_stems:
                qf = s / "question.txt"
                if qf.exists():
                    qtxt = qf.read_text(encoding="utf-8").strip().replace("\n", " ")
                    print(f"      [{s.name}]: {qtxt[:100]}...")
