"""Quy tắc lá sửa ngày 26/10/2026 theo kiểm chứng 161 run (pipeline.leaf_review), mỗi test ứng với một mục người duyệt."""
import re

from project3.crawl import gold_labels
from project3.crawl.fine_labels import subtype


def test_flaky_only_without_real_failures():
    rx = re.search(r'\("flaky", r"(.+?)"\)', open(gold_labels.__file__, encoding="utf-8").read()).group(1)
    assert not re.search(rx, "[ERROR] Tests run: 3658, Failures: 4, Errors: 0, Skipped: 29, Flakes: 1")
    assert re.search(rx, "[WARNING] Tests run: 3658, Failures: 0, Errors: 0, Skipped: 29, Flakes: 2")


def test_maven_lock_is_infra_not_git():
    assert subtype("infra", "[ERROR] Could not acquire shared lock for artifacts: a:b:jar:1", "", "") is None


def test_test_vs_itest_prefers_failing_tool():
    assert subtype("test", "Tests run: 30, Failures: 4", "Integration Tests", "", test_stage="test") == "testfailure"
    assert subtype("test", "Tests run: 30, Failures: 4", "CI", "", test_stage="itest") == "itestfailure"
    assert subtype("test", "Execution failed for task ':app:connectedDebugAndroidTest'", "CI", "") == "itestfailure"


def test_network_vs_infra_vs_crash_vs_androidsdk():
    assert subtype("infra", "java.net.ConnectException: Connection refused to jdbc:hive2://localhost:32786", "", "") is None
    assert subtype("infra", "after connection broken by 'ReadTimeoutError(\"HTTPSConnectionPool\")'", "", "") == "network"
    assert subtype("infra", "##[warning]Failed to download action 'https://codeload.github.com/ReactiveCircus/"
                            "android-emulator-runner/tar.gz/a4'", "", "") == "network"
    assert subtype("infra", "error: could not connect to TCP port 5554: Connection refused", "", "") == "androidsdk"
    assert subtype("infra", "> Remote host terminated the handshake", "", "") == "network"
    assert subtype("infra", "Primary download failed, trying archive mirror", "", "") == "network"


def test_cross_branch_leaves():
    assert subtype("compile", "com.google.googlejavaformat.java.FormatterException: 144:2: error", "", "") == "quality"
    assert subtype("compile", "e: Module was compiled with an incompatible version of Kotlin.", "", "") == "dependency"
    log = "[ERROR] Non-resolvable import POM: org.openrewrite:rewrite-bom:pom:8.91.0 absent"
    assert subtype("buildconfig", "'dependencies.dependency.version' for x:y:jar is missing.", "", "", log) == "dependency"
    assert subtype("buildconfig", "'dependencies.dependency.version' for x:y:jar is missing.", "", "") == "buildconfig"
