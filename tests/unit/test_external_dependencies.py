import glob
import os
import tempfile
import yaml
from unittest import TestCase, mock

from buildpack.util import (
    _delete_other_versions,
    _find_file_in_directory,
    _get_dependency_artifact_url,
    _get_dependencies,
    get_dependency,
    is_path_accessible,
    mkdir_p,
    BLOBSTORE_DEFAULT_URL,
    BLOBSTORE_BUILDPACK_DEFAULT_PREFIX,
    DEPENDENCY_ARTIFACT_KEY,
    DEPENDENCY_NAME_KEY,
)


class TestExternalDependencies(TestCase):
    # Dependency test cases: YAML, expected dependency objects,
    # dependency name, overrides, expected dependency object
    DEPENDENCY_LIST_TEST_CASES = [
        # Simple test case
        (
            r"""
dependencies:
    foo:
        bar:
            version: 1.0.0
            artifact: some_location/some_archive-{{ version }}.tar.gz
""",
            {
                "foo.bar": {
                    "version": "1.0.0",
                    DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-{{ version }}.tar.gz",  # noqa: line-too-long
                    DEPENDENCY_NAME_KEY: ["foo", "bar"],
                }
            },
        ),
        # Variable / literal propagation; multiple dependencies
        (
            r"""
dependencies:
    foo:
        version: 1.0.0
        artifact: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz"
        bar:
            type: "fizz"
        baz:
            type: "buzz"
""",
            {
                "foo.bar": {
                    DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",  # noqa: line-too-long
                    "type": "fizz",
                    "version": "1.0.0",
                    DEPENDENCY_NAME_KEY: ["foo", "bar"],
                },
                "foo.baz": {
                    DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",  # noqa: line-too-long
                    "type": "buzz",
                    "version": "1.0.0",
                    DEPENDENCY_NAME_KEY: ["foo", "baz"],
                },
            },
        ),
        # Templated name, matrix expansion
        (
            r"""
dependencies:
    foo:
        "{{ type }}-{{ version_key }}":
            artifact: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz"
            type:
                - "fizz"
                - "buzz"
            version:
                - "1": 1.0.0
                - "2": 2.0.0
""",
            {
                "foo.fizz-1": {
                    DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",  # noqa: line-too-long
                    "type": "fizz",
                    "version": "1.0.0",
                    "version_key": "1",
                    DEPENDENCY_NAME_KEY: ["foo", "fizz-1"],
                },
                "foo.buzz-1": {
                    DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",  # noqa: line-too-long
                    "type": "buzz",
                    "version": "1.0.0",
                    "version_key": "1",
                    DEPENDENCY_NAME_KEY: ["foo", "buzz-1"],
                },
                "foo.fizz-2": {
                    DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",  # noqa: line-too-long
                    "type": "fizz",
                    "version": "2.0.0",
                    "version_key": "2",
                    DEPENDENCY_NAME_KEY: ["foo", "fizz-2"],
                },
                "foo.buzz-2": {
                    DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-{{ type }}-{{ version }}.tar.gz",  # noqa: line-too-long
                    "type": "buzz",
                    "version": "2.0.0",
                    "version_key": "2",
                    DEPENDENCY_NAME_KEY: ["foo", "buzz-2"],
                },
            },
        ),
    ]

    def test_external_dependency_list_generation(self):
        for case in self.DEPENDENCY_LIST_TEST_CASES:
            with mock.patch(
                "buildpack.util._get_dependency_file_contents",
                mock.MagicMock(return_value=yaml.safe_load(case[0])),
            ):
                dependencies = _get_dependencies(os.getcwd())
                assert dependencies == case[1]

    # Single ependency test cases: YAML, dependency name,
    # overrides, expected dependency object
    DEPENDENCY_TEST_CASES = [
        # Simple resolution
        (
            r"""
dependencies:
    foo:
        artifact: some_location/some_archive-{{ version }}.tar.gz
        version: 1.0.0
""",
            "foo",
            {},
            {
                "version": "1.0.0",
                DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-1.0.0.tar.gz",
                DEPENDENCY_NAME_KEY: ["foo"],
            },
        ),
        # Override existing variable
        (
            r"""
dependencies:
    foo:
        artifact: some_location/some_archive-{{ version }}.tar.gz
        version: 1.0.0
""",
            "foo",
            {"version": "2.0.0"},
            {
                "version": "1.0.0",
                DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-2.0.0.tar.gz",
                DEPENDENCY_NAME_KEY: ["foo"],
            },
        ),
        # Override missing variable
        (
            r"""
dependencies:
    foo:
        artifact: some_location/some_archive-{{ version }}.tar.gz
""",
            "foo",
            {"version": "2.0.0"},
            {
                DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-2.0.0.tar.gz",
                DEPENDENCY_NAME_KEY: ["foo"],
            },
        ),
        # Unrendered variable
        (
            r"""
dependencies:
    foo:
        artifact: some_location/some_archive-{{ version }}.tar.gz
""",
            "foo",
            {},
            {
                DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-{{ version }}.tar.gz",  # noqa: line-too-long
                DEPENDENCY_NAME_KEY: ["foo"],
            },
        ),
    ]

    def test_external_dependency_resolution(self):
        for case in self.DEPENDENCY_TEST_CASES:
            with mock.patch(
                "buildpack.util._get_dependency_file_contents",
                mock.MagicMock(return_value=yaml.safe_load(case[0])),
            ):
                dependency = get_dependency(case[1], case[2])
                assert dependency == case[3]

    # Artifact URL resolution test cases: fully resolved dependency object, expected URL
    ARTIFACT_URL_TEST_CASES = [
        # Mendix buildpack CDN relative path
        (
            {
                "version": "1.0.0",
                DEPENDENCY_ARTIFACT_KEY: "some_location/some_archive-1.0.0.tar.gz",
                DEPENDENCY_NAME_KEY: ["foo"],
            },
            f"{BLOBSTORE_DEFAULT_URL}{BLOBSTORE_BUILDPACK_DEFAULT_PREFIX}"
            "some_location/some_archive-1.0.0.tar.gz",
        ),
        # Mendix CDN absolute path
        (
            {
                "version": "1.0.0",
                DEPENDENCY_ARTIFACT_KEY: "/some_location/some_archive-1.0.0.tar.gz",
                DEPENDENCY_NAME_KEY: ["foo"],
            },
            f"{BLOBSTORE_DEFAULT_URL}/some_location/some_archive-1.0.0.tar.gz",
        ),
        # Full url
        (
            {
                "version": "1.0.0",
                DEPENDENCY_ARTIFACT_KEY: "https://myowncdn.com/some_location/some_archive-1.0.0.tar.gz",  # noqa: line-too-long
                DEPENDENCY_NAME_KEY: ["foo"],
            },
            "https://myowncdn.com/some_location/some_archive-1.0.0.tar.gz",
        ),
    ]

    def test_get_artifact_url_for_dependency(self):
        for case in self.ARTIFACT_URL_TEST_CASES:
            print(case[0])
            print(case[1])
            assert _get_dependency_artifact_url(case[0]) == case[1]

    # Works with a set of similar filenames only
    def _test_delete_old_versions(
        self, prefix, versions, index_to_keep, indexes_to_remove
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            files = []
            for version in versions:
                files.append(os.path.join(temp_dir, f"{prefix}{version}"))

            for f in files:
                open(f, "a").close()

            test_file = files[index_to_keep]

            _delete_other_versions(temp_dir, os.path.basename(test_file))

            result = glob.glob(f"{temp_dir}/*.*")

            j = 0
            for i in indexes_to_remove:
                del files[i - j]
                j += 1

        return set(result) == set(files)

    def test_delete_old_versions(self):

        # Example dependencies that we can expect:
        # - AdoptOpenJDK-jre-11.0.3-linux-x64.tar.gz
        # - mendix-8.4.1.63369.tar.gz
        # - nginx-1.15.10-linux-x64-cflinuxfs2-6247377a.tgz
        # - cf-datadog-sidecar-v0.21.2_master_103662.tar.gz

        openjdk_prefix = "AdoptOpenJDK-jre-"
        openjdk_versions = ["11.0.3-linux-x64.tar.gz"]

        assert self._test_delete_old_versions(openjdk_prefix, openjdk_versions, 0, {})

        dd_prefix = "cf-datadog-sidecar-"
        dd_versions = [
            "v0.11.1_master_78318.tar.gz",
            "v0.21.1_master_98363.tar.gz",
            "v0.21.2_master_103662.zip",
        ]

        assert self._test_delete_old_versions(dd_prefix, dd_versions, 0, [1])

        mx_prefix = "mendix-"
        mx_versions = [
            "8.4.1.63369.tar.gz",
            "8.5.0.64176.tar.gz",
            "8.6.1.1701.tar.gz",
            "8.7.0.1476.tar.gz",
        ]

        assert self._test_delete_old_versions(mx_prefix, mx_versions, 1, [0, 2, 3])

        ng_prefix = "nginx-"
        ng_versions = ["1.15.10-linux-x64-cflinuxfs2-6247377a.tgz"]

        assert self._test_delete_old_versions(ng_prefix, ng_versions, 0, {})

    def test_find_file_in_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_names = [
                "dependency1.zip",
                "a/dependency2.zip",
                "a/b/dependency3.zip",
                "dependency4.zip/dependency4.zip",
            ]
            files = [os.path.join(temp_dir, f) for f in file_names]
            for file_name in files:
                mkdir_p(os.path.dirname(file_name))
                open(file_name, "a").close()

            for file_name in file_names:
                result = _find_file_in_directory(os.path.basename(file_name), temp_dir)
                assert result and is_path_accessible(result) and os.path.isfile(result)
