"""
tests/test_grade1_workflow.py
──────────────────────────────
End-to-end integration test of the Grade 1 pipeline workflow:
  1. Question bank loading & stem discovery (primary + fallback)
  2. Interest mapping (foods & hobbies)
  3. Stem filtering, role matching, and bank balancing
  4. Template text substitution (child & adult names, pronouns)
  5. MCQ options generation & fallback
  6. Prompt assembly using Grade 1 question_image.md
  7. In-memory PDF generation with Grade 1 fonts & icons
"""

import sys
from pathlib import Path
import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

try:
    from app.stem_pipeline import (
        _get_grade_roots,
        list_ready_stems,
        list_template_foods,
        list_template_hobbies,
        stems_for_available_roles,
        select_stems,
        fill_question_text,
        mcq_from_meta,
        list_topics,
        topic_label,
        food_label_to_id,
        hobby_label_to_id,
        build_workbook_items,
    )
    from app.image_generator import build_generation_prompt
    from app.pdf_generator import generate_pdf
    from app.front_cover_generator import build_front_cover_prompt, FrontCoverError
except ImportError:
    from stem_pipeline import (  # type: ignore
        _get_grade_roots,
        list_ready_stems,
        list_template_foods,
        list_template_hobbies,
        stems_for_available_roles,
        select_stems,
        fill_question_text,
        mcq_from_meta,
        list_topics,
        topic_label,
        food_label_to_id,
        hobby_label_to_id,
        build_workbook_items,
    )
    from image_generator import build_generation_prompt  # type: ignore
    from pdf_generator import generate_pdf  # type: ignore
    from front_cover_generator import build_front_cover_prompt, FrontCoverError  # type: ignore


class TestGrade1StemPipeline:
    """Test Grade 1 stem scanning, role filtering, and selection."""

    def test_grade_roots_exist(self):
        roots = _get_grade_roots("Grade_1")
        assert len(roots) >= 1
        for r in roots:
            assert r.is_dir()
            assert r.exists()

    def test_list_topics_grade_1(self):
        topics = list_topics("Grade_1")
        assert len(topics) > 0
        assert "addition" in topics
        assert "subtraction" in topics
        # Check topic labels
        assert topic_label("addition") == "Addition"

    def test_list_ready_stems_grade_1(self):
        stems = list_ready_stems("Grade_1", require_verified=False)
        assert len(stems) > 0
        sample = stems[0]
        assert "stem_id" in sample
        assert "topic" in sample
        assert "question_template" in sample
        assert "image_path" in sample
        assert "bank" in sample
        assert sample["bank"] == "curriculum"
        assert sample["question_template"]
        assert "curriculum" in str(sample["stem_dir"]).replace("\\", "/")

    def test_list_template_foods_and_hobbies(self):
        foods = list_template_foods("Grade_1", require_verified=False)
        assert isinstance(foods, list)
        assert len(foods) > 0

        hobbies = list_template_hobbies("Grade_1", require_verified=False)
        assert isinstance(hobbies, list)
        assert len(hobbies) > 0

    def test_stems_for_available_roles(self):
        all_stems = list_ready_stems("Grade_1", require_verified=False)
        # Filter for user (child) + mother (Mum)
        filtered = stems_for_available_roles(all_stems, {"mother"})
        assert len(filtered) > 0
        for s in filtered:
            role = s.get("template_adult_role") or ""
            # Either role is mother, or child-only template
            assert role in ("mother", "") or "mother" in s.get("allowed_adult_roles", [])

    def test_sibling_photo_flag_keeps_or_drops_sibling_stems(self):
        sibling_scene = {
            "template_adult_role": "",
            "region_roles": {"child", "sibling"},
            "allowed_adult_roles": [],
            "meta": {},
        }
        with_photo = stems_for_available_roles(
            [sibling_scene],
            set(),
            has_child_photo=True,
            has_sibling_photo=True,
        )
        without_photo = stems_for_available_roles(
            [sibling_scene],
            set(),
            has_child_photo=True,
            has_sibling_photo=False,
        )
        assert with_photo == [sibling_scene]
        assert without_photo == []

    def test_list_ready_stems_requires_grade_id(self):
        with pytest.raises(TypeError):
            list_ready_stems(topics=["addition"])

    def test_select_stems_and_bank_balance(self):
        all_stems = list_ready_stems("Grade_1", require_verified=False)
        eligible = stems_for_available_roles(all_stems, {"mother", "father"})
        chosen = select_stems(
            eligible,
            n=4,
            bank_balance=True,
        )
        assert len(chosen) == 4
        # Verify unique stem_ids
        stem_ids = [s["stem_id"] for s in chosen]
        assert len(stem_ids) == len(set(stem_ids))


