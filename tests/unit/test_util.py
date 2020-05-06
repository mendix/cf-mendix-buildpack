import glob
import os
import tempfile
import unittest

from buildpack import util


class TestUtil(unittest.TestCase):

    # Works with a set of similar filenames only
    def _test_delete_old_versions(
        self, prefix, versions, index_to_keep, indexes_to_remove
    ):
        temp_dir = tempfile.TemporaryDirectory()

        files = []
        for version in versions:
            files.append(
                os.path.join(temp_dir.name, "{}{}".format(prefix, version))
            )

        for f in files:
            open(f, "a").close()

        test_file = files[index_to_keep]

        util._delete_other_versions(temp_dir.name, os.path.basename(test_file))

        result = glob.glob("%s/*.*" % temp_dir.name)

        j = 0
        for i in indexes_to_remove:
            del files[i - j]
            j += 1

        temp_dir.cleanup()

        return set(result) == set(files)

    def test_delete_old_versions(self):

        # Example dependencies that we can expect:
        # - AdoptOpenJDK-jre-11.0.3-linux-x64.tar.gz
        # - mendix-8.4.1.63369.tar.gz
        # - nginx-1.15.10-linux-x64-cflinuxfs2-6247377a.tgz
        # - cf-datadog-sidecar-v0.21.2_master_103662.tar.gz

        openjdk_prefix = "AdoptOpenJDK-jre-"
        openjdk_versions = ["11.0.3-linux-x64.tar.gz"]

        assert self._test_delete_old_versions(
            openjdk_prefix, openjdk_versions, 0, {}
        )

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

        assert self._test_delete_old_versions(
            mx_prefix, mx_versions, 1, [0, 2, 3]
        )

        ng_prefix = "nginx-"
        ng_versions = ["1.15.10-linux-x64-cflinuxfs2-6247377a.tgz"]

        assert self._test_delete_old_versions(ng_prefix, ng_versions, 0, {})
