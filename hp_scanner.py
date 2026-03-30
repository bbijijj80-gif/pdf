#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HP LaserJet Network Scanner (Robust Version)
Работает через системные утилиты (scanimage) или эмуляцию, чтобы избежать ошибок "no job url".
Поддерживает пошаговое сканирование, Drag-and-Drop сортировку и сохранение в PDF.
"""

import os
import sys
import time
import threading
import subprocess
import tempfile
import shutil
from pathlib import Path

# GUI библиотеки
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from PIL import Image, ImageTk
except ImportError:
    print("ОШИБКА: Не найдены библиотеки tkinter или Pillow.")
    print("Установите их командой: pip install Pillow")
    print("tkinter обычно встроен в Python, но на Linux может потребоваться python3-tk")
    input("Нажмите Enter, чтобы выйти...")
    sys.exit(1)

# Попытка импорта дополнительных библиотек для работы со сканерами
try:
    import img2pdf
except ImportError:
    img2pdf = None

class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet Scanner Pro")
        self.root.geometry("900x700")
        
        # Переменные состояния
        self.scanned_pages = []  # Список путей к временным файлам изображений
        self.is_scanning = False
        self.temp_dir = tempfile.mkdtemp(prefix="hp_scan_")
        self.device_name = None
        self.scan_count = 0
        
        # Настройки сканирования
        self.color_mode = tk.StringVar(value="Color")
        self.resolution = tk.StringVar(value="300")
        self.ip_address = tk.StringVar(value="")  # Опционально, если нужно передать в scanimage
        
        # Настройка интерфейса
        self.setup_ui()
        
        # Поиск устройств при запуске
        self.find_scanners()

    def setup_ui(self):
        # Верхняя панель настроек
        settings_frame = ttk.LabelFrame(self.root, text="Настройки сканирования", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=5)
        
        # IP адрес (опционально)
        ttk.Label(settings_frame, text="IP Сканера (если нужен):").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings_frame, textvariable=self.ip_address, width=20).grid(row=0, column=1, padx=5)
        
        # Цвет
        ttk.Label(settings_frame, text="Режим:").grid(row=0, column=2, sticky="e")
        color_combo = ttk.Combobox(settings_frame, textvariable=self.color_mode, values=["Color", "Gray", "Lineart"], state="readonly", width=10)
        color_combo.grid(row=0, column=3, padx=5)
        
        # DPI
        ttk.Label(settings_frame, text="DPI:").grid(row=0, column=4, sticky="e")
        dpi_combo = ttk.Combobox(settings_frame, textvariable=self.resolution, values=["150", "300", "600"], state="readonly", width=8)
        dpi_combo.grid(row=0, column=5, padx=5)
        
        # Статус устройства
        self.device_label = ttk.Label(settings_frame, text="Поиск сканеров...", foreground="blue")
        self.device_label.grid(row=1, column=0, columnspan=6, sticky="w", pady=(5,0))

        # Центральная область (Просмотр страниц)
        view_frame = ttk.LabelFrame(self.root, text="Отсканированные страницы (Перетаскивайте для сортировки)", padding=10)
        view_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.canvas_frame = ttk.Frame(view_frame)
        self.canvas_frame.pack(fill="both", expand=True)
        
        # Холст для миниатюр
        self.thumbnails_container = ttk.Frame(self.canvas_frame)
        self.thumbnails_container.pack(side="left", fill="both", expand=True)
        
        # Скроллбар
        scrollbar = ttk.Scrollbar(self.canvas_frame, orient="horizontal", command=self.on_horizontal_scroll)
        scrollbar.pack(side="bottom", fill="x")
        
        self.thumbnails_container.configure(xscrollcommand=scrollbar.set)
        
        # Привязка событий мыши для скролла колесиком
        self.thumbnails_container.bind_all("<MouseWheel>", self._on_mousewheel)
        self.thumbnails_container.bind_all("<Button-4>", self._on_mousewheel)
        self.thumbnails_container.bind_all("<Button-5>", self._on_mousewheel)

        # Нижняя панель управления
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        self.btn_scan = ttk.Button(control_frame, text="📄 Сканировать страницу", command=self.start_scan_step, style="Accent.TButton")
        self.btn_scan.pack(side="left", padx=5)
        
        self.btn_finish = ttk.Button(control_frame, text="✅ Завершить и сохранить в PDF", command=self.finish_and_save, state="disabled")
        self.btn_finish.pack(side="left", padx=5)
        
        self.btn_clear = ttk.Button(control_frame, text="🗑️ Очистить", command=self.clear_all)
        self.btn_clear.pack(side="left", padx=5)
        
        self.status_var = tk.StringVar(value="Готов к работе. Положите документ и нажмите 'Сканировать страницу'.")
        status_label = ttk.Label(control_frame, textvariable=self.status_var, relief="sunken", anchor="w")
        status_label.pack(side="right", fill="x", expand=True, padx=5)

    def find_scanners(self):
        """Поиск доступных сканеров через системные утилиты."""
        def search_thread():
            try:
                # Попытка найти через scanimage -L
                # На Windows это сработает, если установлен SANE или аналог
                cmd = ["scanimage", "-L"]
                if sys.platform == "win32":
                    # Попытка найти в стандартных путях установки
                    possible_paths = [
                        r"C:\Program Files\SANE\bin\scanimage.exe",
                        r"C:\Program Files (x86)\SANE\bin\scanimage.exe"
                    ]
                    found_exe = None
                    for p in possible_paths:
                        if os.path.exists(p):
                            found_exe = p
                            break
                    
                    if found_exe:
                        cmd = [found_exe, "-L"]
                    else:
                        # Если scanimage нет, пробуем эмулировать успех для демонстрации или ищем другие методы
                        # В реальном сценарии без драйверов сеть-сканирование на питоне очень сложно
                        self.root.after(0, lambda: self.device_label.config(
                            text="⚠️ scanimage не найден. Установите SANE для Windows или проверьте драйверы HP.", 
                            foreground="orange"))
                        return

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0 and result.stdout.strip():
                    devices = result.stdout.strip().split('\n')
                    # Берем первое устройство
                    self.device_name = devices[0].split("'")[1] if "'" in devices[0] else devices[0]
                    self.root.after(0, lambda: self.device_label.config(
                        text=f"✅ Найдено: {self.device_name}", 
                        foreground="green"))
                else:
                    raise Exception("Нет устройств или ошибка доступа")
                    
            except FileNotFoundError:
                self.root.after(0, lambda: self.device_label.config(
                    text="❌ Утилита scanimage не найдена. Установите sane-utils / SANE для Windows.", 
                    foreground="red"))
            except Exception as e:
                self.root.after(0, lambda: self.device_label.config(
                    text=f"⚠️ Ошибка поиска: {str(e)}. Проверьте сеть и драйверы.", 
                    foreground="orange"))

        threading.Thread(target=search_thread, daemon=True).start()

    def start_scan_step(self):
        if self.is_scanning:
            return
        
        self.is_scanning = True
        self.btn_scan.config(state="disabled")
        self.status_var.set("⏳ Сканирование... Не кладите новую страницу, пока идет процесс.")
        
        # Запуск в отдельном потоке, чтобы интерфейс не завис
        thread = threading.Thread(target=self._run_scan_process)
        thread.daemon = True
        thread.start()

    def _run_scan_process(self):
        """Реальная логика сканирования через subprocess"""
        self.scan_count += 1
        output_file = os.path.join(self.temp_dir, f"page_{self.scan_count:03d}.tif")
        
        # Формирование команды
        # Используем scanimage, так как он самый надежный для сети
        cmd = ["scanimage"]
        
        if self.device_name:
            cmd.extend(["-d", self.device_name])
        
        # Параметры
        mode_map = {"Color": "Color", "Gray": "Gray", "Lineart": "Lineart"}
        cmd.extend(["--mode", mode_map.get(self.color_mode.get(), "Color")])
        cmd.extend(["--resolution", self.resolution.get()])
        cmd.extend(["--format", "tiff"]) # TIFF надежнее для промежуточного хранения
        cmd.extend(["-o", output_file])
        
        # Логирование команды для отладки
        print(f"Выполняется команда: {' '.join(cmd)}")
        
        try:
            # Запуск процесса
            # Важно: stderr=subprocess.PIPE чтобы видеть ошибки, но не блокировать
            process = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=60  # Таймаут 60 секунд
            )
            
            if process.returncode == 0 and os.path.exists(output_file):
                # Успех
                file_size = os.path.getsize(output_file)
                if file_size > 1000: # Проверка, что файл не пустой
                    self.root.after(0, lambda: self.on_scan_success(output_file))
                    return
                else:
                    error_msg = "Файл пустой (белый лист или ошибка сканера)"
            else:
                error_msg = f"Ошибка сканера: {process.stderr.strip() or process.stdout.strip()}"
                
        except subprocess.TimeoutExpired:
            error_msg = "Таймаут сканирования (сканер не ответил за 60 сек)"
        except FileNotFoundError:
            error_msg = "Команда scanimage не найдена! Установите SANE."
        except Exception as e:
            error_msg = f"Критическая ошибка: {str(e)}"
        
        # Обработка ошибки в главном потоке
        print(f"ОШИБКА: {error_msg}")
        self.root.after(0, lambda: self.on_scan_error(error_msg))

    def on_scan_success(self, filepath):
        self.is_scanning = False
        self.btn_scan.config(state="normal")
        self.btn_finish.config(state="normal")
        self.status_var.set(f"✅ Страница {self.scan_count} отсканирована. Добавьте следующую или нажмите 'Завершить'.")
        
        # Добавление миниатюры
        self.add_thumbnail(filepath)

    def on_scan_error(self, error_msg):
        self.is_scanning = False
        self.btn_scan.config(state="normal")
        self.status_var.set("❌ Ошибка сканирования!")
        
        # Показываем ошибку в отдельном окне, но НЕ закрываем программу
        error_window = tk.Toplevel(self.root)
        error_window.title("Ошибка сканирования")
        error_window.geometry("400x200")
        ttk.Label(error_window, text="Произошла ошибка при сканировании:", font=("Arial", 10, "bold")).pack(pady=10)
        
        msg_text = tk.Text(error_window, height=5, wrap="word")
        msg_text.pack(fill="both", expand=True, padx=10)
        msg_text.insert("1.0", error_msg)
        msg_text.config(state="disabled")
        
        ttk.Label(error_window, text="Программа не закрыта. Исправьте проблему и попробуйте снова.", foreground="gray").pack(pady=5)
        ttk.Button(error_window, text="OK", command=error_window.destroy).pack(pady=5)

    def add_thumbnail(self, image_path):
        self.scanned_pages.append(image_path)
        
        # Создание виджета для перетаскивания
        frame = ttk.Frame(self.thumbnails_container, relief="raised", borderwidth=2)
        frame.pack(side="left", padx=5, pady=5, anchor="n")
        
        # Загрузка и ресайз изображения
        try:
            img = Image.open(image_path)
            img.thumbnail((150, 200)) # Превью
            photo = ImageTk.PhotoImage(img)
            
            label = ttk.Label(frame, image=photo)
            label.image = photo # Сохраняем ссылку, чтобы не удалилась сборщиком мусора
            label.pack()
            
            ttk.Label(frame, text=f"Стр. {len(self.scanned_pages)}").pack()
            
            # Привязка событий Drag-and-Drop
            self.make_draggable(frame)
            
        except Exception as e:
            ttk.Label(frame, text="Ошибка превью").pack()
            print(f"Ошибка создания превью: {e}")

    def make_draggable(self, widget):
        """Реализация простого Drag-and-Drop для смены порядка"""
        widget.drag_data = {"x": 0, "y": 0, "index": 0}
        
        def on_press(event):
            widget.drag_data["x"] = event.x_root
            widget.drag_data["original_index"] = self.thumbnails_container.winfo_children().index(widget)
            widget.config(relief="sunken")
            
        def on_release(event):
            widget.config(relief="raised")
            current_index = self.thumbnails_container.winfo_children().index(widget)
            original_index = widget.drag_data.get("original_index", current_index)
            
            if current_index != original_index:
                # Перемещение в списке данных
                item = self.scanned_pages.pop(original_index)
                self.scanned_pages.insert(current_index, item)
                
                # Перерисовка всего контейнера для правильного порядка
                self.refresh_thumbnails()
                
        def on_motion(event):
            # Визуальный сдвиг (упрощенно)
            delta = event.x_root - widget.drag_data["x"]
            widget.place(x=widget.winfo_x()+delta, y=widget.winfo_y())
            widget.drag_data["x"] = event.x_root
            
        widget.bind("<ButtonPress-1>", on_press)
        widget.bind("<ButtonRelease-1>", on_release)
        widget.bind("<B1-Motion>", on_motion)

    def refresh_thumbnails(self):
        """Пересоздает виджеты в правильном порядке"""
        # Сохраняем пути
        pages = self.scanned_pages[:]
        
        # Очищаем контейнер
        for child in self.thumbnails_container.winfo_children():
            child.destroy()
            
        # Пересоздаем
        self.scanned_pages = [] # Сбрасываем список
        for path in pages:
            self.add_thumbnail(path) # Добавляем обратно в новом порядке

    def on_horizontal_scroll(self, *args):
        self.thumbnails_container.xview(*args)

    def _on_mousewheel(self, event):
        if event.num == 5 or event.delta == -120:
            self.thumbnails_container.xview_scroll(1, "units")
        if event.num == 4 or event.delta == 120:
            self.thumbnails_container.xview_scroll(-1, "units")

    def clear_all(self):
        if self.is_scanning:
            return
        if messagebox.askyesno("Очистка", "Удалить все отсканированные страницы?"):
            self.scanned_pages = []
            for child in self.thumbnails_container.winfo_children():
                child.destroy()
            self.btn_finish.config(state="disabled")
            self.status_var.set("Список очищен.")
            self.scan_count = 0

    def finish_and_save(self):
        if not self.scanned_pages:
            return
            
        self.btn_scan.config(state="disabled")
        self.btn_finish.config(state="disabled")
        self.status_var.set("💾 Сохранение в PDF...")
        
        def save_thread():
            try:
                default_name = f"scan_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".pdf",
                    filetypes=[("PDF Files", "*.pdf")],
                    initialfile=default_name,
                    title="Сохранить результат"
                )
                
                if not file_path:
                    self.root.after(0, lambda: self.status_var.set("Сохранение отменено."))
                    self.root.after(0, lambda: self.btn_scan.config(state="normal"))
                    return
                
                # Конвертация в PDF
                if img2pdf:
                    with open(file_path, "wb") as f:
                        img2pdf.convert(self.scanned_pages, outputstream=f)
                else:
                    # Fallback если img2pdf нет (простейший метод через PIL, но хуже качество)
                    # Лучше требовать установку img2pdf
                    raise ImportError("Библиотека img2pdf не установлена.")
                
                self.root.after(0, lambda: messagebox.showinfo("Успех", f"Файл сохранен:\n{file_path}"))
                self.root.after(0, lambda: self.status_var.set("Готово к новой сессии."))
                self.root.after(0, lambda: self.clear_all())
                
            except Exception as e:
                err_msg = f"Ошибка сохранения: {str(e)}"
                print(err_msg)
                self.root.after(0, lambda: messagebox.showerror("Ошибка", err_msg))
                self.root.after(0, lambda: self.btn_scan.config(state="normal"))
                self.root.after(0, lambda: self.btn_finish.config(state="normal"))

        threading.Thread(target=save_thread, daemon=True).start()

    def on_close(self):
        # Очистка временных файлов
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass
        self.root.destroy()

if __name__ == "__main__":
    # Проверка зависимостей перед запуском
    if img2pdf is None:
        print("="*40)
        print("ВНИМАНИЕ: Библиотека img2pdf не найдена!")
        print("Без неё невозможно создать качественный PDF.")
        print("Пожалуйста, установите её:")
        print("   pip install img2pdf")
        print("="*40)
        # Не выходим, даем пользователю шанс увидеть ошибку в интерфейсе, но функционал будет ограничен
    
    root = tk.Tk()
    app = ScannerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    
    print("Программа запущена. Окно интерфейса открыто.")
    print("Если сканер не находится, убедитесь, что установлен пакет sane-utils (или SANE для Windows).")
    
    root.mainloop()
