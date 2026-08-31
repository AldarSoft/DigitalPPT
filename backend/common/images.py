from io import BytesIO
import warnings

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError


SAFE_IMAGE_FORMATS = {"JPEG": ("JPEG", ".jpg"), "PNG": ("PNG", ".png"), "WEBP": ("WEBP", ".webp")}


def sanitize_uploaded_image(uploaded_file):
    """Decode and re-encode an uploaded image, stripping metadata and hidden payloads."""
    if uploaded_file.size > settings.MAX_IMAGE_UPLOAD_BYTES:
        raise ValidationError(f"Image must be {settings.MAX_IMAGE_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.")

    raw = uploaded_file.read()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS
            with Image.open(BytesIO(raw)) as probe:
                image_format = (probe.format or "").upper()
                if image_format not in SAFE_IMAGE_FORMATS:
                    raise ValidationError("Only WEBP, JPEG, and PNG images are allowed.")
                if getattr(probe, "is_animated", False):
                    raise ValidationError("Animated images are not allowed.")
                probe.verify()

            with Image.open(BytesIO(raw)) as decoded:
                decoded.load()
                image = ImageOps.exif_transpose(decoded)
                output_format, extension = SAFE_IMAGE_FORMATS[image_format]
                if output_format == "JPEG":
                    image = image.convert("RGB")
                elif image.mode not in {"RGB", "RGBA", "L", "LA"}:
                    image = image.convert("RGBA" if "transparency" in image.info else "RGB")

                output = BytesIO()
                save_options = {"optimize": True}
                if output_format in {"JPEG", "WEBP"}:
                    save_options["quality"] = 88
                image.save(output, format=output_format, **save_options)
    except ValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("The uploaded file is not a valid, safe image.") from exc

    return ContentFile(output.getvalue()), extension
