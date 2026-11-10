"""Publish the registry digest of the image this deployment run pushed.

Buildx writes structured metadata for that push. The output reference is
``repository@sha256:<root digest>``. That digest is the image manifest, or
the image index when the registry stores one. The local image configuration
id is a different hash. The git and ``latest`` tags remain mutable names.
Those tags are still published. They are not the reference used to extract
the archived site or to set Pulumi's ``IMAGE_URI``.

Provenance attestations stay disabled. The previous ``docker build`` and
``docker push`` published one image manifest. Buildx would otherwise make
the pushed root digest an attestation index.
"""

import json
import os
import subprocess
import tempfile

from deployment_readiness import digest_pinned


# Root objects Buildx may record. Configuration blobs are not in this set.
_ROOT_MEDIA_TYPES = frozenset({
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
})


class ImagePinError(Exception):
    """The pushed image could not be identified by a registry manifest digest."""


def publish_pinned_image(registry, image_tag, deploy_env, output_path):
    """Push the stage or production image and record its root manifest digest.

    ``deploy_env`` selects the ECR repository and the ``REPO_BRANCH`` of the
    external repositories cloned during the image build. ``stage`` uses
    ``thunderbird-website-stage`` and external branch ``master``. ``prod``
    uses ``thunderbird-website-prod`` and external branch ``prod``. The
    website files are the checked-out build context, not that branch name.
    The digest comes from this invocation's metadata file.
    """
    repository = _repository(registry, deploy_env)
    _image_tag(image_tag)
    _output_path(output_path)
    branch = "prod" if deploy_env == "prod" else "master"
    with tempfile.TemporaryDirectory() as directory:
        metadata_path = os.path.join(directory, "image-metadata.json")
        # Keep the single image manifest published by the previous docker build/push.
        # Buildx provenance would replace that root digest with an attestation index.
        _run([
            "docker", "buildx", "build",
            "--push",
            "--provenance=false",
            "--metadata-file", metadata_path,
            "-f", "docker/Dockerfile",
            "--build-arg", f"BUILD_ENV={deploy_env}",
            "--build-arg", f"REPO_BRANCH={branch}",
            "-t", f"{repository}:{image_tag}",
            "-t", f"{repository}:latest",
            ".",
        ])
        metadata = _read_metadata(metadata_path)
    reference = select_manifest_reference(repository, metadata)
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"image_uri={reference}\n")
    return reference


def select_manifest_reference(repository, metadata):
    """Return ``repository@sha256:<digest>`` for the pushed root object.

    ``containerimage.digest`` is the registry manifest or image-index digest.
    ``containerimage.config.digest`` is the local image id and is never
    selected. A missing, malformed, or disagreed digest fails closed.
    """
    if not isinstance(metadata, dict) or "containerimage.digest" not in metadata:
        raise ImagePinError("registry manifest digest is missing")
    manifest = metadata["containerimage.digest"]
    if not isinstance(manifest, str) or manifest == "":
        raise ImagePinError("registry manifest digest is malformed")
    reference = f"{repository}@{manifest}"
    if not digest_pinned(reference):
        raise ImagePinError("registry manifest digest is malformed")
    _confirm_descriptor(metadata, manifest)
    _confirm_names(repository, metadata, manifest)
    return reference


def main():
    """Publish the digest selected by the deployment workflow environment."""
    publish_pinned_image(
        os.environ.get("ECR_REGISTRY"),
        os.environ.get("IMAGE_TAG"),
        os.environ.get("DEPLOY_ENV"),
        os.environ.get("GITHUB_OUTPUT"),
    )


def _repository(registry, deploy_env):
    """Return the ECR repository for the selected deployment environment."""
    if deploy_env not in {"stage", "prod"}:
        raise ImagePinError("deployment environment must be stage or prod")
    if not isinstance(registry, str) or registry == "" or registry.startswith("-") or any(
        character in registry for character in "\n\r\t /@:"
    ):
        raise ImagePinError("image repository is invalid")
    return f"{registry}/thunderbird-website-{deploy_env}"


def _image_tag(value):
    """Reject a missing or unsafe published tag.

    The tag is not an immutable image identity. ``latest`` remains the
    separate floating tag and cannot also be the commit tag.
    """
    if (
        not isinstance(value, str)
        or value in {"", "latest"}
        or value.startswith("-")
        or any(character in value for character in "\n\r\t @:/")
    ):
        raise ImagePinError("image tag is invalid")


def _output_path(value):
    """Reject a missing workflow output file before Docker starts."""
    if not isinstance(value, str) or value == "" or "\x00" in value:
        raise ImagePinError("image output path is missing")


def _run(args):
    """Run one Docker command and stream its output to the caller.

    Logs are not stored or parsed. A missing executable or a nonzero exit
    becomes ``ImagePinError`` without the command output.
    """
    try:
        completed = subprocess.run(args)
    except OSError:
        raise ImagePinError("deployment image command failed") from None
    if completed.returncode != 0:
        raise ImagePinError("deployment image command failed")


def _read_metadata(path):
    """Return the metadata object written by this build."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        raise ImagePinError("registry manifest digest is missing") from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (AttributeError, ValueError, OverflowError, RecursionError):
        raise ImagePinError("image metadata is malformed") from None
    if not isinstance(payload, dict):
        raise ImagePinError("image metadata is malformed")
    return payload


def _confirm_descriptor(metadata, manifest):
    """Require a present descriptor to name the same root manifest or index."""
    descriptor = metadata.get("containerimage.descriptor")
    if descriptor is None:
        return
    if not isinstance(descriptor, dict) or descriptor.get("digest") != manifest:
        raise ImagePinError("registry manifest digest is ambiguous")
    media_type = descriptor.get("mediaType")
    if media_type is None:
        return
    if not isinstance(media_type, str) or media_type not in _ROOT_MEDIA_TYPES:
        raise ImagePinError("registry manifest digest is malformed")


def _confirm_names(repository, metadata, manifest):
    """Require every recorded image name to be this repository and digest."""
    value = metadata.get("image.name")
    if not isinstance(value, str):
        raise ImagePinError("registry manifest repository does not match")
    names = [part.strip() for part in value.split(",") if part.strip()]
    if not names:
        raise ImagePinError("registry manifest repository does not match")
    for name in names:
        recorded_repository, recorded_digest = _split_reference(name)
        if recorded_repository != repository:
            raise ImagePinError("registry manifest repository does not match")
        if recorded_digest not in {None, manifest}:
            raise ImagePinError("registry manifest digest is ambiguous")


def _split_reference(reference):
    """Return the repository and any digest embedded in one recorded name."""
    if reference.count("@") > 1:
        raise ImagePinError("image metadata is malformed")
    name, separator, recorded = reference.rpartition("@")
    if not separator:
        name = reference
        recorded = None
    slash = name.rfind("/")
    colon = name.rfind(":")
    if colon > slash:
        name = name[:colon]
    if name == "":
        raise ImagePinError("image metadata is malformed")
    return name, recorded


if __name__ == "__main__":
    main()
