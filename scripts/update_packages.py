import subprocess
import tomllib
from datetime import datetime
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "projects.toml"
LOG_FILE    = Path(__file__).parent / "update_log.txt"
UV_EXE      = Path(r"C:\Users\yokam\.local\bin\uv.exe")


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        log(result.stdout.strip())
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())


def update_project(name: str, path: str, branch: str) -> None:
    project_dir = Path(path)

    log(f"===== {name} 開始 =====")
    run([str(UV_EXE), "lock", "--upgrade"],    cwd=project_dir)
    run([str(UV_EXE), "sync", "--all-extras"], cwd=project_dir)
    run(["git", "add", "uv.lock"],              cwd=project_dir)
    run(["git", "commit", "-m", "Pythonライブラリの定期アップデート"], cwd=project_dir)
    run(["git", "push", "origin", branch],      cwd=project_dir)
    log(f"===== {name} 完了 =====")


def main() -> None:
    with CONFIG_FILE.open("rb") as f:
        config = tomllib.load(f)

    for project in config["projects"]:
        try:
            update_project(
                name   = project["name"],
                path   = project["path"],
                branch = project.get("branch", "main"),
            )
        except Exception as e:
            log(f"[ERROR] {project['name']}: {e}")


if __name__ == "__main__":
    main()
