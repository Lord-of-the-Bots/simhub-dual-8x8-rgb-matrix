# -*- coding: utf-8 -*-
"""Small offline brightness editor for the supplied dual 8x8 SimHub profile.

Python 3 with Tkinter (included in the standard Windows Python installer).
Put this file beside the .ledsprofile and double-click it. No extra packages.
The source is never overwritten; every save creates a new importable profile.
"""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = Path(__file__).resolve().parent
DEFAULT_PROFILE = 'Any Game - Dual 8x8.ledsprofile'
GROUP_LABEL = re.compile(r'^Screen ([12]) - brightness \d+%$')


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get('LedContainers', []))


def panel_groups(profile):
    """Identify our existing wrappers, including disabled idle/music modes."""
    found = {1: [], 2: []}
    if not isinstance(profile, dict) or not isinstance(profile.get('LedContainers'), list):
        raise ValueError('This file does not look like a SimHub profile.')
    for node in walk(profile['LedContainers']):
        if node.get('ContainerType') != 'BrightnessGroupContainer':
            continue
        match = GROUP_LABEL.fullmatch(node.get('Description', ''))
        if not match:
            raise ValueError('This profile contains an unrecognized brightness setting.\nPlease choose the supplied Dual 8x8 profile.')
        panel = int(match[1])
        descendants = list(walk(node.get('LedContainers', [])))
        leaves = [n for n in descendants if 'LedContainers' not in n]
        if (not leaves or node.get('StartPositionMatrix', 1) != 1
                or any(n.get('StartPositionMatrix', 1) != 1 for n in descendants if 'LedContainers' in n)
                or any(n.get('StartPositionMatrix', 1) != panel for n in leaves)
                or any(n.get('ContainerType') == 'BrightnessGroupContainer' for n in descendants)):
            raise ValueError('The screen layout in this profile has been changed.\nPlease choose the supplied Dual 8x8 profile.')
        found[panel].append(node)
    if not all(found.values()):
        raise ValueError('Could not find settings for both screens.\nPlease choose the supplied Dual 8x8 profile.')
    return found


def read_profile(path):
    with Path(path).open('r', encoding='utf-8-sig') as stream:
        profile = json.load(stream)
    panel_groups(profile)
    return profile


def current_levels(profile):
    result = []
    for groups in panel_groups(profile).values():
        values = {n.get('Brightness') for n in groups}
        value = next(iter(values)) if len(values) == 1 else None
        result.append(str(int(value)) if isinstance(value, (int, float)) and 0 <= value <= 100 else '')
    return result


def set_brightness(profile, screen1, screen2):
    """Change percentages once, never RGB values, effect states, or IDs."""
    for value in (screen1, screen2):
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError('Enter a whole number from 0 to 100 for each screen.')
    result = copy.deepcopy(profile)
    for panel, groups in panel_groups(result).items():
        value = screen1 if panel == 1 else screen2
        for node in groups:
            node['Brightness'] = value
            node['Description'] = f'Screen {panel} - brightness {value}%'
    result['GlobalBrightness'] = 100.0
    result['UseProfileBrightness'] = True
    preset = result.get('GlobalBrightnessPreset')
    if not isinstance(preset, dict):
        preset = {}
    preset.update(CurrentMode=0, Brightness=100.0)
    result['GlobalBrightnessPreset'] = preset
    name = re.sub(r' - \d{1,3}-\d{1,3}$', '', result.get('Name', 'Dual 8x8'))
    result['Name'] = f'{name} - {screen1}-{screen2}'
    return result


def save_copy(profile, folder, screen1, screen2):
    """Exclusive creation also protects any previously saved/imported copy."""
    payload = json.dumps(set_brightness(profile, screen1, screen2), ensure_ascii=False, indent=2) + '\n'
    stem = f'Dual 8x8 - {screen1}-{screen2}'
    for number in range(1, 10000):
        suffix = '' if number == 1 else f' ({number})'
        target = Path(folder) / f'{stem}{suffix}.ledsprofile'
        try:
            stream = target.open('x', encoding='utf-8', newline='\n')
        except FileExistsError:
            continue
        try:
            with stream:
                stream.write(payload)
        except OSError:
            target.unlink(missing_ok=True)
            raise
        return target
    raise ValueError('There are too many saved copies in this folder. Please choose another folder.')


