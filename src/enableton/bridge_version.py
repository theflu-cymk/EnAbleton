"""Single source of truth for extension version and supported upstream protocol."""

VERSION = "1.8.1-ext.5"
UPSTREAM_VERSION = "1.8.1"
COMPATIBLE_VERSIONS = tuple("1.8.1-ext." + str(n) for n in range(1, 6))
