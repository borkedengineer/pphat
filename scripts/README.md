# FAA Test Parser

A command-line tool for extracting questions and answers from FAA written test images (PPL, Instrument, etc.) using OCR. It processes question screenshots in parallel and can export results to CSV when paired with an answer key.

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

Process all images in a folder and display extracted text:

```bash
python faa_test_parser.py --source /path/to/test-images
```

### Export to CSV

If your folder contains question images (`q1.png`, `q2.png`, etc.) and an `answer-key.md` file, export everything to a CSV:

```bash
python faa_test_parser.py --export-csv --source practice-tests/2025-10-11
```

Process multiple test folders at once:

```bash
python faa_test_parser.py --export-csv -s practice-tests/2025-10-11 practice-tests/2025-11-02
```

### Advanced Options

Specify number of worker threads:

```bash
python faa_test_parser.py --source ./test-images --workers 4
```

Disable image preprocessing (use raw images):

```bash
python faa_test_parser.py --source ./test-images --no-preprocessing
```

Enable verbose logging:

```bash
python faa_test_parser.py --source ./test-images --verbose
```

### Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--source` | `-s` | Path(s) to folder(s) containing images (required, can specify multiple) |
| `--export-csv` | | Export questions and answers to CSV (requires `answer-key.md` in folder) |
| `--workers` | `-w` | Number of worker threads (default: CPU count) |
| `--no-preprocessing` | | Skip image enhancement before OCR |
| `--verbose` | `-v` | Enable verbose logging |
| `--help` | `-h` | Show help message |

## Expected Folder Structure

For CSV export, your test folder should look like:

```
practice-tests/2025-10-11/
├── q1.png
├── q2.png
├── ...
├── q60.png
├── answer-key.md
└── figures/          # optional reference images
```

The `answer-key.md` file should contain one answer per line (line 1 = Q1's answer, etc.).

## Supported Image Formats

- PNG (.png)
- JPEG (.jpg, .jpeg)
- BMP (.bmp)
- TIFF (.tiff, .tif)
