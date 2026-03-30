#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HP LaserJet Network Scanner Application
Сканирование документов через сеть с последующим редактированием порядка страниц
Поддержка Windows 10/11
"""

import sys
import os
import io
import time
import threading
import traceback
from pathlib import Path
from datetime import datetime

# GUI библиотеки
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

# Сетевое сканирование через HTTP (для HP сканеров)
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

# Для работы с PDF
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Альтернативная библиотека для PDF
try:
    import img2pdf
    IMG2PDF_AVAILABLE = True
except ImportError:
    IMG2PDF_AVAILABLE = False


class ScanImage:
    """Класс для хранения отсканированного изображения"""
    def __init__(self, image_data: bytes, page_number: int, timestamp: float):
        self.image_data = image_data
        self.page_number = page_number
        self.timestamp = timestamp
        self.thumbnail = None
        
    def get_image(self):
        """Получить PIL Image из данных"""
        try:
            return Image.open(io.BytesIO(self.image_data))
        except Exception:
            return None
    
    def create_thumbnail(self, size=(150, 200)):
        """Создать миниатюру для отображения"""
        img = self.get_image()
        if img:
            img_copy = img.copy()
            img_copy.thumbnail(size, Image.Resampling.LANCZOS)
            self.thumbnail = img_copy
        return self.thumbnail


class HPScanner:
    """Класс для сканирования через сеть на HP принтеры"""
    
    def __init__(self, ip_address: str, timeout: int = 30):
        self.ip_address = ip_address
        self.timeout = timeout
        self.base_url = f"http://{ip_address}"
        self.session = requests.Session()
        
    def check_connection(self) -> bool:
        """Проверить подключение к сканеру"""
        try:
            response = self.session.get(f"{self.base_url}/DevMgmt/ProductStatusDyn.xml", 
                                       timeout=5)
            return response.status_code == 200
        except (RequestException, Timeout, ConnectionError):
            pass
        
        # Пробуем альтернативные эндпоинты
        endpoints = [
            "/eSCL/ScannerStatus.xml",
            "/ScanJobStatus.xml",
            "/",
        ]
        
        for endpoint in endpoints:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}", timeout=5)
                if response.status_code == 200:
                    return True
            except (RequestException, Timeout, ConnectionError):
                continue
        
        return False
    
    def scan_page(self, color_mode: str = "Color", resolution: int = 300) -> bytes:
        """
        Отсканировать одну страницу
        color_mode: "Color", "Grayscale", "BlackWhite"
        resolution: DPI (150, 200, 300, 600)
        """
        # HP eSCL протокол (AirScan)
        scan_settings = f"""<?xml version="1.0" encoding="UTF-8"?>
<scanSettings xmlns="http://schemas.hp.com/imaging/escl/v20110503">
    <imageSettings>
        <colorMode>{color_mode}</colorMode>
        <compressionQuality>75</compressionQuality>
        <documentFormat>application/octet-stream</documentFormat>
        <inputSource>Feeder</inputSource>
        <resolution>{resolution}</resolution>
        <xResolution>{resolution}</xResolution>
        <yResolution>{resolution}</yResolution>
    </imageSettings>
