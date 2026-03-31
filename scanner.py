"""
HP LaserJet Scanner Application for Windows
Scans documents via network, allows multi-page scanning with reordering,
and saves as PDF. Uses WIA (Windows Image Acquisition) for native Windows support.

Requirements:
    pip install pywin32 Pillow pypdf2 tkinter

Note: This application is designed for Windows 10/11.
      It uses WIA (Windows Image Acquisition) which is native to Windows.
"""

import os
import sys
import threading
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image
import win32com.client
import win32gui
import win32con
import io

# Global variables
scanned_images = []  # List of PIL Image objects
scanner_device = None
is_scanning = False
scan_thread = None


def get_available_scanners():
    """Get list of available WIA scanners on the system."""
    scanners = []
    try:
        wia = win32com.client.Dispatch("WIA.DeviceManager")
        for device in wia.Devices:
            if device.Type == 1 or device.Type == 2:  # Scanner or Printer with scanner
                scanners.append({
                    'id': device.DeviceID,
                    'name': device.Name,
                    'type': device.Type
                })
    except Exception as e:
        print(f"Error getting scanners: {e}")
        traceback.print_exc()
    return scanners


def scan_page(scanner_id, color_mode=1):
    """
    Scan a single page using WIA.
    
    Args:
        scanner_id: Device ID of the scanner
        color_mode: 1=Color, 2=Grayscale, 4=Black&White
    
    Returns:
        PIL Image object or None if failed
    """
    try:
        wia = win32com.client.Dispatch("WIA.DeviceManager")
        device = None
        
        # Find the device by ID
        for dev in wia.Devices:
            if dev.DeviceID == scanner_id:
                device = dev
                break
        
        if device is None:
            raise Exception(f"Scanner with ID {scanner_id} not found")
        
        # Connect to scanner
        device.Connect()
        
        # Get the first item (usually the flatbed or ADF)
        item = None
        for itm in device.Items:
            if itm.ItemID == 1:  # First item
                item = itm
                break
        
        if item is None:
            raise Exception("No scan item found on device")
        
        # Configure scan settings
        # Set color mode
        for criterion in item.Criteria:
            if criterion.FilterID == "6147":  # WIA_IPS_CURRENT_INTENT
                criterion.Properties["6147"].Value = color_mode
            elif criterion.FilterID == "6148":  # WIA_IPS_XRES
                criterion.Properties["6148"].Value = 200  # DPI
            elif criterion.FilterID == "6149":  # WIA_IPS_YRES
                criterion.Properties["6149"].Value = 200  # DPI
        
        # Execute scan
        image_data = item.Transfer("")
        
        if image_data is None:
            raise Exception("No image data returned from scanner")
        
        # Convert to PIL Image
        image_bytes = image_data.FileData
        image_stream = io.BytesIO(image_bytes)
        pil_image = Image.open(image_stream)
        
        # Convert to RGB if necessary
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        
        return pil_image
        
    except Exception as e:
        error_msg = f"Scan error: {str(e)}\n\nFull traceback:\n{traceback.format_exc()}"
        print(error_msg)
        # Keep terminal open - don't exit
        return None


def images_to_pdf(images, output_path):
    """Save multiple images as a single PDF file."""
    if not images:
        return False
    
    try:
        # Convert all images to RGB
        rgb_images = []
        for img in images:
            if img.mode != 'RGB':
                rgb_images.append(img.convert('RGB'))
            else:
                rgb_images.append(img)
        
        # Save as PDF
        if len(rgb_images) == 1:
            rgb_images[0].save(output_path, 'PDF', resolution=200.0)
        else:
            rgb_images[0].save(
                output_path,
                'PDF',
                resolution=200.0,
                save_all=True,
                append_images=rgb_images[1:]
            )
        
        return True
    except Exception as e:
        print(f"Error saving PDF: {e}")
        traceback.print_exc()
        return False


