#!/usr/bin/env python3
"""
HP LaserJet Network Scanner Application
Scans documents over network, allows multi-page scanning with manual page placement,
reordering via drag-and-drop, and saves as PDF.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import tempfile
import threading
from PIL import Image
import img2pdf
import time

class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet Scanner")
        self.root.geometry("1000x700")
        
        # Store scanned pages
        self.scanned_pages = []  # List of (image_path, thumbnail_label)
        self.temp_dir = tempfile.mkdtemp(prefix="scanner_")
        self.current_page_num = 0
        self.is_scanning = False
        
        # SANE device (will be discovered)
        self.device = None
        self.discover_device()
        
        self.setup_ui()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def discover_device(self):
        """Discover HP LaserJet scanner over network"""
        try:
            result = subprocess.run(['scanimage', '-L'], capture_output=True, text=True, timeout=10)
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'hp' in line.lower() or 'hplj' in line.lower() or 'laserjet' in line.lower():
                    self.device = line.split('`')[1].split('\'')[0] if '`' in line else line.strip()
                    break
            
            if not self.device and lines:
                self.device = lines[0].strip().replace("device `", "").replace("' is a ...", "")
        except Exception as e:
            print(f"Device discovery error: {e}")
            self.device = None
    
    def setup_ui(self):
        """Setup the user interface"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top frame - controls
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Scan button
        self.scan_btn = ttk.Button(control_frame, text="📄 Сканировать страницу", command=self.scan_page)
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        # Finish scanning button
        self.finish_btn = ttk.Button(control_frame, text="✅ Завершить и редактировать", command=self.finish_scanning)
        self.finish_btn.pack(side=tk.LEFT, padx=5)
        self.finish_btn['state'] = 'disabled'
        
        # Color mode selection
        ttk.Label(control_frame, text="Цвет:").pack(side=tk.LEFT, padx=(20, 5))
        self.color_mode = tk.StringVar(value="Color")
        color_combo = ttk.Combobox(control_frame, textvariable=self.color_mode, values=["Color", "Gray", "Lineart"], width=10)
        color_combo.pack(side=tk.LEFT, padx=5)
        
        # Resolution
        ttk.Label(control_frame, text="DPI:").pack(side=tk.LEFT, padx=(10, 5))
        self.dpi = tk.StringVar(value="300")
        dpi_combo = ttk.Combobox(control_frame, textvariable=self.dpi, values=["150", "200", "300", "400", "600"], width=6)
        dpi_combo.pack(side=tk.LEFT, padx=5)
        
        # Status label
        self.status_label = ttk.Label(control_frame, text="Готов к сканированию", foreground="green")
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        # Middle frame - scan preview area
        preview_frame = ttk.LabelFrame(main_frame, text="Отсканированные страницы (перетаскивайте для изменения порядка)", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Canvas for horizontal scrolling
        self.canvas = tk.Canvas(preview_frame, bg="white")
        scrollbar = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.canvas.xview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind mouse wheel for horizontal scrolling
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        
        # Bottom frame - save controls
        save_frame = ttk.Frame(main_frame)
        save_frame.pack(fill=tk.X)
        
        self.save_btn = ttk.Button(save_frame, text="💾 Сохранить в PDF", command=self.save_pdf)
        self.save_btn.pack(side=tk.LEFT, padx=5)
        self.save_btn['state'] = 'disabled'
        
        ttk.Button(save_frame, text="🗑️ Очистить всё", command=self.clear_all).pack(side=tk.LEFT, padx=5)
        
        # Device info
        device_text = f"Устройство: {self.device}" if self.device else "Устройство не найдено (проверьте сеть)"
        ttk.Label(save_frame, text=device_text, foreground="blue").pack(side=tk.RIGHT)
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel for horizontal scrolling"""
        if event.num == 4 or event.delta > 0:
            self.canvas.xview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.xview_scroll(1, "units")
    
    def scan_page(self):
        """Scan a single page - non-blocking, manual page feed"""
        if self.is_scanning:
            messagebox.showwarning("Предупреждение", "Сканирование уже выполняется!")
            return
        
        self.is_scanning = True
        self.scan_btn['state'] = 'disabled'
        self.status_label.config(text=f"Сканирование страницы {len(self.scanned_pages) + 1}...", foreground="orange")
        self.root.update()
        
        # Run scan in thread to keep UI responsive
        thread = threading.Thread(target=self._do_scan)
        thread.daemon = True
        thread.start()
    
    def _do_scan(self):
        """Perform the actual scan"""
        try:
            self.current_page_num = len(self.scanned_pages) + 1
            output_file = os.path.join(self.temp_dir, f"page_{self.current_page_num}.png")
            
            # Determine color mode
            mode_map = {"Color": "color", "Gray": "gray", "Lineart": "lineart"}
            color_mode = mode_map.get(self.color_mode.get(), "color")
            
            # Build scanimage command
            cmd = [
                'scanimage',
                '--source', 'Flatbed',
                '--mode', color_mode,
                '--resolution', self.dpi.get(),
                '--format', 'png',
                '-o', output_file
            ]
            
            if self.device:
                cmd.insert(1, f'-d{self.device}')
            
            print(f"Executing: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                error_msg = f"Ошибка при сканировании страницы {self.current_page_num}: {result.stderr}"
                print(error_msg)
                self.root.after(0, lambda: self.handle_scan_error(error_msg))
                return
            
            if not os.path.exists(output_file):
                error_msg = f"Ошибка: файл не создан после сканирования страницы {self.current_page_num}"
                print(error_msg)
                self.root.after(0, lambda: self.handle_scan_error(error_msg))
                return
            
            # Display thumbnail
            self.root.after(0, lambda: self.add_page_thumbnail(output_file))
            
        except subprocess.TimeoutExpired:
            error_msg = f"Таймаут при сканировании страницы {self.current_page_num}"
            print(error_msg)
            self.root.after(0, lambda: self.handle_scan_error(error_msg))
        except Exception as e:
            error_msg = f"Ошибка при сканировании страницы {self.current_page_num}: {str(e)}"
            print(error_msg)
            self.root.after(0, lambda: self.handle_scan_error(error_msg))
        finally:
            self.root.after(0, self.scan_complete)
    
    def handle_scan_error(self, error_msg):
        """Handle scan error - keep terminal open"""
        messagebox.showerror("Ошибка сканирования", error_msg)
        print("\n" + "="*60)
        print(error_msg)
        print("Терминал остается открытым для просмотра ошибки")
        print("="*60 + "\n")
    
    def scan_complete(self):
        """Called when scan completes"""
        self.is_scanning = False
        self.scan_btn['state'] = 'normal'
        self.status_label.config(text=f"Страница {self.current_page_num} отсканирована", foreground="green")
        self.finish_btn['state'] = 'normal'
        self.save_btn['state'] = 'normal'
    
    def add_page_thumbnail(self, image_path):
        """Add a thumbnail of the scanned page to the canvas"""
        try:
            # Load and create thumbnail
            img = Image.open(image_path)
            thumb_size = (150, 200)
            img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(img)
            
            # Create frame for this page
            page_frame = ttk.Frame(self.scrollable_frame)
            page_frame.pack(side=tk.LEFT, padx=10, pady=10)
            
            # Label with image
            label = ttk.Label(page_frame, image=photo)
            label.image = photo  # Keep reference
            label.pack()
            
            # Page number
            page_num = len(self.scanned_pages) + 1
            ttk.Label(page_frame, text=f"Стр. {page_num}").pack()
            
            # Make draggable
            self.make_draggable(page_frame, label, image_path, photo)
            
            # Store page info
            self.scanned_pages.append({
                'path': image_path,
                'frame': page_frame,
                'label': label,
                'photo': photo
            })
            
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
    
    def make_draggable(self, frame, label, image_path, photo):
        """Make a page frame draggable for reordering"""
        drag_data = {"x": 0, "y": 0, "item": None}
        
        def on_press(event):
            drag_data["x"] = event.x
            drag_data["y"] = event.y
            drag_data["item"] = frame
            frame.config(relief=tk.RAISED, borderwidth=2)
        
        def on_release(event):
            frame.config(relief=tk.FLAT, borderwidth=0)
            drag_data["item"] = None
            self.reorder_pages()
        
        def on_motion(event):
            if drag_data["item"]:
                # Calculate delta
                deltax = event.x - drag_data["x"]
                
                # Move the frame
                current_x = frame.winfo_x()
                new_x = current_x + deltax
                
                # Constrain to canvas
                max_x = self.scrollable_frame.winfo_width() - frame.winfo_width()
                new_x = max(0, min(new_x, max_x))
                
                frame.place(x=new_x, y=frame.winfo_y())
                
                drag_data["x"] = event.x
        
        label.bind("<ButtonPress-1>", on_press)
        label.bind("<ButtonRelease-1>", on_release)
        label.bind("<B1-Motion>", on_motion)
        frame.bind("<ButtonPress-1>", on_press)
        frame.bind("<ButtonRelease-1>", on_release)
        frame.bind("<B1-Motion>", on_motion)
    
    def reorder_pages(self):
        """Reorder pages based on their current position"""
        # Get all frames sorted by x position
        pages_with_pos = []
        for i, page in enumerate(self.scanned_pages):
            x_pos = page['frame'].winfo_x()
            pages_with_pos.append((x_pos, i, page))
        
        # Sort by x position
        pages_with_pos.sort(key=lambda x: x[0])
        
        # Reorder the list
        new_order = [page for _, _, page in pages_with_pos]
        self.scanned_pages = new_order
        
        # Update page numbers
        for i, page in enumerate(self.scanned_pages):
            for widget in page['frame'].winfo_children():
                if isinstance(widget, ttk.Label) and widget.cget("text").startswith("Стр."):
                    widget.config(text=f"Стр. {i+1}")
    
    def finish_scanning(self):
        """Finish scanning and enter edit mode"""
        if not self.scanned_pages:
            messagebox.showinfo("Информация", "Нет отсканированных страниц")
            return
        
        self.status_label.config(text="Режим редактирования: перетаскивайте страницы для изменения порядка", foreground="blue")
        messagebox.showinfo("Редактор", "Перетаскивайте страницы горизонтально для изменения порядка.\nКогда закончите, нажмите 'Сохранить в PDF'.")
    
    def save_pdf(self):
        """Save all pages as a single PDF"""
        if not self.scanned_pages:
            messagebox.showwarning("Предупреждение", "Нет страниц для сохранения")
            return
        
        # Ask for save location
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Сохранить как PDF"
        )
        
        if not file_path:
            return
        
        try:
            # Get image paths in current order
            image_paths = [page['path'] for page in self.scanned_pages]
            
            # Convert to PDF
            with open(file_path, 'wb') as f:
                f.write(img2pdf.convert(image_paths))
            
            self.status_label.config(text=f"Сохранено: {os.path.basename(file_path)}", foreground="green")
            messagebox.showinfo("Успех", f"Документ сохранён:\n{file_path}")
            
        except Exception as e:
            error_msg = f"Ошибка сохранения: {str(e)}"
            print(error_msg)
            messagebox.showerror("Ошибка", error_msg)
    
    def clear_all(self):
        """Clear all scanned pages"""
        if self.scanned_pages:
            if messagebox.askyesno("Подтверждение", "Удалить все отсканированные страницы?"):
                for page in self.scanned_pages:
                    page['frame'].destroy()
                self.scanned_pages = []
                self.finish_btn['state'] = 'disabled'
                self.save_btn['state'] = 'disabled'
                self.status_label.config(text="Готов к сканированию", foreground="green")
    
    def on_closing(self):
        """Handle window close - keep terminal open"""
        if messagebox.askokcancel("Выход", "Закрыть приложение?"):
            # Cleanup temp files
            try:
                import shutil
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except:
                pass
            self.root.destroy()


def check_dependencies():
    """Check if required packages are installed"""
    missing = []
    
    try:
        import PIL
    except ImportError:
        missing.append("Pillow")
    
    try:
        import img2pdf
    except ImportError:
        missing.append("img2pdf")
    
    # Check scanimage
    try:
        subprocess.run(['scanimage', '-V'], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        missing.append("sane-utils")
    
    if missing:
        print("=" * 60)
        print("ОШИБКА: Отсутствуют необходимые пакеты:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nУстановите их командой:")
        print("  sudo apt install sane-utils")
        print("  pip install Pillow img2pdf")
        print("=" * 60)
        return False
    
    return True


if __name__ == "__main__":
    if not check_dependencies():
        # Keep terminal open
        input("\nНажмите Enter для выхода...")
        exit(1)
    
    root = tk.Tk()
    app = ScannerApp(root)
    root.mainloop()
