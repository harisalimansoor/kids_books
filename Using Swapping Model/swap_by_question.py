"""
Pick a template from a question cluster and swap each user photo onto the matching person.

Drive layout:

    clusters/
      mother_and_son/
        template.jpg
        roles.json

roles.json:

    {"roles_left_to_right": ["mother", "son"]}

Faces in the template are ordered from left to right. The user supplies one
photo per role, either as repeated --input role=path arguments or as files
named mother.jpg, son.jpg, user.jpg inside --input_dir.
"""

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

GHOST_ROOT = Path(__file__).resolve().parent
if str(GHOST_ROOT) not in sys.path:
    sys.path.insert(0, str(GHOST_ROOT))

import cv2
import numpy as np
from insightface.utils import face_align

from choose_template import (
    child_photo,
    choose_question,
    cluster_objects,
    find_cluster as find_question_cluster,
    load_index,
    objects_from_question,
    resolve_template,
    roles_for_cluster,
    skin_tone_from_photo,
)
from inference import build_parser, main
from insightface_func.face_detect_crop_multi import Face_detect_crop


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
FILLER = {
    "a", "an", "the", "of", "with", "photo", "picture", "image",
    "her", "his", "their", "my", "our", "me",
}


def roles_from_question(question):
    text = question.lower().replace("&", " and ")
    roles = []
    for part in re.split(r"\band\b|,|/|\+", text):
        words = [word for word in re.findall(r"[a-z0-9]+", part) if word not in FILLER]
        if words:
            roles.append("_".join(words))
    if not roles:
        raise SystemExit(f"No roles found in question: {question}")
    return roles


def load_roles_file(folder):
    path = folder / "roles.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    roles = data.get("roles_left_to_right")
    if not roles:
        raise SystemExit(f"{path} needs a roles_left_to_right list.")
    data["roles_left_to_right"] = [str(role).strip().lower().replace(" ", "_") for role in roles]
    return data


def find_cluster(clusters_root, roles):
    root = Path(clusters_root)
    if not root.is_dir():
        raise SystemExit(f"Clusters folder not found: {root}")

    wanted = set(roles)
    names = {
        "_and_".join(roles),
        "_and_".join(sorted(roles)),
        "_".join(roles),
    }
    matches = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        meta = load_roles_file(folder)
        if meta and set(meta["roles_left_to_right"]) == wanted:
            matches.append((0, folder, meta))
        elif folder.name.lower() in names:
            matches.append((1, folder, meta))

    if not matches:
        raise SystemExit(
            f"No cluster for roles {roles}. Create {root / ('_and_'.join(roles))} "
            "with a template image and roles.json."
        )
    matches.sort(key=lambda item: item[0])
    return matches[0][1], matches[0][2]


def find_template(folder, meta):
    if meta and meta.get("template"):
        path = folder / meta["template"]
        if not path.is_file():
            raise SystemExit(f"Template listed in roles.json was not found: {path}")
        return path

    role_names = set(meta["roles_left_to_right"]) if meta else set()
    images = [
        path for path in folder.iterdir()
        if path.suffix.lower() in IMAGE_EXTS and path.stem.lower() not in role_names
    ]
    preferred = [path for path in images if path.stem.lower().startswith("template")]
    chosen = sorted(preferred or images)
    if not chosen:
        raise SystemExit(f"No template image in {folder}. Add template.jpg.")
    return chosen[0]


def collect_user_photos(roles, inputs, input_dir):
    found = {}
    for item in inputs:
        if "=" not in item:
            raise SystemExit(f"--input must look like role=path, got: {item}")
        role, path = item.split("=", 1)
        role = role.strip().lower().replace(" ", "_")
        photo = Path(path.strip().strip('"'))
        if not photo.is_file():
            raise SystemExit(f"User photo not found for {role}: {photo}")
        found[role] = photo

    if input_dir:
        directory = Path(input_dir)
        if not directory.is_dir():
            raise SystemExit(f"Input folder not found: {directory}")
        for role in roles:
            if role in found:
                continue
            for ext in IMAGE_EXTS:
                candidate = directory / f"{role}{ext}"
                if candidate.is_file():
                    found[role] = candidate
                    break

    missing = [role for role in roles if role not in found]
    if missing:
        raise SystemExit(
            "Missing user photos for: " + ", ".join(missing) +
            ". Pass --input role=path for each role."
        )
    return found


def aligned_face(image, landmarks, crop_size):
    matrix, _ = face_align.estimate_norm(landmarks, crop_size, mode="None")
    return cv2.warpAffine(image, matrix, (crop_size, crop_size), borderValue=0.0)


def faces_left_to_right(image, crop_size):
    app = Face_detect_crop(name="antelope", root=str(GHOST_ROOT / "insightface_func" / "models"))
    app.prepare(ctx_id=-1, det_thresh=0.6, det_size=(640, 640))
    landmarks = app.get(image, crop_size)
    if not landmarks:
        raise SystemExit("No face found in the template.")
    landmarks = [points for points in landmarks if points is not None]
    landmarks.sort(key=lambda points: float(np.asarray(points)[:, 0].mean()))
    return landmarks


