"""
tests/test_grade_config.py
──────────────────────────
Unit tests for the centralized grade configuration and path resolution system.
Validates:
  1. Grade registry & metadata lookups
  2. Grade config loading & strict non-fallback error handling
  3. Feature flags and topics
  4. Question bank path resolution
  5. Prompt path resolution & strict error on missing prompts
  6. Shared asset (fonts, icons) resolution
  7. Runtime job isolation and metadata management
"""

import os
import sys
from pathlib import Path
import pytest

# Ensure app/ is on sys.path
APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

try:
    from app.grade_config import (
        list_grades,
        get_grade_entry,
        get_grade_config,
        get_grade_features,
        get_grade_topics,
        get_grade_dir,
        get_questions_roots,
        get_prompt_path,
        get_fonts_dir,
        get_icons_dir,
        get_assets_dir,
        generate_job_id,
        get_job_dir,
        get_runtime_dir,
        write_job_metadata,
        read_job_metadata,
        is_grade_available,
        grade_select_options,
        get_backcover_image_path,
        GradeNotFoundError,
        GradeConfigError,
        PromptNotFoundError,
    )
except ImportError:
    from grade_config import (  # type: ignore
        list_grades,
        get_grade_entry,
        get_grade_config,
        get_grade_features,
        get_grade_topics,
        get_grade_dir,
        get_questions_roots,
        get_prompt_path,
        get_fonts_dir,
        get_icons_dir,
        get_assets_dir,
        generate_job_id,
        get_job_dir,
        get_runtime_dir,
        write_job_metadata,
        read_job_metadata,
        is_grade_available,
        grade_select_options,
        get_backcover_image_path,
        GradeNotFoundError,
        GradeConfigError,
        PromptNotFoundError,
    )


class TestGradeRegistry:
    """Test registry functions from config/grades.json."""

    def test_list_grades_enabled_only(self):
        enabled = list_grades(enabled_only=True)
        assert isinstance(enabled, list)
        assert len(enabled) >= 1
        grade_ids = [g["id"] for g in enabled]
        assert "Grade_1" in grade_ids
        for g in enabled:
            assert g.get("enabled") is True

    def test_list_grades_all(self):
        all_grades = list_grades(enabled_only=False)
        grade_ids = [g["id"] for g in all_grades]
        expected = [
            "PG", "Nursery", "Prep", "KG",
            "Grade_1", "Grade_2", "Grade_3", "Grade_4", "Grade_5",
            "Grade_6", "Grade_7", "Grade_8", "Grade_9", "Grade_10",
        ]
        assert grade_ids == expected

    def test_year_group_menu_lists_every_grade(self):
        options = grade_select_options()
        assert len(options) == 14
        labels = [opt["label"] for opt in options]
        assert any("Grade 1" in l for l in labels)
        unavailable = [opt for opt in options if not opt["available"]]
        assert len(unavailable) == 5  # Grade 6, 7, 8, 9, 10
        for opt in unavailable:
            assert "content not available yet" in opt["label"]
        ready = [opt for opt in options if opt["available"]]
        assert len(ready) == 9  # PG, KG, Nursery, Prep, Grade 1-5

    def test_configured_grades_are_available(self):
        for grade_id in ("PG", "KG", "Nursery", "Prep", "Grade_1", "Grade_2", "Grade_3", "Grade_4", "Grade_5"):
            assert is_grade_available(grade_id) is True
        for grade_id in ("Grade_6", "Grade_7", "Grade_8", "Grade_9", "Grade_10"):
            assert is_grade_available(grade_id) is False

    def test_unavailable_grades_do_not_resolve_grade_1_questions(self):
        grade_1_roots = {p.resolve() for p in get_questions_roots("Grade_1")}
        assert grade_1_roots
        for grade_id in ("Grade_6", "Grade_10"):
            roots = get_questions_roots(grade_id)
            resolved = {p.resolve() for p in roots}
            assert grade_1_roots.isdisjoint(resolved)
            for root in resolved:
                assert "Grade_1" not in root.parts

    def test_get_grade_entry_valid(self):
        entry = get_grade_entry("Grade_1")
        assert entry["id"] == "Grade_1"
        assert entry["display_name"] == "Grade 1"
        assert entry["enabled"] is True

    def test_get_grade_entry_invalid_raises(self):
        with pytest.raises(GradeNotFoundError) as exc_info:
            get_grade_entry("Grade_99_NonExistent")
        assert "Grade_99_NonExistent" in str(exc_info.value)


