"""EnAbleton: a versioned extension layer over Ableton Live MCP."""

__version__ = "0.1.0b2"

from .port import apply_client_environment

# The pinned upstream client reads ABLETON_PORT at import time. Mapping the
# documented ENABLETON_PORT here covers every entry point, including the
# generated bridge's build and the stdio server.
apply_client_environment()
