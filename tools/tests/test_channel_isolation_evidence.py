"""Behavior checks for evidence rejection; fixtures are never release receipts."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


receipt = load("write_channel_isolation_receipt")
smoke = load("smoke_unix_install_transaction")
SHA = "a" * 64
COORDINATES = dict(build_run_id="fixture-evidence-20260905", root_commit="0" * 40,
                   cli_commit="0" * 40, version="0.0.0", channel="test")


def observations(platform):
    rejections = []
    for probe in ("extra-arguments", "opposite-channel-manifest", "forged-core-url"):
        for _, _, name, _ in receipt._observation_specs(platform):
            rejections.append(dict(wrapper=name, probe=probe, observed_exit_code=1,
                                   diagnostic="fixture rejected", raw_output="fixture rejected",
                                   raw_output_sha256=receipt._sha256_bytes(b"fixture rejected")))
    rejections[8]["probe"] = "tampered-core"
    baseline = "9.9.9" if platform == "windows" else "9.9.1"
    committed = "9.9.14" if platform == "windows" else "9.9.4"
    transactions = [dict(probe=probe, expected_version=baseline, observed_version=baseline,
                         observed_exit_code=1, database_sha256=SHA, database_before_sha256=SHA)
                    for probe in ("invalid-bundle-entry-rollback", "pre-replacement-rollback",
                                  "post-placement-rollback", "post-skills-rollback")]
    transactions.append(dict(probe="committed-update-database-snapshot", expected_version=committed,
                             observed_version=committed, observed_exit_code=0,
                             database_before_sha256=SHA, database_sha256=SHA, snapshot_sha256=SHA))
    return dict(
        alias_runs=[dict(target_channel=target, ambient_alias=alias,
                         effective_core_channel=target,
                         effective_core_marker=f"BYTESTAFF_SMOKE_CORE_CHANNEL={target}",
                         observed_installed_version="9.9.9" if platform == "windows" else
                         "9.9.4" if target == "stable" else "8.8.1")
                    for target in ("stable", "test") for alias in ("testing", "beta")],
        rejection_runs=rejections,
        state_snapshots=[dict(scope=scope, item_count=3, before_sha256=SHA, after_sha256=SHA)
                         for scope in ("caller-controlled-paths", "opposite-test-state-during-stable-uninstall")],
        process_isolation=[dict(target_channel="stable", target_process="RedBeacon", target_exit_code=-15,
                                opposite_process="RedBeacon_test", opposite_process_observed_running=True)],
        transaction_checks=transactions,
        caller_environment=dict(before_sha256=SHA, after_sha256=SHA),
        execution_hijack=dict(probes=receipt.EXECUTION_HIJACK_PROBES[platform],
                              protected_before_sha256=SHA, protected_after_sha256=SHA,
                              marker_observed_count=0),
    )


def report_fixture(root, platform="macos"):
    source, artifacts = root / "source", root / "artifacts"
    source.mkdir(); (artifacts / "installers").mkdir(parents=True)
    extension = "ps1" if platform == "windows" else "sh"
    names = [spec[2] for spec in receipt._observation_specs(platform)] + [f"uninstall-core.{extension}"]
    for name in names:
        (source / name).write_text(f"fixture-only {name}\n")
        (artifacts / "installers" / name).write_bytes((source / name).read_bytes())
    entrypoints = []
    for channel, operation, name, version in receipt._observation_specs(platform):
        path = f"/projects/redbeacon/{channel}/latest.json"
        helper_path = f"/projects/redbeacon/{channel}/releases/{version}/installers/uninstall-core.{extension}"
        helper = None if operation == "install" else dict(path=f"install/uninstall-core.{extension}",
            sha256=receipt._sha256_file(source / f"uninstall-core.{extension}"), request_path=helper_path)
        entrypoints.append(dict(channel=channel, operation=operation, entrypoint_path=f"install/{name}",
            entrypoint_sha256=receipt._sha256_file(source / name),
            canonical_manifest_url=receipt.CENTRAL_ORIGIN + path, manifest_request_path=path,
            observed_request_paths=[path] + ([] if helper is None else [helper_path]),
            effective_channel=channel, effective_channel_marker=f"BYTESTAFF_SMOKE_CORE_CHANNEL={channel}",
            execution_model="single-stage-public-entrypoint" if helper is None else "public-entrypoint-with-internal-helper",
            secondary_shell_observed_count=0 if helper is None else 1,
            secondary_shells=[] if helper is None else [dict(pid=42, command=f"bash uninstall-core.{extension}")],
            internal_helper=helper))
    report = dict(schema=receipt.INSTALLER_REPORT_SCHEMA, project="redbeacon", platform=platform,
                  **COORDINATES, entrypoint_observations=entrypoints, observed_evidence=observations(platform))
    return source, artifacts, report


class EvidenceTests(unittest.TestCase):
    def verify(self, root, report, source, artifacts, platform="macos"):
        path = root / "report.json"
        path.write_text(json.dumps(report))
        return receipt.verify_installer_report(path, installer_source=source, artifact_root=artifacts,
                                               platform=platform, **COORDINATES)

    def test_complete_reports_derive_required_coverage(self):
        for platform in ("macos", "windows"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); source, artifacts, payload = report_fixture(root, platform)
                self.verify(root, payload, source, artifacts, platform)
                self.assertEqual(receipt.verified_installer_coverage(payload, platform=platform),
                                 receipt.DERIVED_INSTALLER_CASES)

    def test_unix_writer_preserves_raw_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source, artifacts, payload = report_fixture(root)
            smoke._write_installer_report(root / "written.json", **COORDINATES,
                entrypoint_observations=payload["entrypoint_observations"],
                observed_evidence=payload["observed_evidence"])
            self.assertEqual(json.loads((root / "written.json").read_text()), payload)

    def test_missing_or_tampered_observations_fail_closed(self):
        mutations = {
            "missing_observed_evidence": lambda p: p.pop("observed_evidence"),
            "empty_evidence": lambda p: p.update(observed_evidence={}),
            "missing_transaction": lambda p: p["observed_evidence"]["transaction_checks"].pop(),
            "false_failure": lambda p: p["observed_evidence"]["transaction_checks"][0].update(observed_exit_code=0),
            "changed_database": lambda p: p["observed_evidence"]["transaction_checks"][0].update(database_sha256="b"*64),
            "changed_state": lambda p: p["observed_evidence"]["state_snapshots"][0].update(after_sha256="b"*64),
            "dead_opposite_process": lambda p: p["observed_evidence"]["process_isolation"][0].update(opposite_process_observed_running=False),
            "bad_output_hash": lambda p: p["observed_evidence"]["rejection_runs"][0].update(raw_output_sha256="b"*64),
            "hidden_second_shell": lambda p: p["entrypoint_observations"][0].update(secondary_shells=[dict(pid=72, command="bash renamed.sh")]),
            "self_reported_success": lambda p: p["observed_evidence"].update(passed=True),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); source, artifacts, payload = report_fixture(root)
                mutate(payload)
                with self.assertRaises(receipt.EvidenceError):
                    self.verify(root, payload, source, artifacts)

    def test_powershell_exception_is_evidence_without_inventing_exit_code(self):
        evidence = observations("windows")
        evidence["rejection_runs"][0].update(observed_exit_code=0, observed_exception=True)
        evidence["transaction_checks"][0].update(observed_exit_code=0, observed_exception=True)
        receipt._validate_observed_installer_evidence(evidence, platform="windows")

    def test_merge_never_writes_receipt_for_a_report_missing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source, artifacts, payload = report_fixture(root)
            payload.pop("observed_evidence")
            reports = {}
            for name in ("bundle-macos", "bundle-windows", "installer-macos", "installer-windows"):
                reports[name] = root / f"{name}.json"
                reports[name].write_text(json.dumps(payload))
            output = artifacts / "receipt.json"
            with mock.patch.object(receipt, "verify_bundle_report", return_value=(b"fixture", {})):
                with self.assertRaises(receipt.EvidenceError):
                    receipt.merge_evidence(
                        artifact_root=artifacts, installer_source=source,
                        bundle_reports={p: reports[f"bundle-{p}"] for p in ("macos", "windows")},
                        installer_reports={p: reports[f"installer-{p}"] for p in ("macos", "windows")},
                        output=output, **COORDINATES,
                    )
            self.assertFalse(output.exists())
            self.assertFalse((artifacts / "metadata/raw").exists())


class ProcessObservationTests(unittest.TestCase):
    def test_arbitrary_helper_name_and_nested_shell_are_detected(self):
        rows = "10 1 /bin/bash /bin/bash install.sh\n11 10 /bin/bash /bin/bash install.sh\n12 10 python python helper.py\n13 12 /bin/sh /bin/sh renamed-stage.sh\n14 1 /bin/bash /bin/bash unrelated.sh\n"
        with mock.patch.object(smoke.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, rows)):
            self.assertEqual(smoke._shell_descendants(10), {(13, "/bin/sh renamed-stage.sh")})

    def test_ps_failure_or_empty_output_never_means_zero_shells(self):
        for result in (subprocess.CompletedProcess([], 1, ""), subprocess.CompletedProcess([], 0, ""),
                       subprocess.CompletedProcess([], 0, "malformed process output")):
            with mock.patch.object(smoke.subprocess, "run", return_value=result), self.assertRaises(RuntimeError):
                smoke._shell_descendants(10)

    def test_observer_thread_failure_is_propagated(self):
        with mock.patch.object(smoke, "_shell_descendants", side_effect=OSError("fixture ps failure")):
            with self.assertRaisesRegex(RuntimeError, "observation failed"):
                smoke._run_observed_entrypoint(["/bin/bash", "-c", "/bin/sleep 0.1"], env=dict(os.environ))

    def test_real_renamed_helper_is_observed(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "renamed-stage.sh"
            helper.write_text("/bin/sleep 0.3\n")
            entrypoint = Path(directory) / "entrypoint.sh"
            entrypoint.write_text(f'/bin/bash "{helper}"\n/bin/sleep 0.05\n')
            result, shells = smoke._run_observed_entrypoint(["/bin/bash", str(entrypoint)], env=dict(os.environ))
            self.assertEqual(result.returncode, 0)
            self.assertTrue(any("renamed-stage.sh" in child["command"] for child in shells), shells)


if __name__ == "__main__":
    unittest.main()
