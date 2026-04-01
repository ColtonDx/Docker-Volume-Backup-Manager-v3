"""
Backup Buddy – application entry point.

Replaces the bare `uvicorn` CLI command so that we can:
  1. Auto-generate a self-signed TLS certificate on first start (SSL_ENABLED=true).
  2. Launch uvicorn programmatically with or without TLS.

Run from WORKDIR /app:
    python start.py
"""

import ipaddress
import logging
import os
import socket
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


def _generate_self_signed_cert(cert_path: Path, key_path: Path) -> None:
    """
    Generate a self-signed RSA-2048 certificate valid for 10 years.

    Subject Alternative Names:
      - DNS: localhost
      - DNS: <container hostname>  (if different from localhost)
      - IP:  127.0.0.1
      - IP:  ::1

    The cert is marked as a CA (BasicConstraints ca=True) so it can be imported
    as a trusted root in browsers / OS trust stores when needed.
    """
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    log.info("Generating self-signed TLS certificate …")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    hostname = socket.gethostname()
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "backup-buddy")]
    )

    san_entries: list = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        x509.IPAddress(ipaddress.IPv6Address("::1")),
    ]
    if hostname and hostname != "localhost":
        san_entries.append(x509.DNSName(hostname))

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))  # 10 years
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                key_cert_sign=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    cert_path.parent.mkdir(parents=True, exist_ok=True)

    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)  # private key: owner-read only

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cert_path.chmod(0o644)

    log.info("Certificate : %s", cert_path)
    log.info("Private key : %s  (mode 0600)", key_path)


def main() -> None:
    from app.config import settings

    host = os.getenv("UVICORN_HOST", "0.0.0.0")
    port = int(os.getenv("UVICORN_PORT", "8000"))
    log_level = os.getenv("UVICORN_LOG_LEVEL", "info")

    uvicorn_kwargs: dict = {
        "host": host,
        "port": port,
        "log_level": log_level,
    }

    if settings.SSL_ENABLED:
        cert_path = settings.ssl_cert_path
        key_path = settings.ssl_key_path

        if not cert_path.exists() or not key_path.exists():
            _generate_self_signed_cert(cert_path, key_path)
        else:
            log.info("Using existing TLS certificate: %s", cert_path)

        uvicorn_kwargs["ssl_certfile"] = str(cert_path)
        uvicorn_kwargs["ssl_keyfile"] = str(key_path)
        log.info("TLS enabled — listening on https://%s:%d", host, port)
    else:
        log.warning(
            "SSL_ENABLED=false — running over plain HTTP on http://%s:%d. "
            "Set SSL_ENABLED=true (default) for encrypted traffic.",
            host,
            port,
        )

    import uvicorn
    uvicorn.run("app.main:app", **uvicorn_kwargs)


if __name__ == "__main__":
    main()
