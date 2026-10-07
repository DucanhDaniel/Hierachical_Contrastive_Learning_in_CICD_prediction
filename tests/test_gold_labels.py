"""Kiểm tra các ranh giới dễ gán nhầm từ log thật và mẫu compiler JVM."""
import unittest

from project3.crawl.gold_labels import NON_BUILD_WF, gold_label


class GoldLabelsTest(unittest.TestCase):
    def test_kafka_summary(self):
        self.assertEqual(gold_label(['369 PASSED, 1 FAILED, 0 FLAKY'])[0], 'test')
        self.assertEqual(gold_label(['35518 PASSED, 0 FAILED, 4 FLAKY'])[0], 'flaky')
        self.assertEqual(gold_label(['35518 PASSED, 0 FAILED, 0 FLAKY'])[0], '?')
        self.assertEqual(gold_label(['Gradle task had a timeout. These are partial results!\n'
                                    '35518 PASSED, 0 FAILED, 4 FLAKY'])[0], 'infra')

    def test_checkstyle_success_and_plugin_download(self):
        self.assertEqual(gold_label(['[INFO] You have 0 Checkstyle violations.'])[0], '?')
        self.assertEqual(gold_label(['[ERROR] checkstyle:check failed: Plugin dependencies could not be resolved'])[0], 'infra')
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
        self.assertEqual(gold_label(["Execution failed for task ':core:compileJava'.\nCould not transfer artifact"])[0], 'infra')
        self.assertEqual(gold_label(["Execution failed for task ':core:spotlessJavaCheck'."])[0], 'lint')

    def test_generic_failure_is_unknown(self):
        for line in ('Process completed with exit code 1.', 'BUILD FAILURE', 'revapi check', '--error-on-binary-incompatibility'):
            self.assertEqual(gold_label([line])[0], '?')

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


if __name__ == '__main__':
    unittest.main()
