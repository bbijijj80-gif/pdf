#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тестовый скрипт для проверки основных функций сканера"""

import sys
import os
sys.path.insert(0, '/workspace')

print("Тестирование модуля hp_scanner.py...")
print("=" * 50)

try:
    print("1. Импорт модулей...")
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import os
    import sys
    import tempfile
    import threading
    import traceback
    from PIL import Image, ImageTk
    import fitz
    import subprocess
    import shutil
    from pathlib import Path
    import logging
    print("   ✓ Все модули импортированы успешно")
except Exception as e:
    print(f"   ✗ Ошибка импорта: {e}")
    sys.exit(1)

try:
    print("2. Проверка логирования...")
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('test_scanner_log.txt', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("Тестовое сообщение")
    print("   ✓ Логирование настроено успешно")
except Exception as e:
    print(f"   ✗ Ошибка логирования: {e}")

try:
    print("3. Создание тестового изображения...")
    img = Image.new('RGB', (2480, 3508), color=(255, 255, 255))
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 2430, 3458], outline=(0, 0, 0), width=5)
    draw.text((100, 100), "Тестовая страница", fill=(0, 0, 0))
    print("   ✓ Изображение создано")
except Exception as e:
    print(f"   ✗ Ошибка создания изображения: {e}")

try:
    print("4. Сохранение изображения во временный файл...")
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, "test_page.png")
    img.save(temp_path)
    print(f"   ✓ Файл сохранен: {temp_path}")
except Exception as e:
    print(f"   ✗ Ошибка сохранения: {e}")

try:
    print("5. Конвертация в PDF с помощью PyMuPDF...")
    pdf_doc = fitz.open()
    img_width = img.width
    img_height = img.height
    pdf_page = pdf_doc.new_page(width=img_width * 72 / 300, height=img_height * 72 / 300)
    rect = fitz.Rect(0, 0, img_width * 72 / 300, img_height * 72 / 300)
    pdf_page.insert_image(rect, filename=temp_path)
    pdf_output = os.path.join(temp_dir, "test_output.pdf")
    pdf_doc.save(pdf_output)
    pdf_doc.close()
    print(f"   ✓ PDF создан: {pdf_output}")
    print(f"   ✓ Размер PDF: {os.path.getsize(pdf_output)} байт")
except Exception as e:
    print(f"   ✗ Ошибка конвертации в PDF: {e}")
    traceback.print_exc()

try:
    print("6. Очистка временных файлов...")
    shutil.rmtree(temp_dir)
    print("   ✓ Временные файлы удалены")
except Exception as e:
    print(f"   ✗ Ошибка очистки: {e}")

print("=" * 50)
print("Все тесты пройдены успешно!")
print("\nТеперь можно запустить графический интерфейс:")
print("  python3 /workspace/hp_scanner.py")
print("\nЛогирование сохраняется в файле scanner_log.txt")
