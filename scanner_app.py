"""
HP LaserJet Network Scanner Application for Windows
Сканирование документов по сети с возможностью многостраничного сканирования,
редактирования порядка страниц и сохранения в PDF.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import sys
from pathlib import Path
from datetime import datetime

# Проверка наличия необходимых библиотек
try:
    import PIL.Image
    from PIL import Image
except ImportError:
    print("Установите Pillow: pip install Pillow")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

try:
    import pyinsane2
except ImportError:
    print("Установите pyinsane2: pip install pyinsane2")
    print("Также установите TWAIN драйверы для вашего сканера")
    input("Нажмите Enter для выхода...")
    sys.exit(1)


class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet Scanner - Сканирование документов")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # Переменные состояния
        self.scanned_images = []  # Список отсканированных изображений
        self.current_session = []  # Текущая сессия сканирования
        self.is_scanning = False
        self.scanner_device = None
        self.scan_settings = {}
        self.color_mode = tk.StringVar(value="Color")
        
        # Настройка стиля
        self.setup_styles()
        
        # Создание интерфейса
        self.create_main_interface()
        
        # Инициализация сканера
        self.init_scanner()
        
        # Обработчик закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_styles(self):
        """Настройка стилей интерфейса"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Конфигурация стилей
        style.configure('Title.TLabel', font=('Segoe UI', 14, 'bold'))
        style.configure('Status.TLabel', font=('Segoe UI', 10))
        style.configure('Error.TLabel', font=('Segoe UI', 10), foreground='red')
        style.configure('Success.TLabel', font=('Segoe UI', 10), foreground='green')
        
        # Стили кнопок
        style.configure('Primary.TButton', font=('Segoe UI', 11, 'bold'))
        style.configure('Secondary.TButton', font=('Segoe UI', 10))
        style.configure('Danger.TButton', font=('Segoe UI', 10), foreground='red')
    
    def create_main_interface(self):
        """Создание основного интерфейса"""
        # Главный контейнер
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Верхняя панель - выбор сканера и настройки
        self.create_top_panel(main_frame)
        
        # Центральная область - предпросмотр страниц
        self.create_preview_area(main_frame)
        
        # Нижняя панель - кнопки управления
        self.create_bottom_panel(main_frame)
        
        # Статус бар
        self.create_status_bar(main_frame)
    
    def create_top_panel(self, parent):
        """Создание верхней панели с настройками"""
        top_frame = ttk.LabelFrame(parent, text="Настройки сканирования", padding="10")
        top_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        parent.columnconfigure(0, weight=1)
        
        # Выбор сканера
        scanner_label = ttk.Label(top_frame, text="Сканер:")
        scanner_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        self.scanner_combo = ttk.Combobox(top_frame, state="readonly", width=40)
        self.scanner_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        self.scanner_combo.bind('<<ComboboxSelected>>', self.on_scanner_selected)
        
        refresh_btn = ttk.Button(top_frame, text="Обновить", command=self.refresh_scanners)
        refresh_btn.grid(row=0, column=2, padx=(0, 20))
        
        # Настройки сканирования
        settings_frame = ttk.Frame(top_frame)
        settings_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # Цветовой режим
        color_label = ttk.Label(settings_frame, text="Цвет:")
        color_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        
        color_modes = ["Color", "Grayscale", "Black & White"]
        self.color_combo = ttk.Combobox(settings_frame, textvariable=self.color_mode, 
                                        values=color_modes, state="readonly", width=15)
        self.color_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))
        self.color_combo.bind('<<ComboboxSelected>>', self.on_color_changed)
        
        # Разрешение
        dpi_label = ttk.Label(settings_frame, text="DPI:")
        dpi_label.grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        
        self.dpi_var = tk.StringVar(value="300")
        dpi_combo = ttk.Combobox(settings_frame, textvariable=self.dpi_var,
                                 values=["150", "200", "300", "400", "600"], 
                                 state="readonly", width=8)
        dpi_combo.grid(row=0, column=3, sticky=tk.W, padx=(0, 20))
        
        # Формат бумаги
        paper_label = ttk.Label(settings_frame, text="Формат:")
        paper_label.grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
        
        self.paper_var = tk.StringVar(value="A4")
        paper_combo = ttk.Combobox(settings_frame, textvariable=self.paper_var,
                                   values=["A4", "A3", "Letter", "Legal"], 
                                   state="readonly", width=10)
        paper_combo.grid(row=0, column=5, sticky=tk.W)
    
    def create_preview_area(self, parent):
        """Создание области предпросмотра страниц"""
        preview_frame = ttk.LabelFrame(parent, text="Отсканированные страницы", padding="10")
        preview_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        
        # Canvas для прокрутки миниатюр
        self.preview_canvas = tk.Canvas(preview_frame, bg="#f0f0f0", height=300)
        self.preview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, 
                                  command=self.preview_canvas.xview)
        scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.preview_canvas.configure(xscrollcommand=scrollbar.set)
        
        # Frame для миниатюр внутри canvas
        self.thumbnails_frame = ttk.Frame(self.preview_canvas)
        self.preview_canvas.create_window((0, 0), window=self.thumbnails_frame, 
                                          anchor=tk.NW)
        
        # Binding для изменения размера
        self.thumbnails_frame.bind('<Configure>', self.on_thumbnails_configure)
        self.preview_canvas.bind('<Configure>', self.on_canvas_configure)
        
        # Label для отображения количества страниц
        self.page_count_label = ttk.Label(preview_frame, text="Страниц: 0")
        self.page_count_label.pack(side=tk.TOP, anchor=tk.E, pady=(5, 0))
    
    def create_bottom_panel(self, parent):
        """Создание нижней панели с кнопками управления"""
        bottom_frame = ttk.Frame(parent)
        bottom_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        parent.columnconfigure(0, weight=1)
        
        # Кнопки сканирования
        scan_btn = ttk.Button(bottom_frame, text="📄 Сканировать страницу", 
                             command=self.scan_page, style='Primary.TButton')
        scan_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.complete_btn = ttk.Button(bottom_frame, text="✓ Завершить сканирование", 
                                       command=self.complete_scanning, 
                                       state=tk.DISABLED)
        self.complete_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Кнопки редактирования
        clear_btn = ttk.Button(bottom_frame, text="🗑 Очистить всё", 
                              command=self.clear_all, style='Danger.TButton')
        clear_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Кнопки сохранения
        save_single_btn = ttk.Button(bottom_frame, text="💾 Сохранить как отдельный PDF", 
                                    command=lambda: self.save_pdf(single=True))
        save_single_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        save_combined_btn = ttk.Button(bottom_frame, text="📚 Сохранить объединённый PDF", 
                                      command=lambda: self.save_pdf(single=False))
        save_combined_btn.pack(side=tk.LEFT)
        
        # Индикатор прогресса
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(bottom_frame, variable=self.progress_var, 
                                           maximum=100, mode='indeterminate')
        self.progress_bar.pack(side=tk.RIGHT, padx=(20, 0))
    
    def create_status_bar(self, parent):
        """Создание статусной строки"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        parent.columnconfigure(0, weight=1)
        
        self.status_label = ttk.Label(status_frame, text="Готов к работе", style='Status.TLabel')
        self.status_label.pack(side=tk.LEFT)
        
        self.error_label = ttk.Label(status_frame, text="", style='Error.TLabel')
        self.error_label.pack(side=tk.RIGHT)
    
    def init_scanner(self):
        """Инициализация сканера"""
        try:
            self.update_status("Поиск доступных сканеров...")
            pyinsane2.init()
            self.refresh_scanners()
            self.update_status("Готов к работе")
        except Exception as e:
            error_msg = f"Ошибка инициализации: {str(e)}"
            self.show_error(error_msg)
            self.update_status(error_msg, is_error=True)
    
    def refresh_scanners(self):
        """Обновление списка доступных сканеров"""
        try:
            self.scanner_combo['values'] = []
            devices = pyinsane2.get_devices()
            
            if not devices:
                self.scanner_combo['values'] = ["Нет доступных сканеров"]
                self.scanner_combo.set("Нет доступных сканеров")
                self.show_error("Не найдено доступных сканеров. Проверьте подключение.")
                return
            
            device_names = [str(device) for device in devices]
            self.scanner_combo['values'] = device_names
            self.scanner_combo.set(device_names[0])
            self.on_scanner_selected(None)
            
            self.update_status(f"Найдено сканеров: {len(devices)}")
        except Exception as e:
            error_msg = f"Ошибка получения списка сканеров: {str(e)}"
            self.show_error(error_msg)
            self.update_status(error_msg, is_error=True)
    
    def on_scanner_selected(self, event):
        """Обработчик выбора сканера"""
        try:
            selected = self.scanner_combo.get()
            if selected and selected != "Нет доступных сканеров":
                devices = pyinsane2.get_devices()
                for device in devices:
                    if str(device) == selected:
                        self.scanner_device = device
                        self.update_status(f"Выбран сканер: {selected}")
                        break
        except Exception as e:
            self.show_error(f"Ошибка выбора сканера: {str(e)}")
    
    def on_color_changed(self, event):
        """Обработчик изменения цветового режима"""
        self.update_scan_settings()
    
    def update_scan_settings(self):
        """Обновление настроек сканирования"""
        if self.scanner_device:
            try:
                options = self.scanner_device.get_options()
                
                # Установка цветового режима
                for option in options:
                    if option.name == 'mode':
                        color_map = {
                            'Color': 'Color',
                            'Grayscale': 'Gray',
                            'Black & White': 'Lineart'
                        }
                        desired_mode = color_map.get(self.color_mode.get(), 'Color')
                        if desired_mode in option.constraint:
                            option.set(desired_mode)
                
                # Установка разрешения
                for option in options:
                    if option.name == 'resolution':
                        dpi = int(self.dpi_var.get())
                        if dpi in option.constraint:
                            option.set(dpi)
                
                self.update_status("Настройки применены")
            except Exception as e:
                self.show_error(f"Ошибка применения настроек: {str(e)}")
    
    def scan_page(self):
        """Сканирование одной страницы"""
        if self.is_scanning:
            messagebox.showwarning("Предупреждение", "Сканирование уже выполняется!")
            return
        
        if not self.scanner_device:
            messagebox.showerror("Ошибка", "Выберите сканер!")
            return
        
        self.is_scanning = True
        self.progress_bar.start()
        self.update_status("Начало сканирования страницы...")
        
        # Запуск сканирования в отдельном потоке
        scan_thread = threading.Thread(target=self._scan_page_thread, daemon=True)
        scan_thread.start()
    
    def _scan_page_thread(self):
        """Поток сканирования страницы"""
        try:
            self.update_scan_settings()
            
            # Начало сканирования
            session = self.scanner_device.scan(multiple_scan=False)
            
            # Получение изображения
            images = []
            for image in session.images:
                images.append(image)
            
            if images:
                # Конвертация в PIL Image
                pil_image = images[0]
                
                # Добавление в список
                self.current_session.append(pil_image)
                self.scanned_images.append(pil_image)
                
                # Обновление UI в главном потоке
                self.root.after(0, lambda: self.on_scan_complete(pil_image))
            else:
                self.root.after(0, lambda: self.show_error("Изображение не получено"))
        
        except Exception as e:
            error_msg = f"Ошибка сканирования: {str(e)}"
            self.root.after(0, lambda: self.show_error(error_msg))
            self.root.after(0, lambda: self.update_status(error_msg, is_error=True))
        
        finally:
            self.is_scanning = False
            self.root.after(0, self.stop_progress)
    
    def on_scan_complete(self, image):
        """Обработка завершения сканирования"""
        # Создание миниатюры
        thumbnail = image.copy()
        thumbnail.thumbnail((150, 200), PIL.Image.Resampling.LANCZOS)
        
        # Добавление миниатюры в превью
        self.add_thumbnail(thumbnail, len(self.scanned_images))
        
        # Обновление счётчика
        self.page_count_label.config(text=f"Страниц: {len(self.scanned_images)}")
        
        # Активация кнопки завершения
        self.complete_btn.config(state=tk.NORMAL if self.scanned_images else tk.DISABLED)
        
        self.update_status(f"Страница {len(self.scanned_images)} отсканирована успешно")
    
    def add_thumbnail(self, thumbnail, index):
        """Добавление миниатюры в область предпросмотра"""
        # Конвертация PIL Image в PhotoImage
        from PIL import ImageTk
        photo = ImageTk.PhotoImage(thumbnail)
        
        # Создание фрейма для миниатюры
        thumb_frame = ttk.Frame(self.thumbnails_frame, relief=tk.RAISED, borderwidth=2)
        thumb_frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Label с изображением
        img_label = ttk.Label(thumb_frame, image=photo)
        img_label.image = photo  # Сохранение ссылки
        img_label.pack()
        
        # Номер страницы
        num_label = ttk.Label(thumb_frame, text=f"#{index}")
        num_label.pack()
        
        # Кнопки управления
        btn_frame = ttk.Frame(thumb_frame)
        btn_frame.pack()
        
        left_btn = ttk.Button(btn_frame, text="◀", width=2,
                             command=lambda: self.move_page(index, -1))
        left_btn.pack(side=tk.LEFT)
        
        right_btn = ttk.Button(btn_frame, text="▶", width=2,
                              command=lambda: self.move_page(index, 1))
        right_btn.pack(side=tk.LEFT)
        
        delete_btn = ttk.Button(btn_frame, text="✕", width=2,
                               command=lambda: self.delete_page(index))
        delete_btn.pack(side=tk.LEFT)
        
        # Сохранение ссылки на фрейм
        if not hasattr(self, 'thumbnail_frames'):
            self.thumbnail_frames = []
        self.thumbnail_frames.append(thumb_frame)
    
    def move_page(self, index, direction):
        """Перемещение страницы влево или вправо"""
        new_index = index + direction
        if 0 <= new_index < len(self.scanned_images):
            # Перемещение в списке
            self.scanned_images[index], self.scanned_images[new_index] = \
                self.scanned_images[new_index], self.scanned_images[index]
            
            # Перестроение превью
            self.rebuild_thumbnails()
            self.update_status(f"Страница {index+1} перемещена на позицию {new_index+1}")
    
    def delete_page(self, index):
        """Удаление страницы"""
        if messagebox.askyesno("Подтверждение", f"Удалить страницу {index+1}?"):
            del self.scanned_images[index]
            self.rebuild_thumbnails()
            self.page_count_label.config(text=f"Страниц: {len(self.scanned_images)}")
            self.update_status(f"Страница {index+1} удалена")
    
    def rebuild_thumbnails(self):
        """Перестроение всех миниатюр"""
        # Очистка текущих миниатюр
        for widget in self.thumbnails_frame.winfo_children():
            widget.destroy()
        
        if hasattr(self, 'thumbnail_frames'):
            self.thumbnail_frames.clear()
        
        # Пересоздание миниатюр
        for i, image in enumerate(self.scanned_images):
            thumbnail = image.copy()
            thumbnail.thumbnail((150, 200), PIL.Image.Resampling.LANCZOS)
            self.add_thumbnail(thumbnail, i + 1)
    
    def complete_scanning(self):
        """Завершение сессии сканирования"""
        if not self.scanned_images:
            messagebox.showinfo("Информация", "Нет отсканированных страниц")
            return
        
        self.update_status("Сканирование завершено. Готово к сохранению.")
        messagebox.showinfo("Готово", 
                          f"Отсканировано страниц: {len(self.scanned_images)}\n\n"
                          "Теперь вы можете:\n"
                          "• Перетащить страницы для изменения порядка\n"
                          "• Удалить ненужные страницы\n"
                          "• Сохранить как один PDF или отдельные файлы")
    
    def clear_all(self):
        """Очистка всех отсканированных страниц"""
        if self.scanned_images and messagebox.askyesno("Подтверждение", 
                                                       "Удалить все отсканированные страницы?"):
            self.scanned_images.clear()
            self.current_session.clear()
            
            for widget in self.thumbnails_frame.winfo_children():
                widget.destroy()
            
            if hasattr(self, 'thumbnail_frames'):
                self.thumbnail_frames.clear()
            
            self.page_count_label.config(text="Страниц: 0")
            self.complete_btn.config(state=tk.DISABLED)
            self.update_status("Все страницы удалены")
    
    def save_pdf(self, single=False):
        """Сохранение в PDF"""
        if not self.scanned_images:
            messagebox.showerror("Ошибка", "Нет страниц для сохранения!")
            return
        
        try:
            if single:
                # Сохранение каждой страницы как отдельного PDF
                save_dir = filedialog.askdirectory(title="Выберите папку для сохранения")
                if not save_dir:
                    return
                
                saved_count = 0
                for i, image in enumerate(self.scanned_images):
                    filename = f"scan_page_{i+1}.pdf"
                    filepath = os.path.join(save_dir, filename)
                    
                    # Конвертация в RGB если нужно
                    if image.mode != 'RGB':
                        image = image.convert('RGB')
                    
                    image.save(filepath, "PDF", resolution=100.0)
                    saved_count += 1
                
                messagebox.showinfo("Готово", f"Сохранено {saved_count} файлов(а)")
                self.update_status(f"Сохранено {saved_count} отдельных PDF файлов")
            
            else:
                # Сохранение всех страниц в один PDF
                filepath = filedialog.asksaveasfilename(
                    title="Сохранить как",
                    defaultextension=".pdf",
                    filetypes=[("PDF files", "*.pdf")],
                    initialfile=f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                )
                
                if not filepath:
                    return
                
                # Конвертация первого изображения
                first_image = self.scanned_images[0]
                if first_image.mode != 'RGB':
                    first_image = first_image.convert('RGB')
                
                # Остальные изображения
                other_images = []
                for img in self.scanned_images[1:]:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    other_images.append(img)
                
                # Сохранение
                if other_images:
                    first_image.save(
                        filepath,
                        "PDF",
                        save_all=True,
                        append_images=other_images,
                        resolution=100.0
                    )
                else:
                    first_image.save(filepath, "PDF", resolution=100.0)
                
                messagebox.showinfo("Готово", "Документ сохранён успешно!")
                self.update_status(f"Сохранён объединённый PDF: {os.path.basename(filepath)}")
        
        except Exception as e:
            error_msg = f"Ошибка сохранения: {str(e)}"
            self.show_error(error_msg)
            self.update_status(error_msg, is_error=True)
    
    def on_thumbnails_configure(self, event):
        """Обработчик изменения размера области миниатюр"""
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))
    
    def on_canvas_configure(self, event):
        """Обработчик изменения размера canvas"""
        pass
    
    def stop_progress(self):
        """Остановка индикатора прогресса"""
        self.progress_bar.stop()
    
    def update_status(self, message, is_error=False):
        """Обновление статусной строки"""
        self.status_label.config(text=message)
        if is_error:
            self.error_label.config(text=message)
        else:
            self.error_label.config(text="")
    
    def show_error(self, message):
        """Показ ошибки"""
        self.error_label.config(text=message)
        messagebox.showerror("Ошибка", message)
    
    def on_closing(self):
        """Обработчик закрытия окна"""
        if self.is_scanning:
            if not messagebox.askyesno("Предупреждение", 
                                      "Сканирование выполняется. Всё равно закрыть?"):
                return
        
        if self.scanned_images:
            response = messagebox.askyesnocancel("Предупреждение",
                                                "Есть несохранённые страницы. Сохранить перед выходом?")
            if response is True:
                self.save_pdf(single=False)
            elif response is None:
                return
        
        self.root.destroy()


def main():
    """Точка входа приложения"""
    root = tk.Tk()
    
    # Установка иконки (если есть)
    try:
        root.iconbitmap("scanner.ico")
    except:
        pass
    
    app = ScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
