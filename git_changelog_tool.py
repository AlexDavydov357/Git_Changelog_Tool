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
from embedded_images import _switcher_3d_1, _switcher_3d_green
from git_setup import GitSetupFrame


CHANGES_FILE = "CHANGES.md"
JSON_FILE = "changelog.json"

# --- Цвета темной темы (Git Bash / VS Code Dark style) ---
DARK_BG = wx.Colour(30, 30, 30)        # #1e1e1e — фон окна/панели
DARK_PANEL = wx.Colour(45, 45, 45)     # #2d2d2d — фон полей ввода, списков
TEXT_LIGHT = wx.Colour(212, 212, 212)  # #d4d4d4 — основной текст
TEXT_DIM = wx.Colour(160, 160, 160)    # #a0a0a0 — второстепенный текст
GIT_BLUE = wx.Colour(14, 99, 156)      # #0e639c — кнопки (Git-style)
GIT_GREEN = wx.Colour(40, 167, 69)     # #28a745 — Commit/Push
GIT_RED = wx.Colour(220, 53, 69)       # #dc3545 — Delete
LIST_HIGHLIGHT = wx.Colour(0, 120, 212) # #0078d6 — выделение в списке


# git_changelog_data.py
from dataclasses import dataclass, field
from typing import Dict, List
import datetime

@dataclass
class CommitItem:
    text: str
    committed: bool = False

@dataclass
class DateGroup:
    date: str  # в формате "25/06/24"
    items: List[CommitItem] = field(default_factory=list)