</scanSettings>"""

        try:
            # Инициализация сканирования
            headers = {"Content-Type": "application/xml"}
            
            response = self.session.post(
                f"{self.base_url}/eSCL/ScanJobs",
                data=scan_settings,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code not in [200, 201]:
                # Пробуем альтернативный метод для некоторых HP принтеров
                return self._scan_legacy(color_mode, resolution)
            
            # Получаем URL для получения отсканированного изображения
            job_url = response.headers.get('Location', '')
            if not job_url:
                return self._scan_legacy(color_mode, resolution)
            
            # Ждем завершения сканирования и получаем данные
            max_attempts = 60
            for attempt in range(max_attempts):
                time.sleep(0.5)
                
                status_response = self.session.get(job_url + "/NextPage", timeout=10)
                
                if status_response.status_code == 200:
                    return status_response.content
                elif status_response.status_code == 404:
                    # Страница ещё не готова или сканирование завершено
                    continue
                else:
                    break
            
            raise Exception("Таймаут ожидания сканирования")
            
        except (RequestException, Timeout, ConnectionError) as e:
            # Пробуем упрощённый метод
            return self._scan_legacy(color_mode, resolution)
    
    def _scan_legacy(self, color_mode: str = "Color", resolution: int = 300) -> bytes:
        """
        Упрощённый метод сканирования для старых моделей
        """
        # Попытка использовать TWAIN через сеть (если доступен)
        # Или прямой запрос к сканеру
        
        scan_urls = [
            f"{self.base_url}/Scan/Index.html",
            f"{self.base_url}/web_interface/scan.htm",
        ]
        
        # Для многих HP LaserJet нужно использовать встроенный веб-интерфейс
        # или стороннее ПО. Здесь мы эмулируем запрос.
        
        # Прямой запрос на получение изображения со сканера
        try:
            # Некоторые модели поддерживают прямой доступ
            response = self.session.get(
                f"{self.base_url}/TSS/ScanToPC",
                params={
                    'color': '1' if color_mode == "Color" else '0',
                    'dpi': str(resolution),
                    'format': 'jpeg'
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200 and len(response.content) > 1000:
                return response.content
        except:
            pass
        
        raise Exception(
            f"Не удалось выполнить сканирование с устройства {self.ip_address}. "
            f"Проверьте:\n"
            f"1. Принтер включен и подключен к сети\n"
            f"2. IP-адрес указан верно\n"
            f"3. Функция сканирования по сети включена в настройках принтера\n"
            f"4. Брандмауэр не блокирует соединение"
        )


class ScannerApp:
    """Основное приложение для сканирования"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet Scanner - Сканер документов")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        
        # Данные сканирования
        self.scanned_pages: list[ScanImage] = []
        self.scanner = None
        self.is_scanning = False
        self.scan_thread = None
        
        # Настройки
        self.ip_address = tk.StringVar(value="")
        self.color_mode = tk.StringVar(value="Color")
        self.resolution = tk.IntVar(value=300)
        
        # Создание интерфейса
        self._create_main_layout()
        self._create_control_panel()
        self._create_preview_area()
        self._create_status_bar()
        
        # Привязка событий для drag-and-drop
        self._setup_drag_drop()
        
        # Обработка закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Логирование ошибок
        self._log_message("Приложение готово к работе")
        
    def _create_main_layout(self):
        """Создать основную разметку"""
        # Главный контейнер
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
    def _create_control_panel(self):
        """Создать панель управления"""
        control_frame = ttk.LabelFrame(self.main_frame, text="Настройки сканирования", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Row 0: IP адрес
        ttk.Label(control_frame, text="IP адрес сканера:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.ip_entry = ttk.Entry(control_frame, textvariable=self.ip_address, width=20)
        self.ip_entry.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        self.btn_check_connection = ttk.Button(
            control_frame, text="Проверить связь", command=self._check_connection
        )
        self.btn_check_connection.grid(row=0, column=2, padx=5)
        
        # Row 1: Цвет и разрешение
        ttk.Label(control_frame, text="Режим:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.color_combo = ttk.Combobox(
            control_frame, 
            textvariable=self.color_mode,
            values=["Color", "Grayscale", "BlackWhite"],
            state="readonly",
            width=15
        )
        self.color_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(control_frame, text="Разрешение (DPI):").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        
        self.resolution_combo = ttk.Combobox(
            control_frame,
            textvariable=self.resolution,
            values=[150, 200, 300, 600],
            state="readonly",
            width=10
        )
        self.resolution_combo.grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)
        
        # Row 2: Кнопки управления сканированием
        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=2, column=0, columnspan=6, pady=10)
        
        self.btn_scan = ttk.Button(
            button_frame, text="📷 Сканировать страницу", command=self._start_scan,
            style="Accent.TButton"
        )
        self.btn_scan.pack(side=tk.LEFT, padx=5)
        
        self.btn_finish = ttk.Button(
            button_frame, text="✓ Завершить и перейти к редактору", 
            command=self._finish_scanning, state=tk.DISABLED
        )
        self.btn_finish.pack(side=tk.LEFT, padx=5)
        
        self.btn_clear = ttk.Button(
            button_frame, text="✗ Очистить все", command=self._clear_all
        )
        self.btn_clear.pack(side=tk.LEFT, padx=5)
        
        # Индикатор количества страниц
        self.lbl_page_count = ttk.Label(button_frame, text="Страниц: 0", font=("Arial", 10, "bold"))
        self.lbl_page_count.pack(side=tk.LEFT, padx=20)
        
    def _create_preview_area(self):
        """Создать область предпросмотра страниц"""
        preview_frame = ttk.LabelFrame(self.main_frame, text="Отсканированные страницы (перетаскивайте для изменения порядка)", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Canvas с прокруткой для миниатюр
        self.preview_canvas = tk.Canvas(preview_frame, bg="#f0f0f0", highlightthickness=0)
        
        # Scrollbars
        h_scrollbar = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.preview_canvas.xview)
        v_scrollbar = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_canvas.yview)
        
        self.preview_canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)
        
        # Grid layout
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        
        # Frame внутри canvas для размещения миниатюр
        self.thumbnails_frame = ttk.Frame(self.preview_canvas)
        self.preview_canvas.create_window((0, 0), window=self.thumbnails_frame, anchor="nw")
        
        # Binding для изменения размера
        self.thumbnails_frame.bind("<Configure>", self._on_thumbnails_configure)
        
    def _create_status_bar(self):
        """Создать строку состояния"""
        self.status_frame = ttk.Frame(self.main_frame)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = ttk.Label(self.status_frame, text="Готов", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self.status_frame, variable=self.progress_var, maximum=100, mode='indeterminate'
        )
        self.progress_bar.pack(side=tk.RIGHT, padx=5, pady=2)
        
        # Текстовая консоль для логов
        self.log_text = tk.Text(self.main_frame, height=6, wrap=tk.WORD, state=tk.DISABLED, bg="#1e1e1e", fg="#00ff00")
        self.log_text.pack(fill=tk.X, pady=(5, 0))
        
        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
    def _setup_drag_drop(self):
        """Настроить drag-and-drop для миниатюр"""
        self.drag_data = {"index": None, "widget": None}
        
    def _on_thumbnails_configure(self, event):
        """Обновить область прокрутки при изменении размера"""
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))
        
    def _log_message(self, message: str):
        """Добавить сообщение в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        
    def _update_status(self, message: str):
        """Обновить строку состояния"""
        self.status_label.configure(text=message)
        self.root.update_idletasks()
        
    def _check_connection(self):
        """Проверить подключение к сканеру"""
        ip = self.ip_address.get().strip()
        if not ip:
            messagebox.showwarning("Предупреждение", "Введите IP адрес сканера")
            return
        
        self._update_status(f"Проверка подключения к {ip}...")
        self.btn_check_connection.configure(state=tk.DISABLED)
        
        def check():
            try:
                scanner = HPScanner(ip)
                if scanner.check_connection():
                    self.root.after(0, lambda: messagebox.showinfo("Успех", f"Сканер {ip} доступен!"))
                    self.root.after(0, lambda: self._update_status(f"Сканер {ip} подключен"))
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Ошибка", 
                        f"Не удалось подключиться к сканеру {ip}.\n\n"
                        f"Возможные причины:\n"
                        f"• Принтер выключен или не в сети\n"
                        f"• Неверный IP адрес\n"
                        f"• Брандмауэр блокирует соединение\n"
                        f"• Функция сетевого сканирования отключена"
                    ))
                    self.root.after(0, lambda: self._update_status("Ошибка подключения"))
            except Exception as e:
                error_msg = f"Ошибка проверки: {str(e)}"
                self.root.after(0, lambda: messagebox.showerror("Ошибка", error_msg))
                self.root.after(0, lambda: self._update_status(error_msg))
            finally:
                self.root.after(0, lambda: self.btn_check_connection.configure(state=tk.NORMAL))
        
        thread = threading.Thread(target=check, daemon=True)
        thread.start()
        
    def _start_scan(self):
        """Начать сканирование одной страницы"""
        if self.is_scanning:
            messagebox.showwarning("Предупреждение", "Сканирование уже выполняется")
            return
        
        ip = self.ip_address.get().strip()
        if not ip:
            messagebox.showwarning("Предупреждение", "Введите IP адрес сканера")
            return
        
        self.is_scanning = True
        self.btn_scan.configure(state=tk.DISABLED)
        self.btn_finish.configure(state=tk.DISABLED)
        self.progress_bar.start()
        
        color = self.color_mode.get()
        resolution = self.resolution.get()
        
        def scan_task():
            try:
                self._update_status("Инициализация сканера...")
                self._log_message(f"Подключение к сканеру {ip}...")
                
                scanner = HPScanner(ip, timeout=60)
                
                self._update_status(f"Сканирование страницы {len(self.scanned_pages) + 1}...")
                self._log_message(f"Начало сканирования (режим: {color}, разрешение: {resolution} DPI)")
                
                start_time = time.time()
                image_data = scanner.scan_page(color_mode=color, resolution=resolution)
                elapsed = time.time() - start_time
                
                if image_data and len(image_data) > 1000:
                    # Создать объект страницы
                    page = ScanImage(
                        image_data=image_data,
                        page_number=len(self.scanned_pages) + 1,
                        timestamp=time.time()
                    )
                    
                    self.root.after(0, lambda: self._add_scanned_page(page))
                    self.root.after(0, lambda: self._log_message(
                        f"Страница {page.page_number} успешно отсканирована за {elapsed:.1f} сек ({len(image_data)} байт)"
                    ))
                    self.root.after(0, lambda: self._update_status(
                        f"Страница {page.page_number} отсканирована"
                    ))
                else:
                    raise Exception("Получены пустые данные или ошибка сканирования")
                    
            except Exception as e:
                error_msg = f"Ошибка при сканировании страницы {len(self.scanned_pages) + 1}: {str(e)}"
                self._log_message(f"❌ {error_msg}")
                self._log_message(traceback.format_exc())
                
                # Показать ошибку но не закрывать приложение
                self.root.after(0, lambda: messagebox.showerror(
                    "Ошибка сканирования",
                    f"{error_msg}\n\n"
                    f"Проверьте:\n"
                    f"1. Принтер включен и готов к сканированию\n"
                    f"2. В лотке есть бумага\n"
                    f"3. Нет замятия бумаги\n"
                    f"4. IP адрес указан правильно"
                ))
                self.root.after(0, lambda: self._update_status("Ошибка сканирования"))
            finally:
                self.is_scanning = False
                self.root.after(0, self._scan_complete)
        
        self.scan_thread = threading.Thread(target=scan_task, daemon=True)
        self.scan_thread.start()
        
    def _scan_complete(self):
        """Завершение сканирования"""
        self.progress_bar.stop()
        self.btn_scan.configure(state=tk.NORMAL)
        
        if len(self.scanned_pages) > 0:
            self.btn_finish.configure(state=tk.NORMAL)
            
    def _add_scanned_page(self, page: ScanImage):
        """Добавить отсканированную страницу в интерфейс"""
        self.scanned_pages.append(page)
        self.lbl_page_count.configure(text=f"Страниц: {len(self.scanned_pages)}")
        
        # Создать миниатюру
        page.create_thumbnail()
        
        # Добавить виджет миниатюры
        self._create_thumbnail_widget(page, len(self.scanned_pages) - 1)
        
    def _create_thumbnail_widget(self, page: ScanImage, index: int):
        """Создать виджет миниатюры страницы"""
        thumb_frame = ttk.Frame(self.thumbnails_frame, relief=tk.RAISED, borderwidth=2)
        thumb_frame.pack(side=tk.LEFT, padx=5, pady=5, anchor=tk.NW)
        
        if page.thumbnail:
            photo = ImageTk.PhotoImage(page.thumbnail)
            label = tk.Label(thumb_frame, image=photo)
            label.image = photo  # Сохранить ссылку
            label.pack(padx=2, pady=2)
        
        # Номер страницы
        num_label = ttk.Label(thumb_frame, text=f"Стр. {index + 1}", font=("Arial", 9))
        num_label.pack(pady=2)
        
        # Кнопка удаления
        del_btn = ttk.Button(
            thumb_frame, text="✕", width=2,
            command=lambda idx=index: self._remove_page(idx)
        )
        del_btn.pack(pady=2)
        
        # Настроить drag-and-drop
        thumb_frame.bind("<ButtonPress-1>", lambda e, idx=index: self._on_drag_start(e, idx))
        thumb_frame.bind("<B1-Motion>", lambda e, idx=index: self._on_drag_motion(e, idx))
        thumb_frame.bind("<ButtonRelease-1>", lambda e, idx=index: self._on_drag_drop(e, idx))
        
        for child in thumb_frame.winfo_children():
            child.bind("<ButtonPress-1>", lambda e, idx=index: self._on_drag_start(e, idx))
            child.bind("<B1-Motion>", lambda e, idx=index: self._on_drag_motion(e, idx))
            child.bind("<ButtonRelease-1>", lambda e, idx=index: self._on_drag_drop(e, idx))
        
        # Сохранить ссылку на виджет
        page.thumbnail_widget = thumb_frame
        
    def _on_drag_start(self, event, index):
        """Начало перетаскивания"""
        widget = self.thumbnails_frame.winfo_children()[index]
        self.drag_data["index"] = index
        self.drag_data["widget"] = widget
        widget.configure(relief=tk.SUNKEN)
        
    def _on_drag_motion(self, event, index):
        """Перемещение при перетаскивании"""
        # Можно добавить визуальный эффект
        pass
        
    def _on_drag_drop(self, event, index):
        """Завершение перетаскивания"""
        if self.drag_data["index"] is None:
            return
            
        from_index = self.drag_data["index"]
        to_index = index
        
        if from_index != to_index and from_index is not None:
            # Поменять местами элементы в списке
            self.scanned_pages[from_index], self.scanned_pages[to_index] = \
                self.scanned_pages[to_index], self.scanned_pages[from_index]
            
            # Перерисовать все миниатюры
            self._refresh_thumbnails()
            
            self._log_message(f"Страницы {from_index + 1} и {to_index + 1} поменяны местами")
        
        # Сбросить состояние
        if self.drag_data["widget"]:
            self.drag_data["widget"].configure(relief=tk.RAISED)
        self.drag_data["index"] = None
        self.drag_data["widget"] = None
        
    def _refresh_thumbnails(self):
        """Обновить отображение всех миниатюр"""
        # Удалить все виджеты
        for widget in self.thumbnails_frame.winfo_children():
            widget.destroy()
        
        # Пересоздать
        for i, page in enumerate(self.scanned_pages):
            page.page_number = i + 1
            self._create_thumbnail_widget(page, i)
            
        self.lbl_page_count.configure(text=f"Страниц: {len(self.scanned_pages)}")
        
    def _remove_page(self, index):
        """Удалить страницу"""
        if 0 <= index < len(self.scanned_pages):
            confirm = messagebox.askyesno("Подтверждение", "Удалить эту страницу?")
            if confirm:
                self.scanned_pages.pop(index)
                self._refresh_thumbnails()
                self._log_message(f"Страница {index + 1} удалена")
                
                if len(self.scanned_pages) == 0:
                    self.btn_finish.configure(state=tk.DISABLED)
                    
    def _clear_all(self):
        """Очистить все страницы"""
        if len(self.scanned_pages) == 0:
            return
            
        confirm = messagebox.askyesno("Подтверждение", "Удалить все отсканированные страницы?")
        if confirm:
            self.scanned_pages.clear()
            
            for widget in self.thumbnails_frame.winfo_children():
                widget.destroy()
                
            self.lbl_page_count.configure(text="Страниц: 0")
            self.btn_finish.configure(state=tk.DISABLED)
            self._log_message("Все страницы удалены")
            
    def _finish_scanning(self):
        """Завершить сканирование и сохранить в PDF"""
        if len(self.scanned_pages) == 0:
            messagebox.showwarning("Предупреждение", "Нет отсканированных страниц")
            return
        
        # Диалог сохранения
        default_filename = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF файлы", "*.pdf"), ("Все файлы", "*.*")],
            initialfile=default_filename,
            title="Сохранить как"
        )
        
        if not file_path:
            return
        
        self._update_status("Сохранение в PDF...")
        self._log_message(f"Сохранение в {file_path}...")
        
        try:
            # Конвертировать в PDF
            success = self._save_to_pdf(file_path)
            
            if success:
                self._log_message(f"✓ Файл успешно сохранён: {file_path}")
                self._update_status("Готово!")
                
                messagebox.showinfo(
                    "Успех", 
                    f"Документ успешно сохранён!\n\n"
                    f"Файл: {file_path}\n"
                    f"Страниц: {len(self.scanned_pages)}"
                )
                
                # Предложить открыть файл
                if messagebox.askyesno("Открыть файл", "Открыть сохранённый PDF файл?"):
                    os.startfile(file_path)
            else:
                raise Exception("Не удалось создать PDF")
                
        except Exception as e:
            error_msg = f"Ошибка сохранения: {str(e)}"
            self._log_message(f"❌ {error_msg}")
            self._log_message(traceback.format_exc())
            messagebox.showerror("Ошибка", error_msg)
            self._update_status("Ошибка сохранения")
            
    def _save_to_pdf(self, file_path: str) -> bool:
        """Сохранить отсканированные страницы в PDF файл"""
        if not self.scanned_pages:
            return False
        
        # Попытка использовать img2pdf (лучшее качество)
        if IMG2PDF_AVAILABLE:
            try:
                temp_images = []
                
                for page in self.scanned_pages:
                    # Сохранить во временный файл
                    temp_path = f"temp_{page.page_number}.jpg"
                    with open(temp_path, 'wb') as f:
                        f.write(page.image_data)
                    temp_images.append(temp_path)
                
                # Конвертировать в PDF
                with open(file_path, 'wb') as f:
                    img2pdf.convert(temp_images, outputstream=f)
                
                # Удалить временные файлы
                for temp_path in temp_images:
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                
                return True
                
            except Exception as e:
                self._log_message(f"img2pdf ошибка: {e}, пробуем альтернативу...")
        
        # Альтернатива: reportlab
        if REPORTLAB_AVAILABLE:
            try:
                c = canvas.Canvas(file_path, pagesize=A4)
                page_width, page_height = A4
                
                for i, page in enumerate(self.scanned_pages):
                    img = page.get_image()
                    if img:
                        # Конвертировать в формат для reportlab
                        img_bytes = io.BytesIO()
                        img.save(img_bytes, format='JPEG')
                        img_bytes.seek(0)
                        
                        img_reader = ImageReader(img_bytes)
                        
                        # Масштабировать изображение под размер страницы A4
                        img_aspect = img.width / img.height
                        page_aspect = page_width / page_height
                        
                        if img_aspect > page_aspect:
                            final_width = page_width - 40
                            final_height = final_width / img_aspect
                        else:
                            final_height = page_height - 40
                            final_width = final_height * img_aspect
                        
                        x = (page_width - final_width) / 2
                        y = (page_height - final_height) / 2
                        
                        c.drawImage(img_reader, x, y, final_width, final_height)
                        
                        if i < len(self.scanned_pages) - 1:
                            c.showPage()
                
                c.save()
                return True
                
            except Exception as e:
                self._log_message(f"reportlab ошибка: {e}")
        
        # Минимальная реализация без внешних библиотек
        self._log_message("Попытка создания базового PDF...")
        
        # Простейший PDF (только для совместимости)
        try:
            pdf_content = self._create_minimal_pdf(file_path)
            return pdf_content
        except Exception as e:
            self._log_message(f"Минимальный PDF ошибка: {e}")
            return False
    
    def _create_minimal_pdf(self, file_path: str) -> bool:
        """Создать минимальный PDF файл (базовая реализация)"""
        # Это упрощённая версия, лучше использовать img2pdf или reportlab
        try:
            from struct import pack
            
            # Для полноценной работы нужны библиотеки
            # Предлагаем пользователю установить их
            raise Exception(
                "Для создания PDF установите одну из библиотек:\n"
                "pip install img2pdf\n"
                "или\n"
                "pip install reportlab"
            )
        except:
            raise
    
    def _on_closing(self):
        """Обработка закрытия окна"""
        if self.is_scanning:
            if not messagebox.askokcancel(
                "Выход", 
                "Сканирование выполняется. Закрыть приложение?"
            ):
                return
        
        if len(self.scanned_pages) > 0:
            result = messagebox.askyesnocancel(
                "Выход",
                "У вас есть неотсканированные страницы. Сохранить перед выходом?"
            )
            
            if result is None:  # Cancel
                return
            elif result:  # Yes
                self._finish_scanning()
        
        self.root.destroy()
        sys.exit(0)


def main():
    """Точка входа приложения"""
    
    # Проверка необходимых библиотек
    missing_libs = []
    
    if not REPORTLAB_AVAILABLE and not IMG2PDF_AVAILABLE:
        missing_libs.append("img2pdf или reportlab (для создания PDF)")
    
    try:
        import requests
    except ImportError:
        missing_libs.append("requests (для сетевого сканирования)")
    
    try:
        from PIL import Image
    except ImportError:
        missing_libs.append("Pillow (для обработки изображений)")
    
    if missing_libs:
        print("=" * 60)
        print("ОШИБКА: Отсутствуют необходимые библиотеки")
        print("=" * 60)
        print("\nУстановите недостающие пакеты:")
        print(f"pip install {' '.join(missing_libs)}\n")
        print("Или все сразу:")
        print("pip install requests Pillow img2pdf reportlab\n")
        print("=" * 60)
        
        # Не закрываем окно сразу, показываем сообщение
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Ошибка запуска",
            "Отсутствуют необходимые библиотеки:\n\n" + 
            "\n".join(missing_libs) +
            "\n\nУстановите их командой:\npip install requests Pillow img2pdf reportlab"
        )
        root.destroy()
        sys.exit(1)
    
    # Запуск приложения
    root = tk.Tk()
    
    # Установка стиля
    style = ttk.Style()
    style.theme_use('clam')
    
    # Настройка цветов
    style.configure("Accent.TButton", foreground="white", background="#0078D7")
    
    app = ScannerApp(root)
    
    # Центрирование окна
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'+{x}+{y}')
    
    root.mainloop()


if __name__ == "__main__":
    main()
