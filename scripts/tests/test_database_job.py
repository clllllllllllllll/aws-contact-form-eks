"""Offline checks for database setup Job lifecycle decisions and diagnostics."""

import importlib.util
import unittest
from pathlib import Path


FILTER_PATH = Path(__file__).resolve().parents[2] / "ansible/filter_plugins/database_job.py"
SPEC = importlib.util.spec_from_file_location("database_job_filter", FILTER_PATH)
database_job = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(database_job)


def job(*conditions, **status):
    return {"status": {"conditions": list(conditions), **status}}


class DatabaseJobTests(unittest.TestCase):
    def test_absent_job_requires_creation(self):
        self.assertEqual(database_job.database_job_state({}), "absent")
        self.assertEqual(database_job.database_job_state(None), "absent")

    def test_completed_job_is_reused(self):
        existing = job({"type": "Complete", "status": "True"}, succeeded=1)
        self.assertEqual(database_job.database_job_state(existing), "complete")

    def test_running_job_is_waited_on(self):
        self.assertEqual(database_job.database_job_state(job(active=1)), "running")
        self.assertEqual(
            database_job.database_job_state(job({"type": "Failed", "status": "False"}, failed=1)),
            "running",
        )

    def test_terminal_failure_requires_recreation(self):
        existing = job({"type": "Failed", "status": "True"}, failed=3)
        self.assertEqual(database_job.database_job_state(existing), "failed")

    def test_running_job_that_fails_moves_to_recreation(self):
        running = job(active=1)
        failed = job({"type": "Failed", "status": "True"}, failed=3)
        self.assertEqual(database_job.database_job_state(running), "running")
        self.assertEqual(database_job.database_job_state(failed), "failed")

    def test_diagnostics_exclude_logs_messages_and_untrusted_reasons(self):
        secret = "sensitive-password-value"
        failed = job(
            {"type": "Failed", "status": "True", "message": secret, "reason": secret},
            failed=2,
            active=0,
            succeeded=0,
        )
        pods = [{
            "metadata": {"name": secret},
            "status": {
                "phase": "Failed",
                "message": secret,
                "containerStatuses": [{
                    "name": "setup",
                    "state": {
                        "terminated": {"exitCode": 1, "reason": "Error", "message": secret}
                    },
                }],
            },
            "logs": secret,
        }, {
            "status": {
                "phase": secret,
                "containerStatuses": [{
                    "name": "setup",
                    "state": {"waiting": {"reason": secret, "message": secret}},
                }],
            },
        }]
        summary = database_job.database_job_diagnostics(failed, pods)
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(summary["pod_count"], 2)
        self.assertEqual(summary["pods"][0], {
            "phase": "Failed",
            "setup_reason": "Error",
            "setup_exit_code": 1,
        })
        self.assertEqual(summary["pods"][1], {
            "phase": "Unknown",
            "setup_reason": "unavailable",
            "setup_exit_code": None,
        })
        self.assertNotIn(secret, repr(summary))


if __name__ == "__main__":
    unittest.main()
