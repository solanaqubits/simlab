"""Build and freeze verifier-owned provenance for the separate compiled mode."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from .alcc_compiled_runner import KERNEL_BASE, PROTOCOL, file_hash

MODULES = ["Kernel", "Completeness", "Syntax", "Schema", "Unbound", "SHA256", "Bound", "Verify"]


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def validate_kernel_sources(lean: Path, manifest_path: Path):
    """Check the reviewed public content pin without needing private Git history."""
    manifest = json.loads(manifest_path.read_text())
    required = {f"Verification/AlgebraicCertificate{x}.lean" for x in MODULES} | {"lean-toolchain", "lake-manifest.json"}
    if (set(manifest) != {"schema_version", "kernel_base_commit", "sources"}
            or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or manifest["kernel_base_commit"] != KERNEL_BASE
            or set(manifest["sources"]) != required):
        raise ValueError("invalid public kernel source manifest")
    for relative, expected in manifest["sources"].items():
        if file_hash(lean / relative) != expected:
            raise ValueError(f"kernel content pin mismatch: {relative}")
    return dict(manifest["sources"])


def make_pin(lean: Path, output: Path):
    lean = lean.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    runner_root = Path(__file__).resolve().parents[1]
    cli_commit = git(lean, "log", "-1", "--format=%H", "--", "AlccVerifyMain.lean", "lakefile.toml").decode().strip()
    runner_commit = git(runner_root, "log", "-1", "--format=%H", "--", "tools/alcc_compiled_runner.py", "tools/alcc_compiled_pin.py", "tools/alcc_kernel_sources.json").decode().strip()
    sources = validate_kernel_sources(lean, runner_root / "tools/alcc_kernel_sources.json")
    for relative in ("AlccVerifyMain.lean", "lakefile.toml"):
        if (lean / relative).read_bytes() != git(lean, "show", f"{cli_commit}:{relative}"):
            raise ValueError(f"uncommitted CLI source: {relative}")
        sources[relative] = file_hash(lean / relative)
    for relative in ("tools/alcc_compiled_runner.py", "tools/alcc_compiled_pin.py", "tools/alcc_kernel_sources.json"):
        if (runner_root / relative).read_bytes() != git(runner_root, "show", f"{runner_commit}:{relative}"):
            raise ValueError(f"uncommitted runner: {relative}")
    toolchain = (lean / "lean-toolchain").read_text().strip()
    build_log = output / "build.log"
    with build_log.open("xb") as log:
        subprocess.run(["lake", "build", "--wfail", "alcc-verify"], cwd=lean,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    # An explicit binary copy, never a copy of .lake or shared Mathlib directories.
    binary = output / "alcc-verify"
    shutil.copyfile(lean / ".lake/build/bin/alcc-verify", binary)
    binary.chmod(0o500)
    oleans = {}
    for module in [f"Verification/AlgebraicCertificate{x}" for x in MODULES] + ["AlccVerifyMain"]:
        relative = f".lake/build/lib/lean/{module}.olean"
        oleans[relative] = file_hash(lean / relative)
    manifest = json.loads((lean / "lake-manifest.json").read_text())
    dependencies = {}
    for package in manifest["packages"]:
        root = lean / ".lake/packages" / package["name"]
        revision = git(root, "rev-parse", "HEAD").decode().strip()
        if revision != package["rev"] or git(root, "status", "--porcelain", "--untracked-files=no").strip():
            raise ValueError(f"dependency not at clean pinned revision: {package['name']}")
        dependencies[package["name"]] = revision
    environment = dict(kernel_base_commit=KERNEL_BASE, cli_source_commit=cli_commit,
                       kernel_source_manifest_sha256=file_hash(runner_root / "tools/alcc_kernel_sources.json"),
                       lean_toolchain=toolchain, source_sha256=sources, olean_sha256=oleans,
                       dependencies=dependencies, build_command=["lake", "build", "--wfail", "alcc-verify"],
                       build_exit_code=0, build_log_hash=file_hash(build_log), binary_sha256=file_hash(binary),
                       lean_version=subprocess.check_output(["lake", "env", "lean", "--version"], cwd=lean).decode().strip(),
                       lake_version=subprocess.check_output(["lake", "--version"], cwd=lean).decode().strip())
    env_path = output / "environment.json"
    env_path.write_text(json.dumps(environment, indent=2, sort_keys=True) + "\n")
    artifacts = {name: {"path": str(path), "sha256": file_hash(path)} for name, path in
                 {"binary": binary, "build_log": build_log, "environment": env_path,
                  "runner": runner_root / "tools/alcc_compiled_runner.py"}.items()}
    pin = dict(protocol_version=PROTOCOL, evidence_kind="compiled_execution", kernel_base_commit=KERNEL_BASE,
               cli_source_commit=cli_commit, bridge_runner_commit=runner_commit,
               lean_toolchain=toolchain, artifacts=artifacts)
    pin_path = output / "pin.json"
    pin_path.write_text(json.dumps(pin, indent=2, sort_keys=True) + "\n")
    return pin_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lean-project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(make_pin(args.lean_project, args.output))
