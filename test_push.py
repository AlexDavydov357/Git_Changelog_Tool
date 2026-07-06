#!/usr/bin/env python3
"""
Создаёт тестовый коммит и пушит его в оба репозитория (origin и backup),
используя текущую ветку и ветку по умолчанию (если отличается).
Если ветка не существует в remote — пропускает с предупреждением.
"""

import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

REMOTES = ("origin", "backup")
TEST_FILE = "test-commit.txt"


def is_git_repo() -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"],
                       capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"❌ Ошибка: {' '.join(cmd)}", file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result


def get_current_branch(cwd: Path) -> str:
    """Возвращает текущую ветку (например, 'main' или 'master')."""
    result = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    return result.stdout.strip()


def get_default_branch(cwd: Path, remote: str) -> str | None:
    """Возвращает ветку по умолчанию для remote (например, 'origin/HEAD' → 'main')."""
    try:
        result = run(["git", "symbolic-ref", f"{remote}/HEAD"], cwd=cwd, check=False)
        if result.returncode == 0:
            # Формат: refs/heads/main → main
            return result.stdout.strip().replace("refs/heads/", "")
    except:
        pass
    return None


def remote_branch_exists(cwd: Path, remote: str, branch: str) -> bool:
    """Проверяет, существует ли ветка branch в remote."""
    try:
        result = run(
            ["git", "ls-remote", "--heads", remote, branch],
            cwd=cwd,
            check=False
        )
        return result.returncode == 0 and branch in result.stdout
    except:
        return False


def push_test_commit():
    """Создаёт тестовый коммит и пушит его в оба репозитория."""
    cwd = Path.cwd()

    if not is_git_repo():
        print("❌ Текущая директория не является git-репозиторием.", file=sys.stderr)
        sys.exit(1)

    try:
        # Определяем ветки
        current_branch = get_current_branch(cwd)

        print(f"🔍 Текущая ветка: {current_branch}")
        # 1. Создаём файл (с датой через Python — кроссплатформенно)
        print("📝 Создание тестового коммита...")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(TEST_FILE, "a") as f:
            f.write(f"Test commit at {timestamp}\n")

        # 2. Добавляем и коммитим
        run(["git", "add", TEST_FILE], cwd=cwd)
        run(["git", "commit", "-m", "test: проверка push в оба репозитория"], cwd=cwd)

        # 3. Пушим в оба репозитория
        for remote in REMOTES:
            # Приоритет: текущая ветка > ветка по умолчанию
            print(f"🚀 Пуш в {remote}:{current_branch}...")
            run(["git", "push", remote, f"{current_branch}:{current_branch}"], cwd=cwd)

        print("✅ Тестовый коммит успешно отправлен в доступные репозитории.")
        print(f"💡 Временный файл: {TEST_FILE} (можно удалить вручную или через `revert_test_commit`)")

    except subprocess.CalledProcessError as e:
        print(f"\n⚠️  Ошибка при push: {e}", file=sys.stderr)
        # Удаляем файл, если коммит не удался
        if Path(TEST_FILE).exists():
            try:
                os.remove(TEST_FILE)
            except:
                pass
        sys.exit(1)


def revert_test_commit():
    """Откатывает последний коммит и пушит откат."""
    cwd = Path.cwd()

    if not is_git_repo():
        print("❌ Текущая директория не является git-репозиторием.", file=sys.stderr)
        sys.exit(1)

    try:
        # Проверяем: есть ли что откатывать?
        run(["git", "rev-parse", "HEAD"], cwd=cwd)

        print("↩️  Откат последнего коммита...")
        run(["git", "revert", "HEAD", "--no-edit"], cwd=cwd)

        # Пушим откат в оба репозитория
        for remote in REMOTES:
            current_branch = get_current_branch(cwd)
            print(f"📤 Пуш отката в {remote}:{current_branch}...")
            run(["git", "push", remote, f"{current_branch}:{current_branch}"], cwd=cwd)

        # Удаляем временный файл
        test_path = Path(TEST_FILE)
        if test_path.exists():
            os.remove(test_path)
            print(f"🗑️  Удалён временный файл: {TEST_FILE}")

        print("✅ Откат и пуш завершены успешно.")

    except subprocess.CalledProcessError as e:
        print(f"\n⚠️  Ошибка при откате: {e}", file=sys.stderr)
        print("💡 Возможно, последний коммит уже откачен или не существует.", file=sys.stderr)
        sys.exit(1)


# === CLI-интерфейс ===
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python test_push.py push   — создать и запушить тестовый коммит")
        print("  python test_push.py revert — откатить последний коммит и запушить откат")
        sys.exit(1)

    action = sys.argv[1].lower()
    if action == "push":
        push_test_commit()
    elif action == "revert":
        revert_test_commit()
    else:
        print(f"Неизвестное действие: {action}", file=sys.stderr)
        sys.exit(1)
