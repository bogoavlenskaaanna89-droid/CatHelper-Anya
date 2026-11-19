# -*- coding: utf-8 -*-
"""Офисный котик для Ани. Все изображения рисуются через QPainter."""
import ctypes
import json
import math
import os
import random
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import requests
from PyQt5.QtCore import Qt, QTimer, QPoint, QRectF, QObject, pyqtSignal, QThread
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPainterPath, QIcon, QPixmap, QRegion, QCursor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLabel, QComboBox, QSlider, QTimeEdit, QCheckBox,
    QSystemTrayIcon, QMenu, QAction, QMessageBox, QFrame
)

APP_NAME = 'Офисный котик для Ани'
AUTOSTART_NAME = 'CatHelper_Anya'
DATA_DIR = Path(os.getenv('APPDATA', str(Path.home()))) / 'CatHelper_Anya'
SETTINGS_PATH = DATA_DIR / 'settings.json'
FUR = {'Черный': '#383743', 'Рыжий': '#E5A05B', 'Белый': '#F5F3EB',
       'Коричневый': '#96735E', 'Серый': '#A8ABB5'}
EYES = {'Голубой': '#58B9EA', 'Черный': '#252532', 'Зеленый': '#65BA7C'}
SEASONS = ('Зима', 'Весна', 'Лето', 'Осень')
DEFAULT = {
    'fur': 'Рыжий', 'eyes': 'Зеленый', 'chubbiness': 45, 'season': 'Весна',
    'avito_times': ['10:00', '14:00', '17:00'], 'panel': True, 'autostart': False,
    'fed_date': '', 'requests_date': '', 'requests_closed': False,
    'morning_asked_date': '', 'avito_fired': {}, 'remind_last': '',
    'compact': False, 'computer_on': True
}


def load_settings():
    result = dict(DEFAULT)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            for key in DEFAULT:
                if key in data and isinstance(data[key], type(DEFAULT[key])):
                    result[key] = data[key]
    except (OSError, ValueError, TypeError):
        pass
    if result['fur'] not in FUR: result['fur'] = 'Рыжий'
    if result['eyes'] not in EYES: result['eyes'] = 'Зеленый'
    if result['season'] not in SEASONS: result['season'] = 'Весна'
    result['chubbiness'] = max(0, min(100, result['chubbiness']))
    if len(result['avito_times']) != 3: result['avito_times'] = list(DEFAULT['avito_times'])
    return result


def save_settings(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(SETTINGS_PATH)


def set_autostart(enabled):
    if sys.platform != 'win32':
        return False, 'Автозапуск доступен только в Windows.'
    try:
        import winreg
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                # sys.executable points at the PyInstaller EXE in the packaged application.
                if getattr(sys, 'frozen', False):
                    command = '"{}"'.format(sys.executable)
                else:
                    command = '"{}" "{}"'.format(sys.executable, os.path.abspath(__file__))
                winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, command)
            else:
                try: winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError: pass
        return True, ''
    except OSError as exc:
        return False, str(exc)


def color(hex_value, alpha=255):
    c = QColor(hex_value)
    c.setAlpha(alpha)
    return c


def round_rect(p, x, y, w, h, radius, fill, stroke=None, width=1):
    p.setPen(QPen(color(stroke), width) if stroke else Qt.NoPen)
    p.setBrush(QBrush(color(fill) if isinstance(fill, str) else fill))
    p.drawRoundedRect(QRectF(x, y, w, h), radius, radius)


def ellipse(p, x, y, w, h, fill, stroke=None, line=1):
    p.setPen(QPen(color(stroke), line) if stroke else Qt.NoPen)
    p.setBrush(color(fill) if isinstance(fill, str) else fill)
    p.drawEllipse(QRectF(x, y, w, h))


def label(p, x, y, w, h, text, size, ink='#514958', bold=False, align=Qt.AlignCenter):
    f = QFont('Segoe UI', size)
    f.setBold(bold)
    p.setFont(f); p.setPen(color(ink))
    p.drawText(QRectF(x, y, w, h), align, text)


