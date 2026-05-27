"""
Tests for reviewpilot/parser.py â€” Commit #3.

All fixtures are inline strings that represent realistic git diff output.
No external files or network access required.

Coverage:
  1. Simple modified file â€” one hunk, path detection, ChangeType.MODIFIED
  2. Added file          â€” /dev/null old path, ChangeType.ADDED
  3. Deleted file        â€” /dev/null new path, ChangeType.DELETED
  4. Renamed file        â€” old_path != new_path, ChangeType.RENAMED
  5. Multiple files      â€” parser correctly segments N files in one diff
  6. Additions/deletions â€” line counts are accurate per file
  7. DiffLine types      â€” ADDED / REMOVED / CONTEXT assigned correctly
  8. Hunk metadata       â€” old_start, new_start, counts parsed correctly
  9. Implicit hunk count â€” missing count defaults to 1
 10. Metadata lines ignored â€” index/mode/similarity lines do not appear as hunks
 11. Empty diff          â€” raises ValueError
 12. No parseable file   â€” raises ValueError (binary-only diff)
"""

import pytest

from reviewpilot.models import ChangeType, LineType
from reviewpilot.parser import parse_diff_text


# ---------------------------------------------------------------------------
# Fixtures â€” inline git diff strings
# ---------------------------------------------------------------------------

SIMPLE_MODIFIED = """\
diff --git a/src/app.py b/src/app.py
index abc123..def456 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@
 def greet(name):
-    return "hello"
+    return "hello, world"
+    # updated greeting
 
 def farewell():
"""

ADDED_FILE = """\
diff --git a/src/new_module.py b/src/new_module.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/src/new_module.py
@@ -0,0 +1,4 @@
+# New module.
+
+def new_function():
+    pass
"""

DELETED_FILE = """\
diff --git a/src/old_module.py b/src/old_module.py
deleted file mode 100644
index abc1234..0000000
--- a/src/old_module.py
+++ /dev/null
@@ -1,4 +0,0 @@
-# Old module.
-
-def old_function():
-    pass
"""

RENAMED_FILE = """\
diff --git a/src/utils.py b/src/helpers.py
similarity index 85%
rename from src/utils.py
rename to src/helpers.py
index aaa..bbb 100644
--- a/src/utils.py
+++ b/src/helpers.py
@@ -1,3 +1,3 @@
 def helper():
-    return "old"
+    return "new"
"""

MULTI_FILE = SIMPLE_MODIFIED + ADDED_FILE + DELETED_FILE

# A diff with no --- / +++ lines â€” parser cannot extract any DiffFile.
NO_PARSEABLE_FILE = """\
diff --git a/assets/logo.png b/assets/logo.png
index abc..def 100644
Binary files a/assets/logo.png and b/assets/logo.png differ
"""

# A diff where one binary file is followed by a real text file.
BINARY_THEN_TEXT = """\
diff --git a/assets/logo.png b/assets/logo.png
index abc..def 100644
Binary files a/assets/logo.png and b/assets/logo.png differ
diff --git a/src/app.py b/src/app.py
index abc123..def456 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
-old_value = 1
+new_value = 2
"""

# Hunk with implicit count (no comma in @@ header â€” git implies count=1).
IMPLICIT_HUNK_COUNT = """\
diff --git a/config.py b/config.py
index 111..222 100644
--- a/config.py
+++ b/config.py
@@ -5 +5 @@
-DEBUG = True
+DEBUG = False
"""


# ---------------------------------------------------------------------------
# Test 1: Simple modified file
# ---------------------------------------------------------------------------


class TestSimpleModified:
    def test_returns_one_file(self) -> None:
        files = parse_diff_text(SIMPLE_MODIFIED)
        assert len(files) == 1

    def test_change_type_is_modified(self) -> None:
        files = parse_diff_text(SIMPLE_MODIFIED)
        assert files[0].change_type is ChangeType.MODIFIED

    def test_paths(self) -> None:
        f = parse_diff_text(SIMPLE_MODIFIED)[0]
        assert f.old_path == "src/app.py"
        assert f.new_path == "src/app.py"

    def test_display_path(self) -> None:
        f = parse_diff_text(SIMPLE_MODIFIED)[0]
        assert f.display_path == "src/app.py"

    def test_one_hunk(self) -> None:
        f = parse_diff_text(SIMPLE_MODIFIED)[0]
        assert len(f.hunks) == 1


# ---------------------------------------------------------------------------
# Test 2: Added file (/dev/null old path)
# ---------------------------------------------------------------------------


