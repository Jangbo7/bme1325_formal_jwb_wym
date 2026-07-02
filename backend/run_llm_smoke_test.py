import argparse
import json
import os
import socket
import ssl
import sys
import time
from urllib import error as urlerror
from urllib import request as urlrequest

from app.config import get_settings


def mask_secret(value: str) -> str:
    if not value:
        return "(missing)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def extract_text_from_response(data):
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, list):
        parts = [extract_text_from_response(item) for item in data]
        return " ".join([item for item in parts if item]).strip()
    if not isinstance(data, dict):
        return ""

    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_items = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_items.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    text_items.append(item)
            return " ".join([item for item in text_items if item]).strip()

    message = data.get("message")
    if isinstance(message, str):
        return message.strip()
    return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a direct smoke test against the configured LLM provider.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Request timeout in seconds. Default: 20",
    )
    parser.add_argument(
        "--message",
        default="Reply with exactly: LLM_SMOKE_OK",
        help="Probe message sent to the LLM.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification for diagnosis only.",
    )
    return parser.parse_args()


def build_request_body(model: str, message: str) -> dict:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a connectivity smoke test assistant. Reply briefly.",
            },
            {
                "role": "user",
                "content": message,
            },
        ],
        "temperature": 0,
        "stream": False,
    }


def main() -> int:
    args = parse_args()
    settings = get_settings()
    provider = settings.get("active_llm_provider", "")
    endpoint = settings.get("llm_endpoint", "")
    model = settings.get("llm_model", "")
    api_key = settings.get("llm_api_key", "")

    print("=== LLM Smoke Test ===")
    print(f"python   : {sys.version.split()[0]}")
    print(f"openssl  : {ssl.OPENSSL_VERSION}")
    print(f"provider : {provider or '(missing)'}")
    print(f"endpoint : {endpoint or '(missing)'}")
    print(f"model    : {model or '(missing)'}")
    print(f"api_key  : {mask_secret(api_key)}")
    print(f"https_proxy : {mask_secret(os.getenv('HTTPS_PROXY', '').strip())}")
    print(f"http_proxy  : {mask_secret(os.getenv('HTTP_PROXY', '').strip())}")
    print(f"all_proxy   : {mask_secret(os.getenv('ALL_PROXY', '').strip())}")
    print(f"ssl_cert_file      : {os.getenv('SSL_CERT_FILE', '').strip() or '(default)'}")
    print(f"requests_ca_bundle : {os.getenv('REQUESTS_CA_BUNDLE', '').strip() or '(default)'}")
    print(f"insecure_tls       : {args.insecure}")

    if not endpoint or not model or not api_key:
        print("")
        print("FAIL: missing required LLM config.")
        print("Check backend/.env or system environment variables first.")
        return 2

    body = build_request_body(model, args.message)
    payload = json.dumps(body).encode("utf-8")
    request_obj = urlrequest.Request(
        endpoint,
        data=payload,
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    started_at = time.time()
    try:
        ssl_context = None
        if args.insecure:
            ssl_context = ssl._create_unverified_context()
        with urlrequest.urlopen(request_obj, timeout=args.timeout, context=ssl_context) as response:
            status_code = getattr(response, "status", None) or response.getcode()
            raw_text = response.read().decode("utf-8", errors="replace")
    except urlerror.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print("")
        print(f"FAIL: upstream returned HTTP {exc.code}.")
        if exc.code in {401, 403}:
            print("Likely cause: invalid API key, expired key, or provider-side permission denial.")
        elif exc.code == 429:
            print("Likely cause: rate limit, quota exhaustion, or account balance issue.")
        else:
            print("Likely cause: provider-side rejection or incompatible request payload.")
        if error_body.strip():
            print("upstream body:")
            print(error_body[:2000])
        return 3
    except urlerror.URLError as exc:
        reason = exc.reason
        print("")
        print("FAIL: network error while reaching the upstream LLM endpoint.")
        print(f"reason: {reason}")
        print("Likely cause: DNS, proxy, firewall, VPN, or outbound network restriction.")
        return 4
    except ssl.SSLError as exc:
        print("")
        print(f"FAIL: TLS handshake failed: {exc}")
        print("Likely cause: local proxy / SSL inspection, broken certificate chain, local system time drift, or incompatible Python/OpenSSL environment.")
        print("Try again with --insecure. If it still fails, the problem is below certificate verification and is usually network interception or TLS stack mismatch.")
        return 4
    except TimeoutError:
        print("")
        print("FAIL: request timed out.")
        print("Likely cause: network instability or upstream response too slow.")
        return 5
    except socket.timeout:
        print("")
        print("FAIL: socket timeout.")
        print("Likely cause: network instability or upstream response too slow.")
        return 5
    except Exception as exc:
        print("")
        print(f"FAIL: unexpected request error: {exc.__class__.__name__}: {exc}")
        return 6

    elapsed_ms = int((time.time() - started_at) * 1000)
    print("")
    print(f"HTTP status : {status_code}")
    print(f"latency_ms  : {elapsed_ms}")

    try:
        response_data = json.loads(raw_text)
    except json.JSONDecodeError:
        print("FAIL: upstream response was not valid JSON.")
        print("raw response:")
        print(raw_text[:2000])
        return 7

    extracted_text = extract_text_from_response(response_data)
    if not extracted_text:
        print("FAIL: upstream returned JSON but no readable assistant text was extracted.")
        print("response json:")
        print(json.dumps(response_data, ensure_ascii=False, indent=2)[:4000])
        return 8

    print("PASS: upstream LLM call succeeded.")
    print("assistant text:")
    print(extracted_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
