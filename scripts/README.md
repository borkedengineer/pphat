# PTAC - Image to Text Converter

A command-line tool for processing multiple images in parallel to extract text using OCR (Optical Character Recognition).

## Installation

### Pre-requisites

The script uses `Tesseract` for OCR. Its binaries need to be installed in order to analyze practice test screenshots.

Installation for your operating system:

- **macOS**: `brew install tesseract`
- **Ubuntu/Debian**: `sudo apt-get install tesseract-ocr`
- **Windows**: Download from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Process all images in a folder:

```bash
python ptac.py --source /path/to/your/images
```

### Advanced Usage

Process images with custom number of worker threads:

```bash
python ptac.py --source /path/to/your/images --workers 4
```

Enable verbose logging:

```bash
python ptac.py --source /path/to/your/images --verbose
```

### Command Line Options

- `--source, -s`: Path to folder containing images to process (required)
- `--workers, -w`: Number of worker threads (default: CPU count)
- `--verbose, -v`: Enable verbose logging
- `--help, -h`: Show help message

## Supported Image Formats

- PNG (.png)
- JPEG (.jpg, .jpeg)
- BMP (.bmp)
- TIFF (.tiff, .tif)
