import webbrowser

# URL of the website you want to open
url = "https://www.example.com"

try:
    # Attempt to open the URL in the default web browser
    webbrowser.open(url)
    print(f"Opening {url} in your default web browser.")
except webbrowser.Error as e:
    print(f"An error occurred: {e}")