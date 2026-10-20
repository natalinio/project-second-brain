from conftest import py


def test_empty_skeleton_refreshes_clean(brain):
    r = py(brain, "tools/kb/refresh.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 error(s)" in r.stdout


def test_query_works_without_structured_db(brain):
    py(brain, "tools/kb/refresh.py")
    r = py(brain, "tools/ingest/query.py", "SELECT count(*) AS n FROM kb.reg_open_points")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "| n |" in r.stdout.replace("|   n |", "| n |") or " n " in r.stdout


def test_lint_rejects_bad_evidence(brain):
    note = brain / "knowledge" / "curated" / "bad.md"
    note.write_text("---\ntitle: Bad\ntype: summary\nstatus: draft\norigin: curated\n"
                    "evidence: rumour\nupdated: 2026-01-01\n---\n\n# Bad\n", encoding="utf-8")
    r = py(brain, "tools/kb/lint.py", "knowledge/curated/bad.md")
    assert r.returncode == 1
    assert "evidence" in r.stdout