class TestGrade1TextAndMCQ:
    """Test text substitution and MCQ creation."""

    def test_fill_question_text(self):
        template = "{user_name} has 3 apples. {adult_name} gives {user_name} 2 more. How many apples does {user_name} have altogether?"
        filled = fill_question_text(
            template,
            user_name="Leo",
            adult_role="mother",
            family_names={"mother": "Sarah"},
            child_gender="boy",
        )
        assert "Leo" in filled
        assert "Sarah" in filled

    def test_mcq_from_meta(self):
        meta = {
            "answer": {
                "correct": "5",
                "options": ["3", "4", "5", "6"],
            }
        }
        res = mcq_from_meta(meta, "How many apples?")
        assert res["correct_answer"] == "5"
        assert len(res["options"]) == 3
        assert "5" in res["options"]

    def test_question_reader_builds_one_correct_and_two_wrong(self):
        from app.mcq_options import build_mcq, local_heading
        question = (
            "Grandfather William has 12 wooden blocks. "
            "Oliver uses 4 blocks. How many blocks remain?"
        )
        res = build_mcq(question, allow_network=False)
        assert res["correct_answer"] == "8"
        assert res["options"] == ["6", "8", "10"]
        heading = local_heading(question)
        assert heading["title"] == "Grandad Building with Blocks"
        assert heading["sticker"] == "building"
        mango = local_heading("Gran has 7 mangoes. How many mangoes are there altogether?")
        assert mango["title"] == "Gran Counting with Mangoes"
        assert mango["sticker"] == "food"
        coins = local_heading("Mum has 8 coins. How many coins are left?", adult="Mum")
        assert coins["title"] == "Mum Counting with Coins"
        apples = local_heading(
            "Hamdan has 8 apples. David takes away 3 apples. How many apples does Hamdan have left?",
            child="Hamdan",
        )
        assert apples["title"] == "Hamdan Counting with Apples"
        assert coins["sticker"] == "shopping"
        assert coins["title"] != heading["title"]


