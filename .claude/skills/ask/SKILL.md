---
name: ask
description: Answer a question about the project and its subject, grounded in the knowledge base and cited (path#lines or SQL). Use for any factual question about the documents, data, systems, open points, claims or decisions of this project.
argument-hint: <question>
---
Question: $ARGUMENTS (the text typed after the command).

Ground before answering, cheapest step first; stop as soon as the answer is grounded.

1. Name the objects/concepts in the question. For each, run in the terminal:
   `uv run python tools/kb/graph.py about <name> --limit 8` (unresolved → `graph.py find <part>`).
2. Countable / listable → SQL with `uv run python tools/ingest/query.py "..."` (structured tables, or `kb.*`:
   `kb.reg_open_points`, `kb.reg_claims`, `kb.reg_decisions`, `kb.catalog`, `kb.sections`, `kb.edges`). Show the query.
3. Read only the line ranges the graph or `kb.sections` point to. Never read a whole note above the abstract
   threshold (`tools/kb/schema.yaml`, 40 KB by default).
4. Text search only if steps 1–3 found nothing.

Answer:
- ≤ 15 lines unless asked for more. The answer first, then the evidence.
- Every factual statement cites `path#Lstart-Lend` or the SQL. Say the evidence level when weaker than `primary-doc`;
  add "(extraction unchecked)" for notes with `status: extracted`. `derived-llm` / `assumed` are never stated as fact.
- What *is* (observed) and what we *intend* (design, decisions) go in separate, labelled sentences.
  Conflicting sources: report both, do not pick.
- Not grounded → "not documented" + a proposed OP (title, owner, impact). Record it only after the user agrees (`/capture`).
- If the graph missed a name that exists in the corpus, add the alias to `tools/kb/entities.yaml` and say so in one line.
