"""Ordinary worker script: configure image/OCR targets for your selected screen."""
# Short functions and device methods share the run's assigned context.
pixel = getPixel(70, 490)
print('Sample RGB:', pixel)
pixels = device.findColor(pixel, tolerance=5, region=Region(60, 480, 240, 64))
print('Matching pixels:', pixels[:5])
try:
    words = recognizeText(region=Region(60, 480, 240, 64), confidence=50)
    print(words.text)
    for word in words.words:
        print(word.text, word.confidence, word.region)
except OCRUnavailable as error:
    print('Optional OCR configuration needed:', error)
# These are demo-sized coordinates. Recapture/adjust for a real phone.
# matches = findAll(Pattern('start.png').preprocess('grayscale').similar(.9))
