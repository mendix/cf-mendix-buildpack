from unittest import TestCase

from buildpack.core import runtime
from lib.m2ee.version import MXVersion

# Current supported / maintained versions
# (https://docs.mendix.com/releasenotes/studio-pro/lts-mts):
# - Mendix 7: 7.23.x (LTS)
# - Mendix 8: 8.18.x (LTS)
# - Mendix 9: 9.6.x (MTS), 9.12.x (MTS), 9.18.x (MTS), 9.24.x (LTS)


class TestCaseMxImplemented(TestCase):
    def test_mx5_not_implemented(self):
        assert not runtime.is_version_implemented(MXVersion("5.3"))

    def test_mx6_implemented(self):
        assert runtime.is_version_implemented(MXVersion("6.7.5"))


class TestCaseMxSupported(TestCase):
    def test_mx6_not_supported(self):
        assert not runtime.is_version_supported(MXVersion("6.2"))

    def test_mx7_supported(self):
        assert runtime.is_version_supported(MXVersion("7.16"))


class TestCaseMxMaintained(TestCase):
    def test_mx7_not_maintained(self):
        assert not runtime.is_version_maintained(MXVersion("7.23.1"))
        assert not runtime.is_version_maintained(MXVersion("7.16"))

    def test_mx8_maintained(self):
        assert runtime.is_version_maintained(MXVersion("8.18.1"))

    def test_mx8_not_maintained(self):
        assert not runtime.is_version_maintained(MXVersion("8.17"))

    def test_mx9_maintained(self):
        assert runtime.is_version_maintained(MXVersion("9.24.0"))

    def test_mx9_not_maintained(self):
        assert not runtime.is_version_maintained(MXVersion("9.18"))
        assert not runtime.is_version_maintained(MXVersion("9.6.9"))
        assert not runtime.is_version_maintained(MXVersion("9.12.1"))

    def test_mx10_maintained(self):
        assert runtime.is_version_maintained(MXVersion("10.6.1"))
        assert runtime.is_version_maintained(MXVersion("10.12.1"))
        assert runtime.is_version_maintained(MXVersion("10.18.1"))
        assert runtime.is_version_maintained(MXVersion("10.21.1"))

    def test_mx10_not_maintained(self):
        assert not runtime.is_version_maintained(MXVersion("10.5.1"))
