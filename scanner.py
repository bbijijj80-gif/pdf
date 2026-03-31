"""
HP LaserJet MFP Scanner Application for Windows
Uses python-twain library for TWAIN-compliant scanners
"""

import sys
import os
import time
import threading
from pathlib import Path

# Check if running on Windows
if sys.platform != 'win32':
    print("ERROR: This application is designed for Windows only!")
    print("Please run this on Windows 10/11.")
    input("Press Enter to exit...")
    sys.exit(1)

try:
    import twain
except ImportError:
    print("ERROR: python-twain library not found!")
    print("Please run install_drivers.bat first to install required libraries.")
    input("Press Enter to exit...")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow library not found!")
    print("Please run install_drivers.bat first to install required libraries.")
    input("Press Enter to exit...")
    sys.exit(1)

try:
    import pypdf2
except ImportError:
    try:
        import PyPDF2
    except ImportError:
        print("ERROR: PyPDF2 library not found!")
        print("Please run install_drivers.bat first to install required libraries.")
        input("Press Enter to exit...")
        sys.exit(1)

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except ImportError:
    print("ERROR: tkinter not available!")
    input("Press Enter to exit...")
    sys.exit(1)


class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet MFP Scanner")
        self.root.geometry("900x700")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Scanned pages storage
        self.scanned_pages = []  # List of (image_path, image_object) tuples
        self.current_image = None
        self.selected_scanner = None
        self.scanners = []
        self.is_scanning = False
        
        self.setup_ui()
        self.detect_scanners()
    
    def setup_ui(self):
        # Top frame - Scanner selection
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="Scanner:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.scanner_combo = ttk.Combobox(top_frame, state="readonly", width=40)
        self.scanner_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.scanner_combo.bind('<<ComboboxSelected>>', self.on_scanner_selected)
        
        self.refresh_btn = ttk.Button(top_frame, text="Refresh", command=self.detect_scanners)
        self.refresh_btn.pack(side=tk.LEFT)
        
        # Settings frame
        settings_frame = ttk.LabelFrame(self.root, text="Scan Settings", padding="10")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(settings_frame, text="Color Mode:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.color_mode = ttk.Combobox(settings_frame, values=["Color", "Grayscale", "Black & White"], state="readonly", width=20)
        self.color_mode.set("Color")
        self.color_mode.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Resolution (DPI):").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.resolution = ttk.Combobox(settings_frame, values=["150", "200", "300", "600"], state="readonly", width=10)
        self.resolution.set("300")
        self.resolution.grid(row=0, column=3, padx=5, pady=5)
        
        # Control buttons frame
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X)
        
        self.scan_btn = ttk.Button(control_frame, text="📷 Scan Page", command=self.scan_page)
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.finish_btn = ttk.Button(control_frame, text="✓ Finish & Edit", command=self.finish_scanning)
        self.finish_btn.pack(side=tk.LEFT, padx=5)
        self.finish_btn['state'] = 'disabled'
        
        self.clear_btn = ttk.Button(control_frame, text="🗑 Clear All", command=self.clear_all)
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Status label
        self.status_label = ttk.Label(control_frame, text="Ready", foreground="green")
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        # Preview area
        preview_frame = ttk.LabelFrame(self.root, text="Scanned Pages (Drag to reorder)", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Canvas for horizontal scrolling
        self.canvas = tk.Canvas(preview_frame, bg="white")
        self.scrollbar = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.canvas.xview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind mouse wheel for horizontal scrolling
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        
        # Page counter
        self.page_count_label = ttk.Label(preview_frame, text="Pages: 0")
        self.page_count_label.pack(side=tk.TOP, pady=5)
    
    def _on_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.canvas.xview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.xview_scroll(1, "units")
    
    def detect_scanners(self):
        """Detect available TWAIN scanners"""
        self.status_label.config(text="Detecting scanners...", foreground="blue")
        self.root.update()
        
        try:
            self.scanners = twain.GetSources()
            self.scanner_combo['values'] = [s['ProductName'] for s in self.scanners]
            
            if self.scanners:
                self.scanner_combo.set(self.scanners[0]['ProductName'])
                self.selected_scanner = self.scanners[0]
                self.status_label.config(text=f"Found {len(self.scanners)} scanner(s)", foreground="green")
            else:
                self.status_label.config(text="No scanners found! Install HP drivers.", foreground="red")
                messagebox.showwarning("Warning", 
                    "No TWAIN scanners detected!\n\n"
                    "Please ensure:\n"
                    "1. HP LaserJet M28w is powered on\n"
                    "2. USB cable is connected OR printer is on same network\n"
                    "3. HP Full Feature Drivers are installed\n"
                    "4. TWAIN driver is installed from HP website")
        except Exception as e:
            self.status_label.config(text="Error detecting scanners", foreground="red")
            messagebox.showerror("Scanner Detection Error", 
                f"Failed to detect scanners:\n{str(e)}\n\n"
                "Make sure HP TWAIN drivers are installed.")
    
    def on_scanner_selected(self, event):
        """Handle scanner selection from dropdown"""
        selection = self.scanner_combo.get()
        for scanner in self.scanners:
            if scanner['ProductName'] == selection:
                self.selected_scanner = scanner
                break
    
    def scan_page(self):
        """Scan a single page"""
        if self.is_scanning:
            messagebox.showwarning("Warning", "Already scanning!")
            return
        
        if not self.selected_scanner:
            messagebox.showerror("Error", "Please select a scanner first!")
            return
        
        self.is_scanning = True
        self.scan_btn['state'] = 'disabled'
        self.status_label.config(text="Scanning...", foreground="orange")
        self.root.update()
        
        # Run scanning in separate thread to avoid freezing
        scan_thread = threading.Thread(target=self._do_scan)
        scan_thread.daemon = True
        scan_thread.start()
    
    def _do_scan(self):
        """Actual scanning operation in background thread"""
        temp_dir = Path(os.environ.get('TEMP', '.')) / 'hp_scanner_temp'
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # Set up scanner
            src_id = twain.OpenSource(self.selected_scanner)
            
            # Configure scan settings
            cap = twain.Capability(src_id, twain.ICAP_PIXELTYPE)
            color_mode = self.color_mode.get()
            if color_mode == "Color":
                cap.Set([twain.TWPT_RGB])
            elif color_mode == "Grayscale":
                cap.Set([twain.TWPT_GRAY])
            else:
                cap.Set([twain.TWPT_BW])
            
            cap = twain.Capability(src_id, twain.ICAP_XRESOLUTION)
            cap.Set([float(self.resolution.get())])
            
            cap = twain.Capability(src_id, twain.ICAP_YRESOLUTION)
            cap.Set([float(self.resolution.get())])
            
            # Acquire image
            self.root.after(0, lambda: self.status_label.config(text="Acquiring image...", foreground="orange"))
            
            # Show TWAIN UI for manual feed
            image_data = twain.AcquireToBuffer(src_id)
            
            twain.CloseSource(src_id)
            
            if image_data:
                # Save temporary image
                timestamp = int(time.time() * 1000)
                temp_file = temp_dir / f'scan_{timestamp}.png'
                
                # Convert to PIL Image
                from io import BytesIO
                img = Image.open(BytesIO(image_data))
                img.save(temp_file, 'PNG')
                
                # Add to pages list
                self.scanned_pages.append((temp_file, img))
                
                # Update UI
                self.root.after(0, lambda: self._update_preview(len(self.scanned_pages) - 1))
                self.root.after(0, lambda: self.status_label.config(text=f"Page {len(self.scanned_pages)} scanned!", foreground="green"))
                self.root.after(0, lambda: self.page_count_label.config(text=f"Pages: {len(self.scanned_pages)}"))
                self.root.after(0, lambda: self.finish_btn.config(state='normal'))
            else:
                self.root.after(0, lambda: messagebox.showerror("Scan Failed", "No image data received from scanner."))
                self.root.after(0, lambda: self.status_label.config(text="Scan failed!", foreground="red"))
        
        except twain.SourceSelectionError as e:
            error_msg = f"Scanner selection error: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("Scanner Error", error_msg))
            self.root.after(0, lambda: self.status_label.config(text="Scanner error!", foreground="red"))
        
        except twain.SourceDeviceError as e:
            error_msg = f"Scanner device error: {str(e)}\n\nCheck if scanner is ready and paper is loaded."
            self.root.after(0, lambda: messagebox.showerror("Scanner Device Error", error_msg))
            self.root.after(0, lambda: self.status_label.config(text="Device error!", foreground="red"))
        
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}\n\nMake sure HP TWAIN drivers are properly installed."
            self.root.after(0, lambda: messagebox.showerror("Scan Error", error_msg))
            self.root.after(0, lambda: self.status_label.config(text="Error!", foreground="red"))
        
        finally:
            self.is_scanning = False
            self.root.after(0, lambda: self.scan_btn.config(state='normal'))
    
    def _update_preview(self, page_index):
        """Update the preview area with scanned page"""
        # Clear existing thumbnails
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Create thumbnails for all pages
        self.thumbnails = []
        for idx, (path, img) in enumerate(self.scanned_pages):
            # Create frame for each thumbnail
            thumb_frame = ttk.Frame(self.scrollable_frame, relief=tk.RAISED, borderwidth=2)
            thumb_frame.pack(side=tk.LEFT, padx=5, pady=5)
            
            # Resize for thumbnail
            thumb_img = img.copy()
            thumb_img.thumbnail((150, 200), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(thumb_img)
            self.thumbnails.append(photo)
            
            # Display thumbnail
            label = ttk.Label(thumb_frame, image=photo)
            label.image = photo
            label.pack()
            
            # Page number
            ttk.Label(thumb_frame, text=f"Page {idx + 1}").pack()
            
            # Delete button
            del_btn = ttk.Button(thumb_frame, text="🗑", 
                               command=lambda i=idx: self.delete_page(i))
            del_btn.pack()
            
            # Make draggable
            self._make_draggable(thumb_frame, idx)
    
    def _make_draggable(self, widget, index):
        """Make widget draggable for reordering"""
        widget.bind("<ButtonPress-1>", lambda e, i=index: self._start_drag(e, i))
        widget.bind("<B1-Motion>", self._drag)
        widget.bind("<ButtonRelease-1>", self._end_drag)
        
        for child in widget.winfo_children():
            child.bind("<ButtonPress-1>", lambda e, i=index: self._start_drag(e, i))
            child.bind("<B1-Motion>", self._drag)
            child.bind("<ButtonRelease-1>", self._end_drag)
    
    def _start_drag(self, event, index):
        self.drag_index = index
        self.drag_widget = self.scrollable_frame.winfo_children()[index]
        self.drag_widget.config(relief=tk.SOLID, borderwidth=3)
    
    def _drag(self, event):
        if hasattr(self, 'drag_widget'):
            # Move widget horizontally
            x = event.x_root - self.scrollable_frame.winfo_rootx()
            self.drag_widget.place(x=x, y=0)
    
    def _end_drag(self, event):
        if hasattr(self, 'drag_widget'):
            self.drag_widget.config(relief=tk.RAISED, borderwidth=2)
            self.drag_widget.place_forget()
            
            # Calculate new position
            x = event.x_root - self.scrollable_frame.winfo_rootx()
            children = self.scrollable_frame.winfo_children()
            
            # Find insertion point
            insert_pos = len(children)
            for i, child in enumerate(children):
                if i != self.drag_index:
                    child_x = child.winfo_x()
                    child_width = child.winfo_width()
                    if x < child_x + child_width // 2:
                        insert_pos = i
                        break
            
            # Reorder list
            if insert_pos > self.drag_index:
                insert_pos -= 1
            
            page = self.scanned_pages.pop(self.drag_index)
            self.scanned_pages.insert(insert_pos, page)
            
            # Refresh preview
            self._update_preview(insert_pos)
            
            del self.drag_widget
            del self.drag_index
    
    def delete_page(self, index):
        """Delete a scanned page"""
        if 0 <= index < len(self.scanned_pages):
            path, _ = self.scanned_pages[index]
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
            
            self.scanned_pages.pop(index)
            
            if not self.scanned_pages:
                self.finish_btn['state'] = 'disabled'
                self.page_count_label.config(text="Pages: 0")
                for widget in self.scrollable_frame.winfo_children():
                    widget.destroy()
            else:
                self._update_preview(0)
                self.page_count_label.config(text=f"Pages: {len(self.scanned_pages)}")
    
    def clear_all(self):
        """Clear all scanned pages"""
        if messagebox.askyesno("Confirm", "Delete all scanned pages?"):
            for path, _ in self.scanned_pages:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except:
                    pass
            
            self.scanned_pages = []
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            
            self.finish_btn['state'] = 'disabled'
            self.page_count_label.config(text="Pages: 0")
            self.status_label.config(text="Cleared", foreground="blue")
    
    def finish_scanning(self):
        """Finish scanning and save to PDF"""
        if not self.scanned_pages:
            messagebox.showwarning("Warning", "No pages to save!")
            return
        
        # Ask for save location
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Save PDF"
        )
        
        if not file_path:
            return
        
        try:
            self.status_label.config(text="Creating PDF...", foreground="orange")
            self.root.update()
            
            # Sort images by their current order in list
            images = [img for _, img in self.scanned_pages]
            
            if len(images) == 1:
                images[0].save(file_path, 'PDF', resolution=100.0)
            else:
                # Save first image, then append others
                images[0].save(
                    file_path,
                    'PDF',
                    resolution=100.0,
                    save_all=True,
                    append_images=images[1:]
                )
            
            self.status_label.config(text=f"Saved: {os.path.basename(file_path)}", foreground="green")
            messagebox.showinfo("Success", f"PDF saved successfully!\n\n{file_path}")
            
            # Clean up temp files
            for path, _ in self.scanned_pages:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except:
                    pass
            
            self.scanned_pages = []
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            self.finish_btn['state'] = 'disabled'
            self.page_count_label.config(text="Pages: 0")
            
        except Exception as e:
            self.status_label.config(text="Save failed!", foreground="red")
            messagebox.showerror("Save Error", f"Failed to save PDF:\n{str(e)}")
    
    def on_closing(self):
        """Handle window close"""
        # Clean up temp files
        temp_dir = Path(os.environ.get('TEMP', '.')) / 'hp_scanner_temp'
        if temp_dir.exists():
            for path, _ in self.scanned_pages:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except:
                    pass
        
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
