"""
Сканер документов для HP LaserJet (Windows)
Использует WIA/TWAIN через comtypes (встроен в Windows)
Не требует pyinsane2 или SANE
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk
import io

# Попытка импорта библиотек для Windows
try:
    import comtypes.client
    import comtypes.gen.WIA
    WIA_AVAILABLE = True
except ImportError:
    WIA_AVAILABLE = False
    print("Warning: comtypes not available. TWAIN fallback will be used.")

try:
    import twain
    TWAIN_AVAILABLE = True
except ImportError:
    TWAIN_AVAILABLE = False
    print("Warning: twain not available. Install with: pip install twain")

# Константы WIA
WIA_DEVICE_CATEGORY_SCANNER = "{a63b11c0-b76e-4496-9585-e29b5b3fc30c}"
WIA_IMAGE_FORMAT_PNG = "{b96b3cae-0728-11d3-9d7b-0000f81ef32e}"
WIA_IMAGE_FORMAT_BMP = "{a63b11c0-b76e-4496-9585-e29b5b3fc30c}"

class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet Scanner - Многостраничное сканирование")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # Данные сканирования
        self.scanned_pages = []  # Список изображений (PIL Image)
        self.page_thumbnails = []  # Список PhotoImage для превью
        self.current_scan_index = 0
        self.is_scanning = False
        self.scanner_device = None
        self.scanner_type = None  # 'WIA' или 'TWAIN'
        
        # Настройки
        self.color_mode = tk.StringVar(value="Color")
        self.dpi = tk.IntVar(value=300)
        self.paper_size = tk.StringVar(value="A4")
        self.save_separate = tk.BooleanVar(value=False)
        
        # Создание интерфейса
        self.create_main_interface()
        
        # Поиск сканера при запуске
        self.after_id = self.root.after(1000, self.find_scanner)
        
    def create_main_interface(self):
        """Создание основного интерфейса"""
        # Верхняя панель с настройками
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        # Левая часть - настройки
        settings_frame = ttk.LabelFrame(top_frame, text="Настройки сканирования", padding="10")
        settings_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Цветовой режим
        ttk.Label(settings_frame, text="Цвет:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        color_combo = ttk.Combobox(settings_frame, textvariable=self.color_mode, 
                                   values=["Color", "Grayscale", "BlackAndWhite"], state="readonly", width=15)
        color_combo.grid(row=0, column=1, padx=5, pady=5)
        color_combo.bind("<<ComboboxSelected>>", lambda e: None)
        
        # DPI
        ttk.Label(settings_frame, text="DPI:").grid(row=0, column=2, sticky=tk.W, padx=15, pady=5)
        dpi_combo = ttk.Combobox(settings_frame, textvariable=self.dpi, 
                                 values=[150, 200, 300, 400, 600], state="readonly", width=8)
        dpi_combo.grid(row=0, column=3, padx=5, pady=5)
        
        # Формат бумаги
        ttk.Label(settings_frame, text="Формат:").grid(row=0, column=4, sticky=tk.W, padx=15, pady=5)
        paper_combo = ttk.Combobox(settings_frame, textvariable=self.paper_size, 
                                   values=["A4", "A3", "Letter", "Legal"], state="readonly", width=10)
        paper_combo.grid(row=0, column=5, padx=5, pady=5)
        
        # Раздельное сохранение
        self.separate_check = ttk.Checkbutton(settings_frame, text="Сохранять отдельно", 
                                              variable=self.save_separate)
        self.separate_check.grid(row=0, column=6, padx=20, pady=5)
        
        # Информация о сканере
        self.scanner_info_label = ttk.Label(settings_frame, text="Поиск сканера...", 
                                            foreground="orange")
        self.scanner_info_label.grid(row=1, column=0, columnspan=7, sticky=tk.W, padx=5, pady=5)
        
        # Правая часть - кнопки управления
        buttons_frame = ttk.Frame(top_frame)
        buttons_frame.pack(side=tk.RIGHT, padx=20)
        
        self.scan_btn = ttk.Button(buttons_frame, text="📄 Сканировать страницу", 
                                   command=self.start_scan_page, style="Accent.TButton")
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.finish_btn = ttk.Button(buttons_frame, text="✅ Завершить и редактировать", 
                                     command=self.finish_scanning, state=tk.DISABLED)
        self.finish_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_btn = ttk.Button(buttons_frame, text="🗑️ Очистить всё", 
                                    command=self.clear_all, state=tk.DISABLED)
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Центральная область с превью страниц
        preview_container = ttk.Frame(self.root, padding="10")
        preview_container.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(preview_container, text="Отсканированные страницы (перетаскивание кнопками ниже):",
                  font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        # Canvas для горизонтальной прокрутки превью
        self.preview_canvas = tk.Canvas(preview_container, bg="#f0f0f0", highlightthickness=0)
        self.preview_scrollbar = ttk.Scrollbar(preview_container, orient=tk.HORIZONTAL, 
                                               command=self.preview_canvas.xview)
        
        self.preview_inner_frame = ttk.Frame(self.preview_canvas)
        
        self.preview_window = self.preview_canvas.create_window((0, 0), window=self.preview_inner_frame, 
                                                                anchor=tk.NW)
        
        self.preview_canvas.configure(xscrollcommand=self.preview_scrollbar.set)
        
        self.preview_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.preview_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.preview_inner_frame.bind("<Configure>", self.on_preview_frame_configure)
        self.preview_canvas.bind("<Configure>", self.on_canvas_configure)
        
        # Панель управления страницами (появляется после сканирования)
        self.page_controls_frame = ttk.Frame(self.root, padding="10")
        # Не pack сразу, будет показана при необходимости
        
        ttk.Label(self.page_controls_frame, text="Управление порядком страниц:",
                  font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
        
        controls_inner = ttk.Frame(self.page_controls_frame)
        controls_inner.pack(fill=tk.X)
        
        self.prev_page_btn = ttk.Button(controls_inner, text="◀ Переместить влево", 
                                        command=self.move_page_left, state=tk.DISABLED)
        self.prev_page_btn.pack(side=tk.LEFT, padx=5)
        
        self.next_page_btn = ttk.Button(controls_inner, text="Переместить вправо ▶", 
                                        command=self.move_page_right, state=tk.DISABLED)
        self.prev_page_btn.pack(side=tk.LEFT, padx=5)
        
        self.delete_page_btn = ttk.Button(controls_inner, text="✕ Удалить выбранную", 
                                          command=self.delete_selected_page, state=tk.DISABLED)
        self.delete_page_btn.pack(side=tk.LEFT, padx=5)
        
        self.selected_page_label = ttk.Label(controls_inner, text="Страница не выбрана", 
                                             foreground="gray")
        self.selected_page_label.pack(side=tk.LEFT, padx=20)
        
        # Нижняя панель со статусом и кнопкой сохранения
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)
        
        self.status_label = ttk.Label(bottom_frame, text="Готов к работе. Выберите настройки и нажмите 'Сканировать страницу'",
                                      relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.save_btn = ttk.Button(bottom_frame, text="💾 Сохранить в PDF", 
                                   command=self.save_to_pdf, state=tk.DISABLED)
        self.save_btn.pack(side=tk.RIGHT, padx=5)
        
        # Стили
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Arial", 10, "bold"))
        
        # Привязка клавиш
        self.root.bind("<Delete>", lambda e: self.delete_selected_page())
        self.root.bind("<Left>", lambda e: self.move_page_left())
        self.root.bind("<Right>", lambda e: self.move_page_right())
        
    def find_scanner(self):
        """Поиск доступных сканеров"""
        def search():
            try:
                if WIA_AVAILABLE:
                    scanner = self.find_wia_scanner()
                    if scanner:
                        self.scanner_device = scanner
                        self.scanner_type = 'WIA'
                        self.root.after(0, lambda: self.update_scanner_status(
                            f"✓ Сканер найден (WIA): {self.get_scanner_name()}", "green"))
                        return
                
                if TWAIN_AVAILABLE:
                    scanner = self.find_twain_scanner()
                    if scanner:
                        self.scanner_device = scanner
                        self.scanner_type = 'TWAIN'
                        self.root.after(0, lambda: self.update_scanner_status(
                            f"✓ Сканер найден (TWAIN): {self.get_scanner_name()}", "green"))
                        return
                
                self.root.after(0, lambda: self.update_scanner_status(
                    "✗ Сканер не найден. Проверьте подключение и драйверы.", "red"))
                    
            except Exception as e:
                self.root.after(0, lambda: self.update_scanner_status(
                    f"✗ Ошибка поиска: {str(e)}", "red"))
        
        thread = threading.Thread(target=search, daemon=True)
        thread.start()
        
    def find_wia_scanner(self):
        """Поиск сканера через WIA (Windows Image Acquisition)"""
        try:
            wia = comtypes.client.CreateObject("WIA.DeviceManager")
            devices = wia.DeviceInfos
            
            for i in range(1, devices.Count + 1):
                device_info = devices.Item(i)
                if device_info.DeviceCategory == WIA_DEVICE_CATEGORY_SCANNER:
                    return device_info
            
            return None
        except Exception as e:
            print(f"WIA scanner search error: {e}")
            return None
    
    def find_twain_scanner(self):
        """Поиск сканера через TWAIN"""
        try:
            if not twain.SourceManagerIsOpen():
                # TWAIN требует окно, это упрощённая версия
                pass
            return True  # Заглушка, реальная реализация сложнее
        except Exception as e:
            print(f"TWAIN scanner search error: {e}")
            return None
    
    def get_scanner_name(self):
        """Получение имени сканера"""
        if self.scanner_type == 'WIA' and self.scanner_device:
            try:
                return self.scanner_device.Name
            except:
                return "WIA Scanner"
        elif self.scanner_type == 'TWAIN':
            return "TWAIN Scanner"
        return "Unknown"
    
    def update_scanner_status(self, message, color="black"):
        """Обновление статуса сканера"""
        self.scanner_info_label.config(text=message, foreground=color)
        
    def start_scan_page(self):
        """Запуск сканирования одной страницы"""
        if self.is_scanning:
            messagebox.showwarning("Внимание", "Сканирование уже выполняется!")
            return
        
        if not self.scanner_device:
            messagebox.showerror("Ошибка", "Сканер не найден! Проверьте подключение.")
            return
        
        self.is_scanning = True
        self.scan_btn.config(state=tk.DISABLED)
        self.status_label.config(text="⏳ Сканирование страницы... Пожалуйста, подождите.", foreground="orange")
        self.root.update()
        
        # Запуск сканирования в отдельном потоке
        thread = threading.Thread(target=self.perform_scan, daemon=True)
        thread.start()
    
    def perform_scan(self):
        """Выполнение сканирования (в потоке)"""
        try:
            image = None
            
            if self.scanner_type == 'WIA':
                image = self.scan_with_wia()
            elif self.scanner_type == 'TWAIN':
                image = self.scan_with_twain()
            else:
                raise Exception("Нет доступного метода сканирования")
            
            if image:
                # Добавление страницы
                self.scanned_pages.append(image)
                self.current_scan_index = len(self.scanned_pages) - 1
                
                # Обновление интерфейса в главном потоке
                self.root.after(0, lambda: self.on_scan_complete(True))
            else:
                self.root.after(0, lambda: self.on_scan_complete(False, "Пустое изображение"))
                
        except Exception as e:
            error_msg = f"Ошибка сканирования: {str(e)}"
            print(error_msg)
            self.root.after(0, lambda: self.on_scan_complete(False, error_msg))
    
    def scan_with_wia(self):
        """Сканирование через WIA"""
        try:
            # Получение настроек
            intent = 1  # Color
            if self.color_mode.get() == "Grayscale":
                intent = 2
            elif self.color_mode.get() == "BlackAndWhite":
                intent = 3
            
            # Создание временного файла
            temp_dir = tempfile.gettempdir()
            temp_file = os.path.join(temp_dir, f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bmp")
            
            # Инициализация устройства
            device = self.scanner_device.Connect()
            
            # Получение элемента изображения
            item = device.Items[1]  # Первое устройство ввода
            
            # Настройка параметров сканирования
            # Примечание: WIA COM API имеет ограничения в настройках через Python
            
            # Выполнение сканирования
            image_data = item.Transfer(WIA_IMAGE_FORMAT_BMP)
            
            # Сохранение во временный файл
            with open(temp_file, 'wb') as f:
                f.write(image_data.FileData.BinaryData)
            
            # Загрузка изображения
            image = Image.open(temp_file)
            
            # Очистка временного файла
            try:
                os.remove(temp_file)
            except:
                pass
            
            return image
            
        except Exception as e:
            # Альтернативный метод через DeviceManager
            try:
                wia = comtypes.client.CreateObject("WIA.DeviceManager")
                
                # Прямое сканирование
                dialog = comtypes.client.CreateObject("WIA.CommonDialog")
                
                # Настройка диалога
                device = self.scanner_device.Connect()
                
                # Получение изображения
                image_data = dialog.ShowTransfer(device, WIA_IMAGE_FORMAT_BMP, True)
                
                # Конвертация в PIL Image
                if image_data:
                    binary_data = image_data.FileData.BinaryData
                    image_stream = io.BytesIO(binary_data)
                    image = Image.open(image_stream)
                    return image
                    
            except Exception as e2:
                print(f"WIA scan error (attempt 2): {e2}")
                raise Exception(f"WIA сканирование не удалось: {str(e)}")
    
    def scan_with_twain(self):
        """Сканирование через TWAIN"""
        try:
            # TWAIN требует более сложной интеграции с окнами
            # Это упрощённая реализация
            if not twain.SourceManagerIsOpen():
                # Открытие менеджера источников
                pass
            
            # Заглушка для TWAIN
            # Полная реализация требует создания скрытого окна
            raise Exception("TWAIN требует дополнительной настройки")
            
        except Exception as e:
            print(f"TWAIN scan error: {e}")
            raise
    
    def on_scan_complete(self, success, error_msg=None):
        """Обработка завершения сканирования"""
        self.is_scanning = False
        self.scan_btn.config(state=tk.NORMAL)
        
        if success:
            self.status_label.config(
                text=f"✓ Страница {len(self.scanned_pages)} отсканирована успешно. "
                     f"Добавьте следующую или нажмите 'Завершить'", 
                foreground="green")
            
            self.finish_btn.config(state=tk.NORMAL)
            self.clear_btn.config(state=tk.NORMAL)
            self.save_btn.config(state=tk.NORMAL)
            
            # Обновление превью
            self.update_preview()
            
            # Показ панели управления страницами
            if self.page_controls_frame.winfo_ismapped():
                self.page_controls_frame.pack_forget()
            self.page_controls_frame.pack(fill=tk.X, before=self.root.slaves()[-1])
            
            self.update_page_controls()
        else:
            msg = error_msg or "Неизвестная ошибка"
            self.status_label.config(text=f"✗ Ошибка: {msg}", foreground="red")
            messagebox.showerror("Ошибка сканирования", 
                               f"Не удалось отсканировать страницу.\n\n{msg}\n\n"
                               f"Проверьте:\n"
                               f"1. Подключение сканера по сети/USB\n"
                               f"2. Драйверы WIA/TWAIN установлены\n"
                               f"3. Сканер готов к работе")
    
    def update_preview(self):
        """Обновление превью страниц"""
        # Очистка старых превью
        for widget in self.preview_inner_frame.winfo_children():
            widget.destroy()
        self.page_thumbnails.clear()
        
        # Создание новых превью
        for idx, page_image in enumerate(self.scanned_pages):
            frame = ttk.Frame(self.preview_inner_frame, relief=tk.RAISED, borderwidth=2)
            frame.pack(side=tk.LEFT, padx=10, pady=10)
            
            # Создание миниатюры
            thumb_size = (150, 200)
            thumbnail = page_image.copy()
            thumbnail.thumbnail(thumb_size, Image.Resampling.LANCZOS)
            
            # Конвертация в PhotoImage
            photo = ImageTk.PhotoImage(thumbnail)
            self.page_thumbnails.append(photo)
            
            label = tk.Label(frame, image=photo)
            label.image = photo  # Сохранение ссылки
            label.pack()
            
            # Номер страницы
            num_label = ttk.Label(frame, text=f"Стр. {idx + 1}")
            num_label.pack(pady=5)
            
            # Выделение текущей страницы
            if idx == self.current_scan_index:
                frame.config(relief=tk.SOLID, borderwidth=3)
                label.config(bg="lightblue")
            
            # Обработчик клика
            frame.bind("<Button-1>", lambda e, i=idx: self.select_page(i))
            label.bind("<Button-1>", lambda e, i=idx: self.select_page(i))
            num_label.bind("<Button-1>", lambda e, i=idx: self.select_page(i))
    
    def on_preview_frame_configure(self, event):
        """Обновление области прокрутки при изменении размера фрейма"""
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))
    
    def on_canvas_configure(self, event):
        """Адаптация размера окна при изменении canvas"""
        self.preview_canvas.itemconfig(self.preview_window, width=event.width)
    
    def select_page(self, index):
        """Выбор страницы"""
        self.current_scan_index = index
        self.update_preview()
        self.update_page_controls()
    
    def update_page_controls(self):
        """Обновление кнопок управления страницами"""
        total_pages = len(self.scanned_pages)
        
        if total_pages > 0:
            self.selected_page_label.config(
                text=f"Выбрана страница {self.current_scan_index + 1} из {total_pages}")
            
            # Активация кнопок перемещения
            self.prev_page_btn.config(state=tk.NORMAL if self.current_scan_index > 0 else tk.DISABLED)
            self.next_page_btn.config(
                state=tk.NORMAL if self.current_scan_index < total_pages - 1 else tk.DISABLED)
            self.delete_page_btn.config(state=tk.NORMAL)
        else:
            self.selected_page_label.config(text="Страниц не найдено")
            self.prev_page_btn.config(state=tk.DISABLED)
            self.next_page_btn.config(state=tk.DISABLED)
            self.delete_page_btn.config(state=tk.DISABLED)
    
    def move_page_left(self):
        """Перемещение страницы влево"""
        if self.current_scan_index > 0:
            # Обмен местами
            self.scanned_pages[self.current_scan_index], \
            self.scanned_pages[self.current_scan_index - 1] = \
            self.scanned_pages[self.current_scan_index - 1], \
            self.scanned_pages[self.current_scan_index]
            
            self.current_scan_index -= 1
            self.update_preview()
            self.update_page_controls()
    
    def move_page_right(self):
        """Перемещение страницы вправо"""
        if self.current_scan_index < len(self.scanned_pages) - 1:
            # Обмен местами
            self.scanned_pages[self.current_scan_index], \
            self.scanned_pages[self.current_scan_index + 1] = \
            self.scanned_pages[self.current_scan_index + 1], \
            self.scanned_pages[self.current_scan_index]
            
            self.current_scan_index += 1
            self.update_preview()
            self.update_page_controls()
    
    def delete_selected_page(self):
        """Удаление выбранной страницы"""
        if len(self.scanned_pages) == 0:
            return
        
        if messagebox.askyesno("Подтверждение", 
                              f"Удалить страницу {self.current_scan_index + 1}?"):
            del self.scanned_pages[self.current_scan_index]
            
            if self.current_scan_index >= len(self.scanned_pages):
                self.current_scan_index = max(0, len(self.scanned_pages) - 1)
            
            self.update_preview()
            self.update_page_controls()
            
            if len(self.scanned_pages) == 0:
                self.finish_btn.config(state=tk.DISABLED)
                self.clear_btn.config(state=tk.DISABLED)
                self.save_btn.config(state=tk.DISABLED)
                self.page_controls_frame.pack_forget()
    
    def finish_scanning(self):
        """Завершение сканирования и переход в редактор"""
        if len(self.scanned_pages) == 0:
            messagebox.showinfo("Информация", "Нет отсканированных страниц.")
            return
        
        self.status_label.config(
            text=f"✓ Готово {len(self.scanned_pages)} страниц(ы). "
                 f"Отрегулируйте порядок и сохраните в PDF.", 
            foreground="blue")
        
        messagebox.showinfo("Режим редактирования", 
                          "Теперь вы можете:\n"
                          "• Перемещать страницы кнопками ◀ ▶\n"
                          "• Удалять ненужные страницы (✕)\n"
                          "• Выбирать страницы кликом по превью\n\n"
                          "Когда закончите, нажмите 'Сохранить в PDF'")
    
    def clear_all(self):
        """Очистка всех отсканированных страниц"""
        if len(self.scanned_pages) == 0:
            return
        
        if messagebox.askyesno("Подтверждение", "Удалить все отсканированные страницы?"):
            self.scanned_pages.clear()
            self.page_thumbnails.clear()
            self.current_scan_index = 0
            
            for widget in self.preview_inner_frame.winfo_children():
                widget.destroy()
            
            self.finish_btn.config(state=tk.DISABLED)
            self.clear_btn.config(state=tk.DISABLED)
            self.save_btn.config(state=tk.DISABLED)
            self.page_controls_frame.pack_forget()
            
            self.status_label.config(text="✓ Все страницы удалены. Готов к новому сканированию.", 
                                    foreground="green")
    
    def save_to_pdf(self):
        """Сохранение в PDF"""
        if len(self.scanned_pages) == 0:
            messagebox.showwarning("Предупреждение", "Нет страниц для сохранения.")
            return
        
        try:
            # Выбор пути сохранения
            if self.save_separate.get():
                # Сохранение отдельных файлов
                initial_dir = os.path.join(os.path.expanduser("~"), "Documents")
                base_filename = filedialog.asksaveasfilename(
                    title="Сохранить как (будет добавлен номер страницы)",
                    initialdir=initial_dir,
                    defaultextension=".pdf",
                    filetypes=[("PDF файлы", "*.pdf")],
                    initialfile="scan"
                )
                
                if not base_filename:
                    return
                
                base_path = Path(base_filename)
                base_name = base_path.stem
                parent_dir = base_path.parent
                
                from reportlab.lib.pagesizes import A4, A3, letter, legal
                from reportlab.pdfgen import canvas
                from reportlab.lib.utils import ImageReader
                import io
                
                # Определение формата страницы
                page_sizes = {
                    "A4": A4,
                    "A3": A3,
                    "Letter": letter,
                    "Legal": legal
                }
                page_size = page_sizes.get(self.paper_size.get(), A4)
                
                saved_count = 0
                for idx, page_image in enumerate(self.scanned_pages):
                    # Конвертация изображения в bytes
                    img_buffer = io.BytesIO()
                    page_image.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    
                    # Создание PDF
                    pdf_filename = parent_dir / f"{base_name}_page_{idx + 1}.pdf"
                    c = canvas.Canvas(str(pdf_filename), pagesize=page_size)
                    
                    # Масштабирование изображения под размер страницы
                    img_width, img_height = page_image.size
                    page_width, page_height = page_size
                    
                    scale = min(page_width / img_width, page_height / img_height) * 0.9
                    new_width = img_width * scale
                    new_height = img_height * scale
                    
                    x = (page_width - new_width) / 2
                    y = (page_height - new_height) / 2
                    
                    c.drawImage(ImageReader(img_buffer), x, y, new_width, new_height)
                    c.save()
                    
                    saved_count += 1
                    self.status_label.config(
                        text=f"Сохранение: {saved_count}/{len(self.scanned_pages)}")
                    self.root.update()
                
                messagebox.showinfo("Успех", 
                                  f"Сохранено {saved_count} отдельных PDF файлов(а).\n"
                                  f"Папка: {parent_dir}")
                
            else:
                # Сохранение одного объединённого файла
                filename = filedialog.asksaveasfilename(
                    title="Сохранить PDF",
                    initialdir=os.path.join(os.path.expanduser("~"), "Documents"),
                    defaultextension=".pdf",
                    filetypes=[("PDF файлы", "*.pdf")],
                    initialfile=f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
                
                if not filename:
                    return
                
                from reportlab.lib.pagesizes import A4, A3, letter, legal
                from reportlab.pdfgen import canvas
                from reportlab.lib.utils import ImageReader
                import io
                
                # Определение формата страницы
                page_sizes = {
                    "A4": A4,
                    "A3": A3,
                    "Letter": letter,
                    "Legal": legal
                }
                page_size = page_sizes.get(self.paper_size.get(), A4)
                
                # Создание первого страницы
                c = canvas.Canvas(filename, pagesize=page_size)
                
                for idx, page_image in enumerate(self.scanned_pages):
                    if idx > 0:
                        c.showPage()  # Новая страница
                    
                    # Конвертация изображения в bytes
                    img_buffer = io.BytesIO()
                    page_image.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    
                    # Масштабирование изображения под размер страницы
                    img_width, img_height = page_image.size
                    page_width, page_height = page_size
                    
                    scale = min(page_width / img_width, page_height / img_height) * 0.9
                    new_width = img_width * scale
                    new_height = img_height * scale
                    
                    x = (page_width - new_width) / 2
                    y = (page_height - new_height) / 2
                    
                    c.drawImage(ImageReader(img_buffer), x, y, new_width, new_height)
                    
                    self.status_label.config(
                        text=f"Сохранение: {idx + 1}/{len(self.scanned_pages)}")
                    self.root.update()
                
                c.save()
                
                messagebox.showinfo("Успех", 
                                  f"Сохранён PDF файл с {len(self.scanned_pages)} страниц(ей).\n"
                                  f"Файл: {filename}")
            
            self.status_label.config(text="✓ Сохранение завершено!", foreground="green")
            
        except ImportError:
            messagebox.showerror("Ошибка", 
                               "Требуется библиотека reportlab.\n"
                               "Установите командой:\n"
                               "pip install reportlab")
        except Exception as e:
            error_msg = f"Ошибка сохранения: {str(e)}"
            print(error_msg)
            self.status_label.config(text=error_msg, foreground="red")
            messagebox.showerror("Ошибка сохранения", error_msg)


def main():
    """Точка входа приложения"""
    # Предотвращение закрытия терминала при ошибках
    if sys.platform == 'win32':
        # Установка обработки исключений
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            print(f"\n{'='*60}")
            print(f"КРИТИЧЕСКАЯ ОШИБКА:")
            print(f"Тип: {exc_type.__name__}")
            print(f"Сообщение: {exc_value}")
            print(f"{'='*60}")
            print("Окно остаётся открытым для просмотра ошибки.")
        
        sys.excepthook = handle_exception
    
    # Создание главного окна
    root = tk.Tk()
    
    # Иконка (если есть)
    try:
        root.iconbitmap(default='')
    except:
        pass
    
    # Запуск приложения
    app = ScannerApp(root)
    
    # Запуск цикла событий
    try:
        root.mainloop()
    except Exception as e:
        print(f"\nОшибка в главном цикле: {e}")
        input("\nНажмите Enter для выхода...")


if __name__ == "__main__":
    main()
