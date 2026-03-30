#!/usr/bin/env python3
"""
HP LaserJet Network Scanner - Modern Multi-Page PDF Scanner
Works with Windows 10/11 and Linux
Uses eSCL/AirScan protocol for network scanning
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import sys
import time
from datetime import datetime
from io import BytesIO

# Third-party imports
try:
    import requests
    from PIL import Image
    import img2pdf
except ImportError as e:
    print(f"ERROR: Missing required package: {e}")
    print("Please install: pip install requests Pillow img2pdf")
    input("\nPress Enter to exit...")
    sys.exit(1)


class HPScanner:
    """HP LaserJet network scanner using eSCL protocol"""
    
    def __init__(self, ip_address):
        self.ip = ip_address
        self.base_url = f"http://{ip_address}/eSCL"
        self.session = requests.Session()
        self.session.timeout = 30
        
    def get_scanner_info(self):
        """Get scanner capabilities"""
        try:
            resp = self.session.get(f"{self.base_url}/ScannerCapabilities", timeout=10)
            if resp.status_code == 200:
                return resp.text
            return None
        except Exception as e:
            raise Exception(f"Cannot connect to scanner: {e}")
    
    def scan_page(self, color_mode='Color', resolution=200):
        """Scan a single page and return image data"""
        # Create scan job
        scan_settings = f"""<?xml version="1.0" encoding="UTF-8"?>
<scanSettings xmlns="http://www.hp.com/schemas/imaging/con/escl/2011/05/03">
    <adsConfig>
        <selectedInputTray>Feeder1</selectedInputTray>
    </adsConfig>
    <documentFormatInfo>
        <documentFormat>Png</documentFormat>
    </documentFormatInfo>
    <imageInfo>
        <colorMode>{color_mode}</colorMode>
        <grayscaleRendering>BlackWhiteText</grayscaleRendering>
        <inputSource>Feeder1</inputSource>
        <resolution>{resolution}</resolution>
        <xResolution>{resolution}</xResolution>
        <yResolution>{resolution}</yResolution>
    </imageInfo>
