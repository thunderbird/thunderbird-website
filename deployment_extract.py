"""Copy the archived site out of a pinned deployment image."""

import re
import shutil
import subprocess
import tempfile
import uuid
from contextlib import contextmanager

from deployment_readiness import digest_pinned


# docker create may pull the pinned image into the local daemon.
CREATE_TIMEOUT = 300
# The copy is the generated site tree, not a full image export.
COPY_TIMEOUT = 120
# Each docker lookup or removal waits this long. Directory removal does not.
CLEANUP_TIMEOUT = 30

# The archived website tree. Server configuration outside it is not copied.
_ARCHIVE = "/var/www/html/start/."
_LABEL = "deployment-artifact"
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}")


class ArtifactExtractionError(Exception):
    """The pinned image could not be extracted into a complete artifact."""


@contextmanager
def extract_pinned_content(image):
    """Yield the archived site copied from a stopped container of ``image``.

    ``image`` is the digest-pinned reference from the build step. A mutable
    tag is rejected before Docker starts. ``docker create`` does not run the
    entrypoint. The yielded directory is the contents of
    ``/var/www/html/start`` only.

    A unique name and label are chosen before create. Cleanup removes the
    printed container id. When create does not return an id, including
    timeout, a bad result, or an interruption, it removes containers that
    carry this call's label. It then removes this call's directory. The
    daemon may be down, the process may be killed, or the container may
    never have been allocated. Removal is best-effort and is not a
    transactional rollback.

    Docker waits are 300 seconds for create, 120 for copy, and 30 for each
    lookup or removal. Directory removal is synchronous and has no timeout.
    Diagnostics stay on the process error stream. Errors and notes omit
    credentials and command arguments. An exception from this operation,
    including cancellation or exit, is re-raised with its traceback.
    Cleanup failure after success is raised. After an earlier failure it is
    noted and does not replace that failure.
    """
    if not digest_pinned(image):
        raise ValueError("image must be pinned by digest")
    directory = tempfile.mkdtemp(prefix="deployment-artifact-")
    name, token = _ownership()
    container_id = None
    primary = None
    try:
        container_id = _create(image, name, token)
        _copy(container_id, directory)
        yield directory
    except BaseException as exc:
        primary = exc
        raise
    finally:
        notes = _cleanup(container_id, token, directory)
        if primary is None:
            if notes:
                error = ArtifactExtractionError("artifact cleanup failed")
                _note(error, notes)
                raise error
        else:
            _note(primary, notes)


def _ownership():
    """Return a container name and label value that no other call shares."""
    token = uuid.uuid4().hex
    return f"{_LABEL}-{token}", token


def _create(image, name, token):
    """Create a stopped container and return the id it printed."""
    try:
        completed = _run(
            ["docker", "create", "--name", name, "--label", f"{_LABEL}={token}", image],
            CREATE_TIMEOUT,
            stdout=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        raise ArtifactExtractionError("container creation timed out") from None
    except OSError:
        raise ArtifactExtractionError("container creation failed") from None
    if completed.returncode != 0:
        raise ArtifactExtractionError("container creation failed")
    return _identity(completed.stdout)


def _copy(container_id, directory):
    """Copy the archived site, or raise before the directory is published."""
    source = f"{container_id}:{_ARCHIVE}"
    try:
        completed = _run(["docker", "cp", source, directory], COPY_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ArtifactExtractionError("artifact copy timed out") from None
    except OSError:
        raise ArtifactExtractionError("artifact copy failed") from None
    if completed.returncode != 0:
        raise ArtifactExtractionError("artifact copy failed")


def _cleanup(container_id, token, directory):
    """Remove owned containers, then the directory. Return sanitized notes."""
    notes = []
    if container_id is not None:
        notes.extend(_remove_ids([container_id]))
    else:
        notes.extend(_remove_labeled(token))
    try:
        shutil.rmtree(directory)
    except OSError:
        notes.append("artifact directory cleanup failed")
    return notes


def _remove_labeled(token):
    """Remove containers that carry this call's label and nothing else."""
    try:
        ids = _lookup(token)
    except ArtifactExtractionError as exc:
        return [str(exc)]
    return _remove_ids(ids)


def _lookup(token):
    """Return full ids for this call's label."""
    try:
        completed = _run(
            ["docker", "ps", "-aq", "--no-trunc", "--filter", f"label={_LABEL}={token}"],
            CLEANUP_TIMEOUT,
            stdout=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        raise ArtifactExtractionError("container removal timed out") from None
    except OSError:
        raise ArtifactExtractionError("container removal failed") from None
    if completed.returncode != 0:
        raise ArtifactExtractionError("container removal failed")
    return _ids(completed.stdout)


def _remove_ids(ids):
    """Remove known ids. Keep going after one removal fails."""
    notes = []
    seen = set()
    for container_id in ids:
        if container_id in seen:
            continue
        seen.add(container_id)
        try:
            _remove(container_id)
        except ArtifactExtractionError as exc:
            notes.append(str(exc))
    return notes


def _remove(container_id):
    """Remove one container id owned by this extraction."""
    try:
        completed = _run(["docker", "rm", "-f", container_id], CLEANUP_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ArtifactExtractionError("container removal timed out") from None
    except OSError:
        raise ArtifactExtractionError("container removal failed") from None
    if completed.returncode != 0:
        raise ArtifactExtractionError("container removal failed")


def _run(args, timeout, stdout=None):
    """Wait for one Docker command. The wait is the configured limit."""
    return subprocess.run(
        args,
        stdout=stdout,
        stderr=None,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )


def _ids(stdout):
    """Return full container ids, or fail rather than remove an unclear value."""
    if not isinstance(stdout, bytes):
        raise ArtifactExtractionError("container removal failed")
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise ArtifactExtractionError("container removal failed") from None
    ids = []
    for line in text.splitlines():
        if _CONTAINER_ID.fullmatch(line) is None:
            raise ArtifactExtractionError("container removal failed")
        ids.append(line)
    return ids


def _identity(stdout):
    """Return the one container id printed by docker create."""
    if not isinstance(stdout, bytes):
        raise ArtifactExtractionError("container creation failed")
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise ArtifactExtractionError("container creation failed") from None
    if text.count("\n") != 1 or not text.endswith("\n"):
        raise ArtifactExtractionError("container creation failed")
    container_id = text[:-1]
    if _CONTAINER_ID.fullmatch(container_id) is None:
        raise ArtifactExtractionError("container creation failed")
    return container_id


def _note(error, notes):
    """Attach sanitized cleanup notes without changing the error's traceback."""
    for note in notes:
        error.add_note(note)
