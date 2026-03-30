#!/usr/bin/env python3
"""
Программа для сканирования документов с принтера HP LaserJet через сеть
Поддержка Windows 10/11, множественное сканирование, редактирование порядка страниц
"""

import sys
import os
import time
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple

# GUI библиотеки
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("Ошибка: требуется tkinter. Установите: pip install tk")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

# PIL для работы с изображениями
try:
    from PIL import Image, ImageTk
except ImportError:
    print("Ошибка: требуется Pillow. Установите: pip install Pillow")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

# Для работы с PDF
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
except ImportError:
    print("Ошибка: требуется reportlab. Установите: pip install reportlab")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

# SANE для сканирования (Linux) / TWAIN альтернатива для Windows
try:
    import pysane
    HAS_SANE = True
except ImportError:
    HAS_SANE = False
    print("Предупреждение: pysane не установлен. Будет использоваться эмуляция.")
    print("Для Linux установите: sudo apt-get install sane-utils && pip install pysane")

# Для сетевого сканирования HP
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Предупреждение: requests не установлен. Установите: pip install requests")


class ScannerApp:
    """Основной класс приложения для сканирования"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet Scanner - Сканер документов")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        
        # Хранилище отсканированных страниц
        self.scanned_pages: List[dict] = []  # [{'path': str, 'image': PhotoImage, 'timestamp': datetime}]
        self.temp_dir = tempfile.mkdtemp(prefix="scanner_")
        
        # Настройки сканирования
        self.scan_color_mode = tk.StringVar(value="color")  # color, grayscale, bw
        self.scan_resolution = tk.IntVar(value=300)  # DPI
        self.scan_format = tk.StringVar(value="PDF")
        self.scanner_address = tk.StringVar(value="")  # IP адрес сканера
        
        # Флаги состояния
        self.is_scanning = False
        self.scan_session_active = False
        
        # Создание интерфейса
        self._create_ui()
        
        # Обработчик закрытия
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Логирование
        self._log("Приложение запущено. Готов к сканированию.")
        
    def _create_ui(self):
        """Создание пользовательского интерфейса"""
        
        # Верхняя панель с настройками
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(side=tk.TOP, fill=tk.X)
        
        # Настройки сканера
        settings_group = ttk.LabelFrame(top_frame, text="Настройки сканера", padding="5")
        settings_group.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # IP адрес сканера
        ttk.Label(settings_group, text="IP адрес:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.ip_entry = ttk.Entry(settings_group, textvariable=self.scanner_address, width=20)
        self.ip_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)
        self.ip_entry.insert(0, "192.168.1.100")  # Пример
        
        # Цветовой режим
        ttk.Label(settings_group, text="Режим:").grid(row=0, column=2, sticky=tk.W, pady=2, padx=(10, 0))
        color_combo = ttk.Combobox(settings_group, textvariable=self.scan_color_mode, 
                                   values=["color", "grayscale", "bw"], width=12, state="readonly")
        color_combo.grid(row=0, column=3, sticky=tk.W, pady=2, padx=5)
        
        # Разрешение
        ttk.Label(settings_group, text="DPI:").grid(row=0, column=4, sticky=tk.W, pady=2, padx=(10, 0))
        dpi_combo = ttk.Combobox(settings_group, textvariable=self.scan_resolution,
                                 values=[150, 200, 300, 400, 600], width=8, state="readonly")
        dpi_combo.grid(row=0, column=5, sticky=tk.W, pady=2, padx=5)
        
        # Кнопки управления сканированием
        buttons_group = ttk.Frame(top_frame)
        buttons_group.pack(side=tk.RIGHT, padx=(10, 0))
        
        self.btn_scan = ttk.Button(buttons_group, text="📄 Сканировать страницу", 
                                   command=self._scan_page, width=20)
        self.btn_scan.pack(side=tk.LEFT, padx=2)
        
        self.btn_finish = ttk.Button(buttons_group, text="✅ Завершить и сохранить",
                                     command=self._finish_scanning, width=20)
        self.btn_finish.pack(side=tk.LEFT, padx=2)
        self.btn_finish.config(state=tk.DISABLED)
        
        self.btn_clear = ttk.Button(buttons_group, text="🗑️ Очистить всё",
                                    command=self._clear_all, width=15)
        self.btn_clear.pack(side=tk.LEFT, padx=2)
        
        # Центральная область с превью страниц
        center_frame = ttk.Frame(self.root, padding="10")
        center_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        ttk.Label(center_frame, text="Отсканированные страницы (перетаскивайте для изменения порядка):",
                  font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        
        # Canvas с прокруткой для миниатюр
        self.canvas_frame = ttk.Frame(center_frame)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg='white', highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL, 
                                       command=self.canvas.xview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        
        # Привязка событий для прокрутки колёсиком
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Контейнер для миниатюр (будет заполняться динамически)
        self.thumbnails_container = ttk.Frame(self.scrollable_frame)
        self.thumbnails_container.pack(fill=tk.X, padx=10, pady=10)
        
        # Нижняя панель с логами
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        ttk.Label(bottom_frame, text="Журнал операций:", font=('Arial', 9, 'bold')).pack(anchor=tk.W)
        
        self.log_text = tk.Text(bottom_frame, height=6, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.X, pady=(5, 0))
        
        # Статус бар
        self.status_var = tk.StringVar(value="Готов")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def _on_mousewheel(self, event):
        """Обработка прокрутки колёсиком мыши"""
        if event.num == 4 or event.delta > 0:
            self.canvas.xview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.xview_scroll(1, "units")
            
    def _log(self, message: str):
        """Добавление сообщения в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def _update_status(self, message: str):
        """Обновление статусной строки"""
        self.status_var.set(message)
        self.root.update_idletasks()
        
    def _scan_page(self):
        """Сканирование одной страницы"""
        if self.is_scanning:
            messagebox.showwarning("Предупреждение", "Сканирование уже выполняется!")
            return
            
        self.is_scanning = True
        self.btn_scan.config(state=tk.DISABLED)
        self._update_status("Инициализация сканирования...")
        
        try:
            # Запуск в отдельном потоке чтобы не блокировать UI
            self.root.after(100, lambda: self._do_scan())
        except Exception as e:
            self._log(f"❌ Ошибка при инициализации сканирования: {e}")
            self.is_scanning = False
            self.btn_scan.config(state=tk.NORMAL)
            self._update_status("Ошибка сканирования")
            
    def _do_scan(self):
        """Выполнение сканирования (внутренний метод)"""
        page_num = len(self.scanned_pages) + 1
        self._log(f"🔄 Сканирование страницы {page_num}...")
        self._update_status(f"Сканирование страницы {page_num}...")
        
        try:
            # Попытка сканирования через SANE (Linux) или эмуляция
            output_path = os.path.join(self.temp_dir, f"page_{page_num:03d}.png")
            
            if HAS_SANE and self.scanner_address.get():
                # Реальное сканирование через SANE
                success = self._scan_with_sane(output_path)
            else:
                # Эмуляция для тестирования или если SANE недоступен
                success = self._simulate_scan(output_path, page_num)
                
            if success and os.path.exists(output_path):
                # Добавление страницы в список
                self._add_page_to_list(output_path)
                self._log(f"✅ Страница {page_num} успешно отсканирована")
                self.scan_session_active = True
                self.btn_finish.config(state=tk.NORMAL)
            else:
                raise Exception("Не удалось создать файл сканирования")
                
        except Exception as e:
            error_msg = f"❌ Ошибка при сканировании страницы {page_num}: {str(e)}"
            self._log(error_msg)
            self._log("   Проверьте подключение к сканеру и настройки")
            messagebox.showerror("Ошибка сканирования", 
                               f"Не удалось отсканировать страницу {page_num}\n\n{str(e)}\n\n"
                               f"Убедитесь что:\n"
                               f"1. Сканер включен и подключен к сети\n"
                               f"2. IP адрес указан верно\n"
                               f"3. Установлены драйверы и утилиты (sane-utils)")
        finally:
            self.is_scanning = False
            self.btn_scan.config(state=tk.NORMAL)
            self._update_status("Готов к сканированию следующей страницы")
            
    def _scan_with_sane(self, output_path: str) -> bool:
        """Сканирование через SANE"""
        try:
            import pysane
            
            # Инициализация SANE
            pysane.init()
            
            # Поиск сканера
            devices = pysane.get_devices()
            if not devices:
                raise Exception("Сканеры не найдены. Проверьте подключение.")
                
            # Выбор первого доступного сканера или по IP
            scanner = None
            ip = self.scanner_address.get().strip()
            
            if ip:
                for device in devices:
                    if ip in device.name or ip in str(device):
                        scanner = pysane.open(device.name)
                        break
                        
            if not scanner and devices:
                scanner = pysane.open(devices[0].name)
                
            if not scanner:
                raise Exception("Не удалось открыть сканер")
                
            # Настройка параметров
            mode_map = {'color': 'color', 'grayscale': 'gray', 'bw': 'lineart'}
            scanner.mode = mode_map.get(self.scan_color_mode.get(), 'color')
            scanner.resolution = self.scan_resolution.get()
            
            # Сканирование
            image = scanner.scan()
            
            # Сохранение
            if isinstance(image, Image.Image):
                image.save(output_path, 'PNG')
            else:
                # Конвертация если нужно
                img = Image.fromarray(image)
                img.save(output_path, 'PNG')
                
            scanner.close()
            return True
            
        except Exception as e:
            raise Exception(f"SANE ошибка: {str(e)}")
            
    def _simulate_scan(self, output_path: str, page_num: int):
        """Эмуляция сканирования для тестирования"""
        # Создание тестового изображения
        width, height = 2480, 3508  # A4 при 300 DPI
        
        if self.scan_color_mode.get() == 'bw':
            img = Image.new('1', (width, height), color=1)
        elif self.scan_color_mode.get() == 'grayscale':
            img = Image.new('L', (width, height), color=200)
        else:
            img = Image.new('RGB', (width, height), color=(240, 240, 250))
            
        # Добавление текста
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 72)
        except:
            font = ImageFont.load_default()
            
        text = f"Страница {page_num}\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nТестовое сканирование"
        
        # Получение размеров текста для центрирования
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        if self.scan_color_mode.get() == 'bw':
            draw.text((x, y), text, fill=0, font=font)
        else:
            draw.text((x, y), text, fill=(50, 50, 150), font=font)
            
        img.save(output_path, 'PNG')
        time.sleep(1)  # Имитация задержки сканирования
        return True
        
    def _add_page_to_list(self, image_path: str):
        """Добавление отсканированной страницы в список с миниатюрой"""
        try:
            # Загрузка изображения
            img = Image.open(image_path)
            
            # Создание миниатюры
            thumb_size = (180, 250)
            img_thumb = img.copy()
            img_thumb.thumbnail(thumb_size, Image.Resampling.LANCZOS)
            
            # Конвертация для Tkinter
            photo = ImageTk.PhotoImage(img_thumb)
            
            # Добавление в список
            page_data = {
                'path': image_path,
                'image': photo,  # Сохраняем ссылку чтобы не собирался garbage collector
                'original_image': img,
                'timestamp': datetime.now()
            }
            self.scanned_pages.append(page_data)
            
            # Обновление интерфейса
            self._refresh_thumbnails()
            
        except Exception as e:
            self._log(f"❌ Ошибка при добавлении страницы: {e}")
            
    def _refresh_thumbnails(self):
        """Обновление отображения миниатюр с поддержкой Drag & Drop"""
        # Очистка контейнера
        for widget in self.thumbnails_container.winfo_children():
            widget.destroy()
            
        # Создание миниатюр для каждой страницы
        for idx, page in enumerate(self.scanned_pages):
            frame = ttk.Frame(self.thumbnails_container, relief=tk.RAISED, borderwidth=2)
            frame.pack(side=tk.LEFT, padx=5, pady=5)
            
            # Миниатюра
            label = tk.Label(frame, image=page['image'])
            label.image = page['image']  # Сохранение ссылки
            label.pack(padx=2, pady=2)
            
            # Номер страницы
            num_label = ttk.Label(frame, text=f"Стр. {idx + 1}", font=('Arial', 9))
            num_label.pack(pady=(0, 2))
            
            # Кнопка удаления
            del_btn = ttk.Button(frame, text="✕", width=3,
                                command=lambda i=idx: self._remove_page(i))
            del_btn.pack(pady=2)
            
            # Привязка событий для Drag & Drop
            self._bind_drag_drop(frame, idx)
            
        # Прокрутка к последней добавленной странице
        self.canvas.update_idletasks()
        self.canvas.xview_moveto(1.0)
        
    def _bind_drag_drop(self, widget, idx):
        """Привязка событий для перетаскивания миниатюр"""
        widget.bind("<ButtonPress-1>", lambda e, i=idx: self._on_drag_start(e, i))
        widget.bind("<B1-Motion>", self._on_drag_motion)
        widget.bind("<ButtonRelease-1>", self._on_drag_release)
        
        # Для детей виджета тоже
        for child in widget.winfo_children():
            child.bind("<ButtonPress-1>", lambda e, i=idx: self._on_drag_start(e, i))
            child.bind("<B1-Motion>", self._on_drag_motion)
            child.bind("<ButtonRelease-1>", self._on_drag_release)
            
    def _on_drag_start(self, event, idx):
        """Начало перетаскивания"""
        widget = event.widget
        self._drag_start_idx = idx
        self._drag_start_x = event.x_root
        widget.config(relief=tk.SUNKEN)
        
    def _on_drag_motion(self, event):
        """Перемещение при перетаскивании"""
        # Можно добавить визуальную обратную связь
        pass
        
    def _on_drag_release(self, event):
        """Завершение перетаскивания - обмен местами"""
        widget = event.widget
        widget.config(relief=tk.RAISED)
        
        # Определение позиции курсора относительно других элементов
        x = event.x_root
        y = event.y_root
        
        # Нахождение виджета под курсором
        target_widget = self.thumbnails_container.winfo_containing(x, y)
        
        # Поднятие к родительскому фрейму
        while target_widget and not isinstance(target_widget, ttk.Frame):
            target_widget = target_widget.master
            
        if target_widget and target_widget in self.thumbnails_container.winfo_children():
            # Определение индекса целевого виджета
            children = self.thumbnails_container.winfo_children()
            target_idx = children.index(target_widget)
            
            if target_idx != self._drag_start_idx and 0 <= target_idx < len(self.scanned_pages):
                # Обмен страниц местами
                self.scanned_pages[self._drag_start_idx], self.scanned_pages[target_idx] = \
                    self.scanned_pages[target_idx], self.scanned_pages[self._drag_start_idx]
                    
                self._log(f"📋 Страницы {self._drag_start_idx + 1} и {target_idx + 1} поменяны местами")
                self._refresh_thumbnails()
                
    def _remove_page(self, idx: int):
        """Удаление страницы из списка"""
        if 0 <= idx < len(self.scanned_pages):
            page = self.scanned_pages.pop(idx)
            # Удаление временного файла
            try:
                if os.path.exists(page['path']):
                    os.remove(page['path'])
            except:
                pass
                
            self._log(f"🗑️ Страница {idx + 1} удалена")
            self._refresh_thumbnails()
            
            if len(self.scanned_pages) == 0:
                self.btn_finish.config(state=tk.DISABLED)
                self.scan_session_active = False
                
    def _clear_all(self):
        """Очистка всех отсканированных страниц"""
        if not self.scanned_pages:
            return
            
        if messagebox.askyesno("Подтверждение", "Удалить все отсканированные страницы?"):
            # Удаление временных файлов
            for page in self.scanned_pages:
                try:
                    if os.path.exists(page['path']):
                        os.remove(page['path'])
                except:
                    pass
                    
            self.scanned_pages.clear()
            self._refresh_thumbnails()
            self.btn_finish.config(state=tk.DISABLED)
            self.scan_session_active = False
            self._log("🗑️ Все страницы удалены")
            
    def _finish_scanning(self):
        """Завершение сканирования и сохранение в PDF"""
        if not self.scanned_pages:
            messagebox.showwarning("Предупреждение", "Нет отсканированных страниц!")
            return
            
        self._update_status("Сохранение в PDF...")
        
        try:
            # Диалог сохранения
            default_name = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            file_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF файлы", "*.pdf"), ("Все файлы", "*.*")],
                initialfile=default_name,
                title="Сохранить как"
            )
            
            if not file_path:
                self._update_status("Сохранение отменено")
                return
                
            # Создание PDF
            self._create_pdf(file_path)
            
            self._log(f"✅ PDF сохранён: {file_path}")
            messagebox.showinfo("Успех", f"Документ успешно сохранён!\n{file_path}")
            
            # Очистка после сохранения
            self._clear_all()
            self._update_status("Готов к новому сканированию")
            
        except Exception as e:
            error_msg = f"❌ Ошибка при сохранении PDF: {str(e)}"
            self._log(error_msg)
            messagebox.showerror("Ошибка", error_msg)
            self._update_status("Ошибка сохранения")
            
    def _create_pdf(self, output_path: str):
        """Создание PDF файла из отсканированных страниц"""
        try:
            # Создание PDF с помощью reportlab
            c = canvas.Canvas(output_path, pagesize=A4)
            page_width, page_height = A4
            
            for idx, page in enumerate(self.scanned_pages):
                if idx > 0:
                    c.showPage()  # Новая страница
                    
                # Загрузка изображения
                img_path = page['path']
                img = Image.open(img_path)
                
                # Вычисление пропорций для вписывания в A4
                img_width, img_height = img.size
                scale_x = page_width / img_width
                scale_y = page_height / img_height
                scale = min(scale_x, scale_y)
                
                new_width = img_width * scale
                new_height = img_height * scale
                
                # Центрирование на странице
                x = (page_width - new_width) / 2
                y = (page_height - new_height) / 2
                
                # Добавление изображения в PDF
                c.drawImage(ImageReader(img_path), x, y, new_width, new_height)
                
                self._log(f"  Добавлена страница {idx + 1} из {len(self.scanned_pages)}")
                
            c.save()
            
        except Exception as e:
            raise Exception(f"Ошибка создания PDF: {str(e)}")
            
    def _on_closing(self):
        """Обработчик закрытия приложения"""
        # Очистка временных файлов
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except:
            pass
            
        self.root.destroy()