def main_question():
    parser = argparse.ArgumentParser(description="Swap user photos onto a question's template.")
    parser.add_argument("--question", default="", help='Example: "Sharing Apples with Grandfather"')
    parser.add_argument("--topic", default="", help="Child's topic, such as addition. The question is chosen inside it.")
    parser.add_argument("--clusters", default="clusters", help="Folder whose subfolders are question clusters")
    parser.add_argument("--input", action="append", default=[], help="role=path, repeat for each person")
    parser.add_argument("--input_dir", default="", help="Folder of role images such as mother.jpg and son.jpg")
    parser.add_argument("--template", default="", help="Template file name inside the cluster, if there are several")
    parser.add_argument("--templates", default="", help="Folder of shared scene templates and index.json")
    parser.add_argument("--skin", default="", choices=["", "white", "brown", "black"], help="Force a template skin tone")
    parser.add_argument("--out", default="", help="Output image path")
    parser.add_argument("--batch_size", default=1, type=int)
    args = parser.parse_args()

    templates_root = Path(args.templates) if args.templates else (GHOST_ROOT / "templates")
    index = load_index(templates_root / "index.json")
    # Tone comes from the child photo before a template is chosen. No API call.
    skin = args.skin
    if not skin:
        named = {}
        for item in args.input:
            if "=" in item:
                role, path = item.split("=", 1)
                named[role.strip().lower().replace(" ", "_")] = Path(path.strip().strip('"'))
        photo = child_photo(named)
        if photo is None and args.input_dir:
            folder_photos = collect_user_photos(["child"], [], args.input_dir)
            photo = folder_photos.get("child")
        if photo is not None:
            skin = skin_tone_from_photo(photo)
    if not args.question and not args.topic:
        raise SystemExit("Pass --question or --topic.")
    question_cluster = None
    if args.topic and not args.question:
        picked = choose_question(args.topic, index, templates_root, skin=skin)
        if picked is None:
            raise SystemExit(f"No template image is on disk for topic {args.topic}.")
        question_cluster = picked["cluster"]
        args.question = picked["question"]
        print(f"Topic {args.topic}: chose question with an available template: {args.question}")
    elif args.question:
        question_cluster = find_question_cluster(args.question, index, skin=skin, topic=args.topic)

    if question_cluster:
        order = roles_for_cluster(question_cluster)
        photos = collect_user_photos(order, args.input, args.input_dir)
        if not skin:
            skin = skin_tone_from_photo(child_photo(photos) or next(iter(photos.values())))
        template_path, used_skin = resolve_template(question_cluster, skin, templates_root)
        matched = sorted(set(objects_from_question(args.question)) & set(cluster_objects(question_cluster)))
        print(f"Cluster: {question_cluster.get('id')}")
        print(f"Skin tone from photo: {skin}")
        if used_skin != skin:
            print(f"Using another available template ({used_skin}) so the swap still runs.")
        print(f"Question objects in this template: {', '.join(matched) or '(listed question)'}")
        folder = template_path.parent
    else:
        roles = roles_from_question(args.question)
        folder, meta = find_cluster(args.clusters, roles)
        if meta:
            order = meta["roles_left_to_right"]
            if set(order) != set(roles):
                raise SystemExit(f"Cluster roles {order} do not match the question roles {roles}.")
        else:
            order = roles
            print(f"No roles.json in {folder}. Using question order from left to right: {order}")

        if args.template:
            template_path = folder / args.template
            if not template_path.is_file():
                raise SystemExit(f"Template not found: {template_path}")
        else:
            template_path = find_template(folder, meta)

        photos = collect_user_photos(order, args.input, args.input_dir)
    template = cv2.imread(str(template_path))
    if template is None:
        raise SystemExit(f"Could not read template: {template_path}")

    landmarks = faces_left_to_right(template, 224)
    if len(landmarks) != len(order):
        raise SystemExit(
            f"Template has {len(landmarks)} faces, question has {len(order)} roles ({', '.join(order)}). "
            "Use a template with the same number of people, and set roles_left_to_right to match left-to-right order."
        )

    out_path = args.out or str(GHOST_ROOT / "examples" / "results" / f"{folder.name}.png")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"Question: {args.question}")
    print(f"Template: {template_path}")
    for role, points in zip(order, landmarks):
        center_x = float(np.asarray(points)[:, 0].mean())
        print(f"  {role}: user photo {photos[role]} -> template face at x={center_x:.0f}")

    with tempfile.TemporaryDirectory() as temp_dir:
        target_faces = []
        for role, points in zip(order, landmarks):
            crop_path = Path(temp_dir) / f"{role}.png"
            cv2.imwrite(str(crop_path), aligned_face(template, points, 224))
            target_faces.append(str(crop_path))

        infer_args = build_parser().parse_args([])
        infer_args.batch_size = args.batch_size
        infer_args.source_paths = [str(photos[role]) for role in order]
        infer_args.target_faces_paths = target_faces
        infer_args.target_image = str(template_path)
        infer_args.out_image_name = out_path
        main(infer_args)


if __name__ == "__main__":
    main_question()
