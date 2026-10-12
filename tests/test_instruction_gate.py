"""Instruction and architecture gate, ported from gap-trap's pytest reference."""
import ast
import hashlib
import json
import re
import subprocess

import pytest

from quality_common import ROOT, copy_public, inventory, python_files

WORD_BUDGET = 3000
LOADED = ("AGENTS.md", "AGENTS.project.md", "CLAUDE.md")
FIELDS = ("Owns", "Path", "Never", "Gate")
KNOWLEDGE_FILES = (
    "agents/generic/agent-workflows.md",
    "agents/project/domain-context.md",
    "agents/project/out-of-scope.md",
    "agents/project/glossary.md",
    "agents/project/testing.md",
    "agents/project/documentation.md",
    "agents/project/project-decisions.md",
)
SPAN_CONSUMERS = {
    "pipeline/04_mine_passages.py": {
        "mine_work": ["registry.claim"], "mine_corpus": ["spine.SpanRegistry"],
        "build_reserved_registry": ["spine.SpanRegistry", "registry.claim"],
    },
    "pipeline/gen_bucket1_candidates.py": {
        "load_registry": ["spine.SpanRegistry", "reg.claim"], "mine": ["reg.overlaps"],
    },
    "pipeline/gen_bucket2.py": {
        "reserved_registry": ["spine.SpanRegistry"], "_claim_file": ["reg.claim"],
    },
    "pipeline/gen_bucket3_farewell.py": {"reserved_registry": ["spine.SpanRegistry", "reg.claim"]},
    "pipeline/gen_bucket3_sun.py": {"reserved_registry": ["spine.SpanRegistry", "reg.claim"]},
}
INTEGRITY_CONSUMERS = {
    "pipeline/04_mine_passages.py": ["content_hash", "append_record"],
    "pipeline/gen_bucket1_candidates.py": ["content_hash", "append_record"],
    "pipeline/reserve_bucket1.py": ["content_hash", "append_record"],
    "pipeline/gen_bucket1_requests.py": ["content_hash", "append_record", "load_done_ids"],
    "pipeline/gen_bucket1_select.py": ["append_record", "load_done_ids"],
    "pipeline/gen_bucket2.py": ["content_hash", "append_record", "load_done_ids"],
    "pipeline/gen_bucket2_requests.py": ["append_record", "load_done_ids"],
    "pipeline/06_bucket3_generate.py": ["append_record", "load_done_ids"],
    "pipeline/gen_bucket3_farewell.py": ["content_hash", "append_record", "load_done_ids"],
    "pipeline/gen_bucket3_sun.py": ["content_hash", "append_record", "load_done_ids"],
    "pipeline/gen_bucket4_pool.py": ["content_hash", "append_record"],
    "pipeline/gen_bucket4_select.py": ["append_record", "load_done_ids"],
    "pipeline/gen_bucket4.py": ["content_hash", "append_record", "load_done_ids"],
    "pipeline/07_acceptance_gate.py": ["append_record"],
    "pipeline/08_bucket1_gate.py": ["content_hash", "append_record"],
    "pipeline/08_bucket2_gate.py": ["append_record"],
    "pipeline/08_bucket4_gate.py": ["content_hash", "append_record"],
    "pipeline/09_assemble.py": ["content_hash"],
}


def text(path):
    return path.read_text(encoding="utf-8")


def contracts(root=ROOT):
    section = text(root / "AGENTS.project.md").split("## Architecture contracts", 1)[1].split("\n## ", 1)[0]
    return [part.partition("\n") for part in section.split("\n### ")[1:]]


def fields(body):
    result = {}
    active = None
    for line in body.splitlines():
        match = re.match(r"^(Owns|Path|Never|Gate):\s*(.*)", line)
        if match:
            active = match[1]
            result[active] = match[2]
        elif not line.strip():
            active = None
        elif active:
            result[active] += " " + line.strip()
    return result