class TestGrade1PromptAndPDF:
    """Test prompt building and PDF compilation."""

    def test_build_generation_prompt_grade_1(self):
        prompt = build_generation_prompt(
            "Leo has 5 red apples and Dad has 3 green apples.",
            character_context="Leo is a 6-year-old boy. Dad is an adult male.",
            grade_id="Grade_1",
        )
        assert "Leo has 5 red apples" in prompt
        assert "Leo is a 6-year-old boy" in prompt

    def test_generate_pdf_grade_1(self):
        questions = [
            "1. Leo has 4 balloons and Mum gives him 2 more. How many balloons in total?",
            "2. Dad counts 6 cars in the car park. 3 drive away. How many cars are left?",
        ]
        pdf_bytes = generate_pdf(
            student_name="Leo",
            grade="Grade 1",
            topic_header_text="Addition, Subtraction",
            questions=questions,
            question_topics=["Addition", "Subtraction"],
            favourite_colour="Blue",
            workbook_title="Leo's Maths Practice Book",
            workbook_subtitle="Personalised Grade 1 practice",
            question_adults=["Mum", "Dad"],
            question_options=[
                {"options": ["4", "5", "6", "7"], "correct_answer": "6"},
                {"options": ["1", "2", "3", "4"], "correct_answer": "3"},
            ],
            grade_id="Grade_1",
        )
        assert isinstance(pdf_bytes, (bytes, bytearray))
        assert len(pdf_bytes) > 1000
        assert pdf_bytes[:5] == b"%PDF-"
        import re
        pages = len(re.findall(rb'/Type\s*/Page\b', pdf_bytes))
        # 2 question pages + 1 backcover page = 3 pages
        assert pages == 3

    def test_generate_pdf_grade_1_backcover_disabled(self):
        questions = [
            "1. Leo has 4 balloons and Mum gives him 2 more. How many balloons in total?",
            "2. Dad counts 6 cars in the car park. 3 drive away. How many cars are left?",
        ]
        pdf_bytes = generate_pdf(
            student_name="Leo",
            grade="Grade 1",
            topic_header_text="Addition, Subtraction",
            questions=questions,
            question_topics=["Addition", "Subtraction"],
            favourite_colour="Blue",
            workbook_title="Leo's Maths Practice Book",
            workbook_subtitle="Personalised Grade 1 practice",
            question_adults=["Mum", "Dad"],
            question_options=[
                {"options": ["4", "5", "6", "7"], "correct_answer": "6"},
                {"options": ["1", "2", "3", "4"], "correct_answer": "3"},
            ],
            grade_id="Grade_1",
            backcover_image_path=False,
        )
        import re
        pages = len(re.findall(rb'/Type\s*/Page\b', pdf_bytes))
        # 2 question pages only (no backcover)
        assert pages == 2

    def test_generate_pdf_with_pets(self):
        questions = [
            "1. Leo has 4 balloons and Mum gives him 2 more. How many balloons in total?",
            "2. Dad counts 6 cars in the car park. 3 drive away. How many cars are left?",
        ]
        pets = [
            {"id": "pet_1", "name": "Buddy", "type": "Dog"},
            {"id": "pet_2", "name": "Milo", "type": "Cat"},
        ]
        pdf_bytes = generate_pdf(
            student_name="Leo",
            grade="Grade 1",
            topic_header_text="Addition, Subtraction",
            questions=questions,
            question_topics=["Addition", "Subtraction"],
            favourite_colour="Purple",
            workbook_title="Leo's Maths Practice Book",
            workbook_subtitle="Personalised Grade 1 practice",
            question_adults=["Mum", "Dad"],
            question_options=[
                {"options": ["4", "5", "6", "7"], "correct_answer": "6"},
                {"options": ["1", "2", "3", "4"], "correct_answer": "3"},
            ],
            grade_id="Grade_1",
            pets=pets,
        )
        assert isinstance(pdf_bytes, (bytes, bytearray))
        assert len(pdf_bytes) > 1000
        assert pdf_bytes[:5] == b"%PDF-"
        import re
        pages = len(re.findall(rb'/Type\s*/Page\b', pdf_bytes))
        # 2 question pages + 1 backcover page = 3 pages
        assert pages == 3


    def test_food_and_hobby_normalization_no_ghost_imports(self):
        # Must normalize cleanly without attempting to import deleted interactive_templates
        assert food_label_to_id("Apples") == "apples"
        assert food_label_to_id("Cupcakes") == "cupcakes"
        assert hobby_label_to_id("Baking") == "baking"
        assert hobby_label_to_id("Football") == "football"

    def test_build_generation_prompt_missing_grade_strict_error(self):
        # Must raise error when unconfigured grade requested — NO silent Grade 1 fallback!
        with pytest.raises(Exception):
            build_generation_prompt("Question text", grade_id="Grade_10")


    def test_build_workbook_items_requires_grade_id(self):
        import inspect
        sig = inspect.signature(build_workbook_items)
        assert "grade_id" in sig.parameters
        assert sig.parameters["grade_id"].default != "Grade_1"

    def test_front_cover_prompt_uses_selected_grade_file(self):
        prompt = build_front_cover_prompt(
            grade_id="Grade_1",
            child_name="Leo",
            subject="MATH",
            selected_topics=["Addition"],
            grade_label="Grade 1",
            face_paths={"user": "child.png", "brother": "brother.png"},
        )
        assert "MYINTELIBOOKS" in prompt
        assert "KID_NAME: Leo" in prompt
        assert "GRADE: Grade 1" in prompt
        assert "PAGE SIZE LOCK" not in prompt
        assert "GRADE LOCK" not in prompt
        assert "- Addition" in prompt
        assert "Phonics" not in prompt
        assert len(prompt) <= 3800

    def test_mixed_or_all_topics_cover_shows_four_random_pills(self):
        import random
        catalog = [
            "Addition", "Subtraction", "Money", "Time",
            "Fractions", "Geometry", "Measurement", "General Math",
        ]
        random.seed(3)
        mixed_prompt = build_front_cover_prompt(
            grade_id="Grade_1",
            child_name="Kelly",
            selected_topics=["Mixed"],
            all_available_topics=catalog,
            grade_label="Grade 1",
        )
        mixed_block = mixed_prompt.split("SELECTED_TOPICS:\n", 1)[1].split("ALL_AVAILABLE_TOPICS:", 1)[0]
        mixed_pills = [line[2:] for line in mixed_block.splitlines() if line.startswith("- ")]
        assert len(mixed_pills) == 4
        assert len(set(mixed_pills)) == 4
        assert "mixed" not in {pill.lower() for pill in mixed_pills}
        assert "KID_NAME: Kelly" in mixed_prompt

        random.seed(3)
        all_prompt = build_front_cover_prompt(
            grade_id="Grade_1",
            child_name="Kelly",
            selected_topics=list(catalog),
            all_available_topics=catalog,
            grade_label="Grade 1",
        )
        all_block = all_prompt.split("SELECTED_TOPICS:\n", 1)[1].split("ALL_AVAILABLE_TOPICS:", 1)[0]
        all_pills = [line[2:] for line in all_block.splitlines() if line.startswith("- ")]
        assert len(all_pills) == 4

    def test_front_cover_prompt_refuses_grade_without_content(self):
        with pytest.raises(Exception):
            build_front_cover_prompt(
                grade_id="Grade_10",
                child_name="Leo",
                selected_topics=["Addition"],
                grade_label="Grade 10",
            )


    def test_unavailable_grade_stems_are_not_grade_1(self):
        grade_1 = list_ready_stems("Grade_1", topics=["addition"], require_verified=False)
        other = list_ready_stems("Grade_2", topics=["addition"], require_verified=False)
        assert grade_1
        assert other == []
        grade_1_ids = {s["stem_id"] for s in grade_1}
        assert grade_1_ids.isdisjoint({s["stem_id"] for s in other})

    def test_selected_stem_keeps_the_bank_count(self):
        from app.stem_pipeline import preserve_bank_counts

        stems = list_ready_stems("Grade_1", require_verified=False)
        books = next(s for s in stems if s["stem_id"] == "add_books_5_5_user_grandfather")
        plan = books["count_plan"]
        assert plan["total"] == 10
        assert plan["correct"] == "10"
        assert plan["formula"] == "5+5"
        assert plan["use_board"] is False
        assert len(plan["people"]) == 2

        changed = preserve_bank_counts(
            books["meta"],
            {
                "visual_groups": [
                    {"owner": "table", "plural": "pizzas", "count": 99},
                    {"owner": "table", "plural": "pizzas", "count": 1},
                ],
                "answer": {"correct": "99", "formula": "99+1"},
            },
        )
        assert changed["visual_groups"][0]["count"] == 5
        assert changed["visual_groups"][0]["owner"] == "child"
        assert changed["visual_groups"][1]["count"] == 5
        assert changed["answer"]["correct"] == "10"
        assert changed["answer"]["formula"] == "5+5"
        assert changed["visual_groups"][0]["plural"] == "pizzas"


