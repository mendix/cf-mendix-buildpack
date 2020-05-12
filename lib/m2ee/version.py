import re


def __to_mx_version__(version):
    if isinstance(version, MXVersion):
        return version
    if isinstance(version, (int, float)):
        version = str(version)
    return MXVersion(version)


class MXVersion:
    def __init__(self, version):
        if isinstance(version, (int, float)):
            version = str(version)
        parsed = re.match(
            "(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?(?:-(.*))?", version
        )
        if parsed is None:
            raise Exception("Could not parse version string '%s'" % version)
        groups = parsed.groups()
        self.major, self.minor, self.patch, self.hotfix = [
            int(x) if x else None for x in groups[:-1]
        ]
        self.addendum = groups[-1]

    def _numbers(self):
        v = [self.major, self.minor, self.patch, self.hotfix]
        return [x for x in v if x is not None]

    def __str__(self):
        version = ".".join(map(str, self._numbers()))
        if self.addendum:
            version = "%s-%s" % (version, self.addendum)
        return version

    def __contains__(self, other):
        if isinstance(other, str):
            other = MXVersion(other)
        s = self._numbers()
        o = other._numbers()
        if len(s) > len(o):
            return False
        for i in range(len(s)):
            if s[i] != o[i]:
                return False
        return True

    def __lt__(self, other):
        if isinstance(other, tuple):
            mxother = list(map(__to_mx_version__, other))
            return self < min(mxother) or any(
                [self // x.major and self < x for x in mxother]
            )
        return self._numbers() < __to_mx_version__(other)._numbers()

    def __le__(self, other):
        return self._numbers() <= __to_mx_version__(other)._numbers()

    def __eq__(self, other):
        if isinstance(other, tuple):
            return any([self == x for x in other])
        return self._numbers() == __to_mx_version__(other)._numbers()

    def __ge__(self, other):
        if isinstance(other, tuple):
            mxother = list(map(__to_mx_version__, other))
            return self >= max(mxother) or any(
                [self // x.major and self >= x for x in mxother]
            )
        return self._numbers() >= __to_mx_version__(other)._numbers()

    def __gt__(self, other):
        return self._numbers() > __to_mx_version__(other)._numbers()

    def __floordiv__(self, other):
        if isinstance(other, tuple):
            return any([self // x for x in other])
        return self in __to_mx_version__(other)
