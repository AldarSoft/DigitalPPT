"""Run after deployment to verify health and minimum response security headers."""

import argparse
import sys

import requests


REQUIRED_HEADERS = {
    "content-security-policy",
    "permissions-policy",
    "x-content-type-options",
    "x-frame-options",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="Deployed HTTPS origin, for example https://shop.example.com")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if not base_url.startswith("https://"):
        raise SystemExit("The deployed smoke test requires an HTTPS URL.")

    response = requests.get(f"{base_url}/health/", timeout=15)
    response.raise_for_status()
    if response.json().get("status") != "ok":
        raise SystemExit("Health endpoint did not report ok.")

    missing = sorted(REQUIRED_HEADERS - {key.lower() for key in response.headers})
    if missing:
        raise SystemExit(f"Missing security headers: {', '.join(missing)}")
    print("Deployment smoke test passed.")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        print(f"Deployment smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
