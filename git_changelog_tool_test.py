# git_changelog_tool.py
import wx
import wx.lib.mixins.listctrl as listmix
import wx.adv
import os
import subprocess
import datetime
import re
import sys
from pathlib import Path
from test_push import is_git_repo, get_current_branch, TEST_FILE, REMOTES, run

CHANGES_FILE = "CHANGES.md"
# --- Цвета темной темы (Git Bash / VS Code Dark style) ---
DARK_BG = wx.Colour(30, 30, 30)        # #1e1e1e — фон окна/панели
DARK_PANEL = wx.Colour(45, 45, 45)     # #2d2d2d — фон полей ввода, списков
TEXT_LIGHT = wx.Colour(212, 212, 212)  # #d4d4d4 — основной текст
TEXT_DIM = wx.Colour(160, 160, 160)    # #a0a0a0 — второстепенный текст
GIT_BLUE = wx.Colour(14, 99, 156)      # #0e639c — кнопки (Git-style)
GIT_GREEN = wx.Colour(40, 167, 69)     # #28a745 — Commit/Push
GIT_RED = wx.Colour(220, 53, 69)       # #dc3545 — Delete
LIST_HIGHLIGHT = wx.Colour(0, 120, 212) # #0078d6 — выделение в списке

import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

# --- Класс данных: один комментарий ---
@dataclass
class CommitItem:
    """ Класс для хнанения строки коммита и флага закоммиченности """
    text: str
    committed: bool = False  # False = не закоммичен, True = уже в коммите

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(text=d["text"], committed=d.get("committed", False))


# --- Контейнер: дата → список комментариев ---
class CommitsByDate:
    def __init__(self):
        self.data: Dict[str, List[CommitItem]] = {}

    def add(self, date_str: str, text: str):
        """ Добавляет комментарий на указанную дату """
        if date_str not in self.data:
            self.data[date_str] = []
        self.data[date_str].append(CommitItem(text=text, committed=False))

    def remove(self, date_str: str, index: int):
        """ Удаляет комментарий по дате и индексу """
        if date_str in self.data and 0 <= index < len(self.data[date_str]):
            del self.data[date_str][index]
            if not self.data[date_str]:
                del self.data[date_str]

    def update(self, date_str: str, index: int, new_text: str):
        """ Редактирует комментарий по дате и индексу """
        if date_str in self.data and 0 <= index < len(self.data[date_str]):
            self.data[date_str][index].text = new_text

    def toggle_committed(self, date_str: str, index: int):
        """ Переключает флаг закоммиченности """
        if date_str in self.data and 0 <= index < len(self.data[date_str]):
            self.data[date_str][index].committed = not self.data[date_str][index].committed

    def get_items(self, date_str: str) -> List[CommitItem]:
        """ Возвращает список комментариев на указанную дату """
        return self.data.get(date_str, [])

    def get_all_dates(self) -> List[str]:
        """ Возвращает список всех дат в порядке возрастания для которых есть комментарии """
        return sorted(self.data.keys(), reverse=False)