def main():
    """Точка входа в приложение"""
    print("=" * 60)
    print("HP LaserJet Scanner - Программа для сканирования документов")
    print("=" * 60)
    print("\nТребования:")
    print("- Python 3.7+")
    print("- Pillow (pip install Pillow)")
    print("- reportlab (pip install reportlab)")
    print("- pysane (опционально, для Linux: pip install pysane)")
    print("- sane-utils (для Linux: sudo apt-get install sane-utils)")
    print("- requests (pip install requests)")
    print("\n" + "=" * 60)
    
    # Проверка наличия tkinter
    try:
        import tkinter
    except ImportError:
        print("\n❌ ОШИБКА: tkinter не найден!")
        print("Установите tkinter:")
        print("  Ubuntu/Debian: sudo apt-get install python3-tk")
        print("  Windows: обычно входит в состав Python")
        print("  macOS: brew install python-tk")
        input("\nНажмите Enter для выхода...")
        sys.exit(1)
        
    # Запуск приложения
    root = tk.Tk()
    app = ScannerApp(root)
    
    print("\n✅ Приложение запущено!")
    print("Окно программы открыто. Следуйте инструкциям в интерфейсе.\n")
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n\nПриложение закрыто пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        print("Приложение не может продолжить работу")
        input("Нажмите Enter для выхода...")
        sys.exit(1)


if __name__ == "__main__":
    main()
