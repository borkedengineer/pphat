from PIL import Image
import pytesseract
def main():
    img = Image.open('../practice-tests/test.png')
    text = pytesseract.image_to_string(img)
    print(text)

main()
