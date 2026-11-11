"""Publish a pinned archive, and purge that deployment after it is ready.

``publish`` and ``purge`` call the existing coordinators. Stage publication
does not read purge configuration, credentials, or state. Production writes
the receipt only after publication succeeds. Purge uses that receipt's
intent and the caller's explicit deployment id. Command examples, the
``CACHE_PURGE_ZONE_CREDENTIALS`` binding, and purge's Git authentication
requirement are documented in ``docs/deployment.md``.
"""

import argparse
import json
import os
import sys
import tempfile

from cache_purge import (
    PurgeError,
    decode_purge_state,
    encode_purge_state,
    load_purge_config,
    validate_api_token,
)
from deployment_content import ContentSnapshotError
from deployment_extract import ArtifactExtractionError
from deployment_polling import DeploymentPollingError
from deployment_purge import purge_ready_deployment
from deployment_readiness import digest_pinned
from deployment_release import ArchivePublicationError, publish_pinned_release
from purge_state_store import PurgeStateSnapshot, PurgeStateStoreError


ZONE_CREDENTIALS = "CACHE_PURGE_ZONE_CREDENTIALS"
_CREDENTIAL_HELP = (
    f"Production reads {ZONE_CREDENTIALS}, a JSON object mapping zone aliases "
    "to API tokens. The variable is not a command argument, and its document "
    "is not echoed."
)


class _Pairs(list):
    """JSON object pairs, retained so a repeated alias stays visible."""


# Messages these components already document as safe to show.
_SANITIZED_ERRORS = (
    ValueError,
    ArchivePublicationError,
    ArtifactExtractionError,
    ContentSnapshotError,
    PurgeError,
    PurgeStateStoreError,
    DeploymentPollingError,
)
_COMMAND_FAILED = "deployment command failed"
_RECEIPT_FAILED = "receipt could not be written"


def main(argv=None):
    """Run one deployment command and return its process status.

    ``0`` means the command finished, including a production receipt when
    publication required one. A documented validation or coordinator error
    is printed and the status is ``1``. Any other failure prints
    ``deployment command failed`` without the exception text. ``KeyboardInterrupt``
    and ``SystemExit`` propagate.
    """
    try:
        _dispatch(sys.argv[1:] if argv is None else argv)
    except _SANITIZED_ERRORS as error:
        print(error, file=sys.stderr)
        return 1
    except Exception:
        print(_COMMAND_FAILED, file=sys.stderr)
        return 1
    return 0


