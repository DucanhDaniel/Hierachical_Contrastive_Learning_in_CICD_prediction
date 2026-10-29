from project3.crawl.stages import failed_tools, run_axes, step_stage


def chunk(text, steps="", header="", ev=False):
    return {"text": text, "failed_steps": steps, "step_header": header, "has_evidence": ev}


def test_failed_tools_maven_gradle_and_it_module():
    text = ("[ERROR] Failed to execute goal org.apache.maven.plugins:maven-surefire-plugin:3.2:test (default-test) "
            "on project paimon-e2e-tests: x\n> Task :integration-tests:test FAILED\n"
            "Execution failed for task ':app:compileJava'\n> Task :build FAILED")
    assert failed_tools(text) == [("maven-surefire-plugin:test@paimon-e2e-tests", "itest"),
                                  (":integration-tests:test", "itest"), (":app:compileJava", "compile")]


def test_compile_test_task_is_compile_not_test():
    assert failed_tools("Execution failed for task ':core:compileTestJava'")[0][1] == "compile"
    assert failed_tools("> Task :spotlessJavaCheck FAILED")[0][1] == "check"


def test_leaf_stage_and_tool_override_for_tests():
    c = [chunk("Failed to execute goal org.apache.maven.plugins:maven-failsafe-plugin:3.2:verify (v) on project a: x",
               ev=True)]
    out = run_axes("testfailure", "x", "x", c)
    assert (out["location"], out["stage"], out["stage_src"]) == ("code", "itest", "tool")
    assert run_axes("quality", "x", "x", c)["stage"] == "check"  # lá không phải test: giữ giai đoạn của lá


def test_env_failure_gets_stage_from_log():
    c = [chunk("> Could not GET 'https://repo.maven.apache.org/x.pom'", ev=True)]
    out = run_axes("network", "> Could not GET 'https://repo.maven.apache.org/x.pom'", "", c)
    assert (out["location"], out["stage"], out["stage_src"]) == ("env", "prepare", "evidence")
    shutdown = [chunk("[INFO] --- maven-surefire-plugin:3.2:test (default-test) @ core ---\nRunning FooTest\n"
                      "##[error]The runner has received a shutdown signal.", ev=True)]
    out = run_axes("crash", "##[error]The runner has received a shutdown signal.", "##[error]The runner", shutdown)
    assert out["stage"] == "setup"  # dòng bằng chứng runner đứng trước ngữ cảnh


def test_unknown_run_stage_from_step_and_governance():
    out = run_axes(None, "", "", [chunk("boom", steps="Run unit tests")])
    assert (out["location"], out["stage"], out["governance"]) == (None, "test", False)
    out = run_axes(None, "", "", [chunk("boom", steps="Run dangoslen/changelog-enforcer@v3")])
    assert (out["stage"], out["governance"]) == (None, True)
    assert step_stage(["Check sub-job results", "Build"]) is None