class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet Scanner")
        self.root.geometry("900x700")
        
        self.scanned_images = []
        self.image_labels = []
        self.current_scanner_id = None
        
        self.setup_ui()
        self.load_scanners()
    
    def setup_ui(self):
        """Setup the user interface."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scanner selection
        scanner_frame = ttk.LabelFrame(main_frame, text="Scanner Selection", padding="5")
        scanner_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(scanner_frame, text="Select Scanner:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.scanner_combo = ttk.Combobox(scanner_frame, state="readonly", width=50)
        self.scanner_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.scanner_combo.bind('<<ComboboxSelected>>', self.on_scanner_selected)
        
        ttk.Button(scanner_frame, text="Refresh", command=self.load_scanners).pack(side=tk.LEFT, padx=(5, 0))
        
        # Color mode selection
        color_frame = ttk.LabelFrame(main_frame, text="Scan Settings", padding="5")
        color_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(color_frame, text="Color Mode:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.color_var = tk.IntVar(value=1)
        ttk.Radiobutton(color_frame, text="Color", variable=self.color_var, value=1).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(color_frame, text="Grayscale", variable=self.color_var, value=2).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(color_frame, text="Black & White", variable=self.color_var, value=4).pack(side=tk.LEFT, padx=5)
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.scan_btn = ttk.Button(button_frame, text="Scan Page", command=self.start_scan)
        self.scan_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.finish_btn = ttk.Button(button_frame, text="Finish & Save", command=self.finish_scanning)
        self.finish_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.finish_btn['state'] = 'disabled'
        
        self.clear_btn = ttk.Button(button_frame, text="Clear All", command=self.clear_all)
        self.clear_btn.pack(side=tk.LEFT)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_label.pack(fill=tk.X, pady=(0, 10))
        
        # Image preview area with horizontal scrolling
        preview_frame = ttk.LabelFrame(main_frame, text="Scanned Pages (drag to reorder)", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas with scrollbar for horizontal scrolling
        self.canvas = tk.Canvas(preview_frame, bg="white")
        scrollbar = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.canvas.xview)
        
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        self.canvas.configure(xscrollcommand=scrollbar.set)
        
        # Bind mouse wheel for horizontal scrolling
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel)
        
        scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Bind canvas resize
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        # Drag and drop variables
        self.drag_start_x = None
        self.dragged_widget = None
    
    def _on_canvas_configure(self, event):
        """Update scrollable frame width when canvas resizes."""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def _on_mousewheel(self, event):
        """Handle vertical mouse wheel scrolling."""
        # For horizontal scrolling with Shift+MouseWheel
        pass
    
    def _on_shift_mousewheel(self, event):
        """Handle horizontal scrolling with Shift+MouseWheel."""
        self.canvas.xview_scroll(int(-1*(event.delta/120)), "units")
    
    def load_scanners(self):
        """Load available scanners into combo box."""
        self.status_var.set("Loading scanners...")
        self.root.update()
        
        scanners = get_available_scanners()
        
        if not scanners:
            self.scanner_combo['values'] = ["No scanners found"]
            self.scanner_combo.set("No scanners found")
            self.current_scanner_id = None
            self.status_var.set("No scanners found. Make sure your HP LaserJet is connected and powered on.")
            return
        
        scanner_names = [f"{s['name']} (ID: {s['id']})" for s in scanners]
        self.scanner_combo['values'] = scanner_names
        self.scanner_combo.set(scanner_names[0])
        self.current_scanner_id = scanners[0]['id']
        self.status_var.set(f"Found {len(scanners)} scanner(s)")
    
    def on_scanner_selected(self, event):
        """Handle scanner selection change."""
        selection = self.scanner_combo.get()
        if selection and selection != "No scanners found":
            # Extract ID from selection
            try:
                self.current_scanner_id = selection.split("(ID: ")[1].rstrip(")")
            except:
                self.current_scanner_id = None
    
    def start_scan(self):
        """Start scanning a page in a separate thread."""
        global is_scanning
        
        if is_scanning:
            messagebox.showwarning("Warning", "Scan already in progress!")
            return
        
        if not self.current_scanner_id:
            messagebox.showerror("Error", "No scanner selected!")
            return
        
        is_scanning = True
        self.scan_btn['state'] = 'disabled'
        self.status_var.set("Scanning... Please wait")
        
        # Run scan in background thread
        scan_thread = threading.Thread(target=self._scan_thread_worker)
        scan_thread.daemon = True
        scan_thread.start()
    
    def _scan_thread_worker(self):
        """Worker thread for scanning."""
        global is_scanning
        
        try:
            color_mode = self.color_var.get()
            image = scan_page(self.current_scanner_id, color_mode)
            
            if image:
                # Add to scanned images
                self.scanned_images.append(image)
                
                # Update UI in main thread
                self.root.after(0, self._add_image_to_preview, image, len(self.scanned_images) - 1)
                self.root.after(0, lambda: self.status_var.set(f"Page {len(self.scanned_images)} scanned successfully"))
                self.root.after(0, lambda: self.finish_btn.config(state='normal' if len(self.scanned_images) > 0 else 'disabled'))
            else:
                self.root.after(0, lambda: self.status_var.set("Scan failed! Check console for details."))
                self.root.after(0, lambda: messagebox.showerror(
                    "Scan Error",
                    "Failed to scan page. Check the console/terminal for detailed error information.\n\n"
                    "Make sure:\n"
                    "1. The scanner is powered on\n"
                    "2. The scanner is connected to the network\n"
                    "3. Windows has the correct drivers installed\n"
                    "4. You can scan from another Windows application"
                ))
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}\n\n{traceback.format_exc()}"
            print(error_msg)
            self.root.after(0, lambda: self.status_var.set("Scan error occurred"))
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
        finally:
            is_scanning = False
            self.root.after(0, lambda: self.scan_btn.config(state='normal'))
    
    def _add_image_to_preview(self, image, index):
        """Add scanned image to preview area."""
        # Resize image for preview
        max_width = 150
        max_height = 200
        ratio = min(max_width / image.width, max_height / image.height)
        preview_size = (int(image.width * ratio), int(image.height * ratio))
        preview_image = image.copy().resize(preview_size, Image.Resampling.LANCZOS)
        
        # Create label with image
        from PIL import ImageTk
        photo = ImageTk.PhotoImage(preview_image)
        
        frame = ttk.Frame(self.scrollable_frame, relief=tk.RAISED, borderwidth=2)
        frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        label = ttk.Label(frame, image=photo, text=f"Page {index + 1}", compound=tk.TOP)
        label.image = photo  # Keep reference
        label.pack(padx=5, pady=5)
        
        # Add drag and drop functionality
        label.bind("<ButtonPress-1>", self._on_drag_start)
        label.bind("<B1-Motion>", self._on_drag_motion)
        label.bind("<ButtonRelease-1>", self._on_drag_release)
        frame.bind("<ButtonPress-1>", self._on_drag_start)
        frame.bind("<B1-Motion>", self._on_drag_motion)
        frame.bind("<ButtonRelease-1>", self._on_drag_release)
        
        self.image_labels.append({
            'frame': frame,
            'label': label,
            'photo': photo,
            'index': index
        })
    
    def _on_drag_start(self, event):
        """Start dragging a widget."""
        widget = event.widget
        self.drag_start_x = event.x
        self.dragged_widget = widget
    
    def _on_drag_motion(self, event):
        """Handle drag motion."""
        if self.dragged_widget is None:
            return
        
        x = event.widget.winfo_x() + event.x - self.drag_start_x
        event.widget.place(x=x, y=event.widget.winfo_y())
    
    def _on_drag_release(self, event):
        """Handle drag release - reorder images."""
        if self.dragged_widget is None:
            return
        
        # Get the frame that contains the dragged label
        dragged_frame = None
        widget = event.widget
        while widget:
            if isinstance(widget, ttk.Frame) and widget in [item['frame'] for item in self.image_labels]:
                dragged_frame = widget
                break
            widget = widget.master
        
        if dragged_frame is None:
            self.dragged_widget = None
            return
        
        # Find current position
        current_idx = None
        for i, item in enumerate(self.image_labels):
            if item['frame'] == dragged_frame:
                current_idx = i
                break
        
        if current_idx is None:
            self.dragged_widget = None
            return
        
        # Calculate new position based on x coordinate
        dragged_x = dragged_frame.winfo_x()
        
        # Find target position
        target_idx = current_idx
        for i, item in enumerate(self.image_labels):
            if i != current_idx:
                item_x = item['frame'].winfo_x()
                item_width = item['frame'].winfo_width()
                
                if dragged_x > item_x and dragged_x < item_x + item_width:
                    target_idx = i
                    break
        
        # Reorder if needed
        if target_idx != current_idx:
            # Swap in list
            self.scanned_images[current_idx], self.scanned_images[target_idx] = \
                self.scanned_images[target_idx], self.scanned_images[current_idx]
            
            # Rebuild preview
            self._rebuild_preview()
        
        self.dragged_widget = None
    
    def _rebuild_preview(self):
        """Rebuild the preview area with reordered images."""
        # Clear existing widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.image_labels = []
        
        # Re-add all images
        for i, image in enumerate(self.scanned_images):
            self._add_image_to_preview(image, i)
        
        self.status_var.set(f"Pages reordered. Total: {len(self.scanned_images)}")
    
    def finish_scanning(self):
        """Finish scanning and save to PDF."""
        if not self.scanned_images:
            messagebox.showwarning("Warning", "No pages scanned!")
            return
        
        # Ask for save location
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Save PDF As"
        )
        
        if not file_path:
            return
        
        self.status_var.set("Saving PDF...")
        self.root.update()
        
        try:
            success = images_to_pdf(self.scanned_images, file_path)
            
            if success:
                self.status_var.set(f"Saved successfully: {os.path.basename(file_path)}")
                messagebox.showinfo("Success", f"PDF saved successfully!\n\nLocation: {file_path}\nPages: {len(self.scanned_images)}")
                
                # Clear after successful save
                self.clear_all()
            else:
                self.status_var.set("Failed to save PDF")
                messagebox.showerror("Error", "Failed to save PDF. Check console for details.")
        except Exception as e:
            error_msg = f"Error saving PDF: {str(e)}\n\n{traceback.format_exc()}"
            print(error_msg)
            self.status_var.set("Error saving PDF")
            messagebox.showerror("Error", error_msg)
    
    def clear_all(self):
        """Clear all scanned images."""
        self.scanned_images = []
        
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.image_labels = []
        self.finish_btn['state'] = 'disabled'
        self.status_var.set("Cleared. Ready to scan.")


def main():
    """Main entry point."""
    # Prevent terminal from closing on errors
    if sys.platform == 'win32':
        # Keep console open
        pass
    
    try:
        root = tk.Tk()
        app = ScannerApp(root)
        root.mainloop()
    except Exception as e:
        error_msg = f"Fatal error: {str(e)}\n\n{traceback.format_exc()}"
        print(error_msg)
        print("\nProgram terminated. Press Enter to exit...")
        try:
            input()
        except:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