class TestCoverGradeLabel:
    def test_numbered_years_keep_the_word_grade(self):
        from app.front_cover_generator import cover_grade_label, to_a4_image
        from PIL import Image

        assert cover_grade_label("Grade 1", "Grade_1") == "Grade 1"
        assert cover_grade_label("", "Grade_3") == "Grade 3"
        assert cover_grade_label("G2") == "Grade 2"
        assert cover_grade_label("Year 4") == "Grade 4"

        page = to_a4_image(Image.new("RGB", (1024, 1536), (255, 255, 255)))
        assert abs((page.size[0] / page.size[1]) - (210 / 297)) < 0.004

    def test_early_years_do_not_get_the_word_grade(self):
        from app.front_cover_generator import cover_grade_label

        assert cover_grade_label("PG") == "Playgroup"
        assert cover_grade_label("Grade PG") == "Playgroup"
        assert cover_grade_label("Nursery") == "Nursery"
        assert cover_grade_label("Prep") == "Prep"
        assert cover_grade_label("KG") == "Kindergarten"
        assert cover_grade_label("Kindergarten") == "Kindergarten"
        for label in ("Playgroup", "Nursery", "Prep", "Kindergarten"):
            assert not label.lower().startswith("grade")


class TestQuestionImageBox:
    def test_scene_is_cropped_to_the_brown_board_window(self):
        from PIL import Image
        from app.workbook_layout import (
            IMAGE_H,
            IMAGE_PX_H,
            IMAGE_PX_W,
            IMAGE_W,
            IMAGE_X,
            IMAGE_Y,
            STAGE_H,
            STAGE_W,
            STAGE_X,
            STAGE_Y,
            to_question_image,
        )

        assert IMAGE_X >= STAGE_X
        assert IMAGE_Y >= STAGE_Y
        assert IMAGE_X + IMAGE_W <= STAGE_X + STAGE_W
        assert IMAGE_Y + IMAGE_H <= STAGE_Y + STAGE_H

        wide = to_question_image(Image.new("RGB", (2000, 800), (10, 20, 30)))
        square = to_question_image(Image.new("RGB", (1024, 1024), (10, 20, 30)))
        assert wide.size == (IMAGE_PX_W, IMAGE_PX_H)
        assert square.size == (IMAGE_PX_W, IMAGE_PX_H)
        assert abs((wide.size[0] / wide.size[1]) - (IMAGE_W / IMAGE_H)) < 0.004


