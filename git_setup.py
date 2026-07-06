# git_setup_frame.py
import wx
import subprocess
from pathlib import Path
from test_push import run
import os
import json

# Цвета (дублируем, если не импортировать из основного модуля)
DARK_BG = wx.Colour(30, 30, 30)
DARK_PANEL = wx.Colour(45, 45, 45)
TEXT_LIGHT = wx.Colour(212, 212, 212)
TEXT_DIM = wx.Colour(160, 160, 160)
GIT_GREEN = wx.Colour(40, 167, 69)
GIT_RED = wx.Colour(220, 53, 69)
GIT_BLUE = wx.Colour(14, 99, 156)
GITHUB_TOKEN_FILE = "github_token.txt"
class GitSetupFrame(wx.Frame):
    def __init__(self, parent):
        super().__init__(parent, title="⚙️ Настройка Git-репозитория", size=(700, 600),
                         style=wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP)

        self.parent = parent
        self.cwd = Path.cwd()
        panel = wx.Panel(self)

        # Темная тема
        if hasattr(parent, 'dark_theme') and parent.dark_theme:
            panel.SetBackgroundColour(DARK_BG)
            self.SetForegroundColour(TEXT_LIGHT)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Лог выполнения ---
        self.log_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.log_ctrl.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        if hasattr(parent, 'dark_theme') and parent.dark_theme:
            self.log_ctrl.SetBackgroundColour(wx.Colour(20, 20, 20))
            self.log_ctrl.SetForegroundColour(wx.Colour(200, 200, 200))
        main_sizer.Add(self.log_ctrl, 1, wx.EXPAND | wx.ALL, 10)

        # --- Кнопки-проверки ---
        check_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.check_branch_btn = wx.Button(panel, label="🔍 Текущая ветка")
        self.check_branch_btn.SetToolTip("Показать текущую активную ветку (git rev-parse --abbrev-ref HEAD)")
        self.check_branch_btn.Bind(wx.EVT_BUTTON, self.on_check_branch)
        check_sizer.Add(self.check_branch_btn, 0, wx.RIGHT, 5)

        self.check_remotes_btn = wx.Button(panel, label="🌐 Remote-ы")
        self.check_remotes_btn.SetToolTip("Показывает список всех удаленных рпозиториев (git remote -v)")
        self.check_remotes_btn.Bind(wx.EVT_BUTTON, self.on_check_remotes)
        check_sizer.Add(self.check_remotes_btn, 0, wx.RIGHT, 5)

        main_sizer.Add(check_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # --- Кнопки действий ---
        actions_sizer = wx.StaticBoxSizer(wx.StaticBox(panel, label="Действия:"), wx.VERTICAL)

        # 1. git init
        self.init_btn = wx.Button(panel, label="📦 git init")
        self.init_btn.Bind(wx.EVT_BUTTON, self.on_git_init)
        actions_sizer.Add(self.init_btn, 0, wx.EXPAND | wx.BOTTOM, 5)

        # 2. Переименовать master → main
        self.rename_branch_btn = wx.Button(panel, label="🔄 master → main")
        self.rename_branch_btn.Bind(wx.EVT_BUTTON, self.on_rename_branch)
        actions_sizer.Add(self.rename_branch_btn, 0, wx.EXPAND | wx.BOTTOM, 5)

        # --- Проверка URL ---
        url_check_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.url_check_combo = wx.ComboBox(panel, choices=["origin", "backup"], value="origin", style=wx.CB_READONLY)
        self.url_check_combo.SetToolTip("Выберите remote для проверки URL")
        url_check_sizer.Add(self.url_check_combo, 1, wx.EXPAND | wx.RIGHT, 5)
        self.check_url_btn = wx.Button(panel, label="🌐 Проверить URL")
        self.check_url_btn.Bind(wx.EVT_BUTTON, self.on_check_url)
        url_check_sizer.Add(self.check_url_btn, 0)
        actions_sizer.Add(url_check_sizer, 0, wx.EXPAND | wx.BOTTOM, 5)

        # --- Создание репозитория на GitHub ---
        gh_create_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.gh_token = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        self.gh_token.SetToolTip("GitHub Personal Access Token (scope: repo)")
        token = self.load_github_token()
        if token:
            self.gh_token.SetValue(token)
        gh_create_sizer.Add(wx.StaticText(panel, label="GitHub Token:"), 0, wx.ALIGN_CENTER | wx.RIGHT, 5)
        gh_create_sizer.Add(self.gh_token, 1, wx.EXPAND | wx.RIGHT, 5)
        # Кнопка сохранения токена
        self.save_token_btn = wx.Button(panel, label="💾 Сохранить токен")
        self.save_token_btn.SetToolTip("Сохранить текущий токен в файл github_token.txt")
        self.save_token_btn.Bind(wx.EVT_BUTTON, self.on_save_token)
        gh_create_sizer.Add(self.save_token_btn, 0, wx.LEFT, 5)

        self.gh_repo_name = wx.TextCtrl(panel, value="my-new-repo")
        gh_create_sizer.Add(wx.StaticText(panel, label="Repo Name:"), 0, wx.ALIGN_CENTER | wx.RIGHT, 5)
        gh_create_sizer.Add(self.gh_repo_name, 1, wx.EXPAND)

        self.create_gh_repo_btn = wx.Button(panel, label="🚀 Создать на GitHub")
        self.create_gh_repo_btn.Bind(wx.EVT_BUTTON, self.on_create_github_repo)
        gh_create_sizer.Add(self.create_gh_repo_btn, 0)
        actions_sizer.Add(gh_create_sizer, 0, wx.EXPAND | wx.BOTTOM, 5)

        # 3. Добавить origin
        origin_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.origin_url = wx.TextCtrl(panel, value="https://github.com/user/repo.git")
        origin_sizer.Add(wx.StaticText(panel, label="origin:"), 0, wx.ALIGN_CENTER | wx.RIGHT, 5)
        origin_sizer.Add(self.origin_url, 1, wx.EXPAND)
        self.add_origin_btn = wx.Button(panel, label="🔗 Добавить")
        self.add_origin_btn.Bind(wx.EVT_BUTTON, self.on_add_origin)
        origin_sizer.Add(self.add_origin_btn, 0, wx.LEFT, 5)
        actions_sizer.Add(origin_sizer, 0, wx.EXPAND | wx.BOTTOM, 5)

        # В InitUI, в check_sizer:
        self.check_branch_btn = wx.Button(panel, label="🔍 Проверить ветку")
        self.check_branch_btn.SetToolTip("Показывает состояние ветки main и её привязку к origin")
        self.check_branch_btn.Bind(wx.EVT_BUTTON, self.on_check_main_branch)
        actions_sizer.Add(self.check_branch_btn, 0, wx.EXPAND | wx.BOTTOM, 5)

        # 4. Добавить backup
        backup_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.backup_url = wx.TextCtrl(panel, value="https://backup.github.com/user/repo.git")
        backup_sizer.Add(wx.StaticText(panel, label="backup:"), 0, wx.ALIGN_CENTER | wx.RIGHT, 5)
        backup_sizer.Add(self.backup_url, 1, wx.EXPAND)
        self.add_backup_btn = wx.Button(panel, label="🔗 Добавить")
        self.add_backup_btn.Bind(wx.EVT_BUTTON, self.on_add_backup)
        backup_sizer.Add(self.add_backup_btn, 0, wx.LEFT, 5)
        actions_sizer.Add(backup_sizer, 0, wx.EXPAND | wx.BOTTOM, 5)

        # 5. Удалить remote (опционально)
        remove_remote_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.remove_remote_combo = wx.ComboBox(panel, choices=["origin", "backup"], value="origin", style=wx.CB_READONLY)
        self.remove_remote_combo.SetToolTip("Выберите remote для удаления")
        self.remove_remote_btn = wx.Button(panel, label="❌ Удалить remote")
        self.remove_remote_btn.Bind(wx.EVT_BUTTON, self.on_remove_remote)
        remove_remote_sizer.Add(self.remove_remote_combo, 1, wx.EXPAND | wx.RIGHT, 5)
        remove_remote_sizer.Add(self.remove_remote_btn, 0)
        actions_sizer.Add(remove_remote_sizer, 0, wx.EXPAND)

        main_sizer.Add(actions_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # --- Кнопки управления ---
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        clear_log_btn = wx.Button(panel, label="🗑️ Очистить лог")
        clear_log_btn.Bind(wx.EVT_BUTTON, lambda e: self.log_ctrl.Clear())
        btn_sizer.Add(clear_log_btn, 0, wx.RIGHT, 10)

        close_btn = wx.Button(panel, label="❌ Закрыть")
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        apply_all_btn = wx.Button(panel, label="✅ Применить всё")
        apply_all_btn.Bind(wx.EVT_BUTTON, self.on_apply_all)
        btn_sizer.Insert(0, apply_all_btn, 0, wx.RIGHT, 10)

        btn_sizer.Add(close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(main_sizer)
        self.Layout()
        self.Centre()

        # Автодетект текущих значений
        self.autodetect_current_state()

    def on_check_main_branch(self, event):
        try:
            # Текущая ветка
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, cwd=self.cwd
            )
            current = result.stdout.strip() if result.returncode == 0 else "неизвестно"

            # Есть ли main?
            has_main = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", "refs/heads/main"],
                capture_output=True, cwd=self.cwd
            ).returncode == 0

            # Привязка к origin/main?
            branch_info = subprocess.run(
                ["git", "branch", "-vv"],
                capture_output=True, text=True, cwd=self.cwd
            ).stdout

            self.log(f"Текущая ветка: `{current}`")
            self.log(f"Ветка `main` существует: {'✅' if has_main else '❌'}")
            if has_main:
                if "origin/main" in branch_info:
                    self.log("✅ Ветка `main` привязана к `origin/main`", is_success=True)
                else:
                    self.log("⚠️ Ветка `main` есть, но не привязана к `origin/main`", is_error=True)
            else:
                self.log("ℹ️ Ветка `main` не найдена — нужно создать", is_error=False)
        except Exception as e:
            self.log(f"Ошибка проверки: {e}", is_error=True)
    def on_apply_all(self, event):
        """Выполняет все действия по порядку"""
        self.log("🚀 Запуск полной настройки репозитория...")

        # 1. git init
        try:
            self.log("📦 Выполняется `git init`...")
            run(["git", "init"], cwd=self.cwd)
            self.log("✅ `git init` завершён", is_success=True)
        except Exception as e:
            self.log(f"❌ Ошибка `git init`: {e}", is_error=True)
            return

        # 2. Переименовать master → main
        try:
            self.log("🔄 Переименование ветки `master` → `main`...")
            result = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", "refs/heads/master"],
                capture_output=True, cwd=self.cwd
            )
            if result.returncode == 0:
                run(["git", "branch", "-m", "master", "main"], cwd=self.cwd)
                self.log("✅ Ветка переименована", is_success=True)
            else:
                self.log("ℹ️ Ветка `master` не найдена (возможно, уже `main`)", is_success=True)
        except Exception as e:
            self.log(f"❌ Ошибка переименования: {e}", is_error=True)

        # 3. Добавить origin
        origin_url = self.origin_url.GetValue().strip()
        if origin_url:
            try:
                self.log(f"🔗 Добавление remote `origin`: {origin_url}")
                run(["git", "remote", "add", "origin", origin_url], cwd=self.cwd)
                self.log("✅ `origin` добавлен", is_success=True)
            except Exception as e:
                self.log(f"❌ Ошибка добавления `origin`: {e}", is_error=True)
        else:
            self.log("ℹ️ Пропущено добавление `origin` (не указан URL)", is_success=True)

        try:
            self.log("🔍 Проверка наличия удалённой ветки `origin/main`...")
            result = subprocess.run(
                ["git", "ls-remote", "--heads", "origin", "main"],
                capture_output=True, text=True, cwd=self.cwd
            )
            if result.returncode == 0 and "refs/heads/main" in result.stdout:
                self.log("⚠️ Удалённая ветка `origin/main` существует — удаляем её...")
                run(["git", "push", "origin", "--delete", "main"], cwd=self.cwd)
                self.log("✅ Удалённая ветка `origin/main` удалена", is_success=True)
            else:
                self.log("ℹ️ Удалённой ветки `origin/main` нет — можно создавать новую", is_success=True)
        except Exception as e:
            self.log(f"⚠️ Ошибка проверки/удаления удалённой ветки: {e}", is_error=True)

        # 3.5. Создать локальную ветку main и сделать первый коммит (если нужно)
        try:
            # Проверяем: есть ли ветка main?
            result = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", "refs/heads/main"],
                capture_output=True, cwd=self.cwd
            )
            if result.returncode != 0:
                # Ветки main нет — создаём её из HEAD (но HEAD может быть несуществующим)
                # Сначала проверим: есть ли хотя бы один коммит?
                commit_check = subprocess.run(
                    ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=self.cwd
                )
                if commit_check.returncode != 0:
                    # Нет коммитов — создаём "пустой" коммит
                    self.log("ℹ️ Нет коммитов — создаю первый коммит (README)...")
                    readme_path = self.cwd / "README.md"
                    readme_path.write_text("# Новый репозиторий\n\nСоздан через Git Changelog Tool.\n",
                                           encoding="utf-8")
                    run(["git", "add", "README.md"], cwd=self.cwd)
                    run(["git", "commit", "-m", "chore: initial commit"], cwd=self.cwd)
                    self.log("✅ Первый коммит создан", is_success=True)

                # Теперь создаём ветку main (если ещё не существует)
                run(["git", "checkout", "-b", "main"], cwd=self.cwd)
                self.log("✅ Ветка `main` создана", is_success=True)
            else:
                self.log("ℹ️ Ветка `main` уже существует", is_success=True)

            # Привязываем локальную main к удалённой (если origin уже добавлен)
            if origin_url:
                self.log(f"🔗 Привязка `main` к `origin/main`...")
                run(["git", "push", "-u", "origin", "main"], cwd=self.cwd)
                self.log("✅ Ветка `main` привязана к `origin/main`", is_success=True)

        except Exception as e:
            self.log(f"❌ Ошибка подготовки ветки `main`: {e}", is_error=True)

        # 4. Добавить backup
        backup_url = self.backup_url.GetValue().strip()
        if backup_url:
            try:
                self.log(f"🔗 Добавление remote `backup`: {backup_url}")
                run(["git", "remote", "add", "backup", backup_url], cwd=self.cwd)
                self.log("✅ `backup` добавлен", is_success=True)
            except Exception as e:
                self.log(f"❌ Ошибка добавления `backup`: {e}", is_error=True)
        else:
            self.log("ℹ️ Пропущено добавление `backup` (не указан URL)", is_success=True)

        self.log("🎉 Полная настройка завершена!", is_success=True)

    def on_create_github_repo(self, event):
        """Создаёт репозиторий на GitHub через API"""
        token = self.gh_token.GetValue().strip()
        repo_name = self.gh_repo_name.GetValue().strip()

        if not token:
            self.log("❌ GitHub token не указан", is_error=True)
            return
        if not repo_name:
            self.log("❌ Имя репозитория не указано", is_error=True)
            return

        import urllib.request
        import json

        url = "https://api.github.com/user/repos"
        data = json.dumps({"name": repo_name, "private": False}).encode("utf-8")

        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"token {token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
                repo_url = result.get("html_url", "неизвестно")
                self.log(f"✅ Репозиторий создан: {repo_url}", is_success=True)

                # Автоматически добавляем origin
                self.origin_url.SetValue(repo_url.replace("https://github.com/", "https://github.com/"))
                self.log(f"🔗 URL добавлен в поле `origin`", is_success=True)

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            self.log(f"❌ GitHub API ошибка {e.code}: {error_body}", is_error=True)
        except Exception as e:
            self.log(f"❌ Ошибка создания репозитория: {e}", is_error=True)

    def on_check_url(self, event):
        """Проверяет доступность URL через git ls-remote"""
        remote = self.url_check_combo.GetValue()
        try:
            # Получаем URL remote-а
            result = subprocess.run(
                ["git", "remote", "get-url", remote],
                capture_output=True, text=True, cwd=self.cwd
            )
            if result.returncode != 0:
                self.log(f"Remote `{remote}` не найден", is_error=True)
                return

            url = result.stdout.strip()
            self.log(f"Проверка URL remote `{remote}`: {url}")

            # Выполняем git ls-remote
            proc = subprocess.Popen(
                ["git", "ls-remote", "--exit-code", url],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.cwd
            )
            # Ждём с таймаутом (например, 10 сек)
            try:
                stdout, stderr = proc.communicate(timeout=10)
                if proc.returncode == 0:
                    self.log(f"✅ URL `{url}` доступен и содержит данные", is_success=True)
                else:
                    self.log(f"❌ URL `{url}` недоступен: {stderr.strip()}", is_error=True)
            except subprocess.TimeoutExpired:
                proc.kill()
                self.log(f"⏳ Таймаут при проверке URL `{url}`", is_error=True)

        except Exception as e:
            self.log(f"Ошибка проверки URL: {e}", is_error=True)

    def log(self, msg, is_error=False, is_success=False):
        """Добавляет сообщение в лог с цветом и эмодзи"""
        if is_error:
            color = GIT_RED
            prefix = "❌ "
        elif is_success:
            color = GIT_GREEN
            prefix = "✅ "
        else:
            color = GIT_BLUE
            prefix = "ℹ️ "

        self.log_ctrl.SetDefaultStyle(wx.TextAttr(color))
        self.log_ctrl.AppendText(f"{prefix}{msg}\n")
        # self.log_ctrl.SetDefaultStyle(wx.TextAttr(wx.Colour(212, 212, 212)))

    def load_github_token(self) -> str:
        """Загружает токен из файла, если он существует"""
        if os.path.exists(GITHUB_TOKEN_FILE):
            try:
                with open(GITHUB_TOKEN_FILE, "r", encoding="utf-8") as f:
                    token = f.read().strip()
                    if token:
                        return token
            except Exception as e:
                self.log(f"⚠️ Ошибка чтения токена из {GITHUB_TOKEN_FILE}: {e}", is_error=True)
        return ""

    def on_save_token(self, event):
        token = self.gh_token.GetValue().strip()
        if not token:
            wx.MessageBox("Поле токена пустое", "Ошибка", wx.OK | wx.ICON_WARNING)
            return
        self.save_github_token(token)

    def save_github_token(self, token: str):
        """Сохраняет токен в файл"""
        try:
            with open(GITHUB_TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(token.strip())
            self.log(f"✅ Токен сохранён в {GITHUB_TOKEN_FILE}", is_success=True)
        except Exception as e:
            self.log(f"❌ Ошибка сохранения токена: {e}", is_error=True)

    def autodetect_current_state(self):
        """Автоматически определяет текущую ветку и remote-ы"""
        try:
            # Текущая ветка
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, cwd=self.cwd
            )
            if result.returncode == 0 and result.stdout.strip():
                branch = result.stdout.strip()
                self.log(f"Текущая ветка: `{branch}`", is_success=True)
            else:
                self.log("Ветка ещё не создана (нужен первый коммит)", is_error=False)

            # Remote-ы
            result = subprocess.run(["git", "remote"], capture_output=True, text=True, cwd=self.cwd)
            if result.returncode == 0:
                remotes = result.stdout.strip().split()
                if remotes:
                    self.log(f"Найденные remote-ы: {', '.join(remotes)}", is_success=True)
                    for r in remotes:
                        if r not in self.remove_remote_combo.GetItems():
                            self.remove_remote_combo.Append(r)
                else:
                    self.log("Нет ни одного remote-а (добавьте через кнопки)", is_error=False)
            else:
                self.log("Ошибка при получении remote-ов", is_error=True)
        except Exception as e:
            self.log(f"Ошибка автодетекта: {e}", is_error=True)

    def autodetect_current_state_old(self):
        """Автоматически определяет текущую ветку и remote-ы"""
        try:
            # Текущая ветка
            result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                    capture_output=True, text=True, cwd=self.cwd)
            if result.returncode == 0:
                current_branch = result.stdout.strip()
                self.log(f"Текущая ветка: `{current_branch}`", is_success=True)

            # Remote-ы
            result = subprocess.run(["git", "remote"], capture_output=True, text=True, cwd=self.cwd)
            if result.returncode == 0:
                remotes = result.stdout.strip().split()
                if remotes:
                    self.log(f"Найденные remote-ы: {', '.join(remotes)}", is_success=True)
                    # Заполняем комбобокс
                    for r in remotes:
                        if r not in self.remove_remote_combo.GetItems():
                            self.remove_remote_combo.Append(r)
                else:
                    self.log("Нет ни одного remote-а", is_error=True)
        except Exception as e:
            self.log(f"Ошибка автодетекта: {e}", is_error=True)

    # --- Обработчики ---

    def on_check_branch(self, event):
        """Показывает текущую ветку"""
        try:
            result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                    capture_output=True, text=True, cwd=self.cwd)
            if result.returncode == 0:
                branch = result.stdout.strip()
                self.log(f"Текущая ветка: `{branch}`", is_success=True)
            else:
                self.log("Не удалось определить ветку", is_error=True)
        except Exception as e:
            self.log(f"Ошибка: {e}", is_error=True)

    def on_check_remotes(self, event):
        """Показывает список удаленный репозиториев"""
        try:
            result = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True, cwd=self.cwd)
            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    self.log("Remote-ы:")
                    for line in output.split("\n"):
                        self.log(f"  {line}", is_success=True)
                else:
                    self.log("Нет ни одного remote-а (добавьте через кнопки)", is_error=False)
            else:
                self.log("Ошибка при получении remote-ов", is_error=True)
        except Exception as e:
            self.log(f"Ошибка: {e}", is_error=True)

    def on_check_remotes_old(self, event):
        """Показывает список remote-ов"""
        try:
            result = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True, cwd=self.cwd)
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if lines:
                    self.log("Remote-ы:")
                    for line in lines:
                        self.log(f"  {line}", is_success=True)
                else:
                    self.log("Нет ни одного remote-а", is_error=True)
            else:
                self.log("Ошибка при получении remote-ов", is_error=True)
        except Exception as e:
            self.log(f"Ошибка: {e}", is_error=True)

    def on_git_init(self, event):
        """Выполняет git init"""
        try:
            self.log("Выполняется `git init`...")
            run(["git", "init"], cwd=self.cwd)
            self.log("Репозиторий инициализирован", is_success=True)
            self.autodetect_current_state()
        except Exception as e:
            self.log(f"Ошибка: {e}", is_error=True)

    def on_rename_branch(self, event):
        """Переименовывает master → main"""
        try:
            # Проверяем, существует ли master
            result = subprocess.run(["git", "show-ref", "--verify", "--quiet", "refs/heads/master"],
                                    capture_output=True, cwd=self.cwd)
            if result.returncode == 0:
                self.log("Переименование `master` → `main`...")
                run(["git", "branch", "-m", "master", "main"], cwd=self.cwd)
                self.log("Ветка переименована", is_success=True)
            else:
                self.log("Ветка `master` не найдена (возможно, уже `main`)", is_success=True)
        except Exception as e:
            self.log(f"Ошибка: {e}", is_error=True)

    def on_add_origin(self, event):
        """Добавляет remote origin и привязывает main"""
        url = self.origin_url.GetValue().strip()
        if not url:
            wx.MessageBox("Введите URL для origin", "Ошибка", wx.OK | wx.ICON_WARNING)
            return

        try:
            # Проверяем, существует ли уже origin
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, cwd=self.cwd
            )
            if result.returncode == 0:
                existing = result.stdout.strip()
                if existing == url:
                    self.log(f"Remote `origin` уже существует с этим URL", is_success=True)
                    # Привязываем main, даже если origin уже есть
                    self.binding_origin_to_main()
                    self.autodetect_current_state()
                    return
                else:
                    self.log(f"Remote `origin` уже существует, но с другим URL: {existing}", is_error=True)
                    return

            self.log(f"Добавление remote `origin`: {url}")
            run(["git", "remote", "add", "origin", url], cwd=self.cwd)
            self.log("Remote `origin` добавлен", is_success=True)

            # Привязываем main
            self.binding_origin_to_main()

            self.autodetect_current_state()
        except Exception as e:
            self.log(f"Ошибка: {e}", is_error=True)

    def binding_origin_to_main(self):
        """Создаёт локальную ветку main (если нет) и принудительно пушит её на origin/main"""
        try:
            # 1. Создаём локальную ветку main (если её нет)
            self.log("🔍 Проверка наличия локальной ветки `main`...")
            result = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", "refs/heads/main"],
                capture_output=True, cwd=self.cwd
            )
            if result.returncode != 0:
                self.log("ℹ️ Ветка `main` не найдена — проверяем наличие коммитов...")
                commit_check = subprocess.run(
                    ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=self.cwd
                )
                if commit_check.returncode != 0:
                    # Нет коммитов — создаём README и первый коммит
                    self.log("ℹ️ Нет коммитов — создаю README.md и первый коммит...")
                    readme_path = self.cwd / "README.md"
                    readme_path.write_text("# Новый репозиторий\n\nСоздан через Git Changelog Tool.\n",
                                           encoding="utf-8")
                    run(["git", "add", " ."], cwd=self.cwd) # README.md
                    run(["git", "commit", "-m", "chore: initial commit"], cwd=self.cwd)
                    self.log("✅ Первый коммит создан", is_success=True)

                # Теперь создаём ветку main
                run(["git", "checkout", "-b", "main"], cwd=self.cwd)
                self.log("✅ Ветка `main` создана", is_success=True)
            else:
                self.log("ℹ️ Ветка `main` уже существует", is_success=True)

            # 2. Принудительно пушим локальную main на удалённую (перезаписывает origin/main)
            self.log("🔄 Принудительная перезапись `origin/main` локальной веткой `main`...")
            run(["git", "push", "-f", "origin", "main"], cwd=self.cwd)
            self.log("✅ `origin/main` перезаписан локальной веткой `main`", is_success=True)

        except Exception as e:
            self.log(f"❌ Ошибка привязки ветки: {e}", is_error=True)

    def on_add_backup(self, event):
        """Добавляет remote backup"""
        url = self.backup_url.GetValue().strip()
        if not url:
            wx.MessageBox("Введите URL для backup", "Ошибка", wx.OK | wx.ICON_WARNING)
            return

        try:
            self.log(f"Добавление remote `backup`: {url}")
            run(["git", "remote", "add", "backup", url], cwd=self.cwd)
            self.log("Remote `backup` добавлен", is_success=True)
            self.autodetect_current_state()
        except Exception as e:
            self.log(f"Ошибка: {e}", is_error=True)

    def on_remove_remote(self, event):
        """Удаляет выбранный remote"""
        remote = self.remove_remote_combo.GetValue()
        try:
            self.log(f"Удаление remote `{remote}`...")
            run(["git", "remote", "remove", remote], cwd=self.cwd)
            self.log(f"Remote `{remote}` удалён", is_success=True)
            self.autodetect_current_state()
        except Exception as e:
            self.log(f"Ошибка: {e}", is_error=True)

if __name__ == "__main__":
    app = wx.App(False)
    frame = GitSetupFrame(None)
    app.MainLoop()
