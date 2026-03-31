"""
HP LaserJet MFP Scanner Application
Для Windows 10/11
Использует WIA (Windows Image Acquisition) - нативный интерфейс Windows
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import sys
from datetime import datetime
from pathlib import Path

# Попытка импорта WIA через comtypes
try:
    import comtypes.client
    from comtypes import GUID
    WIA_AVAILABLE = True
except ImportError:
    WIA_AVAILABLE = False
    print("WARNING: comtypes не установлен. Запустите install_dependencies.bat")

# Константы WIA
WIA_DEVICE_CLASS = "{6BDA1E60-7D8C-4538-9F8C-BF6A0BA8A23B}"
WIA_IMAGE_FORMAT_PNG = "{B96B3CA9-0728-11D3-9D7B-0000F81EF32E}"
WIA_IMAGE_FORMAT_JPEG = "{B96B3CA8-0728-11D3-9D7B-0000F81EF32E}"
WIA_IMAGE_FORMAT_BMP = "{B96B3CAA-0728-11D3-9D7B-0000F81EF32E}"
WIA_IMAGE_FORMAT_GIF = "{B96B3CB0-0728-11D3-9D7B-0000F81EF32E}"
WIA_IMAGE_FORMAT_TIFF = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
WIA_IMAGE_FORMAT_PDF = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"

class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet MFP Scanner")
        self.root.geometry("900x700")
        
        # Переменные
        self.scanned_images = []  # Список отсканированных изображений
        self.current_scan_index = 0
        self.scanner_device = None
        self.is_scanning = False
        
        # Создание интерфейса
        self.create_widgets()
        
        # Поиск сканеров при запуске
        self.find_scanners()
    
    def create_widgets(self):
        # Верхняя панель - выбор сканера
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="Сканер:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.scanner_combo = ttk.Combobox(top_frame, width=50, state="readonly")
        self.scanner_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.scanner_combo.bind('<<ComboboxSelected>>', self.on_scanner_selected)
        
        self.refresh_btn = ttk.Button(top_frame, text="Обновить", command=self.find_scanners)
        self.refresh_btn.pack(side=tk.LEFT)
        
        # Панель настроек
        settings_frame = ttk.LabelFrame(self.root, text="Настройки сканирования", padding="10")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Цветовой режим
        ttk.Label(settings_frame, text="Цвет:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.color_var = tk.StringVar(value="color")
        color_options = [
            ("Цветное", "color"),
            ("Оттенки серого", "grayscale"),
            ("Ч/Б", "blackwhite")
        ]
        for i, (text, value) in enumerate(color_options):
            ttk.Radiobutton(settings_frame, text=text, variable=self.color_var, 
                          value=value).grid(row=0, column=i+1, padx=10, pady=5, sticky=tk.W)
        
        # Разрешение
        ttk.Label(settings_frame, text="DPI:").grid(row=0, column=4, padx=(20, 5), pady=5, sticky=tk.W)
        self.dpi_var = tk.StringVar(value="300")
        dpi_combo = ttk.Combobox(settings_frame, textvariable=self.dpi_var, 
                                values=["150", "200", "300", "400", "600"], width=8)
        dpi_combo.grid(row=0, column=5, padx=5, pady=5)
        
        # Формат сохранения
        ttk.Label(settings_frame, text="Формат:").grid(row=0, column=6, padx=(20, 5), pady=5, sticky=tk.W)
        self.format_var = tk.StringVar(value="pdf")
        format_combo = ttk.Combobox(settings_frame, textvariable=self.format_var,
                                   values=["pdf", "png", "jpg"], width=8, state="readonly")
        format_combo.grid(row=0, column=7, padx=5, pady=5)
        
        # Область предпросмотра с прокруткой
        preview_frame = ttk.LabelFrame(self.root, text="Отсканированные страницы", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Canvas для горизонтальной прокрутки
        self.canvas = tk.Canvas(preview_frame, bg="white")
        self.scrollbar = ttk.Scrollbar(preview_frame, orient="horizontal", 
                                      command=self.canvas.xview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Привязка колесика мыши для горизонтальной прокрутки
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        
        # Нижняя панель с кнопками
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)
        
        self.scan_btn = ttk.Button(bottom_frame, text="📷 Сканировать страницу", 
                                  command=self.scan_page, style="Accent.TButton")
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.finish_btn = ttk.Button(bottom_frame, text="✅ Завершить и сохранить", 
                                    command=self.finish_scanning, state=tk.DISABLED)
        self.finish_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_btn = ttk.Button(bottom_frame, text="🗑 Очистить всё", 
                                   command=self.clear_all)
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Статус бар
        self.status_var = tk.StringVar(value="Готов к работе. Выберите сканер.")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Прогресс бар
        self.progress = ttk.Progressbar(self.root, mode='indeterminate')
        self.progress.pack(fill=tk.X, side=tk.BOTTOM)
    
    def _on_mousewheel(self, event):
        """Горизонтальная прокрутка колесиком мыши"""
        if event.num == 5 or event.delta == -120:
            self.canvas.xview_scroll(1, "units")
        elif event.num == 4 or event.delta == 120:
            self.canvas.xview_scroll(-1, "units")
    
    def find_scanners(self):
        """Поиск доступных сканеров через WIA"""
        self.status_var.set("Поиск сканеров...")
        self.root.update()
        
        try:
            if not WIA_AVAILABLE:
                messagebox.showerror("Ошибка", 
                    "comtypes не установлен.\nЗапустите install_dependencies.bat")
                return
            
            # Создание объекта WIA DeviceManager
            wia_device_manager = comtypes.client.CreateObject("WIA.DeviceManager")
            
            # Получение списка устройств
            devices = wia_device_manager.DeviceInfos
            
            scanner_list = []
            for i in range(devices.Count):
                device_info = devices.Item(i + 1)
                device_type = device_info.Type
                
                # Фильтрация только сканеров и МФУ
                if device_type in [1, 4]:  # 1 = Scanner, 4 = Multifunction
                    name = device_info.Name
                    device_id = device_info.DeviceID
                    scanner_list.append(f"{name} ({device_id})")
            
            if scanner_list:
                self.scanner_combo['values'] = scanner_list
                if scanner_list:
                    self.scanner_combo.current(0)
                    self.on_scanner_selected(None)
                self.status_var.set(f"Найдено сканеров: {len(scanner_list)}")
            else:
                self.scanner_combo['values'] = ["Сканеры не найдены"]
                self.scanner_combo.current(0)
                self.status_var.set("Сканеры не найдены. Проверьте подключение.")
                
        except Exception as e:
            error_msg = f"Ошибка поиска сканеров: {str(e)}"
            self.status_var.set(error_msg)
            messagebox.showerror("Ошибка", error_msg)
            # Окно не закрывается, ошибка видна в статус баре
    
    def on_scanner_selected(self, event):
        """Выбор сканера из списка"""
        selected = self.scanner_combo.get()
        if selected and selected != "Сканеры не найдены":
            self.status_var.set(f"Выбран сканер: {selected}")
            self.scan_btn.config(state=tk.NORMAL)
        else:
            self.scan_btn.config(state=tk.DISABLED)
    
    def scan_page(self):
        """Сканирование одной страницы"""
        if self.is_scanning:
            messagebox.showwarning("Предупреждение", "Сканирование уже выполняется!")
            return
        
        selected_scanner = self.scanner_combo.get()
        if not selected_scanner or selected_scanner == "Сканеры не найдены":
            messagebox.showerror("Ошибка", "Выберите сканер!")
            return
        
        self.is_scanning = True
        self.scan_btn.config(state=tk.DISABLED)
        self.progress.start()
        self.status_var.set("Начало сканирования...")
        
        # Запуск сканирования в отдельном потоке
        thread = threading.Thread(target=self._scan_thread, daemon=True)
        thread.start()
    
    def _scan_thread(self):
        """Поток сканирования"""
        try:
            if not WIA_AVAILABLE:
                raise Exception("comtypes не установлен")
            
            # Получение устройства
            wia_device_manager = comtypes.client.CreateObject("WIA.DeviceManager")
            devices = wia_device_manager.DeviceInfos
            
            selected_name = self.scanner_combo.get()
            device = None
            
            for i in range(devices.Count):
                device_info = devices.Item(i + 1)
                full_name = f"{device_info.Name} ({device_info.DeviceID})"
                if full_name == selected_name:
                    device = device_info.Connect()
                    break
            
            if not device:
                raise Exception("Не удалось подключиться к сканеру")
            
            # Настройка параметров сканирования
            items = device.Items
            if items.Count == 0:
                raise Exception("Нет доступных элементов сканирования")
            
            # Первый элемент обычно сканер
            scanner_item = items.Item(1)
            
            # Установка параметров
            dpi = int(self.dpi_var.get())
            color_mode = self.color_var.get()
            
            # Установка разрешения
            try:
                scanner_item.Properties("6146").Value = dpi  # WIA_PROPERTY_HORIZONTAL_RESOLUTION
                scanner_item.Properties("6147").Value = dpi  # WIA_PROPERTY_VERTICAL_RESOLUTION
            except:
                pass  # Если свойство недоступно, используем значение по умолчанию
            
            # Установка цветового режима
            try:
                if color_mode == "blackwhite":
                    scanner_item.Properties("6148").Value = 4  # Black & White
                elif color_mode == "grayscale":
                    scanner_item.Properties("6148").Value = 2  # Grayscale
                else:
                    scanner_item.Properties("6148").Value = 1  # Color
            except:
                pass
            
            # Сканирование
            self.status_var.set("Сканирование страницы...")
            image_format = "{B96B3CA9-0728-11D3-9D7B-0000F81EF32E}"  # PNG
            
            image_file = scanner_item.Transfer(image_format)
            
            if image_file is None:
                raise Exception("Сканер вернул пустой результат")
            
            # Сохранение во временный файл
            temp_dir = Path(os.environ.get('TEMP', '.')) / "scanner_temp"
            temp_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_path = temp_dir / f"scan_{timestamp}_{self.current_scan_index}.png"
            
            # Сохранение изображения
            image_file.SaveAs(str(temp_path))
            
            # Добавление в список
            self.scanned_images.append({
                'path': str(temp_path),
                'index': self.current_scan_index
            })
            self.current_scan_index += 1
            
            # Обновление интерфейса в главном потоке
            self.root.after(0, self._update_preview)
            self.root.after(0, lambda: self.status_var.set(
                f"Страница {self.current_scan_index} отсканирована. "
                "Положите следующую и нажмите 'Сканировать' или 'Завершить'"))
            
        except Exception as e:
            error_msg = f"Ошибка при сканировании: {str(e)}"
            self.root.after(0, lambda: self.status_var.set(error_msg))
            self.root.after(0, lambda: messagebox.showerror("Ошибка сканирования", error_msg))
            # Окно остается открытым для просмотра ошибки
        
        finally:
            self.is_scanning = False
            self.root.after(0, self._scan_complete)
    
    def _update_preview(self):
        """Обновление области предпросмотра"""
        # Очистка предыдущих превью
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Добавление новых превью
        for i, img_data in enumerate(self.scanned_images):
            frame = ttk.Frame(self.scrollable_frame, relief=tk.RIDGE, borderwidth=2)
            frame.pack(side=tk.LEFT, padx=5, pady=5)
            
            # Метка с номером страницы
            ttk.Label(frame, text=f"Стр. {i+1}", font=('Arial', 10, 'bold')).pack()
            
            # Кнопки управления
            btn_frame = ttk.Frame(frame)
            btn_frame.pack()
            
            if i > 0:
                up_btn = ttk.Button(btn_frame, text="◀", width=3,
                                   command=lambda idx=i: self.move_page(idx, -1))
                up_btn.pack(side=tk.LEFT, padx=2)
            
            if i < len(self.scanned_images) - 1:
                down_btn = ttk.Button(btn_frame, text="▶", width=3,
                                     command=lambda idx=i: self.move_page(idx, 1))
                down_btn.pack(side=tk.LEFT, padx=2)
            
            del_btn = ttk.Button(btn_frame, text="✕", width=3,
                                command=lambda idx=i: self.delete_page(idx))
            del_btn.pack(side=tk.LEFT, padx=2)
            
            # Путь к файлу
            path_label = ttk.Label(frame, text=os.path.basename(img_data['path']), 
                                  font=('Arial', 7), wraplength=150)
            path_label.pack()
        
        # Активация кнопки завершения
        if self.scanned_images:
            self.finish_btn.config(state=tk.NORMAL)
    
    def move_page(self, index, direction):
        """Перемещение страницы влево/вправо"""
        new_index = index + direction
        if 0 <= new_index < len(self.scanned_images):
            # Обмен местами
            self.scanned_images[index], self.scanned_images[new_index] = \
                self.scanned_images[new_index], self.scanned_images[index]
            self._update_preview()
    
    def delete_page(self, index):
        """Удаление страницы"""
        if messagebox.askyesno("Подтверждение", "Удалить эту страницу?"):
            try:
                os.remove(self.scanned_images[index]['path'])
            except:
                pass
            del self.scanned_images[index]
            self._update_preview()
            
            if not self.scanned_images:
                self.finish_btn.config(state=tk.DISABLED)
    
    def clear_all(self):
        """Очистка всех отсканированных страниц"""
        if not self.scanned_images:
            return
        
        if messagebox.askyesno("Подтверждение", "Удалить все отсканированные страницы?"):
            for img_data in self.scanned_images:
                try:
                    os.remove(img_data['path'])
                except:
                    pass
            self.scanned_images = []
            self.current_scan_index = 0
            self._update_preview()
            self.status_var.set("Все страницы удалены")
    
    def finish_scanning(self):
        """Завершение сканирования и сохранение"""
        if not self.scanned_images:
            messagebox.showwarning("Предупреждение", "Нет отсканированных страниц!")
            return
        
        # Выбор места сохранения
        default_name = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf" if self.format_var.get() == "pdf" else ".png",
            filetypes=[
                ("PDF файлы", "*.pdf"),
                ("PNG файлы", "*.png"),
                ("JPG файлы", "*.jpg"),
                ("Все файлы", "*.*")
            ],
            initialfile=default_name,
            title="Сохранить как"
        )
        
        if not file_path:
            return
        
        self.status_var.set("Сохранение файла...")
        self.progress.start()
        
        # Сохранение в отдельном потоке
        thread = threading.Thread(target=self._save_thread, args=(file_path,), daemon=True)
        thread.start()
    
    def _save_thread(self, file_path):
        """Поток сохранения файла"""
        try:
            output_format = self.format_var.get()
            
            if output_format == "pdf":
                self._save_as_pdf(file_path)
            elif output_format == "png":
                self._save_as_png(file_path)
            elif output_format == "jpg":
                self._save_as_jpg(file_path)
            
            self.root.after(0, lambda: self.status_var.set(
                f"Файл сохранён: {os.path.basename(file_path)}"))
            self.root.after(0, lambda: messagebox.showinfo("Успех", 
                f"Файл успешно сохранён:\n{file_path}"))
            
        except Exception as e:
            error_msg = f"Ошибка сохранения: {str(e)}"
            self.root.after(0, lambda: self.status_var.set(error_msg))
            self.root.after(0, lambda: messagebox.showerror("Ошибка", error_msg))
        
        finally:
            self.root.after(0, self._scan_complete)
            # Очистка временных файлов после сохранения
            self.root.after(1000, self._cleanup_temp_files)
    
    def _save_as_pdf(self, file_path):
        """Сохранение в PDF с использованием pypdf"""
        try:
            from PIL import Image
            import io
            
            images = []
            for img_data in self.scanned_images:
                img = Image.open(img_data['path'])
                # Конвертация в RGB для PDF
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                images.append(img)
            
            if images:
                # Сохранение первого изображения с добавлением остальных
                images[0].save(
                    file_path,
                    save_all=True,
                    append_images=images[1:],
                    resolution=100.0,
                    quality=95
                )
        except ImportError:
            # Если PIL нет, пробуем простой метод
            self._save_single_pdf(file_path)
    
    def _save_single_pdf(self, file_path):
        """Простое сохранение в PDF (первая страница)"""
        from PIL import Image
        img = Image.open(self.scanned_images[0]['path'])
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        img.save(file_path, "PDF", resolution=100.0)
    
    def _save_as_png(self, file_path):
        """Сохранение как PNG (объединение вертикально)"""
        from PIL import Image
        
        images = [Image.open(img_data['path']) for img_data in self.scanned_images]
        
        # Определение общей ширины и суммы высот
        max_width = max(img.width for img in images)
        total_height = sum(img.height for img in images)
        
        # Создание нового изображения
        result = Image.new('RGB', (max_width, total_height), color='white')
        
        y_offset = 0
        for img in images:
            # Конвертация в RGB если нужно
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            result.paste(img, (0, y_offset))
            y_offset += img.height
        
        result.save(file_path, "PNG", dpi=(300, 300))
    
    def _save_as_jpg(self, file_path):
        """Сохранение как JPG (объединение вертикально)"""
        from PIL import Image
        
        images = [Image.open(img_data['path']) for img_data in self.scanned_images]
        
        max_width = max(img.width for img in images)
        total_height = sum(img.height for img in images)
        
        result = Image.new('RGB', (max_width, total_height), color='white')
        
        y_offset = 0
        for img in images:
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            result.paste(img, (0, y_offset))
            y_offset += img.height
        
        result.save(file_path, "JPEG", quality=95, dpi=(300, 300))
    
    def _cleanup_temp_files(self):
        """Очистка временных файлов"""
        for img_data in self.scanned_images:
            try:
                if os.path.exists(img_data['path']):
                    os.remove(img_data['path'])
            except:
                pass
        self.scanned_images = []
        self.current_scan_index = 0
    
    def _scan_complete(self):
        """Завершение сканирования"""
        self.is_scanning = False
        self.scan_btn.config(state=tk.NORMAL)
        self.progress.stop()


def main():
    root = tk.Tk()
    
    # Настройка стиля
    style = ttk.Style()
    style.theme_use('clam')
    
    # Настройка цветов
    style.configure('TFrame', background='#f0f0f0')
    style.configure('TLabel', background='#f0f0f0')
    style.configure('Accent.TButton', foreground='blue')
    
    app = ScannerApp(root)
    
    # Обработка закрытия окна
    def on_closing():
        if app.is_scanning:
            if messagebox.askokcancel("Выход", 
                "Сканирование выполняется. Всё равно выйти?"):
                app.clear_all()
                root.destroy()
        else:
            app.clear_all()
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
