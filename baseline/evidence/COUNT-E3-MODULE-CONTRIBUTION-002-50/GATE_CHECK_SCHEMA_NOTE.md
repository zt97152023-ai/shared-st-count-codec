# Gate-check note

The first generic `check_gate.py --gate verified` invocation failed on missing generic task fields (`task_id`, `acceptance_criteria`, `approval`, and `evidence`) because this iteration contract initially used the repository's older `id/acceptance/outputs` naming. This was an engineering schema mismatch, not an experiment or verification failure. The contract was amended with equivalent completed evidence fields; no scientific endpoint or result changed.
