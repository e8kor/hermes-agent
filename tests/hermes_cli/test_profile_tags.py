"""Contract for profile grouping tags.

Tags are free-form grouping labels persisted in ``<profile>/profile.yaml`` and
surfaced on ``ProfileInfo.tags`` (CLI ``hermes profile tag``, dashboard
``PUT /api/profiles/{name}/tags``).

``normalize_tags`` is the authority on canonical form, and it normalizes rather
than rejects: a user typing "Work Stuff" in the dashboard should get
"work-stuff", not an error dialog. It must also never raise — a hand-edited or
corrupt profile.yaml on an unrelated profile must not break
``hermes profile list``.
"""

from __future__ import annotations

import pytest

from hermes_cli.profiles import (
    add_profile_tags,
    normalize_tag,
    normalize_tags,
    read_profile_meta,
    remove_profile_tags,
    write_profile_meta,
)


class TestNormalizeTag:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Work Stuff", "work-stuff"),
            ("  CODING  ", "coding"),
            ("a//b", "a-b"),
            ("--weird--", "weird"),
            ("_x_", "x"),
            ("keep-dash_under", "keep-dash_under"),
        ],
    )
    def test_canonical_forms(self, raw, expected):
        assert normalize_tag(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", "!!!", "///"])
    def test_nothing_usable_yields_empty(self, raw):
        assert normalize_tag(raw) == ""

    def test_length_is_capped_without_a_trailing_separator(self):
        assert len(normalize_tag("x" * 50)) == 32
        # A cut landing on a separator must not leave a dangling "-".
        assert not normalize_tag("y" * 31 + " tail").endswith("-")


class TestNormalizeTags:
    def test_only_commas_split_entries(self):
        assert normalize_tags("work, coding ,research") == [
            "work",
            "coding",
            "research",
        ]
        # Whitespace inside one tag folds to "-" instead of splitting.
        assert normalize_tags(["Work Stuff"]) == ["work-stuff"]

    def test_deduplicates_preserving_first_seen_order(self):
        assert normalize_tags(["b", "a", "b"]) == ["b", "a"]
        assert normalize_tags(["Work", "work"]) == ["work"]

    def test_accepts_a_list_whose_entries_contain_commas(self):
        assert normalize_tags(["work,coding", "research"]) == [
            "work",
            "coding",
            "research",
        ]

    def test_count_is_capped(self):
        assert len(normalize_tags([f"t{i}" for i in range(30)])) == 12

    @pytest.mark.parametrize("raw", [None, 12345, {"a": 1}, object()])
    def test_junk_input_yields_empty_rather_than_raising(self, raw):
        assert normalize_tags(raw) == []

    @pytest.mark.parametrize("junk", [None, True, 42, object()])
    def test_non_string_entries_are_dropped_not_stringified(self, junk):
        """str(entry) would invent tags like "none"/"true"/"42".

        A hand-edited profile.yaml with a bare list item parses as None, which
        would otherwise persist as the literal tag "none" on the next write.
        """
        assert normalize_tags(["work", junk, "coding"]) == ["work", "coding"]


class TestProfileMetaRoundTrip:
    def test_missing_file_reads_as_empty_tags(self, tmp_path):
        assert read_profile_meta(tmp_path)["tags"] == []

    def test_tags_are_normalized_on_write(self, tmp_path):
        write_profile_meta(tmp_path, tags=["Work Stuff", "coding", "coding"])
        assert read_profile_meta(tmp_path)["tags"] == ["work-stuff", "coding"]

    def test_editing_tags_preserves_the_description(self, tmp_path):
        write_profile_meta(tmp_path, description="my profile")
        write_profile_meta(tmp_path, tags=["work"])
        meta = read_profile_meta(tmp_path)
        assert meta["description"] == "my profile"
        assert meta["tags"] == ["work"]

    def test_editing_the_description_preserves_tags(self, tmp_path):
        write_profile_meta(tmp_path, tags=["work"])
        write_profile_meta(tmp_path, description="later")
        assert read_profile_meta(tmp_path)["tags"] == ["work"]

    def test_empty_list_clears_tags(self, tmp_path):
        write_profile_meta(tmp_path, tags=["work"])
        write_profile_meta(tmp_path, tags=[])
        assert read_profile_meta(tmp_path)["tags"] == []

    def test_corrupt_yaml_reads_as_empty_instead_of_raising(self, tmp_path):
        (tmp_path / "profile.yaml").write_text("{{{ not yaml", encoding="utf-8")
        assert read_profile_meta(tmp_path)["tags"] == []

    def test_non_mapping_yaml_reads_as_empty(self, tmp_path):
        (tmp_path / "profile.yaml").write_text("- a\n- b\n", encoding="utf-8")
        assert read_profile_meta(tmp_path)["tags"] == []

    def test_scalar_tags_value_is_accepted(self, tmp_path):
        """``tags: work, coding`` is what a user hand-edits; parse it."""
        (tmp_path / "profile.yaml").write_text(
            "tags: work, coding\n", encoding="utf-8"
        )
        assert read_profile_meta(tmp_path)["tags"] == ["work", "coding"]


class TestAddRemoveTags:
    def test_add_merges_and_deduplicates(self, tmp_path):
        write_profile_meta(tmp_path, tags=["work"])
        assert add_profile_tags(tmp_path, "research, work") == [
            "work",
            "research",
        ]
        assert read_profile_meta(tmp_path)["tags"] == ["work", "research"]

    def test_add_normalizes_incoming_tags(self, tmp_path):
        assert add_profile_tags(tmp_path, ["Work Stuff"]) == ["work-stuff"]

    def test_remove_drops_only_the_named_tags(self, tmp_path):
        write_profile_meta(tmp_path, tags=["work", "coding", "research"])
        assert remove_profile_tags(tmp_path, ["coding"]) == ["work", "research"]

    def test_remove_matches_on_canonical_form(self, tmp_path):
        write_profile_meta(tmp_path, tags=["work-stuff"])
        assert remove_profile_tags(tmp_path, ["Work Stuff"]) == []

    def test_removing_an_absent_tag_is_a_no_op(self, tmp_path):
        write_profile_meta(tmp_path, tags=["work"])
        assert remove_profile_tags(tmp_path, ["nope"]) == ["work"]
