from project3.model.inputs import (DIFF_NAMES, STRUCT_NAMES, chunk_score, file_kind, focus_window, select_chunks,
                                   struct_features)
from project3.model.pack import tail_select


def test_select_prefers_fail_chunk_and_covers_jobs():
    scores = [[0.0, 7.0, 1.0], [0.5, 1.0]]
    got = select_chunks(scores, 2)
    assert got == [(0, 1), (1, 1)]  # mỗi job một đoạn tốt nhất
    assert select_chunks(scores, 4) == [(0, 1), (0, 2), (1, 0), (1, 1)]
    assert tail_select([3, 2], 3) == [(0, 1), (0, 2), (1, 1)]


def test_chunk_score_and_focus():
    log = "[INFO] --- surefire:3:test ---\n" + "ok line\n" * 300 + "[ERROR] Failed to execute goal x\n" + "tail\n" * 300
    assert chunk_score(log, False) > chunk_score("ok\n" * 50, True)
    w = focus_window(log)
    assert w.startswith("[INFO] --- surefire") and "Failed to execute goal" in w


def test_file_kind():
    assert [file_kind(p) for p in ["src/main/java/A.java", "a/src/test/java/BTest.java", "pom.xml",
                                   ".github/workflows/ci.yml", "README.md", "gradle/libs.versions.toml"]] == \
           ["main", "test", "build", "ci", "doc", "build"]


def test_struct_features_label_free():
    t = "[ERROR] Failed to execute goal org.apache.maven.plugins:maven-surefire-plugin:3.2:test (default-test) on project core"
    f = struct_features([t], ["Build with Maven"], ["maven"], 1)
    assert len(f) == len(STRUCT_NAMES) and f[STRUCT_NAMES.index("tool_test")] == 1.0
    # bản che: dòng công cụ fail bị xoá -> không còn giai đoạn công cụ
    assert struct_features([""], ["Build with Maven"], ["maven"], 1)[STRUCT_NAMES.index("tool_none")] == 1.0
    assert len(DIFF_NAMES) == 11
