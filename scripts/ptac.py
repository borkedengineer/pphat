#!/usr/bin/env python3
"""
Image to Text Converter (PTAC)
Processes images in parallel to extract text using OCR.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from pathlib import Path
import re
import sys
from typing import Dict, List, Tuple

try:
    from PIL import Image, ImageEnhance
except ImportError:
    print("Error: PIL (Pillow) is not installed. Please run: pip install -r requirements.txt")
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("Error: pytesseract is not installed. Please run: pip install -r requirements.txt")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}


class ImageProcessor:
    """Handles image processing and OCR operations."""

    def __init__(self, max_workers: int = None, enable_preprocessing: bool = True):
        """
        Initialize the image processor.

        Args:
            max_workers: Maximum number of worker threads. Defaults to CPU count.
            enable_preprocessing: Whether to apply image preprocessing for better OCR
        """
        self.max_workers = max_workers
        self.enable_preprocessing = enable_preprocessing
        self.tesseract_config = '--oem 3 --psm 3'

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image to improve OCR accuracy.
        
        Args:
            image: PIL Image object
            
        Returns:
            Preprocessed PIL Image object
        """
        # Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')

        # Enhance contrast moderately to preserve spacing
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)

        # Enhance brightness slightly
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(1.1)

        # Apply slight sharpening
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.5)

        return image

    def postprocess_ocr_text(self, text: str) -> str:
        """
        Clean OCR text by removing common artifacts and unwanted characters.
        
        Args:
            text: Raw OCR text
            
        Returns:
            Cleaned text
        """
        # Remove common OCR artifacts from radio buttons and checkboxes
        # Patterns like "CD)", "Cc)", "0)", "O)", "A. Cc)", ". Cc)", etc.
        text = re.sub(r'[CDOo0]+\s*\)', '', text)
        text = re.sub(r'0\s+0\s*:', '', text)
        text = re.sub(r'0\s+0\s*', '', text)
        text = re.sub(r'[A-Z]\.\s*Cc\)', '', text)  # Remove "A. Cc)", "B. Cc)", etc.
        text = re.sub(r'\.\s*Cc\)', '', text)       # Remove ". Cc)"
        text = re.sub(r'c\.\s*Cc\)', '', text)      # Remove "c. Cc)" (lowercase)

        # Fix specific OCR errors
        text = re.sub(r'Cc\s+([A-Z])', r'C. \1', text)  # "Cc Damage" -> "C. Damage"
        text = re.sub(r':\s*([A-Z])', r'A. \1', text)   # ": A full stall" -> "A. A full stall"

        # Fix lowercase c that should be C.
        text = re.sub(r'^c\s+', 'C. ', text, flags=re.MULTILINE)  # "c Full fuel" -> "C. Full fuel"
        text = re.sub(r'\nc\s+', '\nC. ', text)                  # "c Full fuel" -> "C. Full fuel" on new line

        # Remove standalone C. or c that appear without content
        text = re.sub(r'^C\.\s*$', '', text, flags=re.MULTILINE)  # Remove standalone "C."
        text = re.sub(r'^c\s*$', '', text, flags=re.MULTILINE)    # Remove standalone "c"
        text = re.sub(r'\nC\.\s*\n', '\n', text)                 # Remove "C." on its own line
        text = re.sub(r'\nc\s*\n', '\n', text)                   # Remove "c" on its own line

        # Remove answer choice prefixes (A., B., C., Cc., etc.) - we'll enumerate later
        text = re.sub(r'^[A-Z]\.\s+', '', text, flags=re.MULTILINE)   # Remove "A. ", "B. ", "C. " at start of line
        text = re.sub(r'\n[A-Z]\.\s+', '\n', text)                   # Remove "A. ", "B. ", "C. " after newline
        text = re.sub(r'^Cc\.\s+', '', text, flags=re.MULTILINE)     # Remove "Cc. " at start of line
        text = re.sub(r'\nCc\.\s+', '\n', text)                      # Remove "Cc. " after newline

        # Remove standalone colons, semicolons, periods, and quotes at start of lines (OCR artifacts)
        text = re.sub(r'^:\s*$', '', text, flags=re.MULTILINE)   # Remove standalone ":"
        text = re.sub(r'^;\s*$', '', text, flags=re.MULTILINE)   # Remove standalone ";"
        text = re.sub(r'\n:\s*\n', '\n', text)                  # Remove ":" on its own line
        text = re.sub(r'\n;\s*\n', '\n', text)                  # Remove ";" on its own line
        text = re.sub(r'^\.\s+', '', text, flags=re.MULTILINE)  # Remove ". " at start of line
        text = re.sub(r'\n\.\s+', '\n', text)                   # Remove ". " after newline
        text = re.sub(r"^'\s+", '', text, flags=re.MULTILINE)   # Remove "' " at start of line
        text = re.sub(r"\n'\s+", '\n', text)                    # Remove "' " after newline

        # Fix semicolons that should be answer choices
        text = re.sub(r';\s*\n([A-Z])', r'\nB. \1', text)        # "; 1 and 2 only" -> "B. 1 and 2 only"
        text = re.sub(r';\s+([A-Z])', r'B. \1', text)            # "; 1 and 2 only" -> "B. 1 and 2 only" (no newline)

        # Clean up spacing around answer choices
        text = re.sub(r'\s+([A-Z]\.\s)', r'\n\1', text)  # Ensure proper line breaks before A., B., C.
        text = re.sub(r'\s+(c\s)', r'\n\1', text)        # Ensure proper line breaks before lowercase c

        # Clean up multiple spaces but preserve newlines
        text = re.sub(r'[ \t]+', ' ', text)

        # Clean up multiple newlines
        text = re.sub(r'\n\s*\n', '\n', text)

        # Split into lines and clean each line
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            line = line.strip()
            # Skip lines that are just a single character (likely OCR artifacts)
            if len(line) == 1 and line in '0Oo':
                continue
            # Skip empty lines
            if not line:
                continue
            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def process_image(self, image_path: Path) -> Tuple[str, str]:
        """
        Process a single image and extract text.

        Args:
            image_path: Path to the image file

        Returns:
            Tuple of (filename, extracted_text)
        """
        try:
            logger.info("Processing: %s", image_path.name)
            img = Image.open(image_path)

            # Preprocess the image for better OCR if enabled
            if self.enable_preprocessing:
                processed_img = self.preprocess_image(img)
            else:
                processed_img = img

            # Extract text using Tesseract with custom configuration
            text = pytesseract.image_to_string(processed_img, config=self.tesseract_config).strip()

            # Clean the extracted text
            cleaned_text = self.postprocess_ocr_text(text)

            return image_path.name, cleaned_text
        except Exception as e:
            logger.error("Error processing %s: %s", image_path.name, str(e))
            return image_path.name, f"ERROR: {str(e)}"

    def process_images_parallel(self, image_paths: List[Path]) -> Dict[str, str]:
        """
        Process multiple images in parallel.

        Args:
            image_paths: List of image file paths

        Returns:
            Dictionary mapping filename to extracted text
        """
        results = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_path = {
                executor.submit(self.process_image, path): path
                for path in image_paths
            }

            for future in as_completed(future_to_path):
                filename, text = future.result()
                results[filename] = text
                logger.info("Completed: %s", filename)

        return results


