#!/usr/bin/env python3
"""
Image to Text Converter (PTAC)
Processes images in parallel to extract text using OCR.
"""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from pathlib import Path
import re
import sys
from typing import Dict, List, Tuple, Optional

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

        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)

        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(1.1)

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
        # Remove OCR noise
        # Patterns like "CD)", "Cc)", "0)", "O)", "A. Cc)", ". Cc)", etc.
        text = re.sub(r'[CDOo0]+\s*\)', '', text)
        text = re.sub(r'0\s+0\s*:', '', text)
        text = re.sub(r'0\s+0\s*', '', text)
        text = re.sub(r'[A-Z]\.\s*Cc\)', '', text)                              # Remove "A. Cc)", "B. Cc)", etc.
        text = re.sub(r'\.\s*Cc\)', '', text)                                   # Remove ". Cc)"
        text = re.sub(r'c\.\s*Cc\)', '', text)                                  # Remove "c. Cc)" (lowercase)

        # Fix specific OCR errors
        text = re.sub(r'Cc\s+([A-Z])', r'C. \1', text)                          # "Cc Damage" -> "C. Damage"
        text = re.sub(r':\s*([A-Z])', r'A. \1', text)                           # ": A full stall" -> "A. A full stall"

        # Fix lowercase c that should be C.
        text = re.sub(r'^c\s+', 'C. ', text, flags=re.MULTILINE)                # "c Full fuel" -> "C. Full fuel"
        text = re.sub(r'\nc\s+', '\nC. ', text)                                 # "c Full fuel" -> "C. Full fuel" on new line

        # Remove standalone C. or c that appear without content
        text = re.sub(r'^C\.\s*$', '', text, flags=re.MULTILINE)                # Remove standalone "C."
        text = re.sub(r'^c\s*$', '', text, flags=re.MULTILINE)                  # Remove standalone "c"
        text = re.sub(r'\nC\.\s*\n', '\n', text)                                # Remove "C." on its own line
        text = re.sub(r'\nc\s*\n', '\n', text)                                  # Remove "c" on its own line

        # Remove answer choice prefixes (A., B., C., Cc., etc.) - we'll enumerate later
        text = re.sub(r'^[A-Z]\.\s+', '', text, flags=re.MULTILINE)             # Remove "A. ", "B. ", "C. " at start of line
        text = re.sub(r'\n[A-Z]\.\s+', '\n', text)                              # Remove "A. ", "B. ", "C. " after newline
        text = re.sub(r'^Cc\.\s+', '', text, flags=re.MULTILINE)                # Remove "Cc. " at start of line
        text = re.sub(r'\nCc\.\s+', '\n', text)                                 # Remove "Cc. " after newline

        # Remove standalone colons, semicolons, periods, and quotes at start of lines (OCR artifacts)
        text = re.sub(r'^:\s*$', '', text, flags=re.MULTILINE)                  # Remove standalone ":"
        text = re.sub(r'^;\s*$', '', text, flags=re.MULTILINE)                  # Remove standalone ";"
        text = re.sub(r'\n:\s*\n', '\n', text)                                  # Remove ":" on its own line
        text = re.sub(r'\n;\s*\n', '\n', text)                                  # Remove ";" on its own line
        text = re.sub(r'^\.\s+', '', text, flags=re.MULTILINE)                  # Remove ". " at start of line
        text = re.sub(r'\n\.\s+', '\n', text)                                   # Remove ". " after newline
        text = re.sub(r"^'\s+", '', text, flags=re.MULTILINE)                   # Remove "' " at start of line
        text = re.sub(r"\n'\s+", '\n', text)                                    # Remove "' " after newline

        # Fix semicolons that should be answer choices
        text = re.sub(r';\s*\n([A-Z])', r'\nB. \1', text)                       # "; 1 and 2 only" -> "B. 1 and 2 only"
        text = re.sub(r';\s+([A-Z])', r'B. \1', text)                           # "; 1 and 2 only" -> "B. 1 and 2 only" (no newline)

        # Clean up spacing around answer choices
        text = re.sub(r'\s+([A-Z]\.\s)', r'\n\1', text)                         # Ensure proper line breaks before A., B., C.
        text = re.sub(r'\s+(c\s)', r'\n\1', text)                               # Ensure proper line breaks before lowercase c

        # Clean up multiple spaces but preserve newlines
        text = re.sub(r'[ \t]+', ' ', text)

        # Clean up multiple newlines
        text = re.sub(r'\n\s*\n', '\n', text)

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

    def process_image(self, image_path: Path, base_paths: List[Path] = None) -> Tuple[str, str]:
        """
        Process a single image and extract text.

        Args:
            image_path: Path to the image file
            base_paths: List of base paths to compute relative path from

        Returns:
            Tuple of (display_key, extracted_text) where display_key includes folder info
        """
        try:
            logger.info("Processing: %s", image_path.name)
            img = Image.open(image_path)

            if self.enable_preprocessing:
                processed_img = self.preprocess_image(img)
            else:
                processed_img = img

            text = pytesseract.image_to_string(processed_img, config=self.tesseract_config).strip()

            cleaned_text = self.postprocess_ocr_text(text)

            if base_paths and len(base_paths) > 1:
                for base_path in base_paths:
                    try:
                        relative_path = image_path.relative_to(base_path)
                        if relative_path.parent == Path('.'):
                            display_key = f"{base_path.name}/{relative_path.name}"
                        else:
                            display_key = f"{base_path.name}/{relative_path}"
                        break
                    except ValueError:
                        continue
                else:
                    display_key = str(image_path)
            else:
                display_key = image_path.name

            return display_key, cleaned_text
        except Exception as e:
            logger.error("Error processing %s: %s", image_path.name, str(e))
            display_key = image_path.name if not base_paths else str(image_path)
            return display_key, f"ERROR: {str(e)}"

    def process_images_parallel(self, image_paths: List[Path], base_paths: List[Path] = None) -> Dict[str, str]:
        """
        Process multiple images in parallel.

        Args:
            image_paths: List of image file paths
            base_paths: List of base paths to compute relative paths from

        Returns:
            Dictionary mapping display key (with folder info) to extracted text
        """
        results = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_path = {
                executor.submit(self.process_image, path, base_paths): path
                for path in image_paths
            }

            for future in as_completed(future_to_path):
                display_key, text = future.result()
                results[display_key] = text
                logger.info("Completed: %s", display_key)

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

    logger.info("Found %d image files in %s", len(image_files), folder_path)
    return sorted(image_files)


