from unittest import TestCase

from lib.m2ee.client import M2EEResponse
from lib.m2ee.munin import (
    _guess_java_version,
    _get_jre_major_version_from_version_string,
)
from lib.m2ee.version import MXVersion


class TestJREVersionFromString(TestCase):
    def test_old_style_jre_versions(self):
        old_style_jre_versions = (
            ("1.8.0_202", 8),
            ("1.7.0_80", 7),
            ("1.8.0_144", 8),
        )
        for version_string, major_version in old_style_jre_versions:
            with self.subTest():
                self.assertEqual(
                    major_version,
                    _get_jre_major_version_from_version_string(version_string),
                )

    def test_new_style_jre(self):
        version_string = "11.0.3"
        self.assertEqual(
            11, _get_jre_major_version_from_version_string(version_string)
        )


class TestGuessJavaVersion(TestCase):
    def test_guess_java8(self):
        m2ee_about = M2EEResponse(
            action="about",
            json={"feedback": {"java_version": "1.8.0_202"}, "result": 0},
        )
        runtime_version = MXVersion("7.2.3.7.55882")
        stats = {}
        guessed_version = _guess_java_version(
            m2ee_about, runtime_version, stats
        )
        self.assertEqual(8, guessed_version)

    def test_guess_java11(self):
        m2ee_about = M2EEResponse(
            action="about",
            json={"feedback": {"java_version": "11.0.3"}, "result": 0},
        )
        runtime_version = MXVersion("8.7.0.1476")
        stats = {}
        guessed_version = _guess_java_version(
            m2ee_about, runtime_version, stats
        )
        self.assertEqual(11, guessed_version)

    def test_guess_mendix_6_with_missing_java_version(self):
        """All Mendix 6 versions are supposed to use Java 8.

        This is reachable in CloudV4 for Mendix runtimes <= 6.5.0, as the
        runtime there does not expose the Java version from the about response.
        """
        m2ee_about = M2EEResponse(
            action="about", json={"feedback": {}, "result": 0}
        )
        runtime_version = MXVersion("6.1.0")
        stats = {}
        guessed_version = _guess_java_version(
            m2ee_about, runtime_version, stats
        )
        self.assertEqual(8, guessed_version)

    def test_guess_mendix_5_java_7_with_missing_java_version(self):
        """For some Mendix 5 versions, Java version is not exposed, so
        you are supposed to infer the Java information from some exposed
        memory statistics.

        This code is deprecated, but I am including unit tests against the
        theoretical implementation to be on the safe side.
        This may be overly defensive.
        """
        m2ee_about = M2EEResponse(
            action="about", json={"feedback": {}, "result": 0}
        )
        runtime_version = MXVersion("5.21.0")
        stats = {"memory": {"used_nonheap": 2, "code": 1, "permanent": 1}}
        guessed_version = _guess_java_version(
            m2ee_about, runtime_version, stats
        )
        self.assertEqual(7, guessed_version)

    def test_guess_mendix_5_java_8_with_missing_java_version(self):
        """For some Mendix 5 versions, Java version is not exposed, so
        you are supposed to infer the Java information from some exposed
        memoery statistics.

        This code is deprecated, but I am including unit tests against the
        theoretical implementation to be on the safe side.
        This may be overly defensive.
        """
        m2ee_about = M2EEResponse(
            action="about", json={"feedback": {}, "result": 0}
        )
        runtime_version = MXVersion("5.21.0")
        # Non-matching values means Java 8. Apparently!
        stats = {"memory": {"used_nonheap": 0, "code": 123, "permanent": 345}}
        guessed_version = _guess_java_version(
            m2ee_about, runtime_version, stats
        )
        self.assertEqual(8, guessed_version)

    def test_guess_future_mendix_versions_doesnt_error(self):
        m2ee_about = M2EEResponse(
            action="about", json={"feedback": {}, "result": 0}
        )
        runtime_version = MXVersion("6.1.0")
        stats = {}
        guessed_version = _guess_java_version(
            m2ee_about, runtime_version, stats
        )
        self.assertEqual(8, guessed_version)
