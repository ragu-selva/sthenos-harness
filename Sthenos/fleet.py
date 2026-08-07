"""Day 5 -- fleet: many independent jobs, many harnesses, one call.

Everything so far runs one Harness at a time. Real work is rarely one
task -- "write utils.py" and "write test_utils.py" are two independent
jobs, not one conversation, and running them one after another wastes the
time neither needed to wait for the other. run_fleet is the smallest thing
that fixes that: it doesn't know what a Harness is, only that make_harness
returns something with .run(task), so the same function fans out real
agents, fakes in a test, or anything else shaped like one.

Design rules:
  - a job never takes down the fleet. One task raising is data the caller
    reads in the result, same as tools.py turning a raised exception into
    a string the model can act on -- ok=False and the exception's own
    message, not a crashed pool.
  - results come back in job order, not completion order. Concurrency is
    an implementation detail of how the jobs run, not something the caller
    should have to re-sort around.
"""

from concurrent.futures import ThreadPoolExecutor


def run_fleet(jobs, make_harness, max_workers=4):
    """Run each job's task in its own harness, concurrently; return results in job order.

    jobs is [{"name", "workdir", "task"}, ...]. make_harness(workdir) builds
    the agent for one job -- run_fleet doesn't care what it is, only that it
    has .run(task). Each result is {"name", "ok", "report"}: the final text
    on success, "<ExceptionType>: message" on failure.
    """
    def run_one(job):
        try:
            report = make_harness(job["workdir"]).run(job["task"])
            return {"name": job["name"], "ok": True, "report": report}
        except Exception as e:
            return {"name": job["name"], "ok": False, "report": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(run_one, jobs))