class EditableChangelogList(wx.ListCtrl,
                            listmix.ListCtrlAutoWidthMixin,
                            listmix.TextEditMixin):
    def __init__(self, parent, top_parent):
        style = wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES | wx.LC_VRULES
        wx.ListCtrl.__init__(self, parent, style=style)
        listmix.ListCtrlAutoWidthMixin.__init__(self)
        listmix.TextEditMixin.__init__(self)
        self.parent = top_parent
        if DARK_THEM:
            self.SetBackgroundColour(DARK_PANEL)
            self.SetForegroundColour(TEXT_LIGHT)
            self.SetFont(self.parent.mono_font)

        # Колонки
        self.InsertColumn(0, "Дата", width=70)
        self.InsertColumn(1, "Изменение", width=450)

        # Заполняем
        self.RefreshItems()

        # Обработчики
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_item_deselected)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.on_end_label_edit)
        self.Bind(wx.EVT_LIST_DELETE_ITEM, self.on_delete_item)

        self.Bind(wx.EVT_KEY_DOWN, self.on_key_down)

    def on_key_down(self, event):
        """ Удаляет выбранный элемент по нажатию кнопки Delete или Backspace """
        key = event.GetKeyCode()
        if key in (wx.WXK_DELETE, wx.WXK_BACK):
            idx = self.GetFirstSelected()
            # Получаем текущую дату из DatePicker
            date_obj = self.parent.wxdate_to_pydate(self.parent.date_picker.GetValue())
            date_str = date_obj.strftime("%d/%m/%y")

            print(f'on_key_down idx={idx}, date={date_str}')

            # Проверка границ
            if idx < 0 or date_str not in self.parent.changes or idx >= len(self.parent.changes[date_str]):
                print(f"[WARN] on_key_down: idx={idx} out of range for date {date_str}")
                event.Veto()
                return

            if idx >= 0:
                del self.parent.changes[date_str][idx]
                self.RefreshItems()
            self.parent.save_changes()
        else:
            event.Skip()

    def RefreshItems(self):
        """Перерисовывает список из self.changes"""
        # Получаем текущую дату из DatePicker
        date_obj = self.parent.wxdate_to_pydate(self.parent.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")
        self.DeleteAllItems()
        for i, change in enumerate(self.parent.changes.get(date_str, [])):
            idx = self.InsertItem(self.GetItemCount(), date_str)
            self.SetItem(idx, 1, change)
            if DARK_THEM:
                # Цвета строк
                self.SetItemBackgroundColour(idx, DARK_PANEL)
                self.SetItemTextColour(idx, TEXT_LIGHT)
                # Выделение — по умолчанию
                if i == 0 and self.GetItemCount() == 1:
                    self.Select(idx)
                    self.Focus(idx)

    def RefreshItems_old(self):
        """Перерисовывает список из self.changes"""
        self.DeleteAllItems()
        for date_str, change in self.parent.changes:
            idx = self.InsertItem(self.GetItemCount(), date_str)
            self.SetItem(idx, 1, change)

    def GetItemData(self, idx):
        """Возвращает (date_str, change) по индексу в списке"""
        return self.parent.changes[idx]

    def SetItemData(self, idx, date_str, change):
        print(f"SetItemData idx={idx}, date_str={date_str}, change={change}")
        """Обновляет данные в списке и UI"""
        self.parent.changes[idx] = (date_str, change)
        self.SetItem(idx, 0, date_str)
        self.SetItem(idx, 1, change)

    def on_end_label_edit(self, event):
        idx = event.GetIndex()
        col = event.GetColumn()
        new_value = event.GetLabel()

        # Получаем текущую дату из DatePicker
        date_obj = self.parent.wxdate_to_pydate(self.parent.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")

        print(f'on_end_label_edit idx={idx}, col={col}, new_value="{new_value}", date={date_str}')

        # Проверка границ
        if idx < 0 or date_str not in self.parent.changes or idx >= len(self.parent.changes[date_str]):
            print(f"[WARN] on_end_label_edit: idx={idx} out of range for date {date_str}")
            event.Veto()
            return

        if col == 1:  # редактируем колонку "Изменение"
            self.parent.changes[date_str][idx] = new_value
            print(f"[OK] Обновлено: date={date_str}, idx={idx}, change='{new_value}'")
        self.parent.save_changes()
        event.Skip()


    def on_end_label_edit_old(self, event):
        """Вызывается после редактирования (в том числе при F2/Enter)"""

        idx = event.GetIndex()
        col = event.GetColumn()
        new_value = event.GetLabel()

        print(f'on_end_label_edit idx={idx}, col={col}, new_value="{new_value}"')
        print(f"Было self.changes={self.parent.changes[idx]}")

        # ✅ ОБНОВЛЯЕМ ГЛОБАЛЬНЫЙ СПИСОК
        if col == 1:  # редактируем колонку "Изменение"
            old_date, _ = self.parent.changes[idx]
            self.parent.changes[idx] = (old_date, new_value)
            print(f"[OK] Обновлено в self.changes: idx={idx}, change='{new_value}'")
        # Если нужно редактировать и дату — добавьте col == 0

        # ✅ ВАЖНО: не вызываем event.Veto() — пусть wx.ListCtrl обновит UI сам
        # (TextEditMixin уже сделал это, но мы не мешаем)
        event.Skip()

    # --- Обработчики для редактирования ---
    def on_end_label_edit_old(self, event):
        """Вызывается после редактирования (в том числе при F2/Enter)"""

        idx = event.GetIndex()
        col = event.GetColumn()
        new_value = event.GetLabel()
        print(f'on_end_label_edit idx={idx}, col={col}, new_value={new_value}')

        # if col == 1:  # редактирование колонки "Изменение"
        #     old_date, _ = self.changes[idx]
        #     self.SetItemData(idx, old_date, new_value)
        #     event.Veto()  # не вызываем event.Skip(), чтобы не перерисовывать лишнее
        # else:
        #     event.Skip()  # для колонки даты — можно оставить как есть (но лучше запретить)

    def on_delete_item(self, event):
        print('on_delete_item')
        """Удаление по Delete/Backspace"""
        date_obj = self.parent.wxdate_to_pydate(self.parent.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")
        idx = event.GetIndex()
        if idx >= 0:
            del self.parent.changes[date_str][idx]
            self.RefreshItems()
        event.Skip()

    def on_item_activated(self, event):
        """Двойной клик → редактирование"""
        print('on_item_activated')
        idx = event.GetIndex()
        if idx >= 0:
            self.EditLabel(idx, 1)  # редактируем колонку 1 (Изменение)

    def on_item_deselected(self, event):
        # Можно очистить фокус — не обязательно
        pass

DARK_THEM = False
class ChangelogFrame(wx.Frame):
    def __init__(self, parent, title):
        super().__init__(parent, title=title, size=(700, 600))
        self.mono_font = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        # Устанавливаем темную тему для окна
        if DARK_THEM:
            self.SetBackgroundColour(DARK_BG)
            self.SetForegroundColour(TEXT_LIGHT)

        self.changes = {}  # list of (date_str, change_line)

        self.InitUI()
        self.Centre()
        self.Show()
        self.load_changes()
        # Устанавливаем заголовок с цветным эмодзи
        # Проверка Git-репозитория
        git_available = self.is_git_repo()

        # Установка иконки
        if git_available:
            icon = wx.ArtProvider.GetIcon(wx.ART_TICK_MARK, wx.ART_FRAME_ICON, (16, 16))
            self.SetTitle(f"Git Changelog Tool [Git OK]")
        else:
            icon = wx.ArtProvider.GetIcon(wx.ART_WARNING, wx.ART_FRAME_ICON, (16, 16))
            self.SetTitle(f"Git Changelog Tool [No Git available]")
        self.SetIcon(icon)
        self.on_date_changed(None)

    def InitUI(self):
        panel = wx.Panel(self)
        # темная тема
        if DARK_THEM:
            panel.SetBackgroundColour(DARK_BG)
            panel.SetForegroundColour(TEXT_LIGHT)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Header: date + add button ---
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        header_sizer.Add((1,1), 1, wx.EXPAND)
        prev_date_btn = wx.Button(panel, label="◀ назад")
        prev_date_btn.Bind(wx.EVT_BUTTON, self.on_prev_date)
        header_sizer.Add(prev_date_btn, 0, flag=wx.EXPAND|wx.TOP|wx.RIGHT, border=5)

        self.date_picker = wx.adv.DatePickerCtrl(
            panel, style=wx.adv.DP_DROPDOWN | wx.adv.DP_SHOWCENTURY | wx.adv.DP_ALLOWNONE)

        # Устанавливаем сегодняшнюю дату
        self.date_picker.SetValue(datetime.date.today())
        self.date_picker.SetFont(wx.Font(wx.FontInfo(12)))
        self.date_picker.Bind(wx.adv.EVT_DATE_CHANGED, self.on_date_changed)

        bbin26 = wx.StaticBox(panel, label='Дата:')
        if DARK_THEM:
            bbin26.SetBackgroundColour(DARK_PANEL)
            bbin26.SetForegroundColour(TEXT_LIGHT)
        data_sz = wx.StaticBoxSizer(bbin26, wx.HORIZONTAL)
        data_sz.Add(self.date_picker, 0, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=5)
        header_sizer.Add(data_sz, 0, wx.EXPAND)
        next_date_btn = wx.Button(panel, label="вперёд ▶")
        next_date_btn.Bind(wx.EVT_BUTTON, self.on_next_date)
        header_sizer.Add(next_date_btn, 0, flag=wx.EXPAND|wx.LEFT|wx.TOP, border=5)
        header_sizer.Add((1, 1), 1, wx.EXPAND)

        main_sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # --- Changes list (редактируемый) ---
        self.list_ctrl = EditableChangelogList(panel, self)

        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)


        # --- Input area ---
        input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.input_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.input_ctrl.SetToolTip("Введите описание изменения и нажмите Enter или кнопку «Добавить»")
        self.input_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_add_change)
        input_sizer.Add(self.input_ctrl, 1, wx.RIGHT, 5)

        add_btn = wx.Button(panel, label="📝 Добавить")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add_change)
        input_sizer.Add(add_btn, 0)

        del_btn = wx.Button(panel, label="🗑️ Удалить")
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete_change)
        input_sizer.Add(del_btn, 0)

        main_sizer.Add(input_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)


        # --- Git sizer ---
        git_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.test_push_btn = wx.Button(panel, label="🚀 Test", name="test")
        self.test_push_btn.SetToolTip("Cоздаёт и пушит тестовый коммит. Берет настройки веток из .git/config")
        self.test_push_btn.Bind(wx.EVT_BUTTON, self.test_push)
        git_sizer.Add(self.test_push_btn, flag=wx.RIGHT, border=10)

        self.rev_push_btn = wx.Button(panel, label="↩️ Revert", name="revert")
        self.rev_push_btn.SetToolTip("Откатывает последний коммит и пушит откат")
        self.rev_push_btn.Bind(wx.EVT_BUTTON, self.revert_test)
        git_sizer.Add(self.rev_push_btn, 0)
        git_sizer.Add((1,1), 1, wx.EXPAND)

        self.commit_btn = wx.Button(panel, label="💾 Commit")
        self.commit_btn.Bind(wx.EVT_BUTTON, self.on_commit)
        git_sizer.Add(self.commit_btn, 0, wx.RIGHT, 10)



        self.push_origin_btn = wx.Button(panel, label="⬆️ Push Origin", name="origin")
        self.push_origin_btn.SetToolTip("Пушит в origin")
        self.push_origin_btn.Bind(wx.EVT_BUTTON, self.on_push)
        git_sizer.Add(self.push_origin_btn, 0)

        self.push_backup_btn = wx.Button(panel, label="⬆️ Push BackUP", name="backup")
        self.push_backup_btn.SetToolTip("Пушит в backup")
        self.push_backup_btn.Bind(wx.EVT_BUTTON, self.on_push)
        git_sizer.Add(self.push_backup_btn, 0)

        self.push_btn = wx.Button(panel, label="🔄 Push All", name="all")
        self.push_btn.SetToolTip("Пушит в origin и backup")
        self.push_btn.Bind(wx.EVT_BUTTON, self.on_push)
        git_sizer.Add(self.push_btn, 0)



        main_sizer.Add(git_sizer, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(main_sizer)

        # Status bar
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetStatusText("Готов к работе")
        self.widget_list = [self.test_push_btn, self.rev_push_btn, self.commit_btn, self.push_origin_btn,
                         self.push_backup_btn, self.push_btn, prev_date_btn, next_date_btn, self.input_ctrl,
                            self.date_picker, self.status_bar]

        if DARK_THEM:
            [self.style_widget(widget) for widget in self.widget_list]

        panel.Refresh()

    # Общая функция для стилизации кнопок
    def style_widget(self, btn):
        btn.SetBackgroundColour(GIT_BLUE)
        btn.SetForegroundColour(wx.WHITE)
        btn.SetFont(self.mono_font)
    def push_test_commit(self):
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
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    def revert_test_commit(self):
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

    def test_push(self, e):
        """ Запускает скрипт для тестового пуша в две ветки origin и backup """
        print(f'test_push {e.GetEventObject().GetName()}')
        self.push_test_commit()

    def revert_test(self, e):
        """ Запускает скрипт для отката тестового коммита и пуша"""
        print(f'revert_test {e.GetEventObject().GetName()}')
        self.revert_test_commit()

    def wxdate_to_pydate(self, date):
        """Конвертирует wx.DateTime в datetime.date"""
        if not date.IsValid():
            return datetime.date.today()
        return datetime.date(date.GetYear(), date.GetMonth() + 1, date.GetDay())

    def filter_by_date(self, date_str):
        """Фильтрует записи по дате и обновляет UI"""
        self.list_ctrl.DeleteAllItems()
        changes_for_date = self.changes.get(date_str, [])
        for i, change in enumerate(changes_for_date):
            idx = self.list_ctrl.InsertItem(i, date_str)
            self.list_ctrl.SetItem(idx, 1, change)
        if self.list_ctrl.GetItemCount() > 0:
            self.list_ctrl.Select(0)
            self.list_ctrl.Focus(0)


    def filter_by_date_old(self, date_str):
        """Фильтрует записи по дате и обновляет UI"""
        self.list_ctrl.DeleteAllItems()
        for d, change in self.changes:
            if d == date_str:
                idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), d)
                self.list_ctrl.SetItem(idx, 1, change)
        if self.list_ctrl.GetItemCount() > 0:
            self.list_ctrl.Select(0)
            self.list_ctrl.Focus(0)

    def on_prev_date(self, event):
        today = self.wxdate_to_pydate(self.date_picker.GetValue())
        new_date = today - datetime.timedelta(days=1)
        self.date_picker.SetValue(wx.DateTime.FromDMY(new_date.day, new_date.month - 1, new_date.year))
        self.on_date_changed(None)

    def on_next_date(self, event):
        today = self.wxdate_to_pydate(self.date_picker.GetValue())
        new_date = today + datetime.timedelta(days=1)
        self.date_picker.SetValue(wx.DateTime.FromDMY(new_date.day, new_date.month - 1, new_date.year))
        self.on_date_changed(None)

    def on_date_changed(self, event):
        """Обновляет список при изменении даты"""
        date_obj = self.wxdate_to_pydate(self.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")  # → "25/06/24"
        self.filter_by_date(date_str)

    def load_changes(self):
        self.changes = {}  # ← словарь
        if not os.path.exists(CHANGES_FILE):
            print(f"ℹ️ Файл {CHANGES_FILE} не найден — начнём с пустого списка.")
            return

        try:
            with open(CHANGES_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            wx.MessageBox(f"Ошибка чтения {CHANGES_FILE}:\n{e}", "Ошибка", wx.OK | wx.ICON_ERROR)
            return

        current_date = None
        raw_entries = {}  # {date_str: [changes]}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.match(r"^#\s*(\d{2}/\d{2}(?:/\d{2})?)\s*$", line)
            if match:
                raw_date = match.group(1)
                parts = raw_date.split("/")
                if len(parts) == 2:
                    current_date = f"{parts[0]}/{parts[1]}/" + datetime.datetime.now().strftime("%y")
                elif len(parts) == 3:
                    year = parts[2]
                    if len(year) == 4:
                        year = year[-2:]
                    current_date = f"{parts[0]}/{parts[1]}/{year}"
                else:
                    current_date = None
                if current_date not in raw_entries:
                    raw_entries[current_date] = []
                continue

            if current_date:
                change = re.sub(r"^[#\*]\s*", "", line)
                if change:
                    raw_entries[current_date].append(change)

        # Сортируем ключи и пересобираем словарь
        sorted_dates = sorted(raw_entries.keys(), key=self.date_key, reverse=True)
        self.changes = {d: raw_entries[d] for d in sorted_dates}

        print(f"✅ Загружено {len(self.changes)} дат, всего {sum(len(v) for v in self.changes.values())} записей")
        print(f"   Пример: {self.changes}")

    def load_changes_old(self):
        self.changes = []
        if not os.path.exists(CHANGES_FILE):
            print(f"ℹ️ Файл {CHANGES_FILE} не найден — начнём с пустого списка.")
            return

        try:
            with open(CHANGES_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            wx.MessageBox(f"Ошибка чтения {CHANGES_FILE}:\n{e}", "Ошибка", wx.OK | wx.ICON_ERROR)
            return

        current_date = None
        raw_entries = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Проверяем, является ли строка заголовком даты
            match = re.match(r"^#\s*(\d{2}/\d{2}(?:/\d{2})?)\s*$", line)
            if match:
                raw_date = match.group(1)
                parts = raw_date.split("/")
                if len(parts) == 2:
                    current_date = f"{parts[0]}/{parts[1]}/" + datetime.datetime.now().strftime("%y")
                elif len(parts) == 3:
                    year = parts[2]
                    if len(year) == 4:
                        year = year[-2:]
                    current_date = f"{parts[0]}/{parts[1]}/{year}"
                else:
                    current_date = None
                continue

            if current_date:
                # Убираем "# " или "* " в начале
                change = re.sub(r"^[#\*]\s*", "", line)
                if change:
                    raw_entries.append((current_date, change))

        self.changes = sorted(raw_entries, key=self.date_key)
        print(f"✅ Загружено {len(self.changes)} записей из {CHANGES_FILE}")
        print(f"   Пример: {self.changes}")
        self.filter_by_date(self.date_picker.GetValue())

    def date_key(self, date_str):
        """ Преобразует строку даты в datetime.date и возвращает ключ для сортировки """
        try:
            return datetime.datetime.strptime(date_str, "%d/%m/%y")
        except ValueError:
            return datetime.datetime.min

    def save_changes(self):
        # Сортируем по дате (новые сверху)
        sorted_dates = sorted(self.changes.keys(), key=self.date_key)

        with open(CHANGES_FILE, "w", encoding="utf-8") as f:
            for date_str in sorted_dates:
                f.write(f"# {date_str}\n")
                for change in self.changes[date_str]:
                    f.write(f"* {change}\n")
            f.write("\n")


    def on_add_change(self, event):
        text = self.input_ctrl.GetValue().strip()
        if not text:
            wx.MessageBox("Введите описание изменения", "Ошибка", wx.OK | wx.ICON_WARNING)
            return

        date_obj = self.wxdate_to_pydate(self.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")

        # Добавляем в список этой даты
        if date_str not in self.changes:
            self.changes[date_str] = []
        self.changes[date_str].append(text)

        # Обновляем UI
        self.filter_by_date(date_str)
        self.input_ctrl.Clear()
        self.save_changes()
        self.status_bar.SetStatusText(f"Добавлено: {text}")


    def on_add_change_old(self, event):
        text = self.input_ctrl.GetValue().strip()
        if not text:
            wx.MessageBox("Введите описание изменения", "Ошибка", wx.OK | wx.ICON_WARNING)
            return

        # Получаем дату из DatePickerCtrl
        date_obj = self.wxdate_to_pydate(self.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")  # "25/06/24"

        print(f"[DEBUG] Добавляем: date={date_str}, text={text}")
        print(f"[DEBUG] До insert: len(self.changes) = {len(self.changes)}")

        # Ищем позицию для вставки (после последней записи этой даты)
        last_idx = next((i for i in reversed(range(len(self.changes))) if self.changes[i][0] == date_str), -1)
        insert_pos = last_idx + 1 if last_idx >= 0 else len(self.changes)
        self.changes.insert(insert_pos, (date_str, text))

        print(f"[DEBUG] После insert: len(self.changes) = {len(self.changes)}")
        print(f"[DEBUG] self.changes[-1] = {self.changes[-1]}")

        # Обновляем UI
        self.list_ctrl.RefreshItems()
        self.on_date_changed(None)

        # Очищаем поле ввода
        self.input_ctrl.Clear()

        # Сохраняем
        self.save_changes()

        self.status_bar.SetStatusText(f"Добавлено: {text}")

    def on_add_change_old(self, event):
        text = self.input_ctrl.GetValue().strip()
        if not text:
            wx.MessageBox("Введите описание изменения", "Ошибка", wx.OK | wx.ICON_WARNING)
            return

        current_date = self.date_picker.GetValue()
        print(f"on_add_change Добавляем: {current_date} - {text}")

        # Ищем последний индекс с текущей датой
        last_idx = next((i for i in reversed(range(len(self.changes))) if self.changes[i][0] == current_date), -1)
        insert_pos = last_idx + 1 if last_idx >= 0 else len(self.changes)
        self.changes.insert(insert_pos, (current_date, text))

        self.list_ctrl.RefreshItems()
        self.input_ctrl.Clear()
        self.save_changes()  # ← вызовет сортировку при сохранении
        self.status_bar.SetStatusText(f"Добавлено: {text}")


    def on_delete_change(self, event):
        print(f"on_delete_change")
        idx = self.list_ctrl.GetFirstSelected()
        if idx == -1:
            wx.MessageBox("Выберите строку для удаления", "Ошибка", wx.OK | wx.ICON_WARNING)
            return
        date_obj = self.wxdate_to_pydate(self.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")

        self.list_ctrl.DeleteItem(idx)
        # self.changes[date_str].pop(idx)
        # if not self.changes[date_str]:
        #     self.changes.pop(date_str)
        self.save_changes()
        # self.list_ctrl.RefreshItems()
        self.status_bar.SetStatusText("Изменение удалено")

    def on_commit(self, event):
        if not self.is_git_repo():
            wx.MessageBox("Текущая директория не является Git-репозиторием", "Ошибка", wx.OK | wx.ICON_ERROR)
            return
        current_date = None
        # Формируем сообщение коммита
        msg_lines = []
        sorted_dates = sorted(self.changes.keys(), key=self.date_key)
        for date_str in sorted_dates: # Словарь
            if date_str != current_date:
                msg_lines.append(f"📅 {date_str}")
                current_date = date_str
                for change in self.changes[date_str]:
                    msg_lines.append(f"• {change}\n")
            commit_msg = "\n".join(msg_lines)

        # Показываем предпросмотр
        dlg = wx.MessageDialog(
            self,
            f"Сообщение коммита:\n\n{commit_msg}\n\nВыполнить `git commit -m`?",
            "Подтверждение коммита",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if dlg.ShowModal() == wx.ID_YES:
            try:
                # Запускаем git commit
                result = subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    capture_output=True,
                    text=True,
                    check=True
                )
                wx.MessageBox("Коммит успешно создан!", "Успех", wx.OK | wx.ICON_INFORMATION)
                self.status_bar.SetStatusText("Коммит выполнен")
            except subprocess.CalledProcessError as e:
                wx.MessageBox(f"Ошибка при коммите:\n{e.stderr}", "Ошибка Git", wx.OK | wx.ICON_ERROR)
                self.status_bar.SetStatusText("Ошибка коммита")
        dlg.Destroy()

    def on_push(self, event):
        brunch = event.GetEventObject().GetName()
        if not self.is_git_repo():
            wx.MessageBox("Текущая директория не является Git-репозиторием", "Ошибка", wx.OK | wx.ICON_ERROR)
            return
        if brunch == "backup":
            cmd = ["git", "push", "backup", "main"]
        if brunch == "origin":
            cmd = ["git", "push", "origin", "main"]
        else:
            cmd = ["git", "push-all"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            wx.MessageBox("Push успешно выполнен!", "Успех", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText("Push выполнен")
        except subprocess.CalledProcessError as e:
            wx.MessageBox(f"Ошибка при push:\n{e.stderr}", "Ошибка Git", wx.OK | wx.ICON_ERROR)
            self.status_bar.SetStatusText("Ошибка push")

    def is_git_repo(self):
        return subprocess.run(["git", "rev-parse", "--git-dir"],
                              capture_output=True).returncode == 0


class ChangelogApp(wx.App):
    def OnInit(self):
        # Проверка: запущена ли программа в корне репозитория
        # if not os.path.exists(".git") and not os.path.exists(".git/HEAD"):
        #     wx.MessageBox(message="⚠️ GIT-репозиторий не обнаружен.\n Программа будет только вести файл CHANGES.md",
        #         style=wx.OK | wx.ICON_WARNING, caption="Предупреждение", parent=None
        #     )
        #     return True

        frame = ChangelogFrame(None, title="Git Changelog Tool")
        self.SetTopWindow(frame)
        return True


if __name__ == "__main__":
    app = ChangelogApp()
    app.MainLoop()
