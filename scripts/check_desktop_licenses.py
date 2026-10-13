"""Check the audited desktop wheel versions and retained notices before freezing."""
import hashlib
from importlib.metadata import distribution
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {"pyzmq": "27.2.0", "Pillow": "12.3.0", "pyinstaller": "6.22.3"}
ZMQ_SHA256 = "1869d629bb18e0341258d04cd3ccc931a019d544d5c05980354d7cffc1fc9084"


def main() -> int:
    try:
        for name, version in VERSIONS.items():
            installed = distribution(name)
            if installed.version != version:
                raise ValueError(f"Unaudited desktop dependency: {name} {installed.version}; expected {version}")
        zmq = Path(distribution("pyzmq").locate_file("zmq/backend/cython/_zmq.cp311-win_amd64.pyd"))
        if hashlib.sha256(zmq.read_bytes()).hexdigest() != ZMQ_SHA256:
            raise ValueError("PyZMQ's bundled native libraries differ from the audited wheel.")
        pillow = distribution("Pillow")
        license_files = [entry for entry in (pillow.files or [])
                         if str(entry).endswith(".dist-info/licenses/LICENSE")]
        if len(license_files) != 1:
            raise ValueError("Cannot locate the exact Pillow wheel license.")
        if Path(pillow.locate_file(license_files[0])).read_bytes() != (ROOT / "LICENSES/pillow/LICENSE").read_bytes():
            raise ValueError("The retained Pillow license differs from the installed wheel.")
    except (OSError, ValueError, ModuleNotFoundError) as exc:
        print("ERROR: " + str(exc))
        return 1
    print("Desktop dependency versions, native PyZMQ identity and Pillow notices verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
