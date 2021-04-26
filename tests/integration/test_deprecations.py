from tests.integration import basetest


class TestCaseMxNotSupported(basetest.BaseTest):
    def test_mx5_notsupported(self):
        with self.assertRaises(RuntimeError):
            self.stage_container("mx5.3.2_app.mda")


class TestCaseMxEndOfSupport(basetest.BaseTest):
    def _test_end_of_support(self, application):
        assert "] is end-of-support" in self.stage_container(application)[0]

    def test_mx6_end_of_support(self):
        self._test_end_of_support("sample-6.2.0.mda")

    def test_mx7_end_of_support(self):
        self._test_end_of_support("BuildpackTestApp-mx-7-16.mda")

    def test_mx8_end_of_support(self):
        self._test_end_of_support("Mendix8.1.1.58432_StarterApp.mda")
