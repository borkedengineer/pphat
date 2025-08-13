#!/usr/bin/env python3
"""
Image to Text Converter (PTAC)
Processes images in parallel to extract text using OCR.
"""
import argparse
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Dict
import logging

try:
    from PIL import Image
except ImportError:
    print("Error: PIL (Pillow) is not installed. Please run: pip install -r requirements.txt")
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("Error: pytesseract is not installed. Please run: pip install -r requirements.txt")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Supported image extensions
SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}


class ImageProcessor:
    """Handles image processing and OCR operations."""

    def __init__(self, max_workers: int = None):
        """
        Initialize the image processor.

        Args:
            max_workers: Maximum number of worker threads. Defaults to CPU count.
        """
        self.max_workers = max_workers

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
            text = pytesseract.image_to_string(img).strip()
            return image_path.name, text
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
            print(text)
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
  python ptac.py --folder-path /path/to/images
  python ptac.py --folder-path ./screenshots --workers 4
        """
    )

    parser.add_argument(
        '--folder-path', '-f',
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

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Convert folder path to Path object
        folder_path = Path(args.folder_path).resolve()

        # Get image files
        image_files = get_image_files(folder_path)

        if not image_files:
            print("No image files found to process.")
            sys.exit(1)

        # Process images
        processor = ImageProcessor(max_workers=args.workers)
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