def validate_contracts(root=ROOT):
    blocks = contracts(root)
    assert len(blocks) == 6, "contract inventory changed; review its minimum and scopes"
    files = python_files(root)
    source = "\n".join(text(root / p) for p in files if not p.startswith("tests/"))
    checked = 0
    for name, _, body in blocks:
        parsed = fields(body)
        assert set(FIELDS) <= set(parsed), f"{name}: missing contract field"
        count = 0
        for field in ("Path", "Gate"):
            tokens = re.findall(r"`([^`]+)`", parsed[field])
            paths = [token for token in tokens if "/" in token]
            for path in paths:
                assert (root / path).is_file(), f"{name}: missing path {path}"
                count += 1
            haystack = "\n".join(text(root / p) for p in paths) if field == "Path" and paths else source
            for token in tokens:
                if "/" not in token:
                    assert re.search(rf"\b{re.escape(token)}\b", haystack), f"{name}: missing symbol {token}"
                    count += 1
        assert count >= 1, f"{name}: no resolvable tokens"
        checked += count
    return len(blocks), checked, len(files)


def test_contract_names_and_fields():
    count, tokens, files = validate_contracts()
    print(f"instruction: {count} contracts, {tokens} tokens resolved, {files} Python files")


def test_core_is_portable_and_loaded_files_fit_budget():
    core = text(ROOT / "AGENTS.md").lower()
    for token in ("ernie", "hemingway", "qwen", "fastapi", "pipeline/", "demo/"):
        assert token not in core, f"portable core contains {token}"
    assert all((ROOT / p).is_file() for p in LOADED)
    total = sum(len(text(ROOT / p).split()) for p in LOADED)
    assert total <= WORD_BUDGET, f"{total} words exceeds {WORD_BUDGET}"
    print(f"instruction words: {total} / {WORD_BUDGET}")


def check_knowledge_inventory(root=ROOT):
    files = {p for p in inventory(root) if p.startswith("agents/") and p.endswith(".md")}
    missing = set(KNOWLEDGE_FILES) - files
    assert missing == set(), f"missing knowledge files: {sorted(missing)}"
    return files