class TestAddedFile:
    def test_change_type_is_added(self) -> None:
        f = parse_diff_text(ADDED_FILE)[0]
        assert f.change_type is ChangeType.ADDED

    def test_old_path_is_none(self) -> None:
        f = parse_diff_text(ADDED_FILE)[0]
        assert f.old_path is None

    def test_new_path_is_set(self) -> None:
        f = parse_diff_text(ADDED_FILE)[0]
        assert f.new_path == "src/new_module.py"

    def test_display_path_uses_new_path(self) -> None:
        f = parse_diff_text(ADDED_FILE)[0]
        assert f.display_path == "src/new_module.py"


# ---------------------------------------------------------------------------
# Test 3: Deleted file (/dev/null new path)
# ---------------------------------------------------------------------------


class TestDeletedFile:
    def test_change_type_is_deleted(self) -> None:
        f = parse_diff_text(DELETED_FILE)[0]
        assert f.change_type is ChangeType.DELETED

    def test_new_path_is_none(self) -> None:
        f = parse_diff_text(DELETED_FILE)[0]
        assert f.new_path is None

    def test_old_path_is_set(self) -> None:
        f = parse_diff_text(DELETED_FILE)[0]
        assert f.old_path == "src/old_module.py"

    def test_display_path_falls_back_to_old_path(self) -> None:
        f = parse_diff_text(DELETED_FILE)[0]
        assert f.display_path == "src/old_module.py"


# ---------------------------------------------------------------------------
# Test 4: Renamed file (old_path != new_path)
# ---------------------------------------------------------------------------


class TestRenamedFile:
    def test_change_type_is_renamed(self) -> None:
        f = parse_diff_text(RENAMED_FILE)[0]
        assert f.change_type is ChangeType.RENAMED

    def test_old_and_new_paths_differ(self) -> None:
        f = parse_diff_text(RENAMED_FILE)[0]
        assert f.old_path == "src/utils.py"
        assert f.new_path == "src/helpers.py"


# ---------------------------------------------------------------------------
# Test 5: Multiple files in one diff
# ---------------------------------------------------------------------------


class TestMultipleFiles:
    def test_returns_three_files(self) -> None:
        files = parse_diff_text(MULTI_FILE)
        assert len(files) == 3

    def test_file_paths_in_order(self) -> None:
        files = parse_diff_text(MULTI_FILE)
        assert files[0].display_path == "src/app.py"
        assert files[1].display_path == "src/new_module.py"
        assert files[2].display_path == "src/old_module.py"

    def test_change_types_in_order(self) -> None:
        files = parse_diff_text(MULTI_FILE)
        assert files[0].change_type is ChangeType.MODIFIED
        assert files[1].change_type is ChangeType.ADDED
        assert files[2].change_type is ChangeType.DELETED

    def test_binary_file_skipped_text_file_parsed(self) -> None:
        """A binary file with no hunks should be skipped; the next text file parsed."""
        files = parse_diff_text(BINARY_THEN_TEXT)
        assert len(files) == 1
        assert files[0].display_path == "src/app.py"


# ---------------------------------------------------------------------------
# Test 6: Additions and deletions counting
# ---------------------------------------------------------------------------


class TestLineCounting:
    def test_modified_file_additions(self) -> None:
        # SIMPLE_MODIFIED has 2 added lines
        f = parse_diff_text(SIMPLE_MODIFIED)[0]
        assert f.additions == 2

    def test_modified_file_deletions(self) -> None:
        # SIMPLE_MODIFIED has 1 removed line
        f = parse_diff_text(SIMPLE_MODIFIED)[0]
        assert f.deletions == 1

    def test_added_file_no_deletions(self) -> None:
        f = parse_diff_text(ADDED_FILE)[0]
        assert f.deletions == 0
        assert f.additions == 4  # 4 lines added

    def test_deleted_file_no_additions(self) -> None:
        f = parse_diff_text(DELETED_FILE)[0]
        assert f.additions == 0
        assert f.deletions == 4  # 4 lines removed

    def test_total_changes(self) -> None:
        f = parse_diff_text(SIMPLE_MODIFIED)[0]
        assert f.total_changes == 3  # 2 additions + 1 deletion


# ---------------------------------------------------------------------------
# Test 7: DiffLine types are assigned correctly
# ---------------------------------------------------------------------------


