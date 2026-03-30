#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Программа для сканирования документов с принтера/сканера HP LaserJet
С возможностью сканирования нескольких страниц, перетаскивания и сохранения в PDF
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import tempfile
import threading
from PIL import Image, ImageTk
import fitz  # PyMuPDF
import subprocess
import shutil
from pathlib import Path


class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Сканер документов HP LaserJet")
        self.root.geometry("1200x800")
        
        # Хранилище отсканированных страниц
        self.scanned_pages = []  # Список словарей: {'image': PIL.Image, 'photo': PhotoImage, 'path': str}
        self.page_counter = 0
        
        # Настройки сканирования
        self.resolution = tk.StringVar(value="300")
        self.color_mode = tk.StringVar(value="Color")
        self.paper_size = tk.StringVar(value="A4")
        self.scan_source = tk.StringVar(value="Flatbed")
        
        self.setup_ui()
        
    def setup_ui(self):
        """Создание пользовательского интерфейса"""
        
        # Верхняя панель с настройками
        settings_frame = ttk.LabelFrame(self.root, text="Настройки сканирования", padding=10)
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Разрешение
        ttk.Label(settings_frame, text="Разрешение (DPI):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        dpi_combo = ttk.Combobox(settings_frame, textvariable=self.resolution, values=["150", "200", "300", "400", "600"], width=10, state="readonly")
        dpi_combo.grid(row=0, column=1, padx=5, pady=5)
        
        # Цветовой режим
        ttk.Label(settings_frame, text="Цвет:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        color_combo = ttk.Combobox(settings_frame, textvariable=self.color_mode, values=["Color", "Gray", "Black&White"], width=15, state="readonly")
        color_combo.grid(row=0, column=3, padx=5, pady=5)
        
        # Размер бумаги
        ttk.Label(settings_frame, text="Размер:").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        size_combo = ttk.Combobox(settings_frame, textvariable=self.paper_size, values=["A4", "A5", "Letter", "Legal"], width=10, state="readonly")
        size_combo.grid(row=0, column=5, padx=5, pady=5)
        
        # Источник сканирования
        ttk.Label(settings_frame, text="Источник:").grid(row=0, column=6, padx=5, pady=5, sticky=tk.W)
        source_combo = ttk.Combobox(settings_frame, textvariable=self.scan_source, values=["Flatbed", "ADF"], width=10, state="readonly")
        source_combo.grid(row=0, column=7, padx=5, pady=5)
        
        # Кнопки управления
        button_frame = ttk.Frame(self.root, padding=10)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.scan_btn = ttk.Button(button_frame, text="📄 Сканировать страницу", command=self.scan_page, width=20)
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.scan_multiple_btn = ttk.Button(button_frame, text="📑 Сканировать несколько", command=self.scan_multiple_pages, width=25)
        self.scan_multiple_btn.pack(side=tk.LEFT, padx=5)
        
        self.delete_btn = ttk.Button(button_frame, text="❌ Удалить выбранное", command=self.delete_selected, width=20)
        self.delete_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_all_btn = ttk.Button(button_frame, text="🗑️ Очистить всё", command=self.clear_all, width=15)
        self.clear_all_btn.pack(side=tk.LEFT, padx=5)
        
        # Инфо о количестве страниц
        self.info_label = ttk.Label(button_frame, text="Страниц: 0", font=("Arial", 12, "bold"))
        self.info_label.pack(side=tk.RIGHT, padx=10)
        
        # Область просмотра страниц с прокруткой
        view_frame = ttk.LabelFrame(self.root, text="Отсканированные страницы (перетаскивайте для изменения порядка)", padding=10)
        view_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Canvas для горизонтальной прокрутки
        self.canvas = tk.Canvas(view_frame, bg="#f0f0f0", highlightthickness=0)
        scrollbar_x = ttk.Scrollbar(view_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        scrollbar_y = ttk.Scrollbar(view_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=scrollbar_x.set, yscrollcommand=scrollbar_y.set)
        
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Привязка колесика мыши для прокрутки
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        
        # Контейнер для миниатюр страниц
        self.thumbnails_frame = ttk.Frame(self.scrollable_frame)
        self.thumbnails_frame.pack(padx=10, pady=10)
        
        # Нижняя панель с кнопками сохранения
        save_frame = ttk.Frame(self.root, padding=10)
        save_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.save_single_btn = ttk.Button(save_frame, text="💾 Сохранить как отдельные PDF", command=self.save_as_separate, width=25)
        self.save_single_btn.pack(side=tk.LEFT, padx=5)
        
        self.save_merged_btn = ttk.Button(save_frame, text="📕 Сохранить всё в один PDF", command=self.save_as_merged, width=25)
        self.save_merged_btn.pack(side=tk.LEFT, padx=5)
        
        self.save_selected_btn = ttk.Button(save_frame, text="📗 Сохранить выбранное в PDF", command=self.save_selected_pages, width=25)
        self.save_selected_btn.pack(side=tk.LEFT, padx=5)
        
        # Статус бар
        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def _on_mousewheel(self, event):
        """Обработка прокрутки колесиком мыши"""
        if event.num == 4 or event.delta > 0:
            self.canvas.xview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.xview_scroll(1, "units")
    
    def scan_page(self):
        """Сканирование одной страницы"""
        self.status_var.set("Сканирование...")
        self.scan_btn.config(state=tk.DISABLED)
        
        thread = threading.Thread(target=self._do_scan, args=(False,))
        thread.daemon = True
        thread.start()
    
    def scan_multiple_pages(self):
        """Сканирование нескольких страниц подряд"""
        dialog = MultipleScanDialog(self.root)
        if dialog.result:
            num_pages = dialog.result
            self.status_var.set(f"Сканирование {num_pages} страниц...")
            self.scan_multiple_btn.config(state=tk.DISABLED)
            
            thread = threading.Thread(target=self._do_multiple_scan, args=(num_pages,))
            thread.daemon = True
            thread.start()
    
    def _do_scan(self, is_batch=False):
        """Выполнение сканирования в фоновом потоке"""
        try:
            # Попытка использовать scanimage (SANE)
            scanned_image = self._scan_with_scanimage()
            
            if scanned_image:
                self.root.after(0, lambda: self._add_scanned_page(scanned_image))
                self.root.after(0, lambda: self.status_var.set("Страница отсканирована успешно"))
            else:
                # Если scanimage не доступен, создаем тестовое изображение
                self.root.after(0, lambda: self._create_test_page())
                self.root.after(0, lambda: self.status_var.set("Создана тестовая страница (сканер не найден)"))
                
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Ошибка сканирования: {str(e)}"))
            if not is_batch:
                self.root.after(0, lambda: self.scan_btn.config(state=tk.NORMAL))
            else:
                self.root.after(0, lambda: self.scan_multiple_btn.config(state=tk.NORMAL))
        finally:
            if not is_batch:
                self.root.after(0, lambda: self.scan_btn.config(state=tk.NORMAL))
            else:
                self.root.after(0, lambda: self.scan_multiple_btn.config(state=tk.NORMAL))
    
    def _do_multiple_scan(self, num_pages):
        """Сканирование нескольких страниц"""
        for i in range(num_pages):
            self.root.after(0, lambda p=i+1: self.status_var.set(f"Сканирование страницы {p}/{num_pages}..."))
            self._do_scan(is_batch=True)
            # Небольшая задержка между сканированиями
            import time
            time.sleep(0.5)
        
        self.root.after(0, lambda: self.status_var.set(f"Отсканировано {num_pages} страниц"))
    
    def _scan_with_scanimage(self):
        """Попытка сканирования через scanimage (SANE backend)"""
        try:
            # Проверка доступности scanimage
            result = subprocess.run(['which', 'scanimage'], capture_output=True, text=True)
            if result.returncode != 0:
                return None
            
            # Создание временного файла для сохранения
            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            temp_file.close()
            
            # Параметры сканирования
            dpi = self.resolution.get()
            mode = self.color_mode.get()
            if mode == "Color":
                mode_param = "Color"
            elif mode == "Gray":
                mode_param = "Gray"
            else:
                mode_param = "Lineart"
            
            # Команда сканирования
            cmd = [
                'scanimage',
                '--resolution', dpi,
                '--mode', mode_param,
                '--format', 'png',
                '-o', temp_file.name
            ]
            
            # Попытка сканирования
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            
            if result.returncode == 0 and os.path.exists(temp_file.name):
                image = Image.open(temp_file.name)
                return image
            else:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                return None
                
        except Exception as e:
            print(f"Ошибка сканирования: {e}")
            return None
    
    def _create_test_page(self):
        """Создание тестовой страницы для демонстрации"""
        # Создаем изображение-заглушку
        img = Image.new('RGB', (2480, 3508), color=(255, 255, 255))  # A4 при 300 DPI
        
        # Рисуем рамку и текст
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        
        # Рамка
        draw.rectangle([50, 50, 2430, 3458], outline=(0, 0, 0), width=5)
        
        # Текст
        self.page_counter += 1
        text = f"Тестовая страница {self.page_counter}"
        
        # Попытка использовать шрифт
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        except:
            font = ImageFont.load_default()
        
        # Центрирование текста
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (2480 - text_width) // 2
        y = (3508 - text_height) // 2
        
        draw.text((x, y), text, fill=(0, 0, 0), font=font)
        draw.text((x, y + 100), f"Дата: {tempfile.gettempdir()}", fill=(128, 128, 128), font=font)
        
        self._add_scanned_page(img)
    
    def _add_scanned_page(self, image):
        """Добавление отсканированной страницы в интерфейс"""
        # Сохраняем изображение во временный файл
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, f"page_{len(self.scanned_pages) + 1}.png")
        image.save(temp_path)
        
        # Создаем миниатюру для отображения
        thumbnail = image.copy()
        thumbnail.thumbnail((200, 280), Image.Resampling.LANCZOS)
        
        # Конвертируем для Tkinter
        photo = ImageTk.PhotoImage(thumbnail)
        
        # Добавляем в список
        page_data = {
            'image': image,
            'thumbnail': thumbnail,
            'photo': photo,
            'path': temp_path,
            'selected': False
        }
        self.scanned_pages.append(page_data)
        
        # Создаем виджет для отображения
        self._create_thumbnail_widget(page_data, len(self.scanned_pages) - 1)
        
        # Обновляем счетчик
        self.info_label.config(text=f"Страниц: {len(self.scanned_pages)}")
        
        # Прокрутка к новой странице
        self.canvas.update_idletasks()
        self.canvas.xview_moveto(1.0)
    
    def _create_thumbnail_widget(self, page_data, index):
        """Создание виджета миниатюры страницы"""
        frame = ttk.Frame(self.thumbnails_frame, relief=tk.RAISED, borderwidth=2)
        frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Метка с изображением
        label = tk.Label(frame, image=page_data['photo'])
        label.pack(padx=5, pady=5)
        
        # Номер страницы
        num_label = ttk.Label(frame, text=f"Стр. {index + 1}")
        num_label.pack(pady=2)
        
        # Чекбокс выбора
        var = tk.BooleanVar(value=False)
        checkbox = ttk.Checkbutton(frame, text="Выбрать", variable=var, 
                                   command=lambda: self._toggle_selection(index, var))
        checkbox.pack(pady=2)
        
        # Сохраняем ссылки на виджеты
        page_data['frame'] = frame
        page_data['label'] = label
        page_data['num_label'] = num_label
        page_data['checkbox_var'] = var
        
        # Добавляем возможность перетаскивания
        self._enable_drag_drop(frame, index)
    
    def _enable_drag_drop(self, frame, index):
        """Включение перетаскивания для миниатюры"""
        frame.bind("<ButtonPress-1>", lambda e: self._on_drag_start(e, index))
        frame.bind("<B1-Motion>", lambda e: self._on_drag_motion(e, index))
        frame.bind("<ButtonRelease-1>", lambda e: self._on_drag_release(e, index))
        
        # Также привязываем для дочерних виджетов
        for widget in frame.winfo_children():
            widget.bind("<ButtonPress-1>", lambda e: self._on_drag_start(e, index))
            widget.bind("<B1-Motion>", lambda e: self._on_drag_motion(e, index))
            widget.bind("<ButtonRelease-1>", lambda e: self._on_drag_release(e, index))
    
    def _on_drag_start(self, event, index):
        """Начало перетаскивания"""
        widget = event.widget
        self._drag_start_x = event.x_root
        self._drag_index = index
        widget.winfo_toplevel().attributes('-alpha', 0.5)
    
    def _on_drag_motion(self, event, index):
        """Перемещение при перетаскивании"""
        widget = self.scanned_pages[index]['frame']
        x = widget.winfo_x() + event.x_root - self._drag_start_x
        widget.place(x=x, y=widget.winfo_y())
    
    def _on_drag_release(self, event, target_index=None):
        """Завершение перетаскивания"""
        # Восстанавливаем прозрачность
        for page in self.scanned_pages:
            page['frame'].winfo_toplevel().attributes('-alpha', 1.0)
        
        # Определяем новую позицию
        current_x = event.x_root
        new_index = self._find_new_index(current_x)
        
        if new_index is not None and new_index != self._drag_index:
            self._reorder_pages(self._drag_index, new_index)
    
    def _find_new_index(self, x_coord):
        """Определение нового индекса на основе позиции"""
        # Получаем все фреймы и их позиции
        positions = []
        for i, page in enumerate(self.scanned_pages):
            frame = page['frame']
            center_x = frame.winfo_x() + frame.winfo_width() // 2
            positions.append((center_x, i))
        
        # Сортируем по позиции
        positions.sort(key=lambda p: p[0])
        
        # Находим ближайший индекс
        for i, (center_x, orig_idx) in enumerate(positions):
            if x_coord < center_x:
                return orig_idx
        
        return len(self.scanned_pages) - 1
    
    def _reorder_pages(self, old_index, new_index):
        """Переупорядочивание страниц"""
        # Перемещаем элемент в списке
        page = self.scanned_pages.pop(old_index)
        self.scanned_pages.insert(new_index, page)
        
        # Перестраиваем интерфейс
        self._rebuild_thumbnails()
        
        self.status_var.set(f"Страница перемещена с {old_index + 1} на {new_index + 1}")
    
    def _rebuild_thumbnails(self):
        """Перестроение всех миниатюр"""
        # Очищаем текущие виджеты
        for widget in self.thumbnails_frame.winfo_children():
            widget.destroy()
        
        # Пересоздаем
        for i, page_data in enumerate(self.scanned_pages):
            self._create_thumbnail_widget(page_data, i)
        
        # Обновляем номера страниц
        self._update_page_numbers()
    
    def _update_page_numbers(self):
        """Обновление номеров страниц"""
        for i, page_data in enumerate(self.scanned_pages):
            if 'num_label' in page_data:
                page_data['num_label'].config(text=f"Стр. {i + 1}")
    
    def _toggle_selection(self, index, var):
        """Переключение выбора страницы"""
        self.scanned_pages[index]['selected'] = var.get()
    
    def delete_selected(self):
        """Удаление выбранных страниц"""
        selected_indices = [i for i, page in enumerate(self.scanned_pages) if page['selected']]
        
        if not selected_indices:
            messagebox.showwarning("Предупреждение", "Выберите страницы для удаления")
            return
        
        if messagebox.askyesno("Подтверждение", f"Удалить {len(selected_indices)} страниц?"):
            # Удаляем в обратном порядке чтобы индексы не сбились
            for i in sorted(selected_indices, reverse=True):
                page = self.scanned_pages[i]
                # Удаляем временные файлы
                try:
                    os.unlink(page['path'])
                    os.rmdir(os.path.dirname(page['path']))
                except:
                    pass
                # Удаляем виджет
                page['frame'].destroy()
                self.scanned_pages.pop(i)
            
            self._update_page_numbers()
            self.info_label.config(text=f"Страниц: {len(self.scanned_pages)}")
            self.status_var.set(f"Удалено {len(selected_indices)} страниц")
    
    def clear_all(self):
        """Очистка всех страниц"""
        if not self.scanned_pages:
            return
        
        if messagebox.askyesno("Подтверждение", "Удалить все отсканированные страницы?"):
            for page in self.scanned_pages:
                try:
                    os.unlink(page['path'])
                    os.rmdir(os.path.dirname(page['path']))
                except:
                    pass
                page['frame'].destroy()
            
            self.scanned_pages = []
            self.page_counter = 0
            self.info_label.config(text="Страниц: 0")
            self.status_var.set("Все страницы удалены")
    
    def save_as_separate(self):
        """Сохранение каждой страницы как отдельный PDF"""
        if not self.scanned_pages:
            messagebox.showwarning("Предупреждение", "Нет страниц для сохранения")
            return
        
        output_dir = filedialog.askdirectory(title="Выберите папку для сохранения")
        if not output_dir:
            return
        
        saved_count = 0
        for i, page in enumerate(self.scanned_pages):
            try:
                # Создаем PDF из изображения
                pdf_path = os.path.join(output_dir, f"page_{i+1}.pdf")
                self._image_to_pdf(page['image'], pdf_path)
                saved_count += 1
            except Exception as e:
                print(f"Ошибка сохранения страницы {i+1}: {e}")
        
        self.status_var.set(f"Сохранено {saved_count} отдельных PDF файлов")
        messagebox.showinfo("Готово", f"Сохранено {saved_count} PDF файлов в:\n{output_dir}")
    
    def save_as_merged(self):
        """Сохранение всех страниц в один PDF файл"""
        if not self.scanned_pages:
            messagebox.showwarning("Предупреждение", "Нет страниц для сохранения")
            return
        
        output_file = filedialog.asksaveasfilename(
            title="Сохранить как",
            defaultextension=".pdf",
            filetypes=[("PDF файлы", "*.pdf")],
            initialfile=f"scanned_document_{len(self.scanned_pages)}_pages.pdf"
        )
        
        if not output_file:
            return
        
        try:
            # Создаем PDF документ
            pdf_doc = fitz.open()
            
            for i, page in enumerate(self.scanned_pages):
                # Конвертируем изображение в формат, подходящий для PDF
                img = page['image']
                
                # Создаем новую страницу в PDF
                # Размер страницы соответствует размеру изображения
                img_width = img.width
                img_height = img.height
                
                # Создаем страницу с размером изображения (в пунктах, 1 пункт = 1/72 дюйма)
                pdf_page = pdf_doc.new_page(width=img_width * 72 / 300, height=img_height * 72 / 300)
                
                # Вставляем изображение
                rect = fitz.Rect(0, 0, img_width * 72 / 300, img_height * 72 / 300)
                
                # Сохраняем изображение во временный файл для вставки
                temp_img = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                img.save(temp_img.name)
                temp_img.close()
                
                pdf_page.insert_image(rect, filename=temp_img.name)
                
                # Удаляем временный файл
                try:
                    os.unlink(temp_img.name)
                except:
                    pass
            
            # Сохраняем PDF
            pdf_doc.save(output_file)
            pdf_doc.close()
            
            self.status_var.set(f"Сохранено в один PDF: {os.path.basename(output_file)}")
            messagebox.showinfo("Готово", f"Документ сохранен:\n{output_file}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить PDF:\n{str(e)}")
    
    def save_selected_pages(self):
        """Сохранение выбранных страниц в один PDF"""
        selected_pages = [page for page in self.scanned_pages if page['selected']]
        
        if not selected_pages:
            messagebox.showwarning("Предупреждение", "Выберите страницы для сохранения")
            return
        
        output_file = filedialog.asksaveasfilename(
            title="Сохранить выбранное как",
            defaultextension=".pdf",
            filetypes=[("PDF файлы", "*.pdf")],
            initialfile=f"selected_pages_{len(selected_pages)}.pdf"
        )
        
        if not output_file:
            return
        
        try:
            pdf_doc = fitz.open()
            
            for page in selected_pages:
                img = page['image']
                img_width = img.width
                img_height = img.height
                
                pdf_page = pdf_doc.new_page(width=img_width * 72 / 300, height=img_height * 72 / 300)
                rect = fitz.Rect(0, 0, img_width * 72 / 300, img_height * 72 / 300)
                
                temp_img = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                img.save(temp_img.name)
                temp_img.close()
                
                pdf_page.insert_image(rect, filename=temp_img.name)
                
                try:
                    os.unlink(temp_img.name)
                except:
                    pass
            
            pdf_doc.save(output_file)
            pdf_doc.close()
            
            self.status_var.set(f"Сохранено {len(selected_pages)} выбранных страниц")
            messagebox.showinfo("Готово", f"Сохранено {len(selected_pages)} страниц:\n{output_file}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить PDF:\n{str(e)}")
    
    def _image_to_pdf(self, image, output_path):
        """Конвертация изображения в PDF"""
        pdf_doc = fitz.open()
        
        img_width = image.width
        img_height = image.height
        
        pdf_page = pdf_doc.new_page(width=img_width * 72 / 300, height=img_height * 72 / 300)
        rect = fitz.Rect(0, 0, img_width * 72 / 300, img_height * 72 / 300)
        
        temp_img = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        image.save(temp_img.name)
        temp_img.close()
        
        pdf_page.insert_image(rect, filename=temp_img.name)
        
        try:
            os.unlink(temp_img.name)
        except:
            pass
        
        pdf_doc.save(output_path)
        pdf_doc.close()


class MultipleScanDialog:
    """Диалоговое окно для указания количества страниц для сканирования"""
    
    def __init__(self, parent):
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Сканирование нескольких страниц")
        self.dialog.geometry("300x150")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        ttk.Label(self.dialog, text="Количество страниц:", font=("Arial", 12)).pack(pady=20)
        
        self.num_var = tk.StringVar(value="5")
        entry = ttk.Entry(self.dialog, textvariable=self.num_var, width=10, font=("Arial", 14), justify='center')
        entry.pack(pady=10)
        entry.focus_set()
        entry.select_range(0, tk.END)
        
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="OK", command=self._on_ok, width=10).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Отмена", command=self._on_cancel, width=10).pack(side=tk.LEFT, padx=10)
        
        # Обработка Enter
        self.dialog.bind('<Return>', lambda e: self._on_ok())
        self.dialog.bind('<Escape>', lambda e: self._on_cancel())
        
        self.dialog.wait_window()
    
    def _on_ok(self):
        try:
            num = int(self.num_var.get())
            if 1 <= num <= 100:
                self.result = num
                self.dialog.destroy()
            else:
                messagebox.showwarning("Предупреждение", "Введите число от 1 до 100", parent=self.dialog)
        except ValueError:
            messagebox.showwarning("Предупреждение", "Введите корректное число", parent=self.dialog)
    
    def _on_cancel(self):
        self.dialog.destroy()


def main():
    root = tk.Tk()
    
    # Установка стиля
    style = ttk.Style()
    style.theme_use('clam')
    
    app = ScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
