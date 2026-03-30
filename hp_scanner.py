#!/usr/bin/env python3
"""
Программа для сканирования документов с принтера/сканера HP LaserJet по сети.
Функции:
- Сканирование нескольких страниц
- Перетаскивание страниц для изменения порядка (горизонтально)
- Объединение всех страниц в один PDF файл
- Сохранение в том же порядке, в котором расположены страницы
- При ошибке терминал не закрывается - можно увидеть сообщение об ошибке
"""

import sys
import os
import time
import subprocess
import tempfile
import shutil
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from PIL import Image, ImageTk
except ImportError as e:
    print(f"ОШИБКА: Не удалось импортировать необходимые библиотеки: {e}")
    print("Убедитесь, что tkinter и pillow установлены.")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

try:
    import img2pdf
except ImportError:
    print("ОШИБКА: Библиотека img2pdf не установлена.")
    print("Установите её командой: pip install img2pdf")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)


class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Сканер документов HP LaserJet")
        self.root.geometry("1000x700")
        
        # Список отсканированных страниц (каждая страница - это путь к временному файлу изображения)
        self.scanned_pages = []  # Список кортежей (image_path, photo_image, label_widget)
        self.temp_dir = tempfile.mkdtemp(prefix="scanner_")
        
        # Настройки сканирования
        self.scan_resolution = tk.StringVar(value="300")
        self.scan_color = tk.StringVar(value="Color")
        self.scan_format = tk.StringVar(value="PDF")
        self.network_scanner = tk.StringVar(value="")
        
        self.setup_ui()
        self.detect_scanners()
        
        # Обработчик закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        """Создание пользовательского интерфейса"""
        
        # Верхняя панель с настройками
        settings_frame = ttk.LabelFrame(self.root, text="Настройки сканирования", padding=10)
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Сканер
        ttk.Label(settings_frame, text="Сканер:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.scanner_combo = ttk.Combobox(settings_frame, textvariable=self.network_scanner, width=40)
        self.scanner_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(settings_frame, text="Обновить список", command=self.detect_scanners).grid(row=0, column=2, padx=5, pady=5)
        
        # Разрешение
        ttk.Label(settings_frame, text="Разрешение (DPI):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        resolution_combo = ttk.Combobox(settings_frame, textvariable=self.scan_resolution, width=10)
        resolution_combo['values'] = ('150', '200', '300', '400', '600')
        resolution_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Цветность
        ttk.Label(settings_frame, text="Цвет:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        color_combo = ttk.Combobox(settings_frame, textvariable=self.scan_color, width=10)
        color_combo['values'] = ('Color', 'Gray', 'Lineart')
        color_combo.grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)
        
        # Формат сохранения
        ttk.Label(settings_frame, text="Формат:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        format_combo = ttk.Combobox(settings_frame, textvariable=self.scan_format, width=10, state='readonly')
        format_combo['values'] = ('PDF', 'PNG', 'JPEG')
        format_combo.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Кнопки управления
        button_frame = ttk.Frame(settings_frame)
        button_frame.grid(row=0, column=3, rowspan=3, padx=20, pady=5)
        
        self.scan_button = ttk.Button(button_frame, text="📄 Сканировать страницу", command=self.scan_page)
        self.scan_button.pack(fill=tk.X, pady=2)
        
        self.scan_multiple_btn = ttk.Button(button_frame, text="📑 Сканировать несколько", command=self.scan_multiple_pages)
        self.scan_multiple_btn.pack(fill=tk.X, pady=2)
        
        self.save_button = ttk.Button(button_frame, text="💾 Сохранить в PDF", command=self.save_to_pdf)
        self.save_button.pack(fill=tk.X, pady=2)
        
        self.clear_button = ttk.Button(button_frame, text="🗑️ Очистить всё", command=self.clear_all)
        self.clear_button.pack(fill=tk.X, pady=2)
        
        # Область предпросмотра страниц (с прокруткой)
        preview_frame = ttk.LabelFrame(self.root, text="Отсканированные страницы (перетаскивайте для изменения порядка)", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Canvas для прокрутки
        self.canvas = tk.Canvas(preview_frame, bg='white')
        scrollbar_y = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        scrollbar_x = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        self.canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Привязка событий для изменения размера canvas
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # Поддержка перетаскивания
        self.drag_data = {"item": None, "start_x": 0, "start_y": 0}
        
        # Статус бар
        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, padx=10, pady=5)
        
        # Инструкция
        info_label = ttk.Label(self.root, text="💡 Совет: Перетаскивайте страницы мышкой для изменения порядка. Сохранение будет в текущем порядке слева направо.", font=('Arial', 9))
        info_label.pack(padx=10, pady=5)
    
    def on_canvas_configure(self, event):
        """Обработка изменения размера canvas"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def detect_scanners(self):
        """Обнаружение доступных сканеров"""
        self.status_var.set("Поиск сканеров...")
        self.root.update()
        
        try:
            # Попытка найти сканеры через scanimage
            result = subprocess.run(
                ['scanimage', '-L'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            scanners = []
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('device `'):
                        scanner_name = line.split('`')[1].split("'")[0]
                        scanners.append(scanner_name)
            
            if scanners:
                self.scanner_combo['values'] = scanners
                self.scanner_combo.set(scanners[0])
                self.status_var.set(f"Найдено сканеров: {len(scanners)}")
            else:
                self.scanner_combo['values'] = ['net:IP_адрес_принтера']
                self.scanner_combo.set('net:IP_адрес_принтера')
                self.status_var.set("Сканеры не найдены. Введите сетевой адрес вручную (например: net:192.168.1.100)")
                
        except FileNotFoundError:
            self.scanner_combo['values'] = ['net:IP_адрес_принтера']
            self.scanner_combo.set('net:IP_адрес_принтера')
            self.status_var.set("scanimage не найден. Установите sane-utils. Введите сетевой адрес вручную.")
        except Exception as e:
            self.scanner_combo['values'] = ['net:IP_адрес_принтера']
            self.scanner_combo.set('net:IP_адрес_принтера')
            self.status_var.set(f"Ошибка при поиске сканеров: {e}")
    
    def scan_page(self):
        """Сканирование одной страницы"""
        scanner_device = self.scanner_combo.get()
        
        if not scanner_device or scanner_device == 'net:IP_адрес_принтера':
            messagebox.showerror("Ошибка", "Выберите или введите корректный адрес сканера!\nПример: net:192.168.1.100")
            return
        
        self.status_var.set("Сканирование...")
        self.root.update()
        
        # Генерация имени файла
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        image_path = os.path.join(self.temp_dir, f"scan_{timestamp}.png")
        
        try:
            # Формирование команды сканирования
            cmd = [
                'scanimage',
                '-d', scanner_device,
                '--resolution', self.scan_resolution.get(),
                '--mode', self.scan_color.get().lower(),
                '-o', image_path,
                '--format', 'png'
            ]
            
            self.status_var.set(f"Сканирование: {scanner_device}...")
            self.root.update()
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else "Неизвестная ошибка сканирования"
                raise Exception(f"Ошибка сканирования: {error_msg}")
            
            if not os.path.exists(image_path):
                raise Exception("Файл изображения не был создан после сканирования")
            
            # Добавление страницы в интерфейс
            self.add_page_to_preview(image_path)
            self.status_var.set(f"Страница отсканирована успешно! Всего страниц: {len(self.scanned_pages)}")
            
        except subprocess.TimeoutExpired:
            error_msg = "Тайм-аут сканирования (превышено 2 минуты)"
            self.status_var.set(f"ОШИБКА: {error_msg}")
            messagebox.showerror("Ошибка сканирования", error_msg)
        except FileNotFoundError:
            error_msg = "Команда scanimage не найдена. Установите пакет sane-utils."
            self.status_var.set(f"ОШИБКА: {error_msg}")
            messagebox.showerror("Ошибка", error_msg)
        except Exception as e:
            error_msg = str(e)
            self.status_var.set(f"ОШИБКА: {error_msg}")
            messagebox.showerror("Ошибка сканирования", f"Произошла ошибка:\n{error_msg}\n\nПроверьте подключение к сканеру и настройки.")
    
    def scan_multiple_pages(self):
        """Сканирование нескольких страниц подряд"""
        scanner_device = self.scanner_combo.get()
        
        if not scanner_device or scanner_device == 'net:IP_адрес_принтера':
            messagebox.showerror("Ошибка", "Выберите или введите корректный адрес сканера!")
            return
        
        # Диалог для указания количества страниц
        dialog = tk.Toplevel(self.root)
        dialog.title("Многостраничное сканирование")
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Количество страниц:").pack(pady=10)
        page_count_var = tk.StringVar(value="3")
        page_count_entry = ttk.Entry(dialog, textvariable=page_count_var, width=10)
        page_count_entry.pack(pady=5)
        page_count_entry.focus()
        
        result_var = {"cancelled": True}
        
        def start_scanning():
            try:
                count = int(page_count_var.get())
                if count < 1 or count > 100:
                    raise ValueError("Число должно быть от 1 до 100")
                result_var["cancelled"] = False
                result_var["count"] = count
                dialog.destroy()
                self.run_multiple_scan(scanner_device, count)
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e))
        
        ttk.Button(dialog, text="Начать сканирование", command=start_scanning).pack(pady=10)
        ttk.Button(dialog, text="Отмена", command=dialog.destroy).pack()
        
        dialog.wait_window()
    
    def run_multiple_scan(self, scanner_device, page_count):
        """Выполнение сканирования нескольких страниц"""
        self.scan_button.config(state=tk.DISABLED)
        self.scan_multiple_btn.config(state=tk.DISABLED)
        
        for i in range(page_count):
            self.status_var.set(f"Сканирование страницы {i+1} из {page_count}...")
            self.root.update()
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            image_path = os.path.join(self.temp_dir, f"scan_{timestamp}_{i+1:03d}.png")
            
            try:
                cmd = [
                    'scanimage',
                    '-d', scanner_device,
                    '--resolution', self.scan_resolution.get(),
                    '--mode', self.scan_color.get().lower(),
                    '-o', image_path,
                    '--format', 'png'
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                
                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Неизвестная ошибка"
                    raise Exception(f"Ошибка на странице {i+1}: {error_msg}")
                
                if not os.path.exists(image_path):
                    raise Exception(f"Файл не создан для страницы {i+1}")
                
                self.add_page_to_preview(image_path)
                self.status_var.set(f"Страница {i+1} из {page_count} готова!")
                self.root.update()
                
                # Небольшая пауза между сканированиями
                if i < page_count - 1:
                    time.sleep(1)
                    
            except Exception as e:
                error_msg = str(e)
                self.status_var.set(f"ОШИБКА: {error_msg}")
                messagebox.showerror("Ошибка", f"Ошибка при сканировании страницы {i+1}:\n{error_msg}")
                break
        
        self.scan_button.config(state=tk.NORMAL)
        self.scan_multiple_btn.config(state=tk.NORMAL)
        self.status_var.set(f"Готово! Отсканировано страниц: {len(self.scanned_pages)}")
    
    def add_page_to_preview(self, image_path):
        """Добавление отсканированной страницы в область предпросмотра"""
        try:
            # Загрузка изображения
            img = Image.open(image_path)
            
            # Масштабирование для предпросмотра (максимум 200px по высоте)
            max_height = 200
            ratio = max_height / img.height
            new_width = int(img.width * ratio)
            new_height = max_height
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(img_resized)
            
            # Создание фрейма для страницы
            page_frame = ttk.Frame(self.scrollable_frame, relief=tk.RAISED, borderwidth=2)
            page_frame.pack(side=tk.LEFT, padx=5, pady=5)
            
            # Метка с изображением
            label = tk.Label(page_frame, image=photo)
            label.image = photo  # Сохраняем ссылку на изображение
            label.pack()
            
            # Номер страницы
            page_num = len(self.scanned_pages) + 1
            num_label = ttk.Label(page_frame, text=f"Стр. {page_num}", font=('Arial', 9))
            num_label.pack(pady=2)
            
            # Кнопка удаления
            del_btn = ttk.Button(page_frame, text="✕", command=lambda p=page_frame: self.remove_page(p))
            del_btn.pack(pady=2)
            
            # Добавление данных о странице
            self.scanned_pages.append({
                'path': image_path,
                'frame': page_frame,
                'original_image': img
            })
            
            # Привязка событий для перетаскивания
            self.enable_drag_and_drop(page_frame)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось добавить страницу в предпросмотр:\n{e}")
    
    def enable_drag_and_drop(self, widget):
        """Включение перетаскивания для виджета"""
        widget.bind("<ButtonPress-1>", self.on_drag_start)
        widget.bind("<B1-Motion>", self.on_drag_motion)
        widget.bind("<ButtonRelease-1>", self.on_drag_release)
        
        # Также привязываем для дочерних элементов
        for child in widget.winfo_children():
            child.bind("<ButtonPress-1>", self.on_drag_start)
            child.bind("<B1-Motion>", self.on_drag_motion)
            child.bind("<ButtonRelease-1>", self.on_drag_release)
    
    def on_drag_start(self, event):
        """Начало перетаскивания"""
        widget = event.widget.winfo_parent()
        if widget == '.':
            widget = event.widget
        
        # Находим фрейм страницы
        current = event.widget
        while current and not hasattr(current, '_is_page_frame'):
            current = current.master
            if current == self.root:
                return
        
        if current:
            self.drag_data["item"] = current
            self.drag_data["start_x"] = event.x_root
            self.drag_data["start_y"] = event.y_root
    
    def on_drag_motion(self, event):
        """Перемещение при перетаскивании"""
        if self.drag_data["item"]:
            item = self.drag_data["item"]
            x_delta = event.x_root - self.drag_data["start_x"]
            y_delta = event.y_root - self.drag_data["start_y"]
            
            # Перемещаем только по горизонтали
            item.place(relx=item.place_info().get('relx', 0), x=x_delta)
    
    def on_drag_release(self, event):
        """Завершение перетаскивания - изменение порядка"""
        if not self.drag_data["item"]:
            return
        
        dropped_widget = self.drag_data["item"]
        dropped_x = dropped_widget.winfo_x()
        
        # Находим все фреймы страниц
        pages = []
        for page_data in self.scanned_pages:
            frame = page_data['frame']
            x_pos = frame.winfo_x()
            pages.append((x_pos, frame, page_data))
        
        # Сортируем по позиции X
        pages.sort(key=lambda p: p[0])
        
        # Определяем новую позицию для перетаскиваемого элемента
        new_order = []
        inserted = False
        
        for x_pos, frame, page_data in pages:
            if frame == dropped_widget:
                continue
            
            frame_center = x_pos + frame.winfo_width() // 2
            
            if not inserted and dropped_x < frame_center:
                new_order.append(dropped_widget)
                inserted = True
            
            new_order.append(frame)
        
        if not inserted:
            new_order.append(dropped_widget)
        
        # Переупорядочиваем фреймы
        for frame in new_order:
            frame.pack_forget()
        
        for frame in new_order:
            frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Обновляем порядок в списке scanned_pages
        new_scanned_pages = []
        for frame in new_order:
            for page_data in self.scanned_pages:
                if page_data['frame'] == frame:
                    new_scanned_pages.append(page_data)
                    break
        
        self.scanned_pages = new_scanned_pages
        
        # Обновляем номера страниц
        for i, page_data in enumerate(self.scanned_pages):
            for child in page_data['frame'].winfo_children():
                if isinstance(child, ttk.Label) and child.cget('text').startswith('Стр.'):
                    child.config(text=f"Стр. {i+1}")
        
        self.drag_data["item"] = None
        self.status_var.set(f"Порядок страниц изменён. Всего: {len(self.scanned_pages)}")
    
    def remove_page(self, page_frame):
        """Удаление страницы"""
        for i, page_data in enumerate(self.scanned_pages):
            if page_data['frame'] == page_frame:
                # Удаляем файл
                try:
                    if os.path.exists(page_data['path']):
                        os.remove(page_data['path'])
                except:
                    pass
                
                # Удаляем из списка
                page_frame.destroy()
                self.scanned_pages.pop(i)
                
                # Обновляем номера оставшихся страниц
                for j, pd in enumerate(self.scanned_pages):
                    for child in pd['frame'].winfo_children():
                        if isinstance(child, ttk.Label) and child.cget('text').startswith('Стр.'):
                            child.config(text=f"Стр. {j+1}")
                
                self.status_var.set(f"Страница удалена. Осталось: {len(self.scanned_pages)}")
                break
    
    def clear_all(self):
        """Очистка всех отсканированных страниц"""
        if len(self.scanned_pages) == 0:
            return
        
        if not messagebox.askyesno("Подтверждение", "Удалить все отсканированные страницы?"):
            return
        
        # Удаление временных файлов
        for page_data in self.scanned_pages:
            try:
                if os.path.exists(page_data['path']):
                    os.remove(page_data['path'])
            except:
                pass
            page_data['frame'].destroy()
        
        self.scanned_pages = []
        self.status_var.set("Все страницы удалены")
    
    def save_to_pdf(self):
        """Сохранение всех страниц в один PDF файл"""
        if len(self.scanned_pages) == 0:
            messagebox.showwarning("Предупреждение", "Нет отсканированных страниц для сохранения!")
            return
        
        # Диалог сохранения файла
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF файлы", "*.pdf"), ("Все файлы", "*.*")],
            title="Сохранить как",
            initialfile=f"scan_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        
        if not file_path:
            return
        
        try:
            self.status_var.set("Сохранение в PDF...")
            self.root.update()
            
            # Получаем пути к изображениям в текущем порядке
            image_paths = [page_data['path'] for page_data in self.scanned_pages]
            
            # Конвертация в PDF
            with open(file_path, "wb") as f:
                f.write(img2pdf.convert(image_paths))
            
            self.status_var.set(f"Успешно сохранено: {os.path.basename(file_path)}")
            messagebox.showinfo("Успех", f"Документ сохранён:\n{file_path}\n\nСтраниц: {len(self.scanned_pages)}")
            
        except Exception as e:
            error_msg = str(e)
            self.status_var.set(f"ОШИБКА сохранения: {error_msg}")
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить PDF:\n{error_msg}")
    
    def on_closing(self):
        """Обработчик закрытия приложения"""
        # Очистка временных файлов
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass
        
        self.root.destroy()


def main():
    """Основная функция запуска"""
    print("=" * 60)
    print("Программа сканирования документов HP LaserJet")
    print("=" * 60)
    print()
    print("Запуск графического интерфейса...")
    print()
    print("Если возникнет ошибка, это окно останется открытым.")
    print("Терминал не закроется автоматически.")
    print()
    
    try:
        root = tk.Tk()
        app = ScannerApp(root)
        
        # Запуск в защищённом режиме (чтобы ошибки не закрывали приложение молча)
        try:
            root.mainloop()
        except Exception as e:
            print(f"\n❗ КРИТИЧЕСКАЯ ОШИБКА: {e}")
            print("\nТерминал не закроется. Вы можете увидеть полное сообщение об ошибке выше.")
            input("\nНажмите Enter для выхода...")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❗ ОШИБКА ПРИ ЗАПУСКЕ: {e}")
        print("\nВозможные причины:")
        print("  - Не установлен tkinter (python3-tk)")
        print("  - Не найдены библиотеки PIL/Pillow")
        print("  - Проблемы с дисплеем (запустите в графической среде)")
        print("\nТерминал не закроется автоматически.")
        input("\nНажмите Enter для выхода...")
        sys.exit(1)


if __name__ == "__main__":
    main()