def _dispatch(argv):
    """Parse one command and run the matching coordinator."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "publish":
        _publish(args)
        return
    _purge(args)


def _parser():
    """Return the publish and purge commands."""
    parser = argparse.ArgumentParser(prog="deployment_cli.py")
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish", epilog=_CREDENTIAL_HELP)
    publish.add_argument("--image", required=True)
    publish.add_argument("--environment", required=True)
    publish.add_argument("--checkout", required=True)
    publish.add_argument("--remote", required=True)
    publish.add_argument("--message", required=True)
    publish.add_argument("--configuration")
    publish.add_argument("--identity")
    publish.add_argument("--state-ref")
    publish.add_argument("--state-path")
    publish.add_argument("--receipt")
    purge = commands.add_parser("purge", epilog=_CREDENTIAL_HELP)
    purge.add_argument("--configuration", required=True)
    purge.add_argument("--receipt", required=True)
    purge.add_argument("--identity", required=True)
    purge.add_argument("--image", required=True)
    purge.add_argument("--workspace", required=True)
    purge.add_argument("--remote", required=True)
    purge.add_argument("--state-ref", required=True)
    purge.add_argument("--state-path", required=True)
    purge.add_argument("--cluster", required=True)
    purge.add_argument("--service", required=True)
    purge.add_argument("--region", required=True)
    purge.add_argument("--deployment-id", required=True)
    return parser


def _publish(args):
    """Publish one archive, and write a production receipt only after success."""
    if args.environment == "stage":
        if any((
            args.configuration,
            args.identity,
            args.state_ref,
            args.state_path,
            args.receipt,
        )):
            raise ValueError("stage publication does not accept purge inputs")
        publish_pinned_release(args.image, "stage", args.checkout, args.remote, args.message)
        return
    if args.environment != "prod":
        raise ValueError("deployment environment must be stage or prod")
    _require_text(args.identity, "deployment intent identity is required")
    _require_text(args.state_ref, "state ref is required")
    _require_text(args.state_path, "state path is required")
    _require_receipt_destination(args.receipt)
    configuration = _load_configuration(args.configuration)
    credentials = _zone_credentials()
    snapshot = publish_pinned_release(
        args.image,
        "prod",
        args.checkout,
        args.remote,
        args.message,
        configuration=configuration,
        credentials=credentials,
        identity=args.identity,
        state_ref=args.state_ref,
        state_path=args.state_path,
    )
    if not isinstance(snapshot, PurgeStateSnapshot):
        raise ValueError("production receipt is required")
    _write_receipt(args.receipt, snapshot.state)


def _purge(args):
    """Purge the receipt's intent using remote state and this run's deployment id."""
    configuration = _load_configuration(args.configuration)
    credentials = _zone_credentials()
    intent = _receipt_intent(args.receipt, args.identity, args.image)
    purge_ready_deployment(
        configuration,
        credentials,
        args.workspace,
        args.remote,
        args.state_ref,
        args.state_path,
        intent,
        args.cluster,
        args.service,
        args.region,
        args.deployment_id,
    )


def _zone_credentials():
    """Return the zone-alias map from ``CACHE_PURGE_ZONE_CREDENTIALS``."""
    return _parse_zone_credentials(os.environ.get(ZONE_CREDENTIALS))


def _parse_zone_credentials(document):
    """Return zone aliases mapped to locally well-formed tokens.

    The document is not included in an error. Duplicate aliases are rejected
    rather than keeping one of the values.
    """
    if not isinstance(document, str) or document == "":
        raise ValueError("zone credentials are required")
    try:
        parsed = json.loads(document, object_pairs_hook=_Pairs)
    except (json.JSONDecodeError, RecursionError, ValueError):
        raise ValueError("malformed JSON") from None
    if not isinstance(parsed, _Pairs):
        raise ValueError("zone credentials must be an object")
    credentials = {}
    for alias, token in parsed:
        if alias in credentials:
            raise ValueError("duplicate key in zone credentials")
        validate_api_token(token)
        credentials[alias] = token
    if not credentials:
        raise ValueError("zone credentials are required")
    return credentials


def _load_configuration(path):
    """Load one explicit purge configuration, without a default file."""
    document = _read_text(path, "purge configuration is required")
    return load_purge_config(document)


def _receipt_intent(path, identity, image):
    """Return the receipt intent when it belongs to this explicit run."""
    _require_text(identity, "deployment intent identity is required")
    if not digest_pinned(image):
        raise ValueError("image must be pinned by digest")
    state = decode_purge_state(_read_text(path, "receipt is required"))
    intent = state.intent
    if intent is None:
        raise ValueError("receipt intent is required")
    if intent.identity != identity or intent.image != image:
        raise ValueError("receipt does not match this deployment")
    return intent


def _read_text(path, missing):
    """Read one caller-supplied file without echoing its contents."""
    if not isinstance(path, str) or path == "" or "\x00" in path:
        raise ValueError(missing)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeError):
        raise ValueError(missing) from None


def _require_receipt_destination(path):
    """Require a receipt path whose directory already exists."""
    _require_text(path, "receipt path is required")
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise ValueError("receipt path is required")


def _require_text(value, message):
    """Reject a missing command value before a coordinator starts."""
    if not isinstance(value, str) or value == "" or "\x00" in value:
        raise ValueError(message)


def _write_receipt(path, state):
    """Replace ``path`` with the encoded state only after the write is complete.

    A filesystem failure leaves any previous receipt in place and raises
    ``ValueError`` with a fixed message. The operating-system error is not
    included. This does not roll back a publication that already finished.
    """
    payload = encode_purge_state(state)
    directory = os.path.dirname(os.path.abspath(path))
    try:
        _install_receipt(path, directory, payload)
    except OSError:
        raise ValueError(_RECEIPT_FAILED) from None


def _install_receipt(path, directory, payload):
    """Write the receipt beside ``path`` and replace it only when complete."""
    descriptor, temporary = tempfile.mkstemp(prefix="tb-purge-receipt-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
