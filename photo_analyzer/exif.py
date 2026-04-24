"""EXIF metadata extraction from images."""

from pathlib import Path

from PIL import ExifTags, Image

from .models import ExifInfo


def _convert_gps_to_deg(value: tuple) -> float | None:
    """Convert GPS coordinates from EXIF format to decimal degrees.

    Handles two formats:
    1. Tuple of (numerator, denominator) pairs: ((32, 1), (2, 1), (21.27, 1))
    2. Tuple of floats/IFDRational: (32.0, 2.0, 21.27)
    """
    try:
        d, m, s = value

        def to_float(v):
            if isinstance(v, (int, float)):
                return float(v)
            # IFDRational has numerator/denominator attributes
            if hasattr(v, "numerator") and hasattr(v, "denominator"):
                return float(v.numerator) / float(v.denominator)
            # Tuple format (numerator, denominator)
            if isinstance(v, (tuple, list)) and len(v) == 2:
                return float(v[0]) / float(v[1])
            return float(v)

        return to_float(d) + to_float(m) / 60.0 + to_float(s) / 3600.0
    except Exception:
        return None


def read_exif(path: Path) -> ExifInfo:
    """Extract EXIF metadata from an image file."""
    info = ExifInfo()

    try:
        img = Image.open(path)
    except Exception:
        return info

    # Get image dimensions
    try:
        info.width, info.height = img.size
    except Exception:
        pass

    # Extract EXIF data
    try:
        exif_obj = img.getexif()
    except Exception:
        return info

    if not exif_obj:
        return info

    # Basic EXIF fields
    info.datetime = exif_obj.get(ExifTags.Base.DateTimeOriginal.value) or exif_obj.get(ExifTags.Base.DateTime.value)
    info.model = exif_obj.get(ExifTags.Base.Model.value)

    # GPS coordinates
    try:
        gps_ifd = exif_obj.get_ifd(ExifTags.IFD.GPSInfo)
        if gps_ifd:
            lat_ref = gps_ifd.get(ExifTags.GPS.GPSLatitudeRef)
            lat_raw = gps_ifd.get(ExifTags.GPS.GPSLatitude)
            lon_ref = gps_ifd.get(ExifTags.GPS.GPSLongitudeRef)
            lon_raw = gps_ifd.get(ExifTags.GPS.GPSLongitude)

            if lat_raw and lat_ref:
                info.gps_lat = _convert_gps_to_deg(lat_raw)
                if info.gps_lat is not None and str(lat_ref) in ["S", "s"]:
                    info.gps_lat = -info.gps_lat

            if lon_raw and lon_ref:
                info.gps_lon = _convert_gps_to_deg(lon_raw)
                if info.gps_lon is not None and str(lon_ref) in ["W", "w"]:
                    info.gps_lon = -info.gps_lon
    except Exception:
        pass

    return info
