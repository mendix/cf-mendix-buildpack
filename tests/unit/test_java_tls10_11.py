import os
import tempfile

from unittest import TestCase, mock

from buildpack.core.java import (
    _configure_outgoing_tls_10_11,
    _get_security_properties_file,
    _get_major_version,
    ENABLE_OUTGOING_TLS_10_11_KEY,
)


class TestJavaEnableTLSv10TLSv11(TestCase):
    JAVA_SECURITY_PROPERTIES_CASES = [
        (
            r"""
jdk.tls.disabledAlgorithms=SSLv3, TLSv1, TLSv1.1, RC4, DES, MD5withRSA, \
DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, \
include jdk.disabled.namedCurves
    """,
            r"""
jdk.tls.disabledAlgorithms=SSLv3, RC4, DES, MD5withRSA, \
DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, \
include jdk.disabled.namedCurves
    """,
        ),
        (
            r"""
jdk.tls.disabledAlgorithms=SSLv3, RC4, DES, MD5withRSA, \
DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, TLSv1, TLSv1.1, \
include jdk.disabled.namedCurves
    """,
            r"""
jdk.tls.disabledAlgorithms=SSLv3, RC4, DES, MD5withRSA, \
DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, \
include jdk.disabled.namedCurves
    """,
        ),
        (
            r"""
jdk.tls.disabledAlgorithms=SSLv3, RC4, DES, MD5withRSA, TLSv1, TLSv1.1
    """,
            r"""
jdk.tls.disabledAlgorithms=SSLv3, RC4, DES, MD5withRSA
    """,
        ),
    ]

    @mock.patch.dict(
        os.environ,
        {ENABLE_OUTGOING_TLS_10_11_KEY: "true"},
        clear=True,
    )
    def test_disable_tls10_11(self):
        for case in self.JAVA_SECURITY_PROPERTIES_CASES:
            security_properties_file = tempfile.NamedTemporaryFile()

            with open(security_properties_file.name, "w+") as f:
                f.writelines(case[0])

            with mock.patch(
                "buildpack.core.java._get_security_properties_file",
                mock.MagicMock(return_value=security_properties_file.name),
            ):
                _configure_outgoing_tls_10_11("", {})

            result = ""
            with open(security_properties_file.name, "r+") as f:
                result = "".join(f.readlines())

            assert result.strip() == case[1].strip()

    SECURITY_PROPERTIES_FILES_PATHS_CASES = [
        (8, "lib"),
        (11, "conf"),
        (7, ""),
        (13, "conf"),
    ]

    def test_security_properties_file(self):
        for case in self.SECURITY_PROPERTIES_FILES_PATHS_CASES:
            if case[1] == "":
                with self.assertRaises(ValueError):
                    _get_security_properties_file("", _get_major_version(case[0]))
            else:
                file = _get_security_properties_file("", _get_major_version(case[0]))
                assert case[1] in str(file)

    MAJOR_VERSION_TEST_CASES = [
        ("8", 8),
        ("1.8.0", 8),
        ("8u372", 8),
        ("11", 11),
        ("11.0.15", 11),
        ("7", ""),
        ("13.0.15", 13),
    ]

    def test_get_major_version(self):
        for case in self.MAJOR_VERSION_TEST_CASES:
            if case[1] == "":
                with self.assertRaises(ValueError):
                    _get_major_version(case[0])
            else:
                result = _get_major_version(case[0])
                assert result == case[1]
