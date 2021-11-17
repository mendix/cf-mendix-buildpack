from unittest import TestCase

from buildpack.core import runtime
from lib.m2ee.version import MXVersion


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