class TestMathCountPlan:
    def test_two_people_keep_their_own_share(self):
        from app.math_visual_engine import count_prompt_for_image, object_count_plan

        meta = {
            "visual_groups": [
                {"owner": "child", "plural": "books", "count": 5},
                {"owner": "grandfather", "plural": "books", "count": 5},
            ]
        }
        plan = object_count_plan("How many books altogether?", meta)
        text = count_prompt_for_image("How many books altogether?", meta)
        assert plan["total"] == 10
        assert plan["use_board"] is False
        assert "exactly 10 books" in text
        assert "The child has exactly 5 books." in text
        assert "The grandfather has exactly 5 books." in text

    def test_more_than_ten_uses_the_front_board(self):
        from app.math_visual_engine import prepare_question_board, render_math_visualization

        meta = {
            "visual_groups": [
                {"owner": "child", "plural": "blocks", "singular": "block", "count": 12, "crossed_count": 4}
            ]
        }
        board = prepare_question_board("Oliver has 12 blocks and crosses out 4.", meta, grade_id="Grade_1")
        assert board is not None
        assert board.numbers.start == 12
        assert board.visualization.cross_out == 4
        assert board.visualization.show_equation is False
        card = render_math_visualization(board, card_w=420, card_h=220)
        assert card.size == (420, 220)

