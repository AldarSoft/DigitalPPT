import json
import logging
import re
from datetime import datetime, timezone


_SENSITIVE_VALUE = re.compile(
    r"(?i)(authorization|password|token|secret|cookie|account_number|iban)(\s*[=:]\s*)([^\s,;]+)"
)


def redact(value):
    return _SENSITIVE_VALUE.sub(r"\1\2[REDACTED]", str(value))


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=True)
