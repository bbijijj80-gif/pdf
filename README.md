# HP LaserJet Network Scanner

Modern multi-page PDF scanner for HP LaserJet printers with network scanning support.

## Features

- ✅ **Network scanning** via eSCL/AirScan protocol (no SANE required)
- ✅ **Step-by-step scanning**: Scan → place next page → Scan again → Finish
- ✅ **Drag-and-drop editor**: Rearrange pages horizontally before saving
- ✅ **Color mode selection**: Color, Grayscale, Black & White
- ✅ **Resolution options**: 150, 200, 300, 600 DPI
- ✅ **Multi-page PDF**: All pages saved in correct order in one file
- ✅ **Error handling**: Terminal stays open to show detailed error messages
- ✅ **Windows 10/11 compatible**: Works on modern Windows systems

## Installation

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install requests Pillow img2pdf
```

### 2. Find your scanner IP address

- Check your printer's network settings
- Or print a network configuration page from the printer menu
- IP should look like: `192.168.1.100`

## Usage

### Run the program

```bash
python hp_scanner.py
```

### Scanning workflow

1. **Enter scanner IP** in the top field
2. Click **"Connect"** - wait for "Connected" status
3. Select **Color mode** and **DPI** resolution
4. Click **"📄 Scan Page"** 
   - Place your document in the scanner
   - Wait for scan to complete (~5-15 seconds)
   - Thumbnail appears in preview area
5. **Place next page** and click **"📄 Scan Page"** again
6. Repeat step 5 for all pages
7. Click **"✓ Finish & Edit"** when done scanning
8. **Drag thumbnails** left/right to reorder pages if needed
9. Click **"💾 Save as PDF"** and choose save location

## Troubleshooting

### "Cannot connect to scanner"
- Verify IP address is correct
- Ensure scanner is powered on
- Check network connection (ping the IP)
- Make sure firewall allows HTTP traffic to scanner

### "Scan timeout" or white image
- Some HP models use different eSCL paths
- Try restarting the scanner
- Check if scanner lid is closed properly
- Verify paper is loaded in ADF (Automatic Document Feeder)

### Program freezes during scan
- The scan process runs in a separate thread (won't freeze UI)
- If stuck, check terminal for error messages
- Terminal stays open so you can see full error details

### Drag and drop not working smoothly
- Click and hold on a thumbnail
- Drag left or right to new position
- Release mouse button to drop
- Page numbers will update automatically

## Technical Details

- **Protocol**: eSCL (AirScan) over HTTP
- **Image format**: PNG (converted to PDF)
- **GUI**: Tkinter (built-in with Python)
- **Threading**: Non-blocking scan operations
- **Dependencies**: Modern libraries only (no deprecated packages)

## Supported Systems

- Windows 10/11
- Windows 7/8 (with Python 3.8+)
- Linux (Ubuntu, Debian, etc.)
- macOS (with Python 3.8+)

## Notes

- No SANE or additional drivers required
- Works with most HP LaserJet Pro models with network scanning
- For USB-connected scanners, use manufacturer software instead