class TestDiffLineTypes:
    def _get_lines(self, diff_text: str) -> list:
        """Return all DiffLine objects from the first hunk of the first file."""
        return parse_diff_text(diff_text)[0].hunks[0].lines

    def test_added_lines_have_correct_type(self) -> None:
        lines = self._get_lines(SIMPLE_MODIFIED)
        added = [ln for ln in lines if ln.line_type is LineType.ADDED]
        assert len(added) == 2
        assert all(ln.content.startswith("+") for ln in added)

    def test_removed_lines_have_correct_type(self) -> None:
        lines = self._get_lines(SIMPLE_MODIFIED)
        removed = [ln for ln in lines if ln.line_type is LineType.REMOVED]
        assert len(removed) == 1
        assert removed[0].content.startswith("-")

    def test_context_lines_have_correct_type(self) -> None:
        lines = self._get_lines(SIMPLE_MODIFIED)
        context = [ln for ln in lines if ln.line_type is LineType.CONTEXT]
        assert len(context) == 3  # "def greet(name):", empty line, "def farewell():"
        assert all(ln.content.startswith(" ") for ln in context)

    def test_line_content_preserved_verbatim(self) -> None:
        lines = self._get_lines(SIMPLE_MODIFIED)
        removed = [ln for ln in lines if ln.line_type is LineType.REMOVED]
        assert removed[0].content == '-    return "hello"'

    def test_added_file_all_lines_are_added(self) -> None:
        lines = self._get_lines(ADDED_FILE)
        assert all(ln.line_type is LineType.ADDED for ln in lines)

    def test_deleted_file_all_lines_are_removed(self) -> None:
        lines = self._get_lines(DELETED_FILE)
        assert all(ln.line_type is LineType.REMOVED for ln in lines)


# ---------------------------------------------------------------------------
# Test 8: Hunk metadata (old_start, new_start, counts)
# ---------------------------------------------------------------------------


class TestHunkMetadata:
    def test_modified_hunk_offsets(self) -> None:
        hunk = parse_diff_text(SIMPLE_MODIFIED)[0].hunks[0]
        # @@ -1,4 +1,5 @@
        assert hunk.old_start == 1
        assert hunk.old_count == 4
        assert hunk.new_start == 1
        assert hunk.new_count == 5

    def test_added_file_hunk_old_start_is_zero(self) -> None:
        hunk = parse_diff_text(ADDED_FILE)[0].hunks[0]
        # @@ -0,0 +1,4 @@
        assert hunk.old_start == 0
        assert hunk.old_count == 0
        assert hunk.new_start == 1
        assert hunk.new_count == 4

    def test_deleted_file_hunk_new_start_is_zero(self) -> None:
        hunk = parse_diff_text(DELETED_FILE)[0].hunks[0]
        # @@ -1,4 +0,0 @@
        assert hunk.old_start == 1
        assert hunk.old_count == 4
        assert hunk.new_start == 0
        assert hunk.new_count == 0


# ---------------------------------------------------------------------------
# Test 9: Implicit hunk count defaults to 1
# ---------------------------------------------------------------------------


class TestImplicitHunkCount:
    def test_missing_count_defaults_to_one(self) -> None:
        hunk = parse_diff_text(IMPLICIT_HUNK_COUNT)[0].hunks[0]
        # @@ -5 +5 @@ â€” no count, implies 1
        assert hunk.old_start == 5
        assert hunk.old_count == 1
        assert hunk.new_start == 5
        assert hunk.new_count == 1


# ---------------------------------------------------------------------------
# Test 10: Metadata lines are ignored (do not become hunks or lines)
# ---------------------------------------------------------------------------


class TestMetadataIgnored:
    def test_index_line_not_in_hunks(self) -> None:
        f = parse_diff_text(SIMPLE_MODIFIED)[0]
        all_content = [
            ln.content for hunk in f.hunks for ln in hunk.lines
        ]
        assert not any("index" in c for c in all_content)

    def test_mode_line_not_in_hunks(self) -> None:
        f = parse_diff_text(ADDED_FILE)[0]
        all_content = [
            ln.content for hunk in f.hunks for ln in hunk.lines
        ]
        assert not any("new file mode" in c for c in all_content)

    def test_similarity_line_not_in_hunks(self) -> None:
        f = parse_diff_text(RENAMED_FILE)[0]
        all_content = [
            ln.content for hunk in f.hunks for ln in hunk.lines
        ]
        assert not any("similarity index" in c for c in all_content)


# ---------------------------------------------------------------------------
# Test 11: Empty diff raises ValueError
# ---------------------------------------------------------------------------


class TestEmptyDiff:
    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            parse_diff_text("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            parse_diff_text("   \n\n\t  ")


# ---------------------------------------------------------------------------
# Test 12: No parseable file raises ValueError
# ---------------------------------------------------------------------------


class TestNoParseable:
    def test_binary_only_diff_raises(self) -> None:
        with pytest.raises(ValueError, match="No parseable files"):
            parse_diff_text(NO_PARSEABLE_FILE)

    def test_random_text_raises(self) -> None:
        with pytest.raises(ValueError, match="No parseable files"):
            parse_diff_text("This is not a diff at all.\nJust some random text.\n")
