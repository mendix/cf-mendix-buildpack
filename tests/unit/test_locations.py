import json
import unittest

from buildpack.core import nginx, runtime

# Custom locations test cases
# (access restrictions custom locations environment variable,
# custom locations expected in result,
# custom locations not expected in result,
# access restrictions expected in result)
CUSTOM_LOCATIONS_CASES = [
    # Simple custom location
    (
        "{}",
        """
{
    "/a_location": {
        "body": "internal;"
    }
}
""",
        [nginx.Location(path="/a_location", body="internal;")],
        [],
        [],
    ),
    # More parameters than just "body", don't expect the location to be present
    (
        "{}",
        """
{
    "/a_location": {
        "body": "internal;",
        "another_param": "something"
    }
}
""",
        [],
        [nginx.Location(path="/a_location", body="internal;")],
        [],
    ),
    # Override by access restriction
    (
        """
{
    "/a_location": {
        "ipfilter": ["10.0.0.0/8"]
    }
}
""",
        """
{
    "/a_location": {
        "body": "internal;",
        "another_param": "something"
    }
}
""",
        [],
        [nginx.Location(path="/a_location", body="internal;")],
        [nginx.Location(path="/a_location", ipfilter_ips=["10.0.0.0/8"])],
    ),
]


class TestCaseLocationUtilFunctions(unittest.TestCase):
    def test_get_paths_from_templates(self):
        test_templates = [
            {"swagger": "2.0", "basePath": "/api/1"},
            {"swagger": "2.0", "basePath": "/api/2", "value": "jdjdj\r\n\r\n"},
            {"swagger": "2.0", "basePatth": "/api/3"},
            "",
        ]

        result = runtime._get_paths_from_swagger_templates(
            [json.dumps(t) for t in test_templates]
        )

        assert "/api/1" in result
        assert "/api/2" in result
        assert "/api/3" not in result

    def test_special_chars_in_template_path(self):
        for char in list("/.-_~!$&'()*+,;=:@"):
            path = f"/rest/my{char}api/v1"
            template = {"swagger": "2.0", "basePath": path}
            assert path in runtime._get_paths_from_swagger_templates(
                [json.dumps(template)]
            )

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

    def test_custom_locations(self):
        for case in CUSTOM_LOCATIONS_CASES:
            locations = nginx._get_locations(
                access_restrictions=json.loads(case[0]),
                custom_locations=json.loads(case[1]),
            )
            assert all(x in locations for x in case[2])
            assert not any(x in locations for x in case[3])
            assert all(x in locations for x in case[4])