@dataclass
class ChangelogData:
    # {date_str: DateGroup}
    groups: Dict[str, DateGroup] = field(default_factory=dict)

    def add_item(self, date_str: str, text: str, committed: bool = False):
        if date_str not in self.groups:
            self.groups[date_str] = DateGroup(date=date_str)
        self.groups[date_str].items.append(CommitItem(text=text, committed=committed))

    def get_items(self, date_str: str) -> List[CommitItem]:
        return self.groups.get(date_str, DateGroup(date=date_str)).items

    def delete_item(self, date_str: str, index: int):
        """Удаляет элемент по индексу из группы с датой date_str"""
        self.groups[date_str].items.pop(index)
        if not self.groups[date_str].items:
            del self.groups[date_str]

    def to_json(self) -> str:
        import json
        data = []
        for date_str, group in sorted(self.groups.items(), key=lambda x: x[0], reverse=False):
            data.append({
                "date": group.date,
                "items": [
                    {"text": item.text, "committed": item.committed}
                    for item in group.items
                ]
            })
        return json.dumps(data, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ChangelogData":
        import json
        data = cls()
        raw = json.loads(json_str)
        for item in raw:
            date_str = item["date"]
            data.groups[date_str] = DateGroup(
                date=date_str,
                items=[CommitItem(**i) for i in item["items"]]
            )
        return data

    def get_uncommitted_items(self) -> List[tuple]:
        """Возвращает [(date_str, CommitItem), ...] для всех незакоммиченных"""
        result = []
        for date_str, group in sorted(self.groups.items(), key=lambda x: x[0], reverse=False):
            for item in group.items:
                if item.committed:
                    result.append((date_str, item))
        return result

class EditableChangelogList(wx.ListCtrl,
                            listmix.ListCtrlAutoWidthMixin,
                            listmix.TextEditMixin):
    def __init__(self, parent, top_parent):
        style = wx.LC_REPORT #| wx.LC_SINGLE_SEL | wx.LC_HRULES | wx.LC_VRULES
        wx.ListCtrl.__init__(self, parent, style=style)
        listmix.ListCtrlAutoWidthMixin.__init__(self)
        listmix.TextEditMixin.__init__(self)
        self.EnableCheckBoxes()
        self.parent = top_parent
        if DARK_THEM:
            self.SetBackgroundColour(DARK_PANEL)
            self.SetForegroundColour(TEXT_LIGHT)
            self.SetFont(self.parent.mono_font)

        # Колонки
        self.InsertColumn(0, "⬆️", width=20)  # пустая колонка для чекбоксов
        self.InsertColumn(1, "Дата", width=70)
        self.InsertColumn(2, "Изменение", width=450)


        # Заполняем
        self.RefreshItems()

        # Обработчики
        # self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_item_deselected)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.on_end_label_edit)
        # self.Bind(wx.EVT_LIST_DELETE_ITEM, self.on_delete_item)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)  # ← ключевой момент
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_left_down)
        self.Bind(wx.EVT_LIST_ITEM_CHECKED, self.ItemCheckChanged) #lambda e: self.RefreshItems())
        self.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self.ItemCheckChanged) #lambda e: self.RefreshItems())

        self.Bind(wx.EVT_KEY_DOWN, self.on_key_down)

    def on_left_down(self, event):
        """Обрабатывает клик мыши: чекбокс/дата → переключение, текст → редактирование"""
        x, y = event.GetPosition()
        idx, flags,  col = self.HitTestSubItem((x, y))
        print(f'on_left_down x={x}, y={y}, flags={flags}, idx={idx}, col={col}')
        # Если кликнули по строке
        if idx >= 0:
            # Если клик по чекбоксу (col 0) или по дате (col 1) — переключаем чекбокс
            if col in (0, 1):
                self.ToggleItem(idx)
                return  # не передаём дальше — редактирование не запускаем

        # Иначе — передаём стандартному обработчику (TextEditMixin)
        event.Skip()

    def ItemCheckChanged(self, evt):
        index = evt.Index
        print(f'ItemCheckChanged: index={index}')
        # data = self.GetItemData(index)
        # what = "checked" if self.IsItemChecked(index) else "unchecked"
        # print('item "%s", at index %d was %s\n' % (data, index, what))

    def ToggleItem(self, idx):
        # toggle = not self.IsItemChecked(idx)
        # print(f'ToggleItem {idx} {toggle}')

        """Переключает флаг committed для строки с индексом idx"""
        date_obj = self.parent.wxdate_to_pydate(self.parent.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")
        items = self.parent.data.get_items(date_str)

        if idx < 0 or idx >= len(items):
            return

        item = items[idx]
        item.committed = not item.committed
        self.CheckItem(idx, item.committed)
        self.parent.save_changes()
        print(f'ToggleItem {idx} {item.committed}')


    def on_key_down(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_DELETE, wx.WXK_BACK):
            idx = self.GetFirstSelected()
            print(f'on_key_down key={key}, idx={idx}')
            if idx >= 0:
                self.parent.on_delete_change(wx.ListEvent(wx.wxEVT_LIST_DELETE_ITEM, self.GetId()))
        else:
            event.Skip()

    def RefreshItems(self):
        """Обновляет список из self.data"""
        print('RefreshItems')
        date_obj = self.parent.wxdate_to_pydate(self.parent.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")
        self.DeleteAllItems()
        items = self.parent.data.get_items(date_str)
        for i, item in enumerate(items):
            idx = self.InsertItem(self.GetItemCount(), '')
            self.SetItem(idx, 1, date_str)
            self.SetItem(idx, 2, item.text)
            self.CheckItem(idx, item.committed)


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
        print(f'on_end_label_edit idx={idx}, col={col}, new_value={new_value}')

        date_obj = self.parent.wxdate_to_pydate(self.parent.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")
        items = self.parent.data.get_items(date_str)

        if idx < 0 or idx >= len(items):
            event.Veto()
            return

        if col == 2:  # редактируем текст
            items[idx].text = new_value
            self.parent.save_changes()
        event.Skip()

    def on_delete_item(self, event):
        print('on_delete_item')
        # """Удаление по Delete/Backspace
        # # Удаляет выбранный элемент из списка listctrl и словаря self.changes"""
        # date_obj = self.parent.wxdate_to_pydate(self.parent.date_picker.GetValue())
        # date_str = date_obj.strftime("%d/%m/%y")
        # idx = event.GetIndex()
        # self.parent.data.delete_item(date_str, idx)
        # self.parent.list_ctrl.DeleteItem(idx) # вызывает фукнцию on_delete_item
        # self.parent.save_changes()
        # self.RefreshItems()

    def on_item_activated(self, event):
        """Двойной клик → редактирование"""
        print(f'on_item_activated idx={event.GetIndex()}')
        idx = event.GetIndex()
        self.ToggleItem(idx)
        # if idx >= 0:
        #     self.EditLabel(idx, 2)  # редактируем колонку 1 (Изменение)

    def on_item_deselected(self, event):
        print('on_item_deselected')
        # Можно очистить фокус — не обязательно
        pass

DARK_THEM = False
class ChangelogFrame(wx.Frame):
    def __init__(self, parent, title):
        super().__init__(parent, title=title, size=(1000, 600))
        self.mono_font = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        # Устанавливаем темную тему для окна
        if DARK_THEM:
            self.SetBackgroundColour(DARK_BG)
            self.SetForegroundColour(TEXT_LIGHT)

        self.load_changes()
        self.InitUI()
        self.Centre()
        self.Show()

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
        self.thema_btn = wx.ToggleButton(panel, id=wx.ID_ANY, style=wx.NO_BORDER|wx.BU_EXACTFIT,
                                                size=(32, 13), name='thema_btn')
        self.thema_btn.SetToolTip('Переключить тему')
        self.thema_btn.SetBitmap(_switcher_3d_1.GetBitmap())
        self.thema_btn.SetBitmapPressed(_switcher_3d_green.GetBitmap())
        self.thema_btn.Bind(wx.EVT_TOGGLEBUTTON, self.switch_theme)

        header_sizer.Add(self.thema_btn, 0, flag=wx.ALIGN_CENTER|wx.LEFT|wx.TOP, border=5)
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

        export_btn = wx.Button(panel, label="📄 Export to CHANGES.md")
        export_btn.Bind(wx.EVT_BUTTON, self.export_changes)
        header_sizer.Add(export_btn, 0, flag=wx.EXPAND | wx.LEFT | wx.TOP, border=5)

        main_sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # --- Changes list (редактируемый) ---
        self.list_ctrl = EditableChangelogList(panel, self)

        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)


        # --- Input area ---
        input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.input_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER, name="add_evt")
        self.input_ctrl.SetToolTip("Введите описание изменения и нажмите Enter или кнопку «Добавить»")
        self.input_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_add_change)
        input_sizer.Add(self.input_ctrl, 1, wx.RIGHT, 5)

        add_btn = wx.Button(panel, label="📝 Добавить", name="add_evt")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add_change)
        input_sizer.Add(add_btn, 0)

        del_btn = wx.Button(panel, label="🗑️ Удалить")
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete_change)
        input_sizer.Add(del_btn, 0)

        main_sizer.Add(input_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)


        # --- Git sizer ---
        git_sizer = wx.BoxSizer(wx.HORIZONTAL)
        # --- Кнопка "Настроить Git" ---
        self.git_setup_btn = wx.Button(panel, label="⚙️ Настроить Git")
        self.git_setup_btn.SetToolTip("Открыть окно для первоначальной настройки Git-репозитория")
        self.git_setup_btn.Bind(wx.EVT_BUTTON, self.open_git_setup)
        git_sizer.Add(self.git_setup_btn, flag=wx.RIGHT, border=5)

        self.test_push_btn = wx.Button(panel, label="🚀 Test", name="test")
        self.test_push_btn.SetToolTip("Cоздаёт и пушит тестовый коммит. Берет настройки веток из .git/config")
        self.test_push_btn.Bind(wx.EVT_BUTTON, self.test_push)
        git_sizer.Add(self.test_push_btn, flag=wx.RIGHT, border=5)

        self.rev_push_btn = wx.Button(panel, label="↩️ Revert", name="revert")
        self.rev_push_btn.SetToolTip("Откатывает последний коммит и пушит откат")
        self.rev_push_btn.Bind(wx.EVT_BUTTON, self.revert_test)
        git_sizer.Add(self.rev_push_btn, 0)
        git_sizer.Add((1,1), 1, wx.EXPAND)

        # --- Кнопка "Последний коммит" ---
        self.last_commit_btn = wx.Button(panel, label="👁️ Последний коммит")
        self.last_commit_btn.SetToolTip("Показывает последний коммит из локального репозитория")
        self.last_commit_btn.Bind(wx.EVT_BUTTON, self.show_last_commit)
        git_sizer.Add(self.last_commit_btn, 0, wx.RIGHT, 5)
        git_sizer.Add(wx.StaticLine(panel, style=wx.LI_VERTICAL), 0, wx.EXPAND | wx.RIGHT, 5)


        self.commit_btn = wx.Button(panel, label="💾 Commit")
        self.commit_btn.Bind(wx.EVT_BUTTON, self.commit)
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

    def open_git_setup(self, e):
        print('git_setup')
        """Открывает окно настройки Git"""
        frame = GitSetupFrame(self)
        frame.Show()

    def switch_theme(self, e):
        DARK_THEM = self.thema_btn.GetValue()
        if self.thema_btn.GetValue():
            self.thema_btn.SetToolTip('Переключить на светлую тему')
        else:
            self.thema_btn.SetToolTip('Переключить на тёмную тему')
        self.Layout()

    def show_last_commit(self, event):
        """Показывает последний коммит в всплывающем окне + выводит в консоль"""
        if not self.is_git_repo():
            wx.MessageBox("Текущая директория не является Git-репозиторием", "Ошибка", wx.OK | wx.ICON_ERROR)
            return

        try:
            # 1. Получаем raw bytes (без text=True!)
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%h - %an, %ar : %s%n%n%b"],
                capture_output=True,  # ← ВАЖНО: без text=True
                cwd=Path.cwd()
            )

            # 2. Выводим в консоль как raw bytes (чтобы вы увидели "сырой" вывод)
            print("=" * 60)
            print("🔍 ОТЛАДКА: raw bytes из git log:")
            print(f"stdout (bytes): {result.stdout!r}")
            print(f"stderr (bytes): {result.stderr!r}")
            print(f"returncode: {result.returncode}")
            print("=" * 60)

            # 3. Пробуем декодировать с разными кодировками
            encodings_to_try = ["utf-8", "cp1251", "latin-1", "cp866"]
            decoded_text = None

            for enc in encodings_to_try:
                try:
                    decoded_text = result.stdout.decode(enc, errors="replace")
                    print(f"✅ Успешно декодировано как {enc}:")
                    print(decoded_text)
                    print("-" * 40)
                    break
                except Exception:
                    continue

            if decoded_text is None:
                # Если ни одна кодировка не сработала — используем замену
                decoded_text = result.stdout.decode("utf-8", errors="replace")
                print(f"⚠️ Использована замена ошибок (utf-8, errors='replace')")

            # 4. Показываем в диалоге
            if not decoded_text.strip():
                wx.MessageBox("Коммитов пока нет.", "Инфо", wx.OK | wx.ICON_INFORMATION)
                return

            dlg = wx.MessageDialog(
                self,
                decoded_text,
                "Последний коммит",
                wx.OK | wx.ICON_INFORMATION | wx.CENTRE
            )
            dlg.SetFont(self.mono_font)
            dlg.ShowModal()
            dlg.Destroy()

        except subprocess.CalledProcessError as e:
            wx.MessageBox(
                f"Ошибка при получении последнего коммита:\n{e.stderr or e.stdout}",
                "Ошибка Git",
                wx.OK | wx.ICON_ERROR
            )

    def show_last_commit_old(self, event):
        """Показывает последний коммит в всплывающем окне"""
        if not self.is_git_repo():
            wx.MessageBox("Текущая директория не является Git-репозиторием", "Ошибка", wx.OK | wx.ICON_ERROR)
            return

        try:
            # Устанавливаем локаль в UTF-8 для корректного вывода
            env = os.environ.copy()
            env["LC_ALL"] = "C.UTF-8"
            env["LANG"] = "C.UTF-8"

            # Получаем форматированный вывод последнего коммита
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%h - %an, %ar : %s%n%n%b"],
                capture_output=True,
                text=True,
                check=True,
                cwd=Path.cwd(),
                env=env,  # ← ВАЖНО: передаём обновлённую локаль
            )
            commit_text = result.stdout.strip()

            if not commit_text:
                wx.MessageBox("Коммитов пока нет.", "Инфо", wx.OK | wx.ICON_INFORMATION)
                return

            # Создаём диалог с текстовым полем (можно редактировать/копировать)
            dlg = wx.MessageDialog(
                self,
                commit_text,
                "Последний коммит",
                wx.OK | wx.ICON_INFORMATION | wx.CENTRE
            )
            # Устанавливаем моноширинный шрифт для читаемости
            dlg.SetFont(self.mono_font)
            dlg.ShowModal()
            dlg.Destroy()

        except subprocess.CalledProcessError as e:
            wx.MessageBox(
                f"Ошибка при получении последнего коммита:\n{e.stderr or e.stdout}",
                "Ошибка Git",
                wx.OK | wx.ICON_ERROR
            )

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
            dlg = wx.MessageDialog(
                self,
                "локальная ветка main не существует или не привязана к удалённой",
                "Последний коммит",
                wx.OK | wx.ICON_INFORMATION | wx.CENTRE
            )
            # Устанавливаем моноширинный шрифт для читаемости
            dlg.SetFont(self.mono_font)
            dlg.ShowModal()
            dlg.Destroy()
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

    def filter_by_date(self, date_str, e=None):
        self.list_ctrl.DeleteAllItems()
        items = self.data.get_items(date_str)
        for i, item in enumerate(items):
            idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), '')
            self.list_ctrl.SetItem(idx, 1, date_str)
            self.list_ctrl.SetItem(idx, 2, item.text)
            self.list_ctrl.CheckItem(idx, item.committed)
        if self.list_ctrl.GetItemCount() > 0:
            self.list_ctrl.Select(self.list_ctrl.GetItemCount() - 1)
            self.list_ctrl.Focus(self.list_ctrl.GetItemCount() - 1)
            if e is not None:
                self.list_ctrl.ToggleItem(idx+1)


    def export_changes(self, event):
        sorted_dates = sorted(self.data.groups.keys(), key=self.date_key, reverse=True)
        with open(CHANGES_FILE, "w", encoding="utf-8") as f:
            for date_str in sorted_dates:
                f.write(f"# {date_str}\n")
                for item in self.data.groups[date_str].items:
                    f.write(f"* {item.text}\n")
            f.write("\n")
        wx.MessageBox(f"✅ Экспортировано в {CHANGES_FILE}", "Успех", wx.OK | wx.ICON_INFORMATION)

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

    def on_date_changed(self, e):
        """Обновляет список при изменении даты"""
        date_obj = self.wxdate_to_pydate(self.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")  # → "25/06/24"
        self.filter_by_date(date_str)

    def load_changes(self):
        """Загружаем историю изменений из файла JSON"""
        self.data = ChangelogData()
        if not os.path.exists(JSON_FILE):
            print(f"ℹ️ Файл {JSON_FILE} не найден — начнём с пустого списка.")
            return

        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                self.data = ChangelogData.from_json(f.read())
            print(
                f"✅ Загружено {len(self.data.groups)} дат, всего {sum(len(g.items) for g in self.data.groups.values())} записей")
        except Exception as e:
            wx.MessageBox(f"Ошибка чтения {JSON_FILE}:\n{e}", "Ошибка", wx.OK | wx.ICON_ERROR)

    def date_key(self, date_str):
        """ Преобразует строку даты в datetime.date и возвращает ключ для сортировки """
        try:
            return datetime.datetime.strptime(date_str, "%d/%m/%y")
        except ValueError:
            return datetime.datetime.min

    def save_changes(self):
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            f.write(self.data.to_json())

    def on_add_change(self, e):
        text = self.input_ctrl.GetValue().strip()
        if not text:
            wx.MessageBox("Введите описание изменения", "Ошибка", wx.OK | wx.ICON_WARNING)
            return

        date_obj = self.wxdate_to_pydate(self.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")

        self.data.add_item(date_str, text, committed=True)
        self.filter_by_date(date_str, e)
        self.input_ctrl.Clear()
        self.save_changes()
        self.status_bar.SetStatusText(f"Добавлено: {text}")


    def on_delete_change(self, event):
        idx = self.list_ctrl.GetFirstSelected()
        print(f"on_delete_change {idx}")
        if idx == -1:
            wx.MessageBox("Выберите строку для удаления", "Ошибка", wx.OK | wx.ICON_WARNING)
            return
        date_obj = self.wxdate_to_pydate(self.date_picker.GetValue())
        date_str = date_obj.strftime("%d/%m/%y")
        self.data.delete_item(date_str, idx)
        print("list_ctrl: ", self.list_ctrl.GetItemText(idx, 2), "idx", idx)
        self.list_ctrl.DeleteItem(idx) # вызывает фукнцию on_delete_item
        self.save_changes()
        self.status_bar.SetStatusText("Изменение удалено")

    def commit(self, event):
        uncommitted = self.data.get_uncommitted_items()
        if not uncommitted:
            wx.MessageBox("Нет незакоммиченных изменений", "Инфо", wx.OK | wx.ICON_INFORMATION)
            return

        # Формируем сообщение
        msg_lines = []
        current_date = None
        for date_str, item in uncommitted:
            if date_str != current_date:
                msg_lines.append(f"📅 {date_str}")
                current_date = date_str
            msg_lines.append(f"• {item.text}")
        commit_msg = "\n".join(msg_lines)

        # Показываем предпросмотр
        dlg = wx.MessageDialog(
            self,
            f"Сообщение коммита:\n\n{commit_msg}\n\nВыполнить `git commit -m`?",
            "Подтверждение коммита",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if dlg.ShowModal() == wx.ID_YES:
            if not self.is_git_repo():
                wx.MessageBox("Текущая директория не является Git-репозиторием", "Ошибка", wx.OK | wx.ICON_ERROR)
                return
            try:
                # Добавляем JSON и CHANGES.md
                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", commit_msg], check=True)

                # Сбрасываем флаги committed=False → True
                for _, item in uncommitted:
                    item.committed = False
                self.save_changes()
                self.list_ctrl.RefreshItems()

                wx.MessageBox("✅ Коммит успешно создан и флаги обновлены!", "Успех", wx.OK | wx.ICON_INFORMATION)
                self.status_bar.SetStatusText("Коммит выполнен")
            except subprocess.CalledProcessError as e:
                wx.MessageBox(f"❌ Ошибка при коммите:\n{e.stderr or e.stdout}", "Ошибка Git", wx.OK | wx.ICON_ERROR)
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