def test_public_knowledge_and_provenance():
    files = check_knowledge_inventory()
    public = [p for p in inventory() if p in LOADED or
              (p.startswith(("agents/", "docs/", "tests/", "scripts/")) and p.endswith((".md", ".py")))]
    for name in public:
        value = text(ROOT / name)
        assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", value), f"address in {name}"
        assert not re.search(r"(?i)[a-z]:[/\\]users[/\\]|/(?:home|Users)/[\w.-]+/", value), f"private path in {name}"
        assert not re.search(r"\b(?:hf|rpa)_[A-Za-z0-9]{16,}|\bsk-[A-Za-z0-9_-]{20,}", value), f"credential in {name}"
        if name.endswith(".md"):
            addresses = re.findall(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b", value)
            assert all(a.endswith(("@example.invalid", "@example.com", "noreply@anthropic.com")) for a in addresses), f"email in {name}"
    context = text(ROOT / "agents/project/domain-context.md")
    hashes = {h for h in re.findall(r"\b[0-9a-f]{7,40}\b", context) if re.search(r"\d", h)}
    assert len(hashes) >= 1, "no provenance hashes measured"
    for value in hashes:
        result = subprocess.run(["git", "cat-file", "-e", f"{value}^{{commit}}"], cwd=ROOT, capture_output=True)
        assert result.returncode == 0, f"unknown cited commit {value}"
    print(f"knowledge: {len(files)} files, {len(hashes)} cited commits; {len(public)} public files scanned")


def test_document_rule_references():
    valid = set(re.findall(r"^- ([IPCM]\d+)\.", text(ROOT / "AGENTS.md"), re.M))
    assert len(valid) >= 20, "core rule inventory unexpectedly shrank"
    docs = [p for p in inventory() if p.startswith(("docs/", "agents/")) and p.endswith(".md")]
    assert set(KNOWLEDGE_FILES) <= set(docs), "knowledge docs missing from rule-reference scan"
    for name in docs:
        for rule in re.findall(r"\brules? ([IPCM]\d+)\b", text(ROOT / name), re.I):
            assert rule.upper() in valid, f"{name}: unknown rule {rule}"


def check_shared(root, name, forbidden, required, function=None):
    tree = ast.parse(text(root / name))
    definitions = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    assert not definitions & set(forbidden), f"{name}: forbidden local helper {definitions & set(forbidden)}"
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update({alias.asname or alias.name: alias.name for alias in node.names})
        elif isinstance(node, ast.ImportFrom):
            imports.update({alias.asname or alias.name: f"{node.module}.{alias.name}" for alias in node.names})
    scope = tree
    if function:
        matches = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function]
        assert len(matches) == 1, f"{name}: expected one {function} consumer"
        scope = matches[0]
    calls = {ast.unparse(n.func) for n in ast.walk(scope) if isinstance(n, ast.Call)}
    for call in required:
        assert call in calls, f"{name}: missing sanctioned call {call} in {function or 'module'}"
        binding = call.split(".")[0]
        if binding in {"spine", "stylometry", "fg_mod", "fidelity_gate", "append_record", "load_done_ids"}:
            expected = {"fg_mod": "fidelity_gate", "fidelity_gate": "fidelity_gate.fidelity_gate",
                        "append_record": "spine.append_record", "load_done_ids": "spine.load_done_ids"}.get(binding, binding)
            assert imports.get(binding) == expected, f"{name}: wrong sanctioned import {binding}"
            assert binding not in definitions, f"{name}: local replacement of {binding}"
            rebound = any((isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == binding)
                          or (isinstance(n, ast.arg) and n.arg == binding) for n in ast.walk(tree))
            rebound |= any(isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                           and ast.unparse(n) == call for n in ast.walk(tree))
            assert rebound is False, f"{name}: rebound sanctioned helper {binding}"


def check_dataset_integrity(root=ROOT):
    forbidden = ["content_hash", "SpanRegistry", "append_record", "load_done_ids", "claim", "overlaps"]
    for name, required in INTEGRITY_CONSUMERS.items():
        calls = required if name == "pipeline/06_bucket3_generate.py" else [f"spine.{n}" for n in required]
        check_shared(root, name, forbidden, calls)
    for name, consumers in SPAN_CONSUMERS.items():
        for function, required in consumers.items():
            check_shared(root, name, forbidden, required, function)


def test_dataset_integrity_consumers():
    check_dataset_integrity()
    print(f"integrity: {len(INTEGRITY_CONSUMERS)} modules; {len(SPAN_CONSUMERS)} span consumers checked")


def test_shared_measurement_and_fidelity_paths():
    scopes = {
        "pipeline/build_style_reference.py": (["split_sentences", "style_metrics", "chunk_text"], ["stylometry.style_metrics", "stylometry.chunk_text"]),
        "pipeline/bucket4_cadence_gate.py": (["split_sentences", "style_metrics"], ["stylometry.style_metrics"]),
        "pipeline/eval/score_generations.py": (["split_sentences", "style_metrics", "chunk_text"], ["stylometry.style_metrics", "stylometry.chunk_text"]),
        "pipeline/06_bucket3_generate.py": (["fidelity_gate"], ["fidelity_gate"]),
        "pipeline/gen_bucket3_farewell.py": (["fidelity_gate"], ["fidelity_gate"]),
        "pipeline/gen_bucket3_sun.py": (["fidelity_gate"], ["fidelity_gate"]),
        "pipeline/07_acceptance_gate.py": (["fidelity_gate"], ["fg_mod.fidelity_gate"]),
        "pipeline/09_assemble.py": (["content_hash"], ["spine.content_hash", "near_dup_groups", "pick_holdout"]),
    }
    for name, (forbidden, required) in scopes.items():
        check_shared(ROOT, name, forbidden, required)
    print(f"shared paths: {len(scopes)} consumers checked")


