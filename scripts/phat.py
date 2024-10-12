import webbrowser

url = "https://www.example.com"

try:
    webbrowser.open(url)
    print(f"Opening {url} in your default web browser.")
except webbrowser.Error as e:
    print(f"An error occurred: {e}")