"""Publish one pinned image's archived site before rollout."""

import os
import shutil
import signal
import stat
import subprocess
import tempfile

from deployment_extract import extract_pinned_content
from deployment_purge import prepare_deployment_intent, require_zone_credentials
from deployment_readiness import digest_pinned


_BOT = "Thundernest Bot"
_BRANCH = {"stage": "master", "prod": "prod"}
_KEEP = {".git", "README.md"}
# Inherited variables that would redirect Git away from the supplied checkout.
_REDIRECTED = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
)
_AUTH_KEYS = (
    "GIT_ASKPASS",
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
)
# Branch inspection is one local rev-parse.
_INSPECT_TIMEOUT = 30
# Adding and committing the site tree is local.
_ARCHIVE_TIMEOUT = 120
# Push may upload the archive.
_PUSH_TIMEOUT = 300
# Best-effort reap after a Git command is interrupted or times out.
_CLEANUP_TIMEOUT = 1


class ArchivePublicationError(Exception):
    """The extracted site could not be published to the builds repository."""


def publish_pinned_release(
    image,
    deploy_env,
    checkout,
    remote,
    message,
    *,
    configuration=None,
    credentials=None,
    identity=None,
    state_ref=None,
    state_path=None,
):
    """Publish the archived site from one digest-pinned image.

    ``deploy_env`` is ``stage`` or ``prod``. ``checkout`` is that
    environment's builds clone and, on production, the purge-state
    workspace. ``remote`` has no embedded credential. ``message`` follows
    ``Website rebuild triggered by``.

    Production requires the caller's configuration, zone credentials,
    identity, and state location. ``require_zone_credentials`` runs before
    Docker. The caller loads configuration and tokens. No example file is
    opened. Stage does not read purge configuration, tokens, or state.

    One extraction supplies the artifact. Production persists its intent
    before the checkout changes. The same bytes then replace the archive.
    ``.git`` is kept, and an artifact that contains it is rejected. Links
    are copied as links. File bytes and executable permission are preserved.
    An unchanged tree creates no commit. The author is Thundernest Bot.
    ``TB_BUILDS_KEY`` stays in the environment and is read by askpass.

    Branch inspection waits 30 seconds. Add, diff, and commit wait 120.
    Push waits 300. A credential or intent failure does not replace the
    archive. A commit or push failure leaves a persisted intent pending.
    Interrupting a Git command signals its process group and, if that
    signal fails, the direct child. Reaping waits at most one second.
    Cleanup is best-effort when termination cannot be confirmed, and the
    original interruption or timeout is propagated. A push may already
    have reached the remote; interruption does not roll it back or retry it.
    Returns ``PurgeStateSnapshot`` for production, or ``None`` for stage.
    """
    email = _validate_request(image, deploy_env, checkout, remote, message)
    if deploy_env == "prod":
        require_zone_credentials(configuration, credentials)
    with BuildsGitAuth():
        with extract_pinned_content(image) as artifact:
            published = None
            _reject_git(artifact)
            if deploy_env == "prod":
                published = prepare_deployment_intent(
                    configuration,
                    artifact,
                    credentials,
                    os.fspath(checkout),
                    remote,
                    state_ref,
                    state_path,
                    identity,
                    image,
                )
            _publish_archive(checkout, artifact, remote, message, _BRANCH[deploy_env], email)
            return published


def _validate_request(image, deploy_env, checkout, remote, message):
    """Reject caller input that must not start Docker or replace an archive."""
    if deploy_env not in _BRANCH:
        raise ValueError("deployment environment must be stage or prod")
    if not digest_pinned(image):
        raise ValueError("image must be pinned by digest")
    email = _builds_setting("TB_BUILDS_GIT_EMAIL")
    token = _builds_setting("TB_BUILDS_KEY")
    if not isinstance(remote, str) or remote == "" or remote.startswith("-") or "@" in remote or any(
        character in remote for character in "\n\r\x00 \t"
    ) or token in remote:
        raise ValueError("remote must be a plain Git remote")
    if not isinstance(message, str) or any(character in message for character in "\n\r\x00"):
        raise ValueError("archive message is required")
    _require_branch(checkout, _BRANCH[deploy_env])
    return email


def _builds_setting(name):
    """Return one required builds setting without echoing its value."""
    value = os.environ.get(name)
    if not isinstance(value, str) or value == "" or any(character.isspace() or character == "\x00" for character in value):
        raise ValueError(f"{name} is required")
    return value