def notebook_cells(root=ROOT):
    tree = ast.parse(text(root / "pipeline/train/build_notebook.py"))
    values = {}
    cells = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            values[name] = node.value.value
        elif name == "cells":
            cells = node.value
    assert isinstance(cells, ast.List), "builder cells must remain declarative"
    expected = []
    for cell in cells.elts:
        assert isinstance(cell, ast.Tuple) and len(cell.elts) == 2
        kind, value = cell.elts
        assert isinstance(value, ast.Name) and value.id in values
        expected.append(("markdown" if ast.literal_eval(kind) == "md" else "code", values[value.id].strip("\n") + "\n"))
    return expected


def test_notebook_matches_builder():
    expected = notebook_cells()
    notebook = json.loads(text(ROOT / "pipeline/train/Ernie_Train_Colab.ipynb"))
    actual = [(c["cell_type"], "".join(c["source"])) for c in notebook["cells"]]
    assert len(actual) == len(expected) == 13
    assert actual == expected, "notebook drift: regenerate from builder"
    print(f"notebook: {len(actual)} cells compared")


def test_corpus_allowlist_and_browser_boundary():
    raw = {"the-sun-also-rises.txt", "farewell-to-arms.txt", "in-our-time.txt", "men-without-women.txt", "three-short-stories-and-ten-poems.txt"}
    tree = ast.parse(text(ROOT / "pipeline/01_clean_corpus.py"))
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "RAW_FILES" for t in n.targets))
    assert set(ast.literal_eval(assignment.value)) == raw
    assert all((ROOT / p).is_file() for p in raw)
    assert not any("oldmansea" in p.lower() for p in inventory())
    html = text(ROOT / "demo/static/index.html")
    urls = re.findall(r"fetch\(\s*[\"']([^\"']+)", html)
    assert set(urls) == {"/api/info", "/api/stream"}
    assert not re.search(r"ERNIE_KEY|BASELINE_KEY|Bearer |rpa_[A-Za-z0-9]|hf_[A-Za-z0-9]", html)
    print(f"corpus: {len(raw)} files; browser: {len(urls)} same-origin requests")


@pytest.fixture
def scratch_repo(tmp_path):
    copy_public(tmp_path, ("pipeline", "demo", "agents"),
                (*LOADED, "tests/test_instruction_gate.py", "tests/test_pipeline.py", "tests/test_demo.py"))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.mark.parametrize("violation", ["symbol", "field", "missing_file"])
def test_contract_gate_rejects_scratch_violations(scratch_repo, violation):
    validate_contracts(scratch_repo)
    path = scratch_repo / "AGENTS.project.md"
    if violation == "symbol":
        path.write_text(text(path).replace("`SpanRegistry`", "`InventedRegistry`"), encoding="utf-8")
    elif violation == "field":
        path.write_text(text(path).replace("Owns:", "Missing:", 1), encoding="utf-8")
    else:
        (scratch_repo / "pipeline/spine.py").unlink()
    with pytest.raises(AssertionError):
        validate_contracts(scratch_repo)


@pytest.mark.parametrize("name", KNOWLEDGE_FILES)
def test_knowledge_gate_rejects_each_missing_file(scratch_repo, name):
    check_knowledge_inventory(scratch_repo)
    (scratch_repo / name).unlink()
    replacement = scratch_repo / "agents/project/unrelated.md"
    replacement.write_text("Unrelated public knowledge.\n", encoding="utf-8")
    with pytest.raises(AssertionError, match=re.escape(name)):
        check_knowledge_inventory(scratch_repo)


