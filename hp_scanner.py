#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Программа для сканирования документов с HP LaserJet по сети
- Пошаговое сканирование (положил страницу -> отсканировал -> положил следующую)
- Редактор порядка страниц с перетаскиванием
- Сохранение в один PDF
- Окно не закрывается при ошибках
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import os
import tempfile
import shutil
from PIL import Image, ImageTk
import img2pdf
import threading

class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet Scanner")
        self.root.geometry("1000x700")
        
        # Хранилище отсканированных страниц
        self.scanned_pages = []  # Список путей к временным файлам
        self.temp_dir = tempfile.mkdtemp(prefix="scanner_")
        self.current_page_index = 0
        
        # Настройки сканирования
        self.scanner_address = tk.StringVar(value="net:192.168.1.100")
        self.color_mode = tk.StringVar(value="Gray")
        self.resolution = tk.StringVar(value="300")
        
        self.setup_ui()
        
        # Обработчик закрытия
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        """Создание интерфейса"""
        # Верхняя панель настроек
        settings_frame = ttk.LabelFrame(self.root, text="Настройки сканирования", padding=10)
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Адрес сканера
        ttk.Label(settings_frame, text="Адрес сканера:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.address_entry = ttk.Entry(settings_frame, textvariable=self.scanner_address, width=30)
        self.address_entry.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # Цветовой режим
        ttk.Label(settings_frame, text="Цвет:").grid(row=0, column=2, sticky=tk.W, padx=10)
        self.color_combo = ttk.Combobox(settings_frame, textvariable=self.color_mode, 
                                        values=["Gray", "Color", "Lineart"], width=10, state="readonly")
        self.color_combo.grid(row=0, column=3, sticky=tk.W, padx=5)
        
        # Разрешение
        ttk.Label(settings_frame, text="DPI:").grid(row=0, column=4, sticky=tk.W, padx=10)
        self.resolution_combo = ttk.Combobox(settings_frame, textvariable=self.resolution,
                                             values=["150", "300", "600"], width=8, state="readonly")
        self.resolution_combo.grid(row=0, column=5, sticky=tk.W, padx=5)
        
        # Кнопка обновления списка сканеров
        ttk.Button(settings_frame, text="Найти сканеры", command=self.find_scanners).grid(row=0, column=6, padx=10)
        
        # Статус сканера
        self.status_label = ttk.Label(settings_frame, text="Статус: Не подключено", foreground="gray")
        self.status_label.grid(row=1, column=0, columnspan=7, sticky=tk.W, pady=5)
        
        # Основная область
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Область предпросмотра
        preview_frame = ttk.LabelFrame(main_frame, text="Отсканированные страницы", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # Canvas для прокрутки и перетаскивания
        self.canvas = tk.Canvas(preview_frame, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.canvas.xview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Привязка событий для перетаскивания
        self.scrollable_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # Панель управления сканированием
        scan_control_frame = ttk.LabelFrame(main_frame, text="Управление сканированием", padding=10, width=250)
        scan_control_frame.pack(fill=tk.Y, side=tk.RIGHT, padx=(10, 0))
        scan_control_frame.pack_propagate(False)
        
        self.scan_btn = ttk.Button(scan_control_frame, text="📄 Сканировать страницу", command=self.scan_page)
        self.scan_btn.pack(fill=tk.X, pady=5)
        
        self.finish_btn = ttk.Button(scan_control_frame, text="✅ Завершить и сохранить", 
                                     command=self.finish_scanning, state=tk.DISABLED)
        self.finish_btn.pack(fill=tk.X, pady=5)
        
        self.clear_btn = ttk.Button(scan_control_frame, text="🗑️ Очистить всё", command=self.clear_all)
        self.clear_btn.pack(fill=tk.X, pady=5)
        
        # Индикатор количества страниц
        self.page_count_label = ttk.Label(scan_control_frame, text="Страниц: 0", font=("Arial", 12, "bold"))
        self.page_count_label.pack(pady=10)
        
        # Лог операций
        log_frame = ttk.LabelFrame(self.root, text="Журнал операций", padding=5)
        log_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=4, wrap=tk.WORD)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log("Программа готова. Введите адрес сканера и нажмите 'Найти сканеры'.")
    
    def log(self, message):
        """Добавление сообщения в лог"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def find_scanners(self):
        """Поиск доступных сканеров"""
        self.log("Поиск сканеров...")
        try:
            result = subprocess.run(["scanimage", "-L"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                scanners = result.stdout.strip()
                if scanners:
                    self.log(f"Найдены сканеры:\n{scanners}")
                    self.status_label.config(text="Статус: Сканеры найдены", foreground="green")
                else:
                    self.log("Сканеры не найдены. Проверьте подключение.")
                    self.status_label.config(text="Статус: Сканеры не найдены", foreground="red")
            else:
                error_msg = result.stderr.strip() if result.stderr else "Неизвестная ошибка"
                self.log(f"Ошибка поиска сканеров: {error_msg}")
                self.status_label.config(text="Статус: Ошибка", foreground="red")
        except FileNotFoundError:
            self.log("Ошибка: команда scanimage не найдена. Установите sane-utils.")
            self.status_label.config(text="Статус: Ошибка установки", foreground="red")
        except Exception as e:
            self.log(f"Ошибка: {str(e)}")
            self.status_label.config(text="Статус: Ошибка", foreground="red")
    
    def scan_page(self):
        """Сканирование одной страницы"""
        scanner_addr = self.scanner_address.get().strip()
        if not scanner_addr:
            messagebox.showerror("Ошибка", "Введите адрес сканера!")
            return
        
        self.scan_btn.config(state=tk.DISABLED)
        self.log(f"Сканирование страницы {len(self.scanned_pages) + 1}...")
        
        # Запуск в отдельном потоке
        thread = threading.Thread(target=self._scan_page_thread, args=(scanner_addr,))
        thread.daemon = True
        thread.start()
    
    def _scan_page_thread(self, scanner_addr):
        """Поток сканирования"""
        try:
            output_file = os.path.join(self.temp_dir, f"page_{len(self.scanned_pages) + 1}.png")
            
            # Формирование команды scanimage
            cmd = [
                "scanimage",
                "-d", scanner_addr,
                "--mode", self.color_mode.get(),
                "--resolution", self.resolution.get(),
                "--format", "png",
                "-o", output_file
            ]
            
            self.log(f"Выполнение: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Неизвестная ошибка сканирования"
                # Важно: не закрываем терминал, просто показываем ошибку
                self.log(f"❌ Ошибка сканирования: {error_msg}")
                self.root.after(0, lambda: messagebox.showerror("Ошибка сканирования", 
                    f"Не удалось отсканировать страницу.\n\nОшибка: {error_msg}\n\n"
                    f"Проверьте:\n- Адрес сканера\n- Подключение к сети\n- Наличие бумаги"))
            else:
                if os.path.exists(output_file):
                    self.scanned_pages.append(output_file)
                    self.root.after(0, lambda: self.on_scan_success(output_file))
                else:
                    self.log(f"❌ Файл не создан: {output_file}")
                    self.root.after(0, lambda: messagebox.showerror("Ошибка", "Файл не был создан"))
                    
        except subprocess.TimeoutExpired:
            self.log("❌ Таймаут сканирования")
            self.root.after(0, lambda: messagebox.showerror("Таймаут", "Сканирование заняло слишком много времени"))
        except Exception as e:
            self.log(f"❌ Критическая ошибка: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Критическая ошибка: {str(e)}"))
        finally:
            self.root.after(0, self.enable_scan_button)
    
    def on_scan_success(self, file_path):
        """Обработка успешного сканирования"""
        self.log(f"✅ Страница {len(self.scanned_pages)} отсканирована")
        self.update_page_display()
        self.page_count_label.config(text=f"Страниц: {len(self.scanned_pages)}")
        self.finish_btn.config(state=tk.NORMAL if len(self.scanned_pages) > 0 else tk.DISABLED)
    
    def enable_scan_button(self):
        """Включение кнопки сканирования"""
        self.scan_btn.config(state=tk.NORMAL)
    
    def update_page_display(self):
        """Обновление отображения страниц"""
        # Очистка canvas
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Отображение всех страниц
        self.page_widgets = []
        for i, page_path in enumerate(self.scanned_pages):
            try:
                # Загрузка изображения
                img = Image.open(page_path)
                # Масштабирование для предпросмотра
                max_height = 200
                ratio = max_height / img.height
                new_width = int(img.width * ratio)
                new_height = max_height
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                photo = ImageTk.PhotoImage(img_resized)
                
                # Создание фрейма для страницы
                page_frame = ttk.Frame(self.scrollable_frame, relief=tk.RAISED, borderwidth=1)
                page_frame.pack(side=tk.LEFT, padx=5, pady=5)
                
                # Метка с изображением
                label = ttk.Label(page_frame, image=photo, cursor="hand")
                label.image = photo  # Сохраняем ссылку
                label.pack()
                
                # Номер страницы
                num_label = ttk.Label(page_frame, text=f"Стр. {i+1}", font=("Arial", 9, "bold"))
                num_label.pack(pady=2)
                
                # Кнопка удаления
                del_btn = ttk.Button(page_frame, text="✕", width=3,
                                    command=lambda idx=i: self.delete_page(idx))
                del_btn.pack(pady=2)
                
                # Привязка событий для перетаскивания
                self.make_draggable(page_frame, i)
                
                self.page_widgets.append(page_frame)
                
            except Exception as e:
                self.log(f"Ошибка отображения страницы {i+1}: {str(e)}")
    
    def make_draggable(self, widget, index):
        """Сделать виджет перетаскиваемым"""
        widget.bind("<ButtonPress-1>", lambda e, idx=index: self.on_drag_start(e, idx))
        widget.bind("<B1-Motion>", self.on_drag_motion)
        widget.bind("<ButtonRelease-1>", self.on_drag_release)
        
        # Также привязываем к дочерним элементам
        for child in widget.winfo_children():
            child.bind("<ButtonPress-1>", lambda e, idx=index: self.on_drag_start(e, idx))
            child.bind("<B1-Motion>", self.on_drag_motion)
            child.bind("<ButtonRelease-1>", self.on_drag_release)
    
    def on_drag_start(self, event, index):
        """Начало перетаскивания"""
        self.drag_start_x = event.x_root
        self.drag_start_index = index
        self.drag_widget = self.page_widgets[index]
        self.drag_widget.config(relief=tk.SOLID, borderwidth=3)
    
    def on_drag_motion(self, event):
        """Перемещение при перетаскивании"""
        if hasattr(self, 'drag_widget'):
            delta = event.x_root - self.drag_start_x
            # Визуальное смещение (фактическое перемещение будет при отпускании)
            pass
    
    def on_drag_release(self, event):
        """Завершение перетаскивания"""
        if not hasattr(self, 'drag_widget'):
            return
        
        self.drag_widget.config(relief=tk.RAISED, borderwidth=1)
        
        # Определение новой позиции
        current_x = self.drag_widget.winfo_x()
        new_x = event.x_root - self.scrollable_frame.winfo_rootx() + self.canvas.xview()[0] * self.scrollable_frame.winfo_width()
        
        # Поиск соседнего виджета
        target_index = self.drag_start_index
        min_distance = float('inf')
        
        for i, widget in enumerate(self.page_widgets):
            if i == self.drag_start_index:
                continue
            widget_x = widget.winfo_x()
            distance = abs(new_x - widget_x)
            if distance < min_distance:
                min_distance = distance
                target_index = i
        
        # Если позиция изменилась, меняем порядок
        if target_index != self.drag_start_index:
            # Перемещение в списке
            page = self.scanned_pages.pop(self.drag_start_index)
            self.scanned_pages.insert(target_index, page)
            self.log(f"Страница {self.drag_start_index + 1} перемещена на позицию {target_index + 1}")
            self.update_page_display()
        
        delattr(self, 'drag_widget')
        delattr(self, 'drag_start_x')
        delattr(self, 'drag_start_index')
    
    def delete_page(self, index):
        """Удаление страницы"""
        if 0 <= index < len(self.scanned_pages):
            self.scanned_pages.pop(index)
            self.log(f"Страница {index + 1} удалена")
            self.update_page_display()
            self.page_count_label.config(text=f"Страниц: {len(self.scanned_pages)}")
            if len(self.scanned_pages) == 0:
                self.finish_btn.config(state=tk.DISABLED)
    
    def clear_all(self):
        """Очистка всех страниц"""
        if len(self.scanned_pages) == 0:
            return
        
        if messagebox.askyesno("Подтверждение", "Удалить все отсканированные страницы?"):
            self.scanned_pages.clear()
            self.update_page_display()
            self.page_count_label.config(text="Страниц: 0")
            self.finish_btn.config(state=tk.DISABLED)
            self.log("Все страницы удалены")
    
    def finish_scanning(self):
        """Завершение сканирования и сохранение"""
        if len(self.scanned_pages) == 0:
            messagebox.showwarning("Предупреждение", "Нет отсканированных страниц!")
            return
        
        # Диалог сохранения
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF файлы", "*.pdf")],
            title="Сохранить как",
            initialfile=f"scan_{len(self.scanned_pages)}_pages.pdf"
        )
        
        if not file_path:
            return
        
        try:
            self.log(f"Сохранение {len(self.scanned_pages)} страниц в {file_path}...")
            
            # Конвертация в PDF
            with open(file_path, "wb") as f:
                f.write(img2pdf.convert(self.scanned_pages))
            
            self.log(f"✅ Файл успешно сохранён: {file_path}")
            messagebox.showinfo("Успех", f"Документ сохранён!\n\nФайл: {file_path}\nСтраниц: {len(self.scanned_pages)}")
            
            # Очистка после сохранения
            self.clear_all()
            
        except Exception as e:
            error_msg = str(e)
            self.log(f"❌ Ошибка сохранения: {error_msg}")
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить файл.\n\nОшибка: {error_msg}")
    
    def on_closing(self):
        """Обработчик закрытия окна"""
        if len(self.scanned_pages) > 0:
            response = messagebox.askyesnocancel("Выход", 
                "Есть неотсканированные страницы.\nУдалить их и выйти?")
            if response is None:  # Cancel
                return
            elif not response:  # No - сохранить сначала
                self.finish_scanning()
                if len(self.scanned_pages) > 0:  # Если пользователь отменил сохранение
                    return
        
        # Очистка временных файлов
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass
        
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