class TestGradeConfigResolution:
    """Test loading grade-level config.json and strict error handling."""

    def test_get_grade_config_grade_1(self):
        cfg = get_grade_config("Grade_1")
        assert cfg["grade_id"] == "Grade_1"
        assert "question_banks" in cfg
        assert "available_topics" in cfg
        assert "features" in cfg

    def test_get_grade_config_pg(self):
        cfg = get_grade_config("PG")
        assert cfg["grade_id"] == "PG"
        assert cfg["features"]["ai_question_images"] is True
        assert len(cfg["available_topics"]) > 0

    def test_get_grade_config_nonexistent_raises(self):
        """CRITICAL: Must raise GradeNotFoundError; NO silent fallback to Grade_1!"""
        with pytest.raises(GradeNotFoundError):
            get_grade_config("NonExistent_Grade")

    def test_get_grade_features(self):
        features = get_grade_features("Grade_1")
        assert features.get("ai_question_images") is True
        assert features.get("front_cover") is True
        assert features.get("last_page") is False

    def test_get_grade_topics(self):
        topics = get_grade_topics("Grade_1")
        assert isinstance(topics, list)
        assert "addition" in topics
        assert "subtraction" in topics
        assert "multiplication" in topics
        assert "division" in topics
        assert "fractions" in topics

        pg_topics = get_grade_topics("PG")
        assert len(pg_topics) > 0
        assert "counting_1_to_3" in pg_topics



class TestPathResolution:
    """Test paths for questions, prompts, fonts, icons, assets."""

    def test_get_grade_dir(self):
        gdir = get_grade_dir("Grade_1")
        assert gdir.is_dir()
        assert gdir.name == "Grade_1"

    def test_get_questions_roots_grade_1(self):
        roots = get_questions_roots("Grade_1")
        assert len(roots) >= 1
        for r in roots:
            assert r.is_dir()
            assert ("questions" in r.parts)

    def test_get_questions_roots_nonexistent_raises(self):
        with pytest.raises(GradeNotFoundError):
            get_questions_roots("NonExistent_Grade")

    def test_get_prompt_path_grade_1(self):
        qi_prompt = get_prompt_path("Grade_1", "question_image")
        assert qi_prompt.is_file()
        assert qi_prompt.name == "question_image.md"

        fc_prompt = get_prompt_path("Grade_1", "front_page")
        assert fc_prompt.is_file()
        assert fc_prompt.name == "front_page.md"

    def test_get_prompt_path_missing_raises(self):
        """CRITICAL: Must raise PromptNotFoundError when prompt is missing; NO silent fallback."""
        with pytest.raises(PromptNotFoundError):
            get_prompt_path("Grade_1", "completely_unknown_prompt_xyz")

        with pytest.raises(PromptNotFoundError):
            get_prompt_path("Grade_10", "question_image")


    def test_get_fonts_dir(self):
        fdir = get_fonts_dir("Grade_1")
        assert fdir.is_dir()
        ttf_files = list(fdir.glob("*.ttf"))
        assert len(ttf_files) > 0

    def test_get_icons_dir(self):
        idir = get_icons_dir("Grade_1")
        assert idir.is_dir()
        png_files = list(idir.glob("*.png"))
        assert len(png_files) > 0

    def test_get_assets_dir(self):
        ref_dir = get_assets_dir("Grade_1", "reference")
        assert ref_dir.is_dir()


class TestRuntimeJobIsolation:
    """Test per-job runtime isolation and metadata persistence."""

    def test_generate_job_id_format(self):
        job_id = generate_job_id()
        assert job_id.startswith("WB_")
        # Should be WB_ followed by digits
        suffix = job_id.split("_")[1]
        assert suffix.isdigit()
        assert len(suffix) == 6

    def test_job_dir_structure(self):
        test_job_id = "WB_999991"
        jdir = get_job_dir(test_job_id)
        assert jdir.is_dir()

        # Check standard subdirectories
        for sub in ("uploads", "generated_images", "front_cover", "last_page", "generated_pdfs"):
            subdir = get_runtime_dir(test_job_id, sub)
            assert subdir.is_dir()
            assert subdir.parent == jdir

    def test_job_metadata_write_and_read(self):
        test_job_id = "WB_999992"
        meta_data = {
            "student_name": "Test Child",
            "grade_id": "Grade_1",
            "test_flag": True,
        }
        write_job_metadata(test_job_id, meta_data)
        read_back = read_job_metadata(test_job_id)
        assert read_back["student_name"] == "Test Child"
        assert read_back["grade_id"] == "Grade_1"
        assert read_back["test_flag"] is True

        # Test metadata update/merge
        write_job_metadata(test_job_id, {"status": "completed"})
        updated = read_job_metadata(test_job_id)
        assert updated["student_name"] == "Test Child"
        assert updated["status"] == "completed"

    def test_invalid_runtime_subdir_raises(self):
        with pytest.raises(ValueError):
            get_runtime_dir("WB_999993", "illegal_subdir_name")


class TestBackcoverResolution:
    """Test discovery and handling of the backcover image."""

    def test_get_backcover_image_path_finds_image(self):
        bc = get_backcover_image_path()
        assert bc is not None
        assert bc.is_file()
        assert bc.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp")

    def test_backcover_image_is_valid_image(self):
        from PIL import Image
        bc = get_backcover_image_path()
        assert bc is not None
        with Image.open(bc) as img:
            assert img.size[0] > 0
            assert img.size[1] > 0