def test_scratch_copy_excludes_ignored_artifacts(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    (source / "demo/deploy").mkdir(parents=True)
    (source / ".gitignore").write_text("demo/deploy/\n", encoding="utf-8")
    (source / "demo/server.py").write_text("PUBLIC = True\n", encoding="utf-8")
    (source / "demo/deploy/private.txt").write_text("ignored fixture marker", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    copied = copy_public(destination, ("demo",), root=source)
    assert copied == ["demo/server.py"]
    assert text(destination / "demo/server.py") == "PUBLIC = True\n"
    assert sorted(p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()) == copied


@pytest.mark.parametrize("name,function,call", [
    (name, function, call) for name, consumers in SPAN_CONSUMERS.items()
    for function, calls in consumers.items() for call in calls
])
def test_span_gate_rejects_bypassed_consumer(scratch_repo, name, function, call):
    check_dataset_integrity(scratch_repo)
    path = scratch_repo / name
    tree = ast.parse(text(path))
    consumer = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    class Bypass(ast.NodeTransformer):
        def visit_Call(self, node):
            if ast.unparse(node.func) == call:
                node.func = ast.Name(id="unshared_helper", ctx=ast.Load())
            return self.generic_visit(node)
    Bypass().visit(consumer)
    # Leave a decoy call elsewhere: module-wide presence cannot prove this consumer.
    tree.body.append(ast.parse(f"def decoy():\n    {call}()\n").body[0])
    path.write_text(ast.unparse(ast.fix_missing_locations(tree)), encoding="utf-8")
    with pytest.raises(AssertionError, match="missing sanctioned call"):
        check_dataset_integrity(scratch_repo)


@pytest.mark.parametrize("name,helper", [
    (name, helper) for name, helpers in INTEGRITY_CONSUMERS.items() for helper in helpers
])
def test_integrity_gate_rejects_helper_bypass(scratch_repo, name, helper):
    check_dataset_integrity(scratch_repo)
    path = scratch_repo / name
    call = helper if name == "pipeline/06_bucket3_generate.py" else f"spine.{helper}"
    tree = ast.parse(text(path))
    class Bypass(ast.NodeTransformer):
        def visit_Call(self, node):
            if ast.unparse(node.func) == call:
                node.func = ast.Name(id="unshared_helper", ctx=ast.Load())
            return self.generic_visit(node)
    Bypass().visit(tree)
    path.write_text(ast.unparse(ast.fix_missing_locations(tree)), encoding="utf-8")
    with pytest.raises(AssertionError, match="missing sanctioned call"):
        check_dataset_integrity(scratch_repo)


@pytest.mark.parametrize("name,helper,call", [
    ("pipeline/06_bucket3_generate.py", "fidelity_gate", "fidelity_gate"),
    ("pipeline/build_style_reference.py", "split_sentences", "stylometry.style_metrics"),
    ("pipeline/bucket4_cadence_gate.py", "style_metrics", "stylometry.style_metrics"),
    ("pipeline/eval/score_generations.py", "chunk_text", "stylometry.chunk_text"),
])
@pytest.mark.parametrize("violation", ["local", "missing_call", "wrong_import", "rebound"])
def test_shared_gate_rejects_helper_bypasses(scratch_repo, name, helper, call, violation):
    forbidden, required = [helper], [call]
    check_shared(scratch_repo, name, forbidden, required)
    path = scratch_repo / name
    value = text(path)
    if violation == "local":
        value += f"\ndef {helper}(*args):\n    return True\n"
    elif violation == "missing_call":
        value = value.replace(f"{call}(", "unshared_helper(")
    elif violation == "wrong_import":
        value = value.replace("from fidelity_gate import", "from unshared_gate import") if call == "fidelity_gate" else value.replace("import stylometry", "import unshared_style as stylometry")
    else:
        value += f"\n{call.split('.')[0]} = lambda *args: True\n"
    path.write_text(value, encoding="utf-8")
    with pytest.raises(AssertionError, match="forbidden local|missing sanctioned|wrong sanctioned|rebound sanctioned"):
        check_shared(scratch_repo, name, forbidden, required)


@pytest.mark.parametrize("violation", ["local_class", "method_rebound", "wrong_import"])
def test_span_gate_rejects_replacement_registry(scratch_repo, violation):
    check_dataset_integrity(scratch_repo)
    path = scratch_repo / "pipeline/gen_bucket3_farewell.py"
    value = text(path)
    if violation == "local_class":
        value += "\nclass SpanRegistry:\n    pass\n"
    elif violation == "method_rebound":
        value += "\nspine.SpanRegistry = lambda: None\n"
    else:
        value = value.replace("import spine", "import unshared_spine as spine")
    path.write_text(value, encoding="utf-8")
    with pytest.raises(AssertionError, match="forbidden local|rebound sanctioned|wrong sanctioned"):
        check_dataset_integrity(scratch_repo)


def check_training_chat(root=ROOT):
    tree = ast.parse(text(root / "pipeline/09_assemble.py"))
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {"_b3_instruction", "to_chat", "chatml"}:
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"SYSTEM_PROMPT", "B3_INSTRUCTIONS"} for t in node.targets):
            selected.append(node)
    namespace = {"hashlib": hashlib}
    # Execute only the declarative prompt values and pure formatting helpers.
    exec(compile(ast.Module(body=selected, type_ignores=[]), "training_chat", "exec"), namespace)
    assert namespace["SYSTEM_PROMPT"] == "You are a helpful assistant."
    instructions = ("Rewrite this in your own voice:", "Rewrite the following passage:",
                    "Say this in your own words:", "Put this into your own style:", "Rewrite this:")
    for index in range(20):
        row = {"id": str(index), "invented_question": "Why wait?", "span_text": "He waited.",
               "invented_request": "Describe a dock.", "real_target": "The dock was wet.",
               "flattened_input": "The dock had water on it.", "instruction": "Plan a walk.",
               "hemingway_answer": "Start early."}
        instruction = instructions[int(hashlib.md5(row["id"].encode()).hexdigest(), 16) % len(instructions)]
        expected = {1: (row["invented_question"], row["span_text"], "reflective_qa"),
                    2: (row["invented_request"], row["real_target"], "description"),
                    3: (instruction + "\n\n" + row["flattened_input"], row["real_target"], "rewrite"),
                    4: (row["instruction"], row["hemingway_answer"], "practical_qa")}
        for bucket, mapped in expected.items():
            assert namespace["to_chat"](row, bucket) == mapped, f"bucket {bucket}: training mapping changed"
            user, assistant, task = mapped
            item = {"id": row["id"], "bucket": bucket, "task": task, "user": user, "assistant": assistant}
            assert namespace["chatml"](item) == {
                "messages": [{"role": "system", "content": "You are a helpful assistant."},
                             {"role": "user", "content": user}, {"role": "assistant", "content": assistant}],
                "id": row["id"], "bucket": bucket, "task": task,
            }, "training ChatML changed or includes voice instructions"


def test_training_system_and_chat_mapping_are_neutral():
    check_training_chat()


@pytest.mark.parametrize("old,new", [
    ('SYSTEM_PROMPT = "You are a helpful assistant."', 'SYSTEM_PROMPT = "Write like Hemingway."'),
    ('"Rewrite this in your own voice:"', '"Rewrite this like Hemingway:"'),
    ('"content": SYSTEM_PROMPT', '"content": "Write like Hemingway."'),
    ('return row["invented_question"], row["span_text"]', 'return row["span_text"], row["invented_question"]'),
])
def test_training_gate_rejects_prompt_and_mapping_drift(scratch_repo, old, new):
    check_training_chat(scratch_repo)
    path = scratch_repo / "pipeline/09_assemble.py"
    value = text(path)
    assert value.count(old) == 1, "training mutation must change one source anchor"
    path.write_text(value.replace(old, new), encoding="utf-8")
    with pytest.raises(AssertionError):
        check_training_chat(scratch_repo)
