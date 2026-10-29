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


def test_infra_cause_from_log():
    """29/10/2026 rà lá infra: nguyên nhân nằm trong log, dòng bằng chứng chỉ là triệu chứng."""
    zip_ev = "Caused by: java.util.zip.ZipException: Archive is not a ZIP archive"
    sdk = '"Install NDK (Side by side) 27.2.12479018 v.27.2.12479018" failed.\n' \
          "> com.android.builder.sdk.InstallFailedException: Failed to install the following SDK components:"
    assert subtype("infra", zip_ev, "", "", log=sdk) == "androidsdk"
    assert subtype("infra", zip_ev, "", "", log="IO Error: Error while expanding jbang.zip") is None
    # lỗi xác thực vẫn là infra dù job khác trong run cài SDK fail
    assert subtype("infra", "google-github-actions/auth failed with: the GitHub Action workflow must specify", "", "",
                   log=sdk) is None
    assert subtype("infra", "> Could not HEAD 'https://repo.maven.apache.org/maven2/a/b/maven-metadata.xml'. "
                            "Received status code 403 from server: Forbidden", "", "") == "network"
    parent = "Non-resolvable parent POM for com.example:myproject:0.0.1-SNAPSHOT: The following artifacts could not be " \
             "resolved: org.springframework.boot:spring-boot-starter-parent:pom:2.6.0 (absent): Could not tra"
    assert subtype("infra", parent, "", "", log=parent + "nsfer artifact org.springframework.boot:x") == "network"
    assert subtype("infra", parent, "", "", log=parent) is None


def test_javadoc_errors_are_doc():
    """29/10/2026 chiều: lỗi in ra giống javac nhưng do bước javadoc (dòng bằng chứng bị cắt 200 ký tự)."""
    ev = "##[error]/home/runner/work/sp/sp/a/src/main/java/org/A.java:21: error: records are not supported in -source 11"
    log = "[INFO] --- javadoc:3.12.0:jar (attach-javadocs) @ a ---\n[ERROR] MavenReportException: Error while generating Javadoc:"
    assert subtype("compile", ev, "", "", log=log) == "doc"
    assert subtype("compile", ev, "", "", log=log + "\n[ERROR] COMPILATION ERROR :") == "compile"
    assert subtype("lint", "##[error]/w/a/b/A.java:44: error: ", "", "", log="Execution failed for task ':a:javadoc'.") == "doc"
    assert subtype("lint", "[ant:checkstyle] [ERROR] /w/A.java:3: Line is longer", "", "", log="") == "quality"