class BrightnessWindow:
    def __init__(self, window):
        self.window = window
        self.source = None
        self.profile = None
        self.saved = None
        window.title('Dual screen brightness')
        window.geometry('680x485')
        window.minsize(630, 465)
        style = ttk.Style(window)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        style.configure('.', font=('Segoe UI', 12))
        style.configure('Title.TLabel', font=('Segoe UI', 20, 'bold'))
        body = ttk.Frame(window, padding=24)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text='Choose your brightness', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(body, text='Applies to every mode: games, clock, dots and music.').grid(row=1, column=0, sticky='w', pady=(5, 18))

        file_row = ttk.Frame(body)
        file_row.grid(row=2, column=0, sticky='ew')
        file_row.columnconfigure(0, weight=1)
        self.file_label = ttk.Label(file_row, text='No profile selected', wraplength=415)
        self.file_label.grid(row=0, column=0, sticky='w')
        ttk.Button(file_row, text='Choose file…', command=self.choose).grid(row=0, column=1, padx=(10, 0))

        levels = ttk.Frame(body)
        levels.grid(row=3, column=0, sticky='ew', pady=20)
        self.values = [tk.StringVar(), tk.StringVar()]
        for index, value in enumerate(self.values):
            ttk.Label(levels, text=f'Screen {index + 1}').grid(row=0, column=index * 3, padx=(0 if index == 0 else 40, 12))
            spin = ttk.Spinbox(levels, from_=0, to=100, width=4, textvariable=value, font=('Segoe UI', 19), justify='center')
            spin.grid(row=0, column=index * 3 + 1)
            ttk.Label(levels, text='%').grid(row=0, column=index * 3 + 2, padx=(6, 0))

        self.save_button = ttk.Button(body, text='Save profile for SimHub', command=self.save, state='disabled')
        self.save_button.grid(row=4, column=0, sticky='ew', ipady=9)
        ttk.Label(body, text='Saves a new copy in the same folder. Your original file is kept.', wraplength=610).grid(row=5, column=0, sticky='w', pady=(9, 13))
        self.status = ttk.Label(body, text='Values: from 0 (off) to 100 (full brightness).', wraplength=610)
        self.status.grid(row=6, column=0, sticky='w')
        self.show_button = ttk.Button(body, text='Show saved file in folder', command=self.show_saved, state='disabled')
        self.show_button.grid(row=7, column=0, sticky='w', pady=(12, 0))
        window.bind('<Return>', lambda event: self.save() if self.profile else None)
        window.after(50, self.autoload)

    def autoload(self):
        if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
            return self.load(Path(sys.argv[1]))
        preferred = HERE / DEFAULT_PROFILE
        if preferred.is_file():
            return self.load(preferred)
        candidates = sorted(HERE.glob('*.ledsprofile'))
        if len(candidates) == 1:
            self.load(candidates[0])
        else:
            self.status.configure(text='Click "Choose file…" and select your .ledsprofile file.')

    def choose(self):
        selected = filedialog.askopenfilename(parent=self.window, title='Choose a SimHub profile',
                    initialdir=str(self.source.parent if self.source else HERE),
                    filetypes=[('SimHub profile', '*.ledsprofile')])
        if selected:
            self.load(Path(selected))

    def load(self, path):
        try:
            profile = read_profile(path)
            levels = current_levels(profile)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            messagebox.showerror('Could not open profile', str(error), parent=self.window)
            return
        self.source, self.profile = path.resolve(), profile
        self.file_label.configure(text=self.source.name)
        for field, value in zip(self.values, levels):
            field.set(value)
        self.save_button.configure(state='normal')
        self.show_button.configure(state='disabled')
        self.saved = None
        self.status.configure(text='Enter each screen\'s brightness and click "Save profile for SimHub".')

    def save(self):
        if self.profile is None:
            return
        try:
            raw = [value.get().strip() for value in self.values]
            if any(not re.fullmatch(r'[0-9]{1,3}', value) for value in raw):
                raise ValueError('Enter a whole number from 0 to 100 for each screen.')
            first, second = map(int, raw)
            # Read again so changes made since opening the window are preserved.
            profile = read_profile(self.source)
            self.saved = save_copy(profile, self.source.parent, first, second)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            messagebox.showerror('Could not save profile', str(error), parent=self.window)
            return
        self.status.configure(text=f'Saved: {self.saved.name}\nImport this new file into SimHub.')
        self.show_button.configure(state='normal')

    def show_saved(self):
        if self.saved:
            try:
                subprocess.Popen(['explorer.exe', f'/select,{self.saved}'])
            except OSError as error:
                messagebox.showerror('Could not open folder', str(error), parent=self.window)


if __name__ == '__main__':
    root = tk.Tk()
    BrightnessWindow(root)
    root.mainloop()
