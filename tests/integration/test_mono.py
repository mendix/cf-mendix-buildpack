from tests.integration import basetest


class TestCaseMono(basetest.BaseTest):
    def test_mono4_present(self):
        assert (
            "Mono available: /tmp/opt/mono-4"
            in self.stage_container("MontBlancApp720.mpk")[0]
        )

    def test_mono5_present(self):
        assert (
            "Mono available: /tmp/opt/mono-5"
            in self.stage_container("AdoptOpenJDKTest_8beta3.mpk")[0]
        )