def painter(widget):
    p = QPainter(widget)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    return p


def paint_cat(p, x, y, scale, settings, tick, mood='normal', waving=False):
    """Vector cat in local 150x135 coordinate system, x/y is top-left."""
    p.save(); p.translate(x, y); p.scale(scale, scale)
    base = color(FUR[settings['fur']]); dark = base.darker(125)
    chub = settings['chubbiness'] / 100.0
    wobble = math.sin(tick * 0.17) * 2
    p.translate(0, wobble)
    # Tail (drawn behind the body)
    tail = QPainterPath(QPoint(99, 91))
    tail.cubicTo(151, 69, 136, 25, 119, 42)
    p.setPen(QPen(base, 13, Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
    p.drawPath(tail)
    # Shadow + body / paws
    ellipse(p, 25, 119, 115, 10, '#D3CAD0')
    ellipse(p, 40-12*chub, 61, 76+28*chub, 66, base)
    ellipse(p, 44-6*chub, 112, 28, 16, base)
    ellipse(p, 87+7*chub, 111, 28, 16, base)
    # Ears droop when sad
    ear_drop = 12 if mood == 'sad' else 0
    p.setPen(Qt.NoPen); p.setBrush(base)
    for coords in [[(43, 52+ear_drop), (42, 12+ear_drop), (73, 31+ear_drop)],
                   [(91, 31+ear_drop), (120, 12+ear_drop), (116, 55+ear_drop)]]:
        poly = QPainterPath(QPoint(*coords[0])); poly.lineTo(*coords[1]); poly.lineTo(*coords[2]); poly.closeSubpath(); p.drawPath(poly)
    p.setBrush(color('#E9AAB4'))
    for coords in [[(50, 40+ear_drop), (49, 25+ear_drop), (65, 35+ear_drop)],
                   [(101, 34+ear_drop), (113, 25+ear_drop), (110, 42+ear_drop)]]:
        poly = QPainterPath(QPoint(*coords[0])); poly.lineTo(*coords[1]); poly.lineTo(*coords[2]); poly.closeSubpath(); p.drawPath(poly)
    ellipse(p, 34-8*chub, 28, 90+16*chub, 87, base)
    # cheeks, eyes, nose, mouth
    ellipse(p, 47-5*chub, 75, 22+6*chub, 17, '#F0B4AC')
    ellipse(p, 99+4*chub, 75, 22+6*chub, 17, '#F0B4AC')
    eye = EYES[settings['eyes']]
    if mood == 'happy':
        p.setPen(QPen(color('#4B3A40'), 3, Qt.SolidLine, Qt.RoundCap))
        for ex in (62, 101): p.drawArc(QRectF(ex-8, 62, 16, 12), 0, 180*16)
    else:
        ellipse(p, 56, 59, 16, 20, '#FFFDFC'); ellipse(p, 94, 59, 16, 20, '#FFFDFC')
        ellipse(p, 61, 63, 10, 14, eye); ellipse(p, 99, 63, 10, 14, eye)
        ellipse(p, 64, 65, 4, 5, '#FFFFFF'); ellipse(p, 102, 65, 4, 5, '#FFFFFF')
    path = QPainterPath(QPoint(78, 85)); path.lineTo(89, 85); path.lineTo(84, 92); path.closeSubpath()
    p.setBrush(color('#C87980')); p.setPen(Qt.NoPen); p.drawPath(path)
    p.setPen(QPen(color('#655460'), 1.8, Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
    if mood == 'sad':
        p.drawArc(QRectF(72, 96, 24, 13), 0, 180*16)
    else:
        p.drawArc(QRectF(74, 88, 20, 15), 180*16, 180*16)
    for side in (-1, 1):
        sx = 83 + side*14
        for d in (-7, 0, 7): p.drawLine(QPoint(sx, 92), QPoint(sx + side*24, 92+d))
    if waving:
        p.save(); p.translate(111, 104); p.rotate(25*math.sin(tick * 0.65)-25)
        ellipse(p, -5, -36, 24, 45, base)
        p.restore()
    p.restore()


class WeatherWorker(QThread):
    done = pyqtSignal(str)
    def run(self):
        try:
            response = requests.get('https://api.open-meteo.com/v1/forecast', params={
                'latitude': 54.9924, 'longitude': 73.3686,
                'current': 'temperature_2m,weather_code', 'timezone': 'Asia/Omsk'
            }, timeout=9)
            response.raise_for_status()
            current = response.json()['current']
            code = int(current['weather_code'])
            if code == 0: weather = 'Ясно'
            elif code in (1, 2, 3): weather = 'Облачно'
            elif code in (45, 48): weather = 'Туман'
            elif code in (51, 53, 55, 56, 57): weather = 'Морось'
            elif code in (61, 63, 65, 66, 67, 80, 81, 82): weather = 'Дождь'
            elif code in (71, 73, 75, 77, 85, 86): weather = 'Снег'
            elif code in (95, 96, 99): weather = 'Гроза'
            else: weather = 'Переменно'
            self.done.emit('Омск  {:+.0f}°  {}'.format(float(current['temperature_2m']), weather))
        except (requests.RequestException, ValueError, KeyError, TypeError):
            self.done.emit('Омск  погода недоступна')


class Office(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(770, 490)
        self.setMouseTracking(True)
        self.setStyleSheet('background: transparent;')
        self.comp_rect = QRectF()
        self.button_rect = QRectF()

    def paintEvent(self, event):
        p = painter(self)
        p.scale(self.width()/1100, self.height()/680)
        p.fillRect(QRectF(0, 0, 1100, 680), color('#F7E9E9'))
        # wall and floor
        p.fillRect(QRectF(0, 460, 1100, 220), color('#E8D7C8'))
        for i in range(8):
            p.setPen(QPen(color('#D9C3B6'), 1)); p.drawLine(0, 478+i*29, 1100, 478+i*29)
        # window & seasons
        round_rect(p, 744, 93, 276, 284, 18, '#FDF9F5')
        sky = {'Зима':'#C7E4F2', 'Весна':'#C9E7E2', 'Лето':'#BCE4F5','Осень':'#F6DAC8'}[self.c.settings['season']]
        round_rect(p, 760, 109, 244, 253, 6, sky)
        ellipse(p, 908, 135, 57, 57, '#FFF4C1')
        for n in range(5):
            x = 774+n*54
            ellipse(p, x-8, 290, 93, 100, '#93BDB1' if self.c.settings['season'] != 'Осень' else '#D99C69')
        p.setPen(QPen(color('#FFFFFF'), 10)); p.drawLine(882, 110, 882, 360)
        p.drawLine(760, 245, 1004, 245)
        random.seed(17)
        for i in range(27):
            x=768+(i*59)%225; y=120+(i*79+self.c.tick*({ 'Зима':2,'Весна':1,'Лето':0,'Осень':2}[self.c.settings['season']]))%227
            season=self.c.settings['season']
            if season == 'Зима': ellipse(p, x, y, 5, 5, '#FFFFFF')
            if season == 'Весна': ellipse(p, x, y, 6, 4, '#F7ACCA')
            if season == 'Осень': ellipse(p, x, y, 8, 5, '#CF8A45')
        if self.c.settings['season'] == 'Лето':
            p.setPen(QPen(color('#FFF5C0', 120), 3))
            for angle in range(0, 360, 35):
                a=math.radians(angle); p.drawLine(int(935+36*math.cos(a)), int(163+36*math.sin(a)),
                                                int(935+60*math.cos(a)), int(163+60*math.sin(a)))
        # title sign
        round_rect(p, 78, 86, 600, 116, 23, '#FEF8F3', '#D7B2AC', 3)
        label(p, 90, 101, 575, 76, 'ИП БОГОЯВЛЕНСКАЯ', 31, '#986E81', True)
        label(p, 180, 161, 385, 26, 'уютный офис · каждый день', 11, '#B198A3')
        # wall ornament
        ellipse(p, 127, 267, 60, 60, '#EFC0C9')
        ellipse(p, 140, 280, 34, 34, '#FDF2D6')
        round_rect(p, 50, 397, 215, 107, 24, '#DDC3AF')
        round_rect(p, 65, 367, 185, 76, 15, '#E3BBAF')
        # desks in the back
        for x in (80, 667):
            round_rect(p, x, 487, 273, 20, 8, '#B28A78')
            round_rect(p, x+17, 503, 17, 105, 3, '#947769')
            round_rect(p, x+239, 503, 17, 105, 3, '#947769')
            round_rect(p, x+76, 528, 120, 92, 28, '#B8A5BB')
        # central table, computer screen and lamp
        round_rect(p, 330, 417, 405, 27, 9, '#AD877A')
        round_rect(p, 351, 437, 18, 156, 3, '#97776E')
        round_rect(p, 690, 437, 18, 156, 3, '#97776E')
        round_rect(p, 430, 273, 212, 137, 15, '#636074')
        self.comp_rect = QRectF(430, 273, 212, 137)
        if self.c.settings['computer_on']:
            round_rect(p, 442, 284, 188, 111, 9, '#C8E9E6')
            for i in range(6):
                w=55+(i*27+self.c.tick*5)%104
                round_rect(p, 457, 303+i*13, w, 5, 2, '#80B9B8' if i%2 else '#F7F5E6')
        else: round_rect(p, 442, 284, 188, 111, 9, '#2C2939')
        round_rect(p, 524, 410, 19, 19, 3, '#797386')
        round_rect(p, 484, 428, 98, 7, 3, '#797386')
        round_rect(p, 482, 448, 135, 14, 6, '#EBD6D2')
        ellipse(p, 628, 436, 25, 31, '#F3E4DA')
        # plant
        round_rect(p, 969, 455, 74, 95, 12, '#D4AA9C')
        for i in range(9):
            a=2*math.pi*i/9
            ellipse(p, 980+25*math.sin(a), 420+35*math.cos(a), 31, 43, '#94B89A')
        # office mode switch
        round_rect(p, 851, 18, 228, 45, 17, '#967489')
        label(p, 853, 20, 224, 42, '— Свернуть офис', 14, '#FFFFFF', True)
        self.button_rect = QRectF(851, 18, 228, 45)
        p.end()

    def mousePressEvent(self, event):
        point = QPoint(round(event.x()*1100/self.width()), round(event.y()*680/self.height()))
        if self.button_rect.contains(point): self.c.toggle_compact()
        elif self.comp_rect.contains(point):
            self.c.settings['computer_on'] = not self.c.settings['computer_on']
            self.c.persist()
            if self.c.settings['computer_on']: self.c.greet()
            self.update()


class BottomBar(QWidget):
    def __init__(self, controller):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.c = controller
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedHeight(54)
        self.setWindowTitle('Панель котика')
        self.enable_clickthrough()

    def enable_clickthrough(self):
        if sys.platform == 'win32':
            try:
                hwnd = int(self.winId())
                GWL_EXSTYLE=-20; WS_EX_TRANSPARENT=0x20; WS_EX_LAYERED=0x80000
                user32=ctypes.windll.user32
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                    user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_TRANSPARENT | WS_EX_LAYERED)
            except Exception: pass
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = painter(self)
        round_rect(p, 0, 0, self.width(), self.height(), 19, color('#FFF8F8', 207))
        label(p, 20, 4, 240, 44, datetime.now().strftime('%H:%M:%S   %d.%m.%Y'), 13, '#5C4C60', True, Qt.AlignLeft|Qt.AlignVCenter)
        fed = self.c.settings['fed_date']==date.today().isoformat()
        label(p, 270, 6, 188, 40, 'Сытость: ' + ('♥ сытый' if fed else '○ голодный'), 11, '#9B7488', True)
        label(p, max(472, self.width()-340), 5, 318, 42, self.c.weather, 12, '#6A5B70', False, Qt.AlignRight|Qt.AlignVCenter)
        p.end()


class CatOverlay(QWidget):
    def __init__(self, controller):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.c = controller
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setFixedSize(190, 191)
        self.hearts = []
        self.apply_mask(False)
        self.last_pet = 0

    def apply_mask(self, speech):
        # Only the cat and speech bubble receive mouse clicks; other pixels pass through.
        region = QRegion(26, 68, 143, 118, QRegion.Ellipse)
        region = region.united(QRegion(35, 49, 118, 80, QRegion.Ellipse))
        if speech: region = region.united(QRegion(3, 5, 181, 39))
        self.setMask(region)

    def paintEvent(self, event):
        p = painter(self)
        for x, y, life in self.hearts:
            label(p, x, y, 36, 32, '♥', 20, '#E99CAF', True)
        if self.c.speech_until > datetime.now():
            round_rect(p, 3, 5, 181, 39, 13, color('#FFFCFA', 245))
            label(p, 9, 6, 170, 35, self.c.speech, 11, '#966D84', True)
        jump = 15*abs(math.sin(self.c.tick*0.31)) if self.c.mood=='happy' and self.c.mood_until>datetime.now() else 0
        paint_cat(p, 18, 47-jump, 1.0, self.c.settings, self.c.tick,
                  self.c.mood if self.c.mood_until>datetime.now() else 'normal',
                  self.c.speech_until>datetime.now())
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton: self.c.pet()
        elif event.button() == Qt.RightButton: self.c.open_settings()

    def mouseMoveEvent(self, event):
        if 35 < event.x() < 156 and 66 < event.y() < 173:
            if self.c.tick-self.last_pet > 13:
                self.last_pet = self.c.tick
                self.c.pet(quiet=True)


class SettingsDialog(QDialog):
    def __init__(self, controller):
        super().__init__(controller.office)
        self.c = controller
        self.setWindowTitle('Настройки котика')
        self.setFixedWidth(390)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        root = QVBoxLayout(self)
        heading = QLabel('🐾 Настройки офисного котика')
        heading.setStyleSheet('font-weight: bold; font-size: 17px; color: #8E6B83; margin: 8px;')
        root.addWidget(heading)
        form = QFormLayout()
        self.fur = QComboBox(); self.fur.addItems(FUR)
        self.fur.setCurrentText(controller.settings['fur'])
        self.eyes = QComboBox(); self.eyes.addItems(EYES)
        self.eyes.setCurrentText(controller.settings['eyes'])
        self.season = QComboBox(); self.season.addItems(SEASONS)
        self.season.setCurrentText(controller.settings['season'])
        self.chub = QSlider(Qt.Horizontal); self.chub.setRange(0, 100)
        self.chub.setValue(controller.settings['chubbiness'])
        self.chub_hint = QLabel('Полнота: {}%'.format(self.chub.value()))
        self.chub.valueChanged.connect(lambda n: self.chub_hint.setText('Полнота: {}%'.format(n)))
        for key, combo in [('fur', self.fur), ('eyes', self.eyes), ('season', self.season)]:
            combo.currentTextChanged.connect(lambda text, k=key: self.live_preview(k, text))
        self.chub.valueChanged.connect(lambda n: self.live_preview('chubbiness', n))
        form.addRow('Цвет шерсти:', self.fur)
        form.addRow('Цвет глаз:', self.eyes)
        form.addRow('Время года:', self.season)
        form.addRow(self.chub_hint, self.chub)
        self.times = []
        for i, time_text in enumerate(controller.settings['avito_times']):
            edit = QTimeEdit(); edit.setDisplayFormat('HH:mm')
            from PyQt5.QtCore import QTime
            edit.setTime(QTime.fromString(time_text, 'HH:mm'))
            self.times.append(edit)
            form.addRow('Звонок Авито №{}:'.format(i+1), edit)
        root.addLayout(form)
        self.panel = QCheckBox('Показывать прозрачную нижнюю панель')
        self.panel.setChecked(controller.settings['panel'])
        self.startup = QCheckBox('Запускать вместе с Windows')
        self.startup.setChecked(controller.settings['autostart'])
        root.addWidget(self.panel); root.addWidget(self.startup)
        buttons = QHBoxLayout()
        cancel = QPushButton('Отмена'); ok = QPushButton('Сохранить')
        ok.setStyleSheet('background:#AE8197;color:white;padding:9px;border-radius:9px;')
        buttons.addWidget(cancel); buttons.addWidget(ok); root.addLayout(buttons)
        cancel.clicked.connect(self.reject); ok.clicked.connect(self.save)
        self.original = dict(controller.settings)

    def live_preview(self, key, value):
        self.c.settings[key] = value
        self.c.cat.update(); self.c.office.update()

    def reject(self):
        self.c.settings.update(self.original)
        self.c.cat.update(); self.c.office.update()
        super().reject()

    def save(self):
        data = self.c.settings
        data.update({'fur':self.fur.currentText(), 'eyes':self.eyes.currentText(),
                     'season':self.season.currentText(), 'chubbiness':self.chub.value(),
                     'avito_times':[e.time().toString('HH:mm') for e in self.times],
                     'panel':self.panel.isChecked()})
        if self.startup.isChecked() != self.original['autostart']:
            ok, reason = set_autostart(self.startup.isChecked())
            if not ok:
                QMessageBox.warning(self, 'Автозапуск', 'Не удалось изменить автозапуск: '+reason)
            else: data['autostart'] = self.startup.isChecked()
        self.c.persist(); self.c.layout_windows(); self.c.setup_schedule()
        super().accept()


class QuestionDialog(QDialog):
    def __init__(self, controller):
        super().__init__()
        self.c=controller
        self.setWindowTitle('Вопрос от котика')
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        box=QVBoxLayout(self)
        title=QLabel('🐱 Аня, закрыты ли заявки?')
        title.setStyleSheet('font-size: 18px; padding: 18px; color:#8F687F;')
        box.addWidget(title)
        row=QHBoxLayout()
        yes=QPushButton('Да, всё закрыто!'); no=QPushButton('Ещё нет')
        row.addWidget(yes); row.addWidget(no); box.addLayout(row)
        yes.clicked.connect(lambda: self.answer(True)); no.clicked.connect(lambda: self.answer(False))

    def answer(self, closed):
        self.c.set_requests(closed)
        self.accept()


class CornerControl(QWidget):
    def __init__(self, controller):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.c=controller
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(64, 64)
        self.setToolTip('Открыть офис / свернуть офис. Правый клик — меню.')

    def paintEvent(self, event):
        p=painter(self)
        ellipse(p, 3, 3, 56, 56, '#B58CA2')
        label(p, 5, 6, 52, 48, '⌂' if self.c.settings['compact'] else '—', 28, '#FFFFFF', True)
        p.end()

    def mousePressEvent(self, event):
        if event.button()==Qt.RightButton: self.c.menu.exec_(self.mapToGlobal(event.pos()))
        else: self.c.toggle_compact()


class Controller(QObject):
    def __init__(self, app):
        super().__init__()
        self.app=app
        self.settings=load_settings()
        self.tick=0
        self.weather='Омск  загрузка погоды…'
        self.weather_worker=None
        self.speech=''; self.speech_until=datetime.min
        self.mood='normal'; self.mood_until=datetime.min
        self.cat_x=170.0; self.cat_velocity=1.2
        self.office=Office(self)
        self.bar=BottomBar(self)
        self.cat=CatOverlay(self)
        self.corner=CornerControl(self)
        self.menu=QMenu()
        self.setup_tray()
        self.office.showMaximized()
        if self.settings['compact']: self.office.hide()
        self.layout_windows()
        self.bar.show() if self.settings['panel'] else self.bar.hide()
        self.cat.show(); self.corner.show()
        self.setup_schedule(initial=True)
        self.timer=QTimer(self); self.timer.timeout.connect(self.advance); self.timer.start(60)
        self.clock=QTimer(self); self.clock.timeout.connect(self.check_clock); self.clock.start(1000)
        self.weather_clock=QTimer(self); self.weather_clock.timeout.connect(self.fetch_weather)
        self.weather_clock.start(15*60*1000)
        self.fetch_weather()
        QTimer.singleShot(900, self.greet)
        QTimer.singleShot(1700, self.ask_morning)
        self.app.aboutToQuit.connect(self.persist)

    def persist(self):
        try: save_settings(self.settings)
        except OSError as exc: print('Сохранение настроек:', exc, file=sys.stderr)

    def setup_tray(self):
        pm=QPixmap(64,64); pm.fill(Qt.transparent)
        p=QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        ellipse(p, 6, 7, 52, 52, '#B58CA2')
        label(p, 10, 9, 44, 44, '♥', 26, '#FFFFFF', True)
        p.end()
        self.tray=QSystemTrayIcon(QIcon(pm), self.app)
        self.tray.setToolTip(APP_NAME)
        self.a_office=self.menu.addAction('Открыть / свернуть офис')
        self.a_office.triggered.connect(self.toggle_compact)
        self.menu.addAction('⚙ Настройки', self.open_settings)
        self.menu.addAction('🍽 Покормить', self.feed)
        self.menu.addAction('✅ Заявки закрыты', lambda: self.set_requests(True))
        self.menu.addAction('📋 Заявки ещё не закрыты', lambda: self.set_requests(False))
        self.menu.addAction('🐾 Показать вопрос о заявках', self.show_question)
        self.menu.addSeparator()
        self.menu.addAction('Выход', self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason: self.toggle_compact() if reason==QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def quit(self):
        self.persist()
        self.tray.hide(); self.app.quit()

    def layout_windows(self):
        screen=QApplication.primaryScreen().availableGeometry()
        self.corner.move(screen.right()-75, screen.top()+9)
        self.bar.setGeometry(screen.left()+16, screen.bottom()-52, screen.width()-32, 50)
        if self.settings['panel']: self.bar.show()
        else: self.bar.hide()
        self.cat_x=max(screen.left(), min(self.cat_x, screen.right()-190))
        self.cat.move(int(self.cat_x), screen.bottom()-188)

    def toggle_compact(self):
        self.settings['compact']=not self.settings['compact']
        if self.settings['compact']:
            self.office.hide()
        else:
            self.office.showMaximized(); self.office.raise_()
        self.persist(); self.corner.update()

    def open_settings(self):
        dialog=SettingsDialog(self)
        dialog.exec_()

    def greet(self):
        self.say('Привет, Аня!', 5)

    def say(self, message, seconds=6):
        self.speech=message
        self.speech_until=datetime.now()+timedelta(seconds=seconds)
        self.cat.apply_mask(True)
        self.cat.update()

    def beep(self):
        QApplication.beep()

    def pet(self, quiet=False):
        self.cat.hearts.extend([(random.randint(40,130), random.randint(45,95), 24) for _ in range(3)])
        self.mood='happy'; self.mood_until=datetime.now()+timedelta(seconds=2)
        if not quiet: self.beep(); self.say('Мур-р-р! ♥', 2)

    def feed(self):
        today=date.today().isoformat()
        if self.settings['fed_date']==today:
            self.say('Я уже сытый сегодня!', 4)
            self.tray.showMessage('Котик сыт', 'Сегодня котик уже покушал.', QSystemTrayIcon.Information, 3500)
            return
        self.settings['fed_date']=today; self.persist()
        self.mood='happy'; self.mood_until=datetime.now()+timedelta(seconds=7)
        self.say('Ням! Спасибо, Аня! ♥', 6); self.beep()

    def set_requests(self, closed):
        self.settings['requests_date']=date.today().isoformat()
        self.settings['requests_closed']=closed
        self.settings['remind_last']=''
        self.persist()
        if closed:
            self.mood='happy'; self.mood_until=datetime.now()+timedelta(seconds=9)
            self.say('Ура! Все заявки закрыты!', 7); self.beep()
        else:
            self.mood='sad'; self.mood_until=datetime.now()+timedelta(seconds=10)
            self.say('Жду закрытия заявок…', 8)

    def show_question(self):
        if getattr(self, 'question', None) and self.question.isVisible():
            self.question.raise_(); self.question.activateWindow(); return
        self.question=QuestionDialog(self)
        self.question.show(); self.question.raise_(); self.question.activateWindow()

    def ask_morning(self):
        today=date.today().isoformat()
        if self.settings['morning_asked_date'] != today:
            self.settings['morning_asked_date']=today
            self.settings['requests_date']=today
            self.settings['requests_closed']=False
            self.persist(); self.show_question()

    def setup_schedule(self, initial=False):
        # Past slots on a fresh app start are not replayed all at once.
        today=date.today().isoformat()
        fired=self.settings.get('avito_fired', {})
        if fired.get('date') != today:
            fired={'date':today,'slots':[]}
            if initial:
                now=datetime.now().strftime('%H:%M')
                fired['slots']=[str(i) for i,t in enumerate(self.settings['avito_times']) if t<now]
            self.settings['avito_fired']=fired
            self.persist()

    def check_clock(self):
        now=datetime.now()
        self.bar.update()
        if self.tick%20==0: self.layout_windows()
        today=now.date().isoformat()
        if self.settings['avito_fired'].get('date')!=today:
            self.setup_schedule()
        if self.settings['requests_date']!=today and self.settings['morning_asked_date']!=today:
            self.ask_morning()
        current=now.strftime('%H:%M')
        fired=self.settings['avito_fired']['slots']
        for i, time_text in enumerate(self.settings['avito_times']):
            # One notification per slot per day, while the app is running.
            if current==time_text and str(i) not in fired:
                fired.append(str(i)); self.persist()
                self.say('Аня, пора позвонить на Авито!', 13)
                self.beep()
                self.tray.showMessage('Звонок на Авито', 'Аня, пора позвонить на Авито!', QSystemTrayIcon.Information, 11000)
        if not self.settings['requests_closed'] and self.settings['morning_asked_date']==today:
            stamp=self.settings.get('remind_last','')
            if now.hour in range(9, 21) and (not stamp or (now-datetime.fromisoformat(stamp)).total_seconds()>90*60):
                self.settings['remind_last']=now.isoformat(); self.persist()
                self.say('Аня, не забудь закрыть заявки!', 9)
                self.tray.showMessage('Напоминание о заявках', 'Аня, заявки ещё не закрыты!', QSystemTrayIcon.Information, 7500)

    def advance(self):
        self.tick+=1
        screen=QApplication.primaryScreen().availableGeometry()
        start=screen.left()+15; end=screen.right()-185
        if self.tick % 700==0: self.cat_velocity *= -1
        if (self.tick//550)%4==2:
            pos=QCursor.pos()
            if abs(pos.y()-(screen.bottom()-120))<240:
                self.cat_velocity=2.7 if pos.x()>self.cat_x+100 else -2.7
        self.cat_x+=self.cat_velocity
        if self.cat_x<start or self.cat_x>end:
            self.cat_x=max(start,min(end,self.cat_x)); self.cat_velocity*=-1
        self.cat.move(int(self.cat_x), screen.bottom()-188)
        self.cat.hearts=[(x, y-1.35, life-1) for x,y,life in self.cat.hearts if life>0]
        self.cat.apply_mask(self.speech_until > datetime.now())
        self.cat.update()
        if self.office.isVisible(): self.office.update()

    def fetch_weather(self):
        if self.weather_worker and self.weather_worker.isRunning(): return
        self.weather_worker=WeatherWorker()
        self.weather_worker.done.connect(self.got_weather)
        self.weather_worker.start()

    def got_weather(self, text):
        self.weather=text
        self.bar.update()


def main():
    if sys.platform=='win32':
        try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('CatHelper.Anya.1')
        except Exception: pass
    app=QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    controller=Controller(app)
    sys.exit(app.exec_())


if __name__=='__main__': main()