def get_image_files(folder_path: Path) -> List[Path]:
    """
    Get all supported image files from the specified folder.

    Args:
        folder_path: Path to the folder containing images

    Returns:
        List of image file paths
    """
    if not folder_path.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    if not folder_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {folder_path}")

    image_files = [
        file_path for file_path in folder_path.iterdir()
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not image_files:
        logger.warning("No supported image files found in %s", folder_path)
        return []

    logger.info("Found %d image files to process", len(image_files))
    return sorted(image_files)


def display_results(results: Dict[str, str]) -> None:
    """
    Display the OCR results to console.

    Args:
        results: Dictionary mapping filename to extracted text
    """
    print("\n" + "="*80)
    print("OCR RESULTS")
    print("="*80)

    for filename, text in results.items():
        print(f"\n--- {filename} ---")
        if text.startswith("ERROR:"):
            print(f"❌ {text}")
        else:
            # Split text into lines and format properly
            lines = text.split('\n')
            for line in lines:
                if line.strip():  # Only print non-empty lines
                    print(line.strip())
        print("-" * 40)


def main():
    """
    Main function to handle command-line execution.
    """
    parser = argparse.ArgumentParser(
        description="Process images to extract text using OCR in parallel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ptac.py --source /path/to/images
  python ptac.py --source ./screenshots --workers 4
  python ptac.py --source ./test-questions --no-preprocessing
        """
    )

    parser.add_argument(
        '--source', '-s',
        type=str,
        required=True,
        help='Path to folder containing images to process'
    )

    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=None,
        help='Number of worker threads (default: CPU count)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--no-preprocessing',
        action='store_true',
        help='Disable image preprocessing (use original image for OCR)'
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Convert source path to Path object
        folder_path = Path(args.source).resolve()

        # Get image files
        image_files = get_image_files(folder_path)

        if not image_files:
            print("No image files found to process.")
            sys.exit(1)

        # Process images
        processor = ImageProcessor(
            max_workers=args.workers,
            enable_preprocessing=not args.no_preprocessing
        )
        results = processor.process_images_parallel(image_files)

        # Display results
        display_results(results)

        # Summary
        successful = sum(1 for text in results.values() if not text.startswith("ERROR:"))
        total = len(results)
        print(f"\n📊 Summary: {successful}/{total} images processed successfully")

    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error("An error occurred: %s", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