def _require_branch(checkout, branch):
    """Require the checkout to be the archive branch for this environment."""
    try:
        completed = _git(
            checkout,
            ["rev-parse", "--abbrev-ref", "HEAD"],
            _INSPECT_TIMEOUT,
            check=False,
        )
    except ArchivePublicationError:
        raise ValueError("archive checkout must be the deployment branch") from None
    if completed.returncode != 0 or completed.stdout.decode("utf-8", "replace").strip() != branch:
        raise ValueError("archive checkout must be the deployment branch")


class BuildsGitAuth:
    """Install the builds-key askpass program for one command.

    ``TB_BUILDS_KEY`` stays in the environment and is read by the program.
    Restoration and removal are attempted independently. A failure or
    interruption while cleaning up does not replace an entry or command
    error that has already been raised, and that original traceback is kept.
    On a successful command, a restoration failure still removes the program.
    """

    def __init__(self):
        self.script = None
        self.saved = None
        self.primary = None

    def __enter__(self):
        try:
            email = _builds_setting("TB_BUILDS_GIT_EMAIL")
            _builds_setting("TB_BUILDS_KEY")
            self.saved = {key: os.environ.get(key) for key in _AUTH_KEYS}
            self.script = _askpass_script()
            _export_auth(self.script, email)
        except BaseException as exc:
            self.primary = exc
            try:
                self._close()
            except BaseException:
                pass
            raise
        return self

    def __exit__(self, _exc_type, exc, _traceback):
        self.primary = exc
        try:
            self._close()
        except BaseException:
            if self.primary is None:
                raise
        return False

    def _close(self):
        """Restore the caller and remove the askpass program."""
        restore_error = None
        if self.saved is not None:
            saved = self.saved
            self.saved = None
            try:
                _restore_auth(saved)
            except BaseException as exc:
                restore_error = exc
        remove_error = None
        if self.script is not None:
            script = self.script
            self.script = None
            try:
                os.unlink(script)
            except OSError:
                pass
            except BaseException as exc:
                remove_error = exc
        if self.primary is not None:
            return
        for error in (restore_error, remove_error):
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise error
        if restore_error is not None:
            raise restore_error
        if remove_error is not None:
            raise remove_error


def _askpass_script():
    """Write an askpass program that reads ``TB_BUILDS_KEY`` from the environment."""
    descriptor, script = tempfile.mkstemp(prefix="tb-builds-askpass-")
    try:
        os.close(descriptor)
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  \"Username for 'https://\"*\"': \")\n"
                "    case \"$1\" in\n"
                "      *\"@\"*) exit 1 ;;\n"
                "    esac\n"
                "    printf '%s\\n' 'x-access-token'\n"
                "    ;;\n"
                "  \"Password for 'https://x-access-token@\"*\"': \")\n"
                "    printf '%s\\n' \"$TB_BUILDS_KEY\"\n"
                "    ;;\n"
                "  *) exit 1 ;;\n"
                "esac\n"
            )
        os.chmod(script, 0o700)
    except OSError:
        try:
            os.unlink(script)
        except OSError:
            pass
        raise ArchivePublicationError("archive publication failed") from None
    except (KeyboardInterrupt, SystemExit):
        try:
            os.unlink(script)
        except BaseException:
            pass
        raise
    return script


def _export_auth(script, email):
    """Point Git at askpass and the bot identity, keeping other configuration."""
    os.environ.update({
        "GIT_ASKPASS": script,
        "GIT_AUTHOR_NAME": _BOT,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": _BOT,
        "GIT_COMMITTER_EMAIL": email,
    })


def _restore_auth(saved):
    """Return the process environment to the caller's Git settings."""
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _reject_git(artifact):
    """Reject an artifact that would replace the checkout's Git directory."""
    for directory, dirnames, filenames in os.walk(artifact, followlinks=False):
        if ".git" in dirnames or ".git" in filenames:
            raise ArchivePublicationError("artifact must not contain .git")
        # A symlink is listed in dirnames but must not be walked.
        dirnames[:] = [
            name for name in dirnames
            if not os.path.islink(os.path.join(directory, name))
        ]


def _publish_archive(checkout, artifact, remote, message, branch, email):
    """Replace the site tree and push it, keeping repository metadata."""
    _remove_site(checkout)
    _copy_tree(artifact, os.fspath(checkout))
    _git(checkout, ["add", "-A"], _ARCHIVE_TIMEOUT)
    difference = _git(checkout, ["diff", "--cached", "--quiet"], _ARCHIVE_TIMEOUT, check=False)
    if difference.returncode == 1:
        _git(checkout, [
            "-c", f"user.name={_BOT}",
            "-c", f"user.email={email}",
            "commit", "-m", f"Website rebuild triggered by {message}",
        ], _ARCHIVE_TIMEOUT)
    elif difference.returncode != 0:
        raise ArchivePublicationError("archive publication failed")
    _git(checkout, ["push", remote, f"HEAD:{branch}"], _PUSH_TIMEOUT)