def get_image_files_from_multiple_folders(folder_paths: List[Path]) -> List[Path]:
    """
    Get all supported image files from multiple folders.

    Args:
        folder_paths: List of paths to folders containing images

    Returns:
        List of image file paths from all folders
    """
    all_image_files = []
    for folder_path in folder_paths:
        try:
            image_files = get_image_files(folder_path)
            all_image_files.extend(image_files)
        except (FileNotFoundError, NotADirectoryError) as e:
            logger.warning("Skipping %s: %s", folder_path, str(e))
            continue

    if all_image_files:
        logger.info("Total: %d image files found across %d folder(s)",
                   len(all_image_files), len(folder_paths))
    return sorted(all_image_files)


def display_results(results: Dict[str, str]) -> None:
    """
    Display the OCR results to console.

    Args:
        results: Dictionary mapping display key (with folder info) to extracted text
    """
    print("\n" + "="*80)
    print("OCR RESULTS")
    print("="*80)

    for display_key, text in sorted(results.items()):
        print(f"\n--- {display_key} ---")
        if text.startswith("ERROR:"):
            print(f"❌ {text}")
        else:
            lines = text.split('\n')
            for line in lines:
                if line.strip():
                    print(line.strip())
        print("-" * 40)


def parse_answer_key(answer_key_path: Path) -> Dict[int, Tuple[str, str]]:
    """
    Parse an answer key file and extract question number and answer text.

    Args:
        answer_key_path: Path to the answer-key.md file

    Returns:
        Dictionary mapping question number to (answer_letter, answer_text) tuple.
        answer_letter will be an empty string since answer keys now only contain text.
    """
    answers = {}
    if not answer_key_path.exists():
        logger.warning("Answer key not found: %s", answer_key_path)
        return answers

    try:
        with open(answer_key_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                answer_text = line
                answers[line_num] = ('', answer_text)
    except Exception as e:
        logger.error("Error reading answer key %s: %s", answer_key_path, str(e))

    return answers


def get_question_images(folder_path: Path) -> Dict[int, Path]:
    """
    Get question image files from a folder, sorted by question number.

    Args:
        folder_path: Path to the folder containing question images

    Returns:
        Dictionary mapping question number to image path
    """
    question_images = {}
    pattern = re.compile(r'^q(\d+)\.(png|jpg|jpeg)$', re.IGNORECASE)

    for file_path in folder_path.iterdir():
        if file_path.is_file():
            match = pattern.match(file_path.name)
            if match:
                question_num = int(match.group(1))
                question_images[question_num] = file_path

    return question_images


def export_to_csv(folder_path: Path, questions: Dict[int, str], answers: Dict[int, Tuple[str, str]], 
                   output_path: Optional[Path] = None) -> Path:
    """
    Export questions and answers to a CSV file.

    Args:
        folder_path: Path to the folder containing the questions
        questions: Dictionary mapping question number to question text
        answers: Dictionary mapping question number to (answer_letter, answer_text) tuple
        output_path: Optional path for the CSV file. If None, uses folder_path/questions.csv

    Returns:
        Path to the created CSV file
    """
    if output_path is None:
        output_path = folder_path / "questions.csv"

    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Question Number', 'Question', 'Answer Text'])

        all_question_nums = sorted(set(questions.keys()) | set(answers.keys()))

        for q_num in all_question_nums:
            question_text = questions.get(q_num, '').replace('\n', ' ').strip()
            if q_num in answers:
                _, answer_text = answers[q_num]
            else:
                answer_text = ''
            writer.writerow([q_num, question_text, answer_text])

    logger.info("Exported CSV to: %s", output_path)
    return output_path


def process_folder_to_csv(folder_path: Path, processor: ImageProcessor) -> Optional[Path]:
    """
    Process a folder containing question images and answer key, then export to CSV.

    Args:
        folder_path: Path to the folder to process
        processor: ImageProcessor instance for OCR

    Returns:
        Path to the created CSV file, or None if processing failed
    """
    answer_key_path = folder_path / "answer-key.md"
    if not answer_key_path.exists():
        logger.warning("No answer-key.md found in %s, skipping", folder_path)
        return None

    answers = parse_answer_key(answer_key_path)
    logger.info("Parsed %d answers from %s", len(answers), answer_key_path)

    question_images = get_question_images(folder_path)
    if not question_images:
        logger.warning("No question images found in %s", folder_path)
        return None

    logger.info("Found %d question images in %s", len(question_images), folder_path)

    image_paths = list(question_images.values())
    ocr_results = processor.process_images_parallel(image_paths, [folder_path])

    questions = {}
    for q_num, img_path in question_images.items():
        img_name = img_path.name
        question_text = ''

        # Try multiple ways to find the OCR result
        # 1. Try by filename only
        if img_name in ocr_results:
            question_text = ocr_results[img_name]
        # 2. Try with folder prefix
        elif f"{folder_path.name}/{img_name}" in ocr_results:
            question_text = ocr_results[f"{folder_path.name}/{img_name}"]
        # 3. Try by matching any key that ends with the filename
        else:
            for key, text in ocr_results.items():
                if key.endswith(img_name) or key == str(img_path):
                    question_text = text
                    break

        # If still not found or error, use empty string
        if question_text.startswith("ERROR:"):
            question_text = ''

        questions[q_num] = question_text

    csv_path = export_to_csv(folder_path, questions, answers)
    return csv_path


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
  python ptac.py --source ./folder1 ./folder2 ./folder3
  python ptac.py -s practice-tests/2025-10-11 practice-tests/2025-11-02
  python ptac.py --export-csv --source practice-tests/2025-10-11 practice-tests/2025-11-11
        """
    )

    parser.add_argument(
        '--source', '-s',
        type=str,
        nargs='+',
        required=True,
        help='Path(s) to folder(s) containing images to process (can specify multiple)'
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

    parser.add_argument(
        '--export-csv',
        action='store_true',
        help='Export questions and answers to CSV files (one per folder with answer-key.md)'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        folder_paths = [Path(source).resolve() for source in args.source]

        processor = ImageProcessor(
            max_workers=args.workers,
            enable_preprocessing=not args.no_preprocessing
        )

        if args.export_csv:
            csv_files = []
            for folder_path in folder_paths:
                if not folder_path.exists() or not folder_path.is_dir():
                    logger.warning("Skipping invalid folder: %s", folder_path)
                    continue
                csv_path = process_folder_to_csv(folder_path, processor)
                if csv_path:
                    csv_files.append(csv_path)

            if csv_files:
                print(f"\n✅ Successfully exported {len(csv_files)} CSV file(s):")
                for csv_path in csv_files:
                    print(f"   - {csv_path}")
            else:
                print("No CSV files were created. Make sure folders contain answer-key.md files.")
        else:
            image_files = get_image_files_from_multiple_folders(folder_paths)

            if not image_files:
                print("No image files found to process.")
                sys.exit(1)

            results = processor.process_images_parallel(image_files, folder_paths)
            display_results(results)

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
