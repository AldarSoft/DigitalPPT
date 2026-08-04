import re

from rest_framework import serializers


PHONE_PATTERN = re.compile(r"^[+]?[0-9][0-9\s().-]{5,19}$")


def validate_phone(value):
    if value and not PHONE_PATTERN.fullmatch(value.strip()):
        raise serializers.ValidationError("Enter a valid phone number.")
    return value
