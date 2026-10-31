"""Failure inspection only. No automatic retries, reconnection or input replay."""
from app.automation.api import errors


def classify_failure(error: BaseException) -> dict:
    """Bounded, JSON-safe advice based on actual exception types, not message guesses.

    Transport acknowledgment/timeouts cannot establish whether input took effect.
    Every restart remains explicit, with a fresh device lease and trust approval.
    """
    rules = (
        ((errors.DeviceUnauthorized, errors.DeviceOffline, errors.DeviceDisconnected),
         'device_connection', 'Inspect Device Manager or reset the demo, verify the screen, then explicitly restart. Never replay pending input after reconnection.'),
        ((errors.CommandTimeout, errors.CommandFailed),
         'input_outcome_unknown', 'Inspect the current screen before restarting; a command may already have taken effect. No automatic retry is safe by default.'),
        ((errors.RecognitionTimeout, errors.ImageNotFound, errors.AmbiguousMatch),
         'recognition', 'Capture a fresh screen in Visual Tools; inspect the target, Region, score and appearance timing before restarting.'),
        ((errors.AssetNotFound, errors.InvalidAsset),
         'image_asset', 'Check this project\'s image library and saved target reference. Choose a textured crop inside the project.'),
        ((errors.OCRUnavailable,),
         'ocr_dependency', 'Configure a local Tesseract executable and requested language data in Settings → Recognition. No model is downloaded automatically.'),
        ((errors.OCRFailed,),
         'ocr_engine', 'Inspect the OCR error, language and search region. Test the frozen capture in Recognition Inspector.'),
        ((errors.InvalidCoordinates, errors.CrossDeviceTarget),
         'target_geometry', 'Inspect original screen coordinates, orientation and device ownership. Capture fresh targets after resolution changes.'),
        ((errors.UnsupportedCapability,),
         'unsupported', 'Check the selected backend capabilities. Simulation cannot launch Android packages.'),
    )
    for classes, category, advice in rules:
        if isinstance(error, classes):
            break
    else:
        category, advice = 'python', 'Inspect the traceback and failed source line. Edit the script and explicitly restart when ready.'
    return {'category': category, 'advice': advice, 'automatic_retry': False}
