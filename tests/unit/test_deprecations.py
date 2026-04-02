from unittest import TestCase

from buildpack.core import runtime
from lib.m2ee.version import MXVersion

# Current supported / maintained versions
# (https://docs.mendix.com/releasenotes/studio-pro/lts-mts):
# - Mendix 8: 8.18.x (Extended Support until July 2026)
# - Mendix 9: 9.24.x (LTS)
# - Mendix 10: 10.24.x (LTS)
# - Mendix 11: 11.x until 11.6 (MTS) is released (December 2025)


class TestCaseMxImplemented(TestCase):
    def test_mx5_not_implemented(self):
        assert not runtime.is_version_implemented(MXVersion("5.3"))

    def test_mx6_implemented(self):
        assert runtime.is_version_implemented(MXVersion("6.7.5"))


class TestCaseMxSupported(TestCase):
    def test_mx6_not_supported(self):
        assert not runtime.is_version_supported(MXVersion("6.2"))

    def test_mx11_supported(self):
        assert runtime.is_version_supported(MXVersion("11.6"))


class TestCaseMxExtendedSupported(TestCase):
    def test_mx7_not_extended_supported(self):
        assert not runtime.is_version_extended_supported(MXVersion("7.2"))

    def test_mx8_extended_supported(self):
        assert runtime.is_version_extended_supported(MXVersion("8.24"))


class TestCaseMxMaintained(TestCase):
    def test_mx7_not_maintained(self):
        assert not runtime.is_version_maintained(MXVersion("7.23.1"))
        assert not runtime.is_version_maintained(MXVersion("7.16"))

    def test_mx8_not_maintained(self):
        assert not runtime.is_version_maintained(MXVersion("8.17"))

    def test_mx9_maintained(self):
        assert runtime.is_version_maintained(MXVersion("9.24.0"))

    def test_mx9_not_maintained(self):
        assert not runtime.is_version_maintained(MXVersion("9.18"))
        assert not runtime.is_version_maintained(MXVersion("9.6.9"))
        assert not runtime.is_version_maintained(MXVersion("9.12.1"))

    def test_mx10_maintained(self):
        assert runtime.is_version_maintained(MXVersion("10.24.1"))

    def test_mx10_not_maintained(self):
        assert not runtime.is_version_maintained(MXVersion("10.5.1"))

    def test_mx11_maintained(self):
        assert runtime.is_version_maintained(MXVersion("11.5.1"))
