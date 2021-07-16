import unittest

from buildpack import nginx, runtime


class TestCaseLocationUtilFunctions(unittest.TestCase):
    def test_get_paths_from_templates(self):
        TEST_SWAGGER_TEMPLATES = [
            r'{"swagger":"2.0","basePath":"/api/1"}',
            r'{"swagger":"2.0","basePath":"/api/2","value":"jdjdj\r\n\r\n"}',
            r'{"swagger":"2.0","basePatth":"/api/3"}',
            "",
        ]

        result = runtime._get_paths_from_swagger_templates(
            TEST_SWAGGER_TEMPLATES
        )

        assert "/api/1" in result
        assert "/api/2" in result
        assert "/api/3" not in result

    def test_get_most_specific_location_config(self):
        locations = {}

        assert nginx._get_most_specific_location_config("/", locations) == {}

        locations = {
            "/path1/subpath1": "somevalue1",
            "/path1": "somevalue2",
            "/path3": "somevalue3",
            "/path1/subpath1/sub": "somevalue4",
        }

        assert (
            nginx._get_most_specific_location_config(
                "/path1/subpath1/subpath2", locations
            )
            == "somevalue1"
        )

    def test_is_subpath_of(self):
        paths = ["/1/2/3/", "/1/2/3/4/", "/1/22"]

        assert not nginx._is_subpath_of("/1/2", paths)
        assert not nginx._is_subpath_of("/1/2/33/4", paths)
        assert not nginx._is_subpath_of("/1/222", paths)
        assert not nginx._is_subpath_of("/1/2/4/3/", paths)
