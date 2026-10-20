from conftest import py


def test_demo_bootstraps_clean(brain):
    r = py(brain, "tools/kb/bootstrap.py", "--demo", "--no-hook")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 error(s)" in r.stdout
    assert "Order platform demo" in (brain / "AGENTS.md").read_text(encoding="utf-8")


def test_demo_graph_lineage_and_sections(brain):
    py(brain, "tools/kb/bootstrap.py", "--demo", "--no-hook")
    r = py(brain, "tools/kb/graph.py", "about", "ORDERS_DAILY")
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "**Upstream**" in out and "ORDERS_RAW" in out and "CUSTOMER_MASTER" in out
    assert "**Downstream**" in out and "SALES_SUMMARY" in out
    assert "JOB_ORDERS_LOAD" in out
    assert "order-service-spec-v1-2.md" in out          # the note section that mentions it
    assert "Defined in" in out                            # curated note with `defines:`


def test_demo_registers_and_impact(brain):
    py(brain, "tools/kb/bootstrap.py", "--demo", "--no-hook")
    r = py(brain, "tools/ingest/query.py", "SELECT id, status FROM kb.reg_claims ORDER BY id")
    assert "C-002" in r.stdout and "conflicting" in r.stdout
    r = py(brain, "tools/kb/graph.py", "impact", "OP-001")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "D-001" in r.stdout or "reporting-refresh.md" in r.stdout


def test_demo_email_and_inventory(brain):
    py(brain, "tools/kb/bootstrap.py", "--demo", "--no-hook")
    assert (brain / "knowledge/extracted/correspondence/2026-02-03-cancelled-order-retention.md").exists()
    r = py(brain, "tools/ingest/query.py", "SELECT count(*) AS n FROM orders_sample")
    assert "8" in r.stdout
