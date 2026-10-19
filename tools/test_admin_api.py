import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.admin_router import list_stems, admin_grades

def run():
    grades_resp = admin_grades()
    print("Total registered grades in admin:", len(grades_resp["grades"]))
    print("-" * 75)
    for g in grades_resp["grades"]:
        gid = g["id"]
        if g.get("enabled"):
            res = list_stems(gid)
            sample_topics = ", ".join(res["topics"][:3])
            print(f"{gid:10s} | {g['display_name']:14s} | Topics: {len(res['topics']):2d} ({sample_topics}...) | Stems: {res['count']:4d}")
    print("-" * 75)

if __name__ == "__main__":
    run()