</scanSettings>"""

        try:
            # Start scan job
            headers = {'Content-Type': 'application/xml'}
            resp = self.session.post(
                f"{self.base_url}/ScanJobs",
                data=scan_settings,
                headers=headers,
                timeout=15
            )
            
            if resp.status_code != 201:
                raise Exception(f"Failed to start scan job: HTTP {resp.status_code}")
            
            # Get job URI from response
            job_uri = resp.headers.get('Job-Uri', '')
            if not job_uri:
                # Try to parse from XML response
                import re
                match = re.search(r'<jobUri>(.*?)</jobUri>', resp.text)
                if match:
                    job_uri = match.group(1)
            
            if not job_uri:
                raise Exception("No job URI returned from scanner")
            
            # Poll for scan completion
            max_attempts = 60
            for attempt in range(max_attempts):
                time.sleep(0.5)
                try:
                    status_resp = self.session.get(job_uri, timeout=10)
                    if status_resp.status_code == 200:
                        # Check if scan is ready
                        if 'Completed' in status_resp.text or status_resp.status_code == 200:
                            # Look for image URI in response
                            import re
                            img_match = re.search(r'<uri>(http://[^<]+)</uri>', status_resp.text)
                            if img_match:
                                img_uri = img_match.group(1)
                                # Download the image
                                img_resp = self.session.get(img_uri, timeout=30)
                                if img_resp.status_code == 200:
                                    return BytesIO(img_resp.content)
                                else:
                                    raise Exception(f"Failed to download image: HTTP {img_resp.status_code}")
                            
                            # If no URI yet, check for next URI
                            next_match = re.search(r'<nextDocumentURI>(http://[^<]+)</nextDocumentURI>', status_resp.text)
                            if next_match:
                                img_resp = self.session.get(next_match.group(1), timeout=30)
                                if img_resp.status_code == 200:
                                    return BytesIO(img_resp.content)
                    
                    # Also try the common image retrieval pattern
                    if attempt > 5:
                        try:
                            img_resp = self.session.get(
                                f"{self.base_url}/ScanJobs/{job_uri.split('/')[-1]}/NextDocument",
                                timeout=10
                            )
                            if img_resp.status_code == 200 and len(img_resp.content) > 100:
                                return BytesIO(img_resp.content)
                        except:
                            pass
                            
                except requests.Timeout:
                    continue
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise Exception(f"Scan failed: {e}")
                    continue
            
            raise Exception("Scan timeout - no image received")
            
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"Connection error - check IP address: {e}")
        except Exception as e:
            raise Exception(f"Scan error: {e}")


class ScannerApp:
    """Main application GUI"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("HP LaserJet Scanner")
        self.root.geometry("900x700")
        
        # State variables
        self.scanner = None
        self.scanned_images = []  # List of (image_data, thumbnail) tuples
        self.is_scanning = False
        self.scan_thread = None
        
        # Setup UI
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface"""
        # Top frame - connection settings
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="Scanner IP:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.ip_entry = ttk.Entry(top_frame, width=20)
        self.ip_entry.grid(row=0, column=1, padx=5, sticky=tk.W)
        self.ip_entry.insert(0, "192.168.1.100")
        
        ttk.Label(top_frame, text="Color:").grid(row=0, column=2, padx=10, sticky=tk.W)
        self.color_var = tk.StringVar(value="Color")
        color_combo = ttk.Combobox(top_frame, textvariable=self.color_var, 
                                   values=["Color", "Grayscale", "BlackWhite"], width=12)
        color_combo.grid(row=0, column=3, padx=5, sticky=tk.W)
        
        ttk.Label(top_frame, text="DPI:").grid(row=0, column=4, padx=10, sticky=tk.W)
        self.dpi_var = tk.StringVar(value="200")
        dpi_combo = ttk.Combobox(top_frame, textvariable=self.dpi_var,
                                 values=["150", "200", "300", "600"], width=6)
        dpi_combo.grid(row=0, column=5, padx=5, sticky=tk.W)
        
        self.connect_btn = ttk.Button(top_frame, text="Connect", command=self.connect_scanner)
        self.connect_btn.grid(row=0, column=6, padx=10)
        
        self.status_label = ttk.Label(top_frame, text="Disconnected", foreground="gray")
        self.status_label.grid(row=0, column=7, padx=10, sticky=tk.W)
        
        # Middle frame - scan controls and preview area
        middle_frame = ttk.Frame(self.root, padding="10")
        middle_frame.pack(fill=tk.BOTH, expand=True)
        
        # Control buttons
        btn_frame = ttk.Frame(middle_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.scan_btn = ttk.Button(btn_frame, text="📄 Scan Page", command=self.scan_page, state=tk.DISABLED)
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.finish_btn = ttk.Button(btn_frame, text="✓ Finish & Edit", command=self.finish_scanning, state=tk.DISABLED)
        self.finish_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_btn = ttk.Button(btn_frame, text="✕ Clear All", command=self.clear_all, state=tk.DISABLED)
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        self.progress_label = ttk.Label(btn_frame, text="", foreground="blue")
        self.progress_label.pack(side=tk.RIGHT, padx=10)
        
        # Preview canvas with scrollbar
        preview_frame = ttk.LabelFrame(middle_frame, text="Scanned Pages (drag to reorder)", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas for horizontal scrolling
        self.canvas = tk.Canvas(preview_frame, bg="white", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        
        # Bind mouse wheel for horizontal scrolling
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Drag and drop support
        self.drag_data = {"item": None, "x": 0, "index": -1}
        
        # Bottom frame - save button
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)
        
        self.save_btn = ttk.Button(bottom_frame, text="💾 Save as PDF", command=self.save_pdf, state=tk.DISABLED)
        self.save_btn.pack(side=tk.RIGHT, padx=5)
        
        self.page_count_label = ttk.Label(bottom_frame, text="Pages: 0", font=("Arial", 10, "bold"))
        self.page_count_label.pack(side=tk.LEFT, padx=10)
        
    def _on_mousewheel(self, event):
        """Handle mouse wheel for horizontal scrolling"""
        if event.num == 5 or event.delta == -120:
            self.canvas.xview_scroll(1, "units")
        elif event.num == 4 or event.delta == 120:
            self.canvas.xview_scroll(-1, "units")
    
    def connect_scanner(self):
        """Connect to the scanner"""
        ip = self.ip_entry.get().strip()
        if not ip:
            messagebox.showerror("Error", "Please enter scanner IP address")
            return
        
        self.connect_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Connecting...", foreground="orange")
        self.root.update()
        
        def connect_thread():
            try:
                self.scanner = HPScanner(ip)
                # Test connection
                self.scanner.get_scanner_info()
                
                self.root.after(0, lambda: self.on_connect_success())
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self.on_connect_error(error_msg))
        
        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()
    
    def on_connect_success(self):
        """Handle successful connection"""
        self.connect_btn.config(state=tk.NORMAL, text="Reconnect")
        self.status_label.config(text=f"Connected to {self.ip_entry.get()}", foreground="green")
        self.scan_btn.config(state=tk.NORMAL)
        messagebox.showinfo("Success", f"Connected to scanner at {self.ip_entry.get()}")
    
    def on_connect_error(self, error_msg):
        """Handle connection error"""
        self.connect_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Connection failed", foreground="red")
        # Keep terminal open - print error but don't exit
        print(f"\n{'='*60}")
        print(f"CONNECTION ERROR: {error_msg}")
        print(f"{'='*60}\n")
        messagebox.showerror("Connection Error", f"Cannot connect to scanner:\n\n{error_msg}\n\nCheck:\n1. IP address is correct\n2. Scanner is powered on\n3. Network connection is working")
    
    def scan_page(self):
        """Scan a single page"""
        if not self.scanner or self.is_scanning:
            return
        
        self.is_scanning = True
        self.scan_btn.config(state=tk.DISABLED)
        self.progress_label.config(text="Scanning...")
        self.root.update()
        
        color_mode = self.color_var.get()
        resolution = int(self.dpi_var.get())
        
        def scan_thread():
            try:
                print(f"\nStarting scan (color={color_mode}, dpi={resolution})...")
                
                # Perform scan
                image_data = self.scanner.scan_page(color_mode=color_mode, resolution=resolution)
                
                # Process image
                image_data.seek(0)
                img = Image.open(image_data)
                
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Create thumbnail
                thumb = img.copy()
                thumb.thumbnail((150, 200), Image.Resampling.LANCZOS)
                
                # Store in main thread
                self.root.after(0, lambda: self.on_scan_complete(image_data.getvalue(), thumb))
                
            except Exception as e:
                error_msg = str(e)
                print(f"\n{'='*60}")
                print(f"SCAN ERROR: {error_msg}")
                print(f"{'='*60}\n")
                self.root.after(0, lambda: self.on_scan_error(error_msg))
        
        self.scan_thread = threading.Thread(target=scan_thread, daemon=True)
        self.scan_thread.start()
    
    def on_scan_complete(self, image_bytes, thumbnail):
        """Handle successful scan completion"""
        self.is_scanning = False
        self.scan_btn.config(state=tk.NORMAL)
        self.finish_btn.config(state=tk.NORMAL)
        self.clear_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.NORMAL)
        self.progress_label.config(text="Ready")
        
        # Add to list
        self.scanned_images.append((image_bytes, thumbnail))
        self.update_page_count()
        
        # Display thumbnail
        self.add_thumbnail(thumbnail, len(self.scanned_images) - 1)
        
        print(f"✓ Page {len(self.scanned_images)} scanned successfully")
    
    def on_scan_error(self, error_msg):
        """Handle scan error"""
        self.is_scanning = False
        self.scan_btn.config(state=tk.NORMAL)
        self.progress_label.config(text="Scan failed")
        
        print(f"\n{'='*60}")
        print(f"SCAN ERROR on page {len(self.scanned_images) + 1}: {error_msg}")
        print(f"{'='*60}\n")
        
        messagebox.showerror("Scan Error", f"Failed to scan page {len(self.scanned_images) + 1}:\n\n{error_msg}\n\nThe program will remain open so you can see this error.")
    
    def add_thumbnail(self, thumbnail, index):
        """Add a thumbnail to the preview area"""
        from tkinter import PhotoImage
        
        # Convert PIL thumbnail to PhotoImage
        photo = PhotoImage(width=thumbnail.width, height=thumbnail.height)
        
        # Put pixel data
        for y in range(thumbnail.height):
            for x in range(thumbnail.width):
                r, g, b = thumbnail.getpixel((x, y))
                photo.put(f"#{r:02x}{g:02x}{b:02x}", (x, y))
        
        # Create frame for this thumbnail
        thumb_frame = ttk.Frame(self.scrollable_frame, relief=tk.RAISED, borderwidth=2)
        thumb_frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        label = tk.Label(thumb_frame, image=photo)
        label.image = photo  # Keep reference
        label.pack(padx=2, pady=2)
        
        # Page number
        page_label = ttk.Label(thumb_frame, text=f"Page {index + 1}")
        page_label.pack()
        
        # Make draggable
        label.bind("<ButtonPress-1>", lambda e, idx=index: self.on_drag_start(e, idx))
        label.bind("<B1-Motion>", self.on_drag_motion)
        label.bind("<ButtonRelease-1>", self.on_drag_release)
        thumb_frame.bind("<ButtonPress-1>", lambda e, idx=index: self.on_drag_start(e, idx))
        thumb_frame.bind("<B1-Motion>", self.on_drag_motion)
        thumb_frame.bind("<ButtonRelease-1>", self.on_drag_release)
        
        # Store widget reference
        thumb_frame.image_widget = label
        thumb_frame.page_index = index
    
    def on_drag_start(self, event, index):
        """Start dragging a thumbnail"""
        self.drag_data["item"] = event.widget.winfo_toplevel()
        self.drag_data["x"] = event.x
        self.drag_data["index"] = index
    
    def on_drag_motion(self, event):
        """Handle drag motion"""
        if self.drag_data["item"]:
            item = self.drag_data["item"]
            delta_x = event.x - self.drag_data["x"]
            item.place(x=item.winfo_x() + delta_x, y=item.winfo_y())
    
    def on_drag_release(self, event):
        """Handle drag release - reorder images"""
        if not self.drag_data["item"]:
            return
        
        # Get all thumbnail frames
        frames = [w for w in self.scrollable_frame.winfo_children() 
                  if hasattr(w, 'page_index')]
        
        # Sort by current x position
        frames_sorted = sorted(frames, key=lambda f: f.winfo_x())
        
        # Get new order
        new_order = [f.page_index for f in frames_sorted]
        
        # Reorder scanned_images list
        new_images = [self.scanned_images[i] for i in new_order]
        self.scanned_images = new_images
        
        # Reset drag data
        self.drag_data["item"] = None
        self.drag_data["index"] = -1
        
        # Rebuild thumbnails with correct page numbers
        self.rebuild_thumbnails()
        
        print(f"Pages reordered: {[i+1 for i in new_order]}")
    
    def rebuild_thumbnails(self):
        """Rebuild all thumbnails with correct page numbers"""
        # Clear existing
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Re-add in order
        for i, (img_bytes, thumb) in enumerate(self.scanned_images):
            # Recreate thumbnail with updated page number
            self.add_thumbnail(thumb, i)
        
        self.update_page_count()
    
    def finish_scanning(self):
        """Finish scanning and go to edit mode"""
        if not self.scanned_images:
            messagebox.showinfo("Info", "No pages scanned yet")
            return
        
        self.scan_btn.config(state=tk.DISABLED)
        self.progress_label.config(text="Ready to save")
        messagebox.showinfo("Scanning Complete", 
                           f"Scanned {len(self.scanned_images)} page(s).\n\n"
                           "Drag thumbnails to reorder pages.\n"
                           "Click 'Save as PDF' when ready.")
    
    def clear_all(self):
        """Clear all scanned pages"""
        if not self.scanned_images:
            return
        
        if messagebox.askyesno("Confirm", "Clear all scanned pages?"):
            self.scanned_images = []
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            self.update_page_count()
            self.finish_btn.config(state=tk.DISABLED)
            self.clear_btn.config(state=tk.DISABLED)
            self.save_btn.config(state=tk.DISABLED)
            self.progress_label.config(text="")
    
    def update_page_count(self):
        """Update page count display"""
        self.page_count_label.config(text=f"Pages: {len(self.scanned_images)}")
    
    def save_pdf(self):
        """Save all scanned pages as a single PDF"""
        if not self.scanned_images:
            messagebox.showerror("Error", "No pages to save")
            return
        
        # Ask for save location
        default_name = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=default_name,
            title="Save PDF"
        )
        
        if not filepath:
            return
        
        try:
            self.progress_label.config(text="Saving PDF...")
            self.root.update()
            
            # Convert images to PDF
            pdf_bytes = img2pdf.convert(
                [BytesIO(img_data) for img_data, _ in self.scanned_images],
                output_filepath=filepath
            )
            
            self.progress_label.config(text="Saved!")
            print(f"\n✓ PDF saved: {filepath}")
            print(f"  Total pages: {len(self.scanned_images)}\n")
            
            messagebox.showinfo("Success", f"PDF saved successfully!\n\n{filepath}\n\nPages: {len(self.scanned_images)}")
            
        except Exception as e:
            error_msg = str(e)
            print(f"\n{'='*60}")
            print(f"SAVE ERROR: {error_msg}")
            print(f"{'='*60}\n")
            messagebox.showerror("Save Error", f"Failed to save PDF:\n\n{error_msg}")
            self.progress_label.config(text="Save failed")


def main():
    """Main entry point"""
    print("=" * 60)
    print("HP LaserJet Network Scanner")
    print("=" * 60)
    print("\nStarting application...")
    print("Terminal will remain open to show any errors.\n")
    
    try:
        root = tk.Tk()
        app = ScannerApp(root)
        root.mainloop()
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"FATAL ERROR: {e}")
        print(f"{'='*60}\n")
        print("Program terminated. Press Enter to exit...")
        input()
        sys.exit(1)


if __name__ == "__main__":
    main()