def _remove_site(checkout):
    """Remove top-level site entries while keeping ``.git`` and ``README.md``."""
    try:
        entries = list(os.scandir(checkout))
    except OSError:
        raise ArchivePublicationError("archive publication failed") from None
    for entry in entries:
        if entry.name in _KEEP:
            continue
        _remove_entry(entry.path)


def _remove_entry(path):
    """Remove one checkout entry without following a symbolic link."""
    try:
        if os.path.islink(path) or not os.path.isdir(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
    except OSError:
        raise ArchivePublicationError("archive publication failed") from None


def _copy_tree(source, destination):
    """Copy the artifact, preserving links and refusing ``.git``."""
    try:
        entries = list(os.scandir(source))
    except OSError:
        raise ArchivePublicationError("archive publication failed") from None
    for entry in entries:
        if entry.name == ".git":
            raise ArchivePublicationError("artifact must not contain .git")
        _copy_entry(entry, os.path.join(destination, entry.name))


def _copy_entry(entry, destination):
    """Copy one file, directory, or symbolic link without following it."""
    try:
        link = entry.is_symlink()
    except OSError:
        raise ArchivePublicationError("archive publication failed") from None
    if link:
        _clear(destination)
        try:
            os.symlink(os.readlink(entry.path), destination)
        except OSError:
            raise ArchivePublicationError("archive publication failed") from None
        return
    try:
        directory = entry.is_dir(follow_symlinks=False)
    except OSError:
        raise ArchivePublicationError("archive publication failed") from None
    if directory:
        _clear(destination)
        try:
            os.mkdir(destination)
        except OSError:
            raise ArchivePublicationError("archive publication failed") from None
        _copy_tree(entry.path, destination)
        return
    try:
        regular = entry.is_file(follow_symlinks=False)
    except OSError:
        raise ArchivePublicationError("archive publication failed") from None
    if not regular:
        raise ArchivePublicationError("archive publication failed")
    _clear(destination)
    _copy_file(entry.path, destination)


def _clear(path):
    """Remove an existing destination without following a symbolic link."""
    if not os.path.lexists(path):
        return
    _remove_entry(path)


def _copy_file(source, destination):
    """Copy one regular file without following a link at either path."""
    try:
        incoming = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ArchivePublicationError("archive publication failed") from None
    try:
        info = os.fstat(incoming)
        if not stat.S_ISREG(info.st_mode):
            raise OSError
        outgoing = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        source_file = os.fdopen(incoming, "rb")
        incoming = None
        with source_file, os.fdopen(outgoing, "wb") as target:
            shutil.copyfileobj(source_file, target)
            os.fchmod(target.fileno(), stat.S_IMODE(info.st_mode))
    except OSError:
        raise ArchivePublicationError("archive publication failed") from None
    finally:
        if incoming is not None:
            os.close(incoming)


def _stop_group(process):
    """Signal one Git process and reap it for at most one second.

    The process group is signaled first. A failed group signal is followed
    by a direct signal to the child. The wait is bounded. If that wait
    expires, termination is unconfirmed. Nothing from the command is reported.
    """
    signaled = False
    try:
        os.killpg(process.pid, signal.SIGKILL)
        signaled = True
    except BaseException:
        pass
    if not signaled:
        try:
            os.kill(process.pid, signal.SIGKILL)
        except BaseException:
            pass
    try:
        process.wait(timeout=_CLEANUP_TIMEOUT)
    except BaseException:
        pass
    for pipe in (process.stdin, process.stdout, process.stderr):
        if pipe is None:
            continue
        try:
            pipe.close()
        except BaseException:
            pass


def _git(checkout, args, timeout, check=True):
    """Run one archive Git command against ``checkout`` only.

    Redirecting variables are removed. ``credential.helper`` is cleared for
    this command, and ``LC_ALL`` is ``C``. Launch and timeout failures omit
    the command and its output. An interruption signals the process group,
    reaps for at most one second, and is propagated with its traceback.
    """
    env = os.environ.copy()
    for name in _REDIRECTED:
        env.pop(name, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    command = ["git", "-C", os.fspath(checkout), "-c", "credential.helper=", *args]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except OSError:
        raise ArchivePublicationError("archive publication failed") from None
    try:
        stdout, _stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_group(process)
        raise ArchivePublicationError("archive publication timed out") from None
    except (KeyboardInterrupt, SystemExit):
        _stop_group(process)
        raise
    if check and process.returncode != 0:
        raise ArchivePublicationError("archive publication failed")
    return subprocess.CompletedProcess((), process.returncode, stdout=stdout)
