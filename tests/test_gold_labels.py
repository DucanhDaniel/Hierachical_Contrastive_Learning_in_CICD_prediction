"""Kiểm tra các ranh giới dễ gán nhầm từ log thật và mẫu compiler JVM."""
import unittest

from project3.crawl.gold_labels import NON_BUILD_WF, base_gold_label, gold_label


class GoldLabelsTest(unittest.TestCase):
    def test_fallback_never_replaces_known_primary(self):
        text = 'COMPILATION ERROR\nJava heap space -> [Help 1]\nNo release type found in pull request title'
        self.assertEqual(gold_label([text]), base_gold_label([text]))

    def test_fallback_compile_before_lint(self):
        text = ('> Task :new-module:spotlessJava FAILED\n'
                'googlejavaformat.java.FormatterException: 23:2: error: class expected')
        self.assertEqual(base_gold_label([text])[0], '?')
        self.assertEqual(gold_label([text])[0], 'compile')
        self.assertEqual(gold_label(['> Task :server-common:spotlessJava FAILED'])[0], 'lint')

    def test_fallback_specific_dependency_and_network(self):
        self.assertEqual(gold_label(["Missing 'x:y' dependency on the classpath"])[0], 'dependency')
        self.assertEqual(gold_label(['AmazonServicesClientsProcessor#setup threw an exception'])[0], '?')
        text = 'could not be resolved: x Could not transfer artifact y: Connect timed out'
        self.assertEqual(base_gold_label([text])[0], '?')
        self.assertEqual(gold_label([text])[0], 'infra')

    def test_fallback_non_build_and_unexplained_tests(self):
        self.assertEqual(gold_label(['No release type found in pull request title'])[0], 'non_build')
        for text in ('Failed before controller upgrade', 'Failed after server upgrade'):
            self.assertEqual(gold_label([text])[0], '?')
        # v2 (14/10/2026): người gán cụm goal surefire :test là test; đo trên mẫu run đã có nhãn đúng 1400/1468 (95%),
        # phần sai chủ yếu là JVM fork crash (infra). Chỉ áp cho run mà quy tắc lõi để `?`.
        surefire = 'Failed to execute goal org.apache.maven.plugins:maven-surefire-plugin:3.5.2:test (default-test)'
        self.assertEqual(gold_label([surefire])[0], 'test')

    def test_kafka_summary(self):
        self.assertEqual(gold_label(['369 PASSED, 1 FAILED, 0 FLAKY'])[0], 'test')
        self.assertEqual(gold_label(['35518 PASSED, 0 FAILED, 4 FLAKY'])[0], 'flaky')
        self.assertEqual(gold_label(['35518 PASSED, 0 FAILED, 0 FLAKY'])[0], '?')
        self.assertEqual(gold_label(['Gradle task had a timeout. These are partial results!\n'
                                    '35518 PASSED, 0 FAILED, 4 FLAKY'])[0], 'infra')

    def test_checkstyle_success_and_plugin_download(self):
        self.assertEqual(gold_label(['[INFO] You have 0 Checkstyle violations.'])[0], '?')
        self.assertEqual(gold_label(['[ERROR] checkstyle:check failed: Plugin dependencies could not be resolved'])[0], '?')
        self.assertEqual(gold_label(['You have 3 Checkstyle violations.'])[0], 'lint')

    def test_missing_artifact_vs_truncated_download(self):
        missing = 'Could not find artifact com.aliyun.jindodata:jindo-core:jar:6.9.1 in central'
        self.assertEqual(gold_label([missing])[0], 'dependency')
        self.assertEqual(gold_label(['Could not resolve dependencies\nCould not transfer artifact: '
                                    'Premature end of Content-Length delimited message body\n' + missing])[0], 'infra')

    def test_test_failure_before_weak_network(self):
        self.assertEqual(gold_label(['Connection refused\nTests run: 10, Failures: 1, Errors: 0'])[0], 'test')
        self.assertEqual(gold_label(['Connection refused'])[0], 'infra')

    def test_license_and_action_download(self):
        self.assertEqual(gold_label(['Counter(s) UNAPPROVED exceeded minimum or maximum values'])[0], 'lint')
        self.assertEqual(gold_label(['Java setup process failed due to: error code: 504'])[0], 'infra')
        self.assertEqual(gold_label(['Failed to resolve action download info. Error: Service Unavailable'])[0], 'infra')
        self.assertEqual(gold_label(['E: There is at least one incompatibility: org.apache.pinot.Foo'])[0], 'lint')

    def test_compiler_and_lint_priority(self):
        self.assertEqual(gold_label(['COMPILATION ERROR\nThere are test failures'])[0], 'compile')
        self.assertEqual(gold_label(['[Error] /src/Foo.scala:12: not found: value foo'])[0], 'compile')
        self.assertEqual(gold_label(['e: file:///src/Foo.kt:12:3 Unresolved reference'])[0], 'compile')
        self.assertEqual(gold_label(["Execution failed for task ':core:compileJava'.\nCould not transfer artifact"])[0], '?')
        self.assertEqual(gold_label(["Execution failed for task ':core:spotlessJavaCheck'."])[0], 'lint')

    def test_generic_failure_is_unknown(self):
        for line in ('Process completed with exit code 1.', 'BUILD FAILURE', 'revapi check', '--error-on-binary-incompatibility'):
            self.assertEqual(gold_label([line])[0], '?')

    def test_resolution_needs_root_cause(self):
        summary = '[ERROR] Plugin dependencies could not be resolved:\n'
        self.assertEqual(gold_label([summary + '[ERROR] Failed to read artifact descriptor for x:y:jar:1'])[0], '?')
        self.assertEqual(gold_label([summary + '[ERROR] Could not find artifact x:y:jar:1 in central'])[0], 'dependency')
        label, evidence = gold_label([summary + '[ERROR] Could not transfer artifact x:y:jar:1: status code: 429'])
        self.assertEqual(label, 'infra')
        self.assertIn('429', evidence)
        self.assertEqual(gold_label(["Could not resolve all files for configuration ':test'.\n"
                                    " > Could not GET 'https://repo/artifact'. Received status code 403 from server: Forbidden"])[0], 'infra')
        self.assertEqual(gold_label(["Could not resolve all dependencies for configuration ':test'.\n"
                                    " > Could not find tools.jackson:jackson-guava:3.2.1.\n"
                                    "   Searched in the following locations: https://repo/artifact"])[0], 'dependency')

    def test_unrelated_job_does_not_change_missing_artifact(self):
        self.assertEqual(gold_label(['Could not find artifact x:y:jar:1',
                                    'Connection reset'])[0], 'dependency')
        self.assertEqual(gold_label(['Plugin dependencies could not be resolved',
                                    'There are test failures'])[0], 'test')

    def test_resolution_ignores_unrelated_numbers_and_network(self):
        text = ('[ERROR] Plugin dependencies could not be resolved:\n'
                '[ERROR] Could not find artifact x:y:jar:429 in central\n'
                '[ERROR] -> [Help 1]\nConnection reset')
        self.assertEqual(gold_label([text])[0], 'dependency')

    def test_echoed_retry_script_is_not_failure(self):
        text = ('2026-10-10T00:00:00Z ##[group]Run retry\n'
                '\x1b[36;1mif grep "Could not transfer artifact" output; then\x1b[0m\n'
                '##[endgroup]\nBUILD FAILURE')
        self.assertEqual(gold_label([text])[0], '?')
        self.assertEqual(gold_label([text + '\nCOMPILATION ERROR'])[0], 'compile')

    def test_mixed_failed_and_flaky_is_test(self):
        self.assertEqual(gold_label(['Found 1 test failures:\nFound 3 flaky test failures:\n'
                                    '38451 PASSED, 1 FAILED, 3 FLAKY'])[0], 'test')

    def test_final_evidence_without_newline(self):
        line = 'Could not find artifact org.example:missing:jar:1.0'
        self.assertEqual(gold_label([line]), ('dependency', line))
        self.assertEqual(gold_label(['\x1b[31m' + line + '\x1b[0m']), ('dependency', line))

    def test_ant_and_shell_test_failures(self):
        self.assertEqual(gold_label(['build.xml:2109: Some tests completed with an Error.'])[0], 'test')
        self.assertEqual(gold_label(['4 tests, 3 passed, 1 failed'])[0], 'test')
        self.assertEqual(gold_label(['ERROR: Test execution of ozone/test.sh is FAILED!!!!'])[0], 'test')
        self.assertEqual(gold_label(['4 tests, 4 passed, 0 failed'])[0], '?')
        self.assertTrue(NON_BUILD_WF.search('CI - Gradle Dependency Submission'))


    def test_buildconfig_and_javadoc(self):
        # 15/10/2026, người duyệt: buildconfig thành nhãn tầng 2 riêng; lỗi javadoc là lint (doc), không phải compile
        pom = "[ERROR] 'dependencies.dependency.version' for org.x:y:jar is missing. @ line 133, column 17"
        self.assertEqual(gold_label([pom])[0], 'buildconfig')
        self.assertEqual(gold_label(["[WARNING] 'build.plugins.plugin.version' for a:b is missing. @ line 1"])[0], '?')
        self.assertEqual(gold_label(['[FATAL] Non-parseable POM /w/pom.xml: unexpected character in markup'])[0], 'buildconfig')
        self.assertEqual(gold_label(['[ERROR] Could not find the selected project in the reactor: perf-tests @'])[0],
                         'buildconfig')
        self.assertEqual(gold_label([pom + '\nCOMPILATION ERROR'])[0], 'buildconfig')
        doc = '/w/src/main/java/a/Records.java:42: error: reference not found'
        self.assertEqual(gold_label([doc])[0], 'lint')
        self.assertEqual(gold_label(['/w/src/main/java/a/B.java:311: error: unknown tag: apiNote'])[0], 'lint')
        self.assertEqual(gold_label(['/w/src/main/java/a/B.java:[12,5] error: cannot find symbol'])[0], 'compile')
        self.assertEqual(gold_label([doc + '\n/w/src/main/java/a/C.java:7: error: incompatible types'])[0], 'compile')

    def test_dependency_review_q1_q3(self):
        # 18/10/2026, người duyệt: enforcer / dependency:analyze -> dependency (Q1); lệch JDK -> dependency, chỉ ghi đè
        # compile/test của chính job quyết định hoặc `?` (Q3); lỗi liên kết NoSuchMethodError không dùng (người chọn unclear)
        self.assertEqual(gold_label(['[ERROR] Used undeclared dependencies found:\n[ERROR]    org.x:y:jar:1:compile'])[0],
                         'dependency')
        self.assertEqual(gold_label(['[ERROR] Rule 1: org.apache.maven.enforcer.rules.dependency.DependencyConvergence '
                                     'failed with message:'])[0], 'dependency')
        wrong = '[ERROR]     class file has wrong version 65.0, should be 61.0'
        self.assertEqual(gold_label(['[ERROR] COMPILATION ERROR :\n' + wrong]), ('dependency', wrong))
        self.assertEqual(gold_label(['java.lang.UnsupportedClassVersionError: a/B has been compiled by a more recent version\n'
                                     'Tests run: 3, Failures: 1, Errors: 0'])[0], 'dependency')
        # tín hiệu Q3 ở job khác job quyết định -> giữ nhãn hiện hành
        self.assertEqual(gold_label(['[ERROR] COMPILATION ERROR :', 'java.lang.UnsupportedClassVersionError: a/B'])[0], 'compile')
        # Q3 không đè lint/infra
        self.assertEqual(gold_label(['You have 3 Checkstyle violations.\n' + wrong])[0], 'lint')
        self.assertEqual(gold_label(['Caused by: java.lang.NoSuchMethodError: a.B.c()\nFailed to execute goal x'])[0], '?')
        self.assertEqual(gold_label(["> Could not GET 'https://repo/x.pom'. Received status code 429 from server: "
                                     "Too Many Requests"])[0], 'infra')


if __name__ == '__main__':
    unittest.main()
