"""Write the review-only proposal. Never installs it in production rules."""
import json
from pathlib import Path


def main():
    current = json.loads(Path("configs/label_rules.json").read_text(encoding="utf-8"))
    rules = []

    def add(key, regex, layer="unknown_only", label="dependency", **extra):
        rules.append({"id":key,"priority":100+len(rules),"label":label,"regex":regex,"signature":key,
                      "matches_unlabeled":0,"conflicts_in_human_sample":[],"note":"Review-only; counts populated after evaluation; not human-approved.",
                      "origin":"codex-proposed","leaf_proposed":"network" if label=="infra" else label,"layer":layer, **extra})

    for r in current["rules"]:
        if r["priority"] in (34,36,44,45):
            rx = r["regex"] if r["priority"] in (34,45) else r"\[ERROR\]\s{1,20}Require\s{1,10}upper\s{1,10}bound\s{1,10}dependencies\s{1,10}error\s{1,10}for\s{1,10}\S{1,200}"
            add(f"Q1-replace-{r['priority']}",rx,"fallback_replace",replaces_priority=r["priority"])
    add("Q1-upper-bound",r"Require upper bound dependencies error for \S{1,200}|RequireUpperBoundDeps failed with message")
    add("Q1-convergence",r"Dependency convergence error for \S{1,200}|DependencyConvergence failed with message")
    add("Q1-banned",r"BannedDependencies failed with message")
    add("Q3-jdk-bytecode",r"(?:java\.lang\.)?UnsupportedClassVersionError:|Unsupported class file major version \d{1,3}|class file has wrong version \d{1,3}\.\d{1,3}|has been compiled by a more recent version of the Java Runtime","q3_override")
    add("Q3-jdk-target",r"(?:error: |Fatal error compiling: )invalid target release: \d{1,3}|(?:error: |Fatal error compiling: )release version \d{1,3} not supported","q3_override")
    add("Q3-linkage",r'(?:Exception in thread "[^"\n]{1,80}" |Caused by: )java\.lang\.(?:NoSuchMethodError|NoSuchFieldError|AbstractMethodError|IncompatibleClassChangeError):',"q3_override",guard="failure_context")
    add("Q3-gradle-jvm",r"Dependency requires at least JVM runtime version \d{1,3}\. This build uses a Java \d{1,3} JVM|Dependency resolution is looking for a library compatible with JVM runtime version [^\n]{1,180}|[Ii]ncompatible because this component declares a component,? compatible with Java \d{1,3} and the consumer needed a component,? compatible with Java \d{1,3}","q3_override",guard="no_network")
    add("Q3-gradle-conflict",r"Conflict found for module '[^'\n]{1,200}': between versions \S{1,100} and \S{1,100}","q3_override",guard="no_network")
    add("Q3-missing-class-pair",r"Caused by: java\.lang\.NoClassDefFoundError: (?!Could not initialize class)([A-Za-z_$][\w$]{0,100}(?:[/.][\w$]{1,100}){1,20})","q3_override",guard="missing_class_failure")
    add("DEP-pnpm-version",r"(?:Error: |ERR! )?ERR_PNPM_NO_MATCHING_VERSION\b",guard="no_network")
    add("DEP-lockfile-frozen",r"ERR_PNPM_OUTDATED_LOCKFILE\b|Cannot install with [^\n]{0,40}frozen-lockfile[^\n]{0,160}(?:not up to date|not up-to-date)|Your lockfile needs to be updated, but yarn was run with [^\n]{0,100}frozen-lockfile",guard="no_network")
    add("DEP-npm-eresolve",r"npm (?:ERR!|error) code ERESOLVE\b",guard="no_network")
    add("DEP-plugin-missing",r"Plugin \[id: [^\]\n]{1,300}\] was not found in any of the following sources:",guard="plugin_missing_context")
    add("DEP-gradle-file-missing",r"Could not find [^\s()]{1,200}\.(?:jar|pom) \([\w.:-]{1,300}\)\.",guard="missing_artifact_context")
    add("NET-gradle-http",r"Could not (?:GET|HEAD) [^\n]{1,400}",label="infra",guard="network_context")
    hints = {
        'Q1-replace-34':['Used'], 'Q1-replace-36':['Require'], 'Q1-replace-44':['Require'], 'Q1-replace-45':['Non-test'],
        'Q1-upper-bound':['Require'], 'Q1-convergence':['convergence','DependencyConvergence'], 'Q1-banned':['BannedDependencies'],
        'Q3-jdk-bytecode':['UnsupportedClassVersionError','Unsupported class file','class file has wrong version','more recent version'],
        'Q3-jdk-target':['invalid target release','release version'], 'Q3-linkage':['NoSuchMethodError','NoSuchFieldError','AbstractMethodError','IncompatibleClassChangeError'],
        'Q3-gradle-jvm':['JVM runtime version','incompatible because','Incompatible because'],
        'Q3-gradle-conflict':['Conflict found for module'], 'Q3-missing-class-pair':['NoClassDefFoundError'],
        'DEP-pnpm-version':['ERR_PNPM_NO_MATCHING_VERSION'],
        'DEP-lockfile-frozen':['ERR_PNPM_OUTDATED_LOCKFILE','frozen-lockfile'], 'DEP-npm-eresolve':['ERESOLVE'],
        'DEP-plugin-missing':['was not found in any'], 'DEP-gradle-file-missing':['Could not find'], 'NET-gradle-http':['Could not GET','Could not HEAD'],
    }
    for r in rules:
        r['hints']=hints[r['id']]
        if r['layer']=='fallback_replace':
            r['regex']=r['regex'].replace(r'\s+',r'\s{1,20}')
    output={"rule_version":current["rule_version"],"status":"codex-proposed-awaiting-human-review","source":"docs/codex/task-ra-soat-quy-tac-dependency.md","rules":rules}
    Path("configs/label_rules_dependency_proposed.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
