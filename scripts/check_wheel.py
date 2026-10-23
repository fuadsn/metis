"""Install a wheel in isolation and exercise the CLI without provider requests."""

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="metis-wheel-") as temporary:
        root = Path(temporary)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        bin_dir = environment / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        command = bin_dir / ("metis.exe" if os.name == "nt" else "metis")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", str(wheel)], check=True
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith("METIS_")}
        env.pop("PYTHONPATH", None)
        data = root / "evidence"
        (root / ".env").write_text(
            f"METIS_SOURCES=github\nMETIS_DATA_DIR={data.as_posix()}\n"
        )

        def run(*arguments):
            result = subprocess.run(
                [str(command), *arguments],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads(result.stdout)

        sources = run("sources")
        assert [row["source"] for row in sources["sources"] if row["enabled"]] == [
            "github"
        ]
        analysis = run("analyze")
        assert analysis["selected_sources"] == ["github"]
        assert analysis["posts_processed"] == 0
        assert (data / "metis.sqlite3").is_file()
        assert run("leads")["leads"] == []
        assert run("candidates")["candidates"] == []
        assert run("evaluate")["evaluated"] == 0
        assert run("research")["research_notes"] == []
        assert len(sources["research_sources"]) == 3
    print("Installed wheel: configuration, analysis, storage, and CLI checks passed.")


if __name__ == "__main__":
    main()
