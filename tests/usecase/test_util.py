import glob
import os
import tempfile
import unittest

from lib import buildpackutil


class TestDatabaseConfigOptions(unittest.TestCase):
    def test_delete_old_versions(self):
        filenames = [
            "a-a-1.0.tar.gz",
            "a-a-1.1.tar.gz",
            "a-a-1.2.zip",
            "a-b-1.0.tar.gz",
            "a-b-1.1.tar.gz",
            "a-b-1.2.zip",
        ]

        temp_dir = tempfile.TemporaryDirectory()

        files = []
        for f in filenames:
            files.append(os.path.join(temp_dir.name, f))

        for f in files:
            open(f, "a").close()

        test_file = files[0]

        buildpackutil._delete_other_versions(
            temp_dir.name, os.path.basename(test_file)
        )

        files.remove(files[1])

        result = glob.glob("%s/*.*" % temp_dir.name)

        assert set(result) == set(files)

        temp_dir.cleanup()
