"""Digest selection for the image this deployment run pushed."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import deployment_image as image
import deployment_readiness as readiness


REGISTRY = "123456789012.dkr.ecr.us-west-2.amazonaws.com"
TAG = "0123456789abcdef0123456789abcdef01234567"
MANIFEST = "a" * 64
CONFIG = "b" * 64
OTHER = "c" * 64
DECOY = "d" * 64
INDEX = "e" * 64
MANIFEST_TYPE = "application/vnd.docker.distribution.manifest.v2+json"
INDEX_TYPE = "application/vnd.oci.image.index.v1+json"
CONFIG_TYPE = "application/vnd.oci.image.config.v1+json"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml"


class Docker:
    """Record the build command and write the metadata file the test supplies."""

    def __init__(self, writer, returncode=0):
        self.writer = writer
        self.returncode = returncode
        self.calls = []
        self.kwargs = []

    def run(self, args, **kwargs):
        self.calls.append(list(args))
        self.kwargs.append(kwargs)
        sys.stdout.write(f"latest: digest: sha256:{DECOY}\n")
        sys.stdout.flush()
        if "--metadata-file" in args:
            self.writer(args[args.index("--metadata-file") + 1])
        return subprocess.CompletedProcess(args, self.returncode)


def _install(monkeypatch, writer, returncode=0):
    """Replace Docker with a stub that cannot reach a registry."""
    docker = Docker(writer, returncode)
    monkeypatch.setattr(image.subprocess, "run", docker.run)
    return docker


def _repository(deploy_env):
    return f"{REGISTRY}/thunderbird-website-{deploy_env}"


def _valid(repository, manifest=MANIFEST, descriptor=None, names=None, media_type=MANIFEST_TYPE):
    """Return Buildx metadata whose root digest differs from the config id."""
    if descriptor is None:
        descriptor = manifest
    if names is None:
        names = f"{repository}:{TAG},{repository}:latest"
    return {
        "containerimage.digest": f"sha256:{manifest}",
        "containerimage.config.digest": f"sha256:{CONFIG}",
        "containerimage.descriptor": {
            "mediaType": media_type,
            "digest": f"sha256:{descriptor}",
            "size": 1234,
        },
        "image.name": names,
    }


def _writer(payload=None, raw=None, skip=False):
    """Write one metadata file when the build command runs."""
    def write(path):
        if skip:
            return
        if raw is not None:
            with open(path, "wb") as handle:
                handle.write(raw)
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    return write


def _publish(monkeypatch, tmp_path, deploy_env, writer, returncode=0):
    """Publish into a temporary workflow output file."""
    output = tmp_path / "github_output"
    output.write_text("existing=kept\n")
    docker = _install(monkeypatch, writer, returncode)
    reference = image.publish_pinned_image(REGISTRY, TAG, deploy_env, str(output))
    return docker, output, reference


class TestDeploymentImage:
    """The workflow output is the manifest digest of this push."""

    @pytest.mark.parametrize("deploy_env, branch", [("stage", "master"), ("prod", "prod")])
    def test_successful_selection_is_shared_by_extraction_and_deployment(self, monkeypatch, tmp_path, deploy_env, branch):
        """One manifest reference feeds docker create and Pulumi's IMAGE_URI."""
        repository = _repository(deploy_env)
        docker, output, reference = _publish(monkeypatch, tmp_path, deploy_env, _writer(_valid(repository)))

        metadata_path = docker.calls[0][docker.calls[0].index("--metadata-file") + 1]
        assert docker.calls == [[
            "docker", "buildx", "build",
            "--push",
            "--provenance=false",
            "--metadata-file", metadata_path,
            "-f", "docker/Dockerfile",
            "--build-arg", f"BUILD_ENV={deploy_env}",
            "--build-arg", f"REPO_BRANCH={branch}",
            "-t", f"{repository}:{TAG}",
            "-t", f"{repository}:latest",
            ".",
        ]]
        assert docker.kwargs == [{}]
        assert reference == f"{repository}@sha256:{MANIFEST}"
        assert readiness.digest_pinned(reference)
        assert output.read_text() == f"existing=kept\nimage_uri={reference}\n"
        assert f"sha256:{CONFIG}" not in reference
        assert f"sha256:{DECOY}" not in reference

    def test_main_uses_the_deployment_environment(self, monkeypatch, tmp_path):
        """The workflow entry point reads DEPLOY_ENV, not a separate image selector."""
        output = tmp_path / "github_output"
        repository = _repository("prod")
        monkeypatch.setenv("ECR_REGISTRY", REGISTRY)
        monkeypatch.setenv("IMAGE_TAG", TAG)
        monkeypatch.setenv("DEPLOY_ENV", "prod")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        docker = _install(monkeypatch, _writer(_valid(repository)))

        image.main()

        assert "BUILD_ENV=prod" in docker.calls[0]
        assert "REPO_BRANCH=prod" in docker.calls[0]
        assert output.read_text() == f"image_uri={repository}@sha256:{MANIFEST}\n"

    @pytest.mark.parametrize("payload, raw, message", [
        ({"containerimage.config.digest": f"sha256:{CONFIG}", "image.name": "repo:tag"}, None, "digest is missing"),
        (_valid(_repository("stage"), manifest="A" * 64), None, "digest is malformed"),
        (_valid(_repository("stage"), manifest="a" * 63), None, "digest is malformed"),
        (None, b"{", "metadata is malformed"),
        (None, b"[]", "metadata is malformed"),
    ])
    def test_missing_or_malformed_digest_is_not_published(self, monkeypatch, tmp_path, payload, raw, message):
        """A config id, push log, or unreadable file cannot become the output."""
        writer = _writer(payload, raw) if raw is not None or payload is not None else _writer(skip=True)
        output = tmp_path / "github_output"
        output.write_text("existing=kept\n")
        _install(monkeypatch, writer)

        with pytest.raises(image.ImagePinError, match=message):
            image.publish_pinned_image(REGISTRY, TAG, "stage", str(output))
        assert output.read_text() == "existing=kept\n"

    def test_missing_metadata_file_is_not_published(self, monkeypatch, tmp_path):
        """A successful command that wrote no metadata still has no digest."""
        output = tmp_path / "github_output"
        output.write_text("existing=kept\n")
        _install(monkeypatch, _writer(skip=True))

        with pytest.raises(image.ImagePinError, match="digest is missing"):
            image.publish_pinned_image(REGISTRY, TAG, "stage", str(output))
        assert output.read_text() == "existing=kept\n"

    @pytest.mark.parametrize("names", [
        f"other.example/thunderbird-website-stage:{TAG}",
        ",",
    ])
    def test_wrong_repository_metadata_is_rejected(self, monkeypatch, tmp_path, names):
        """Metadata for another repository, or for none, is not reused."""
        repository = _repository("stage")
        payload = _valid(repository, names=names)
        output = tmp_path / "github_output"
        output.write_text("existing=kept\n")
        _install(monkeypatch, _writer(payload))

        with pytest.raises(image.ImagePinError, match="repository does not match"):
            image.publish_pinned_image(REGISTRY, TAG, "stage", str(output))
        assert output.read_text() == "existing=kept\n"

    @pytest.mark.parametrize("payload", [
        _valid(_repository("stage"), descriptor=OTHER),
        _valid(
            _repository("stage"),
            names=f"{_repository('stage')}:{TAG},{_repository('stage')}@sha256:{OTHER}",
        ),
    ])
    def test_ambiguous_metadata_is_rejected(self, monkeypatch, tmp_path, payload):
        """Disagreeing descriptor and name digests do not choose a winner."""
        output = tmp_path / "github_output"
        output.write_text("existing=kept\n")
        _install(monkeypatch, _writer(payload))

        with pytest.raises(image.ImagePinError, match="digest is ambiguous"):
            image.publish_pinned_image(REGISTRY, TAG, "stage", str(output))
        assert output.read_text() == "existing=kept\n"

    def test_diagnostics_stream_and_a_failed_build_is_not_published(self, capfd, monkeypatch, tmp_path):
        """Build output stays visible, and a failed build writes no image_uri."""
        script = (
            "import sys\n"
            "sys.stdout.write('build-progress-visible\\n')\n"
            "sys.stdout.flush()\n"
            "sys.stderr.write('build-failure-visible\\n')\n"
            "sys.stderr.flush()\n"
            "raise SystemExit(1)\n"
        )
        with pytest.raises(image.ImagePinError, match="^deployment image command failed$") as caught:
            image._run([sys.executable, "-c", script])
        captured = capfd.readouterr()
        assert captured.out == "build-progress-visible\n"
        assert captured.err == "build-failure-visible\n"
        assert "build-progress-visible" not in str(caught.value)
        assert "build-failure-visible" not in str(caught.value)

        with pytest.raises(image.ImagePinError, match="^deployment image command failed$") as caught:
            image._run(["/tmp/missing-docker-binary"])
        assert "missing-docker-binary" not in str(caught.value)

        output = tmp_path / "github_output"
        output.write_text("existing=kept\n")
        _install(monkeypatch, _writer(_valid(_repository("stage"))), returncode=1)
        with pytest.raises(image.ImagePinError, match="command failed"):
            image.publish_pinned_image(REGISTRY, TAG, "stage", str(output))
        assert output.read_text() == "existing=kept\n"

    @pytest.mark.parametrize("media_type", [
        INDEX_TYPE,
        "application/vnd.docker.distribution.manifest.list.v2+json",
    ])
    def test_root_index_digest_is_selected_instead_of_the_config_id(self, monkeypatch, tmp_path, media_type):
        """An image index is pinned by its own digest, not the configuration id."""
        repository = _repository("stage")
        payload = _valid(repository, manifest=INDEX, media_type=media_type)
        _docker, output, reference = _publish(monkeypatch, tmp_path, "stage", _writer(payload))

        assert reference == f"{repository}@sha256:{INDEX}"
        assert f"sha256:{CONFIG}" not in reference
        assert output.read_text().endswith(f"image_uri={reference}\n")

    def test_config_media_type_is_not_published(self, monkeypatch, tmp_path):
        """A configuration blob is not accepted as the root manifest."""
        repository = _repository("stage")
        payload = _valid(repository, manifest=CONFIG, media_type=CONFIG_TYPE)
        output = tmp_path / "github_output"
        output.write_text("existing=kept\n")
        _install(monkeypatch, _writer(payload))

        with pytest.raises(image.ImagePinError, match="digest is malformed"):
            image.publish_pinned_image(REGISTRY, TAG, "stage", str(output))
        assert output.read_text() == "existing=kept\n"

    def test_command_failure_does_not_publish_metadata_or_a_tag(self, monkeypatch, tmp_path):
        """A failed push is terminal even when the metadata file looks valid."""
        repository = _repository("stage")
        output = tmp_path / "github_output"
        output.write_text("existing=kept\n")
        docker = _install(monkeypatch, _writer(_valid(repository)), returncode=1)

        with pytest.raises(image.ImagePinError, match="command failed"):
            image.publish_pinned_image(REGISTRY, TAG, "stage", str(output))
        assert len(docker.calls) == 1
        assert output.read_text() == "existing=kept\n"
        assert f"sha256:{MANIFEST}" not in output.read_text()
        assert ":latest" not in output.read_text()

    @pytest.mark.parametrize("registry, tag, deploy_env, output_name, message", [
        ("", TAG, "stage", "out", "repository is invalid"),
        (REGISTRY, "latest", "stage", "out", "tag is invalid"),
        (REGISTRY, TAG, "preview", "out", "environment must be stage or prod"),
        (REGISTRY, TAG, "stage", "", "output path is missing"),
    ])
    def test_invalid_inputs_do_not_run_docker(self, monkeypatch, tmp_path, registry, tag, deploy_env, output_name, message):
        """Caller errors fail before a build or a mutable-tag fallback."""
        def refuse(*_args, **_kwargs):
            raise AssertionError("docker started")

        monkeypatch.setattr(image.subprocess, "run", refuse)
        output = "" if output_name == "" else str(tmp_path / output_name)

        with pytest.raises(image.ImagePinError, match=message):
            image.publish_pinned_image(registry, tag, deploy_env, output)

    def test_workflow_consumers_use_the_published_digest(self, monkeypatch, tmp_path):
        """Extraction and Pulumi receive the digest published by this workflow."""
        workflow = yaml.safe_load(WORKFLOW.read_text())
        job = workflow["jobs"]["deploy"]
        steps = job["steps"]
        build = _step(steps, step_id="build-image")
        assert build["run"] == "python3 deployment_image.py"
        assert "DEPLOY_ENV" in job["env"]
        assert "DEPLOY_ENV" not in build["env"]

        context = {
            "github": {"sha": TAG},
            "steps": {"ecr-login": {"outputs": {"registry": REGISTRY}}},
        }
        assert _resolve(build["env"]["ECR_REGISTRY"], context) == REGISTRY
        assert _resolve(build["env"]["IMAGE_TAG"], context) == TAG

        output = tmp_path / "github_output"
        monkeypatch.setenv("ECR_REGISTRY", REGISTRY)
        monkeypatch.setenv("IMAGE_TAG", TAG)
        monkeypatch.setenv("DEPLOY_ENV", "stage")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("SECRET_TOKEN", "secret-workflow-token")
        repository = _repository("stage")
        docker = _install(monkeypatch, _writer(_valid(repository)))

        image.main()

        published = _output_value(output, "image_uri")
        assert readiness.digest_pinned(published)
        assert published == f"{repository}@sha256:{MANIFEST}"
        assert "secret-workflow-token" not in " ".join(" ".join(args) for args in docker.calls)
        assert "BUILD_ENV=stage" in docker.calls[0]
        assert "REPO_BRANCH=master" in docker.calls[0]
        context["steps"]["build-image"] = {"outputs": _output_map(output)}

        extract = _step(steps, name="Publish to tb-website-builds")
        pulumi = _step(steps, name="Deploy infrastructure")
        assert extract["run"].splitlines()[0] == "docker create --name extract $IMAGE_URI"
        assert _resolve(extract["env"]["IMAGE_URI"], context) == published
        assert _resolve(pulumi["env"]["IMAGE_URI"], context) == published
        assert pulumi["uses"].startswith("pulumi/actions@")

        for consumer in (extract, pulumi):
            wrong = dict(consumer["env"])
            wrong["IMAGE_URI"] = "${{ steps.build-image.outputs.tag }}"
            with pytest.raises(KeyError):
                _resolve(wrong["IMAGE_URI"], context)


def _step(steps, step_id=None, name=None):
    """Return one workflow step by its id or name."""
    for step in steps:
        if step_id is not None and step.get("id") == step_id:
            return step
        if name is not None and step.get("name") == name:
            return step
    raise AssertionError(step_id or name)


def _expression(value):
    """Return the dotted path of one exact ``${{ }}`` expression."""
    if not isinstance(value, str):
        raise AssertionError(value)
    match = re.fullmatch(r"\$\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", value)
    if match is None:
        raise AssertionError(value)
    return match.group(1).split(".")


def _resolve(value, context):
    """Resolve one workflow output or context path, without evaluating operators."""
    node = context
    for part in _expression(value):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(value)
        node = node[part]
    return node


def _output_map(path):
    """Return the key/value pairs written to a GitHub output file."""
    outputs = {}
    for line in Path(path).read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            outputs[key] = value
    return outputs


def _output_value(path, name):
    """Return one published output."""
    return _output_map(path)[name]
