from unittest import TestCase

from buildpack.core import runtime
from lib.m2ee.version import MXVersion

"""
Current supported versions (https://docs.mendix.com/releasenotes/studio-pro/lts-mts):
- Mendix 7: 7.23.x (LTS)
- Mendix 8: 8.18.x (LTS)
- Mendix 9: 9.6.x (MTS), > 9.6 (monthly / latest)
"""


class TestCaseMxNotSupported(TestCase):
    def test_mx5_notsupported(self):
        assert not runtime.is_version_supported(MXVersion("5.3.2"))


class TestCaseMxEndOfSupport(TestCase):
    def test_mx6_end_of_support(self):
        assert runtime.is_version_end_of_support(MXVersion("6.2.0"))

    def test_mx7_end_of_support(self):
        assert runtime.is_version_end_of_support(MXVersion("7.16"))

    def test_mx8_end_of_support(self):
        assert runtime.is_version_end_of_support(MXVersion("8.1.1"))

    def test_mx9_end_of_support(self):
        assert runtime.is_version_end_of_support(MXVersion("9.4.0"))
