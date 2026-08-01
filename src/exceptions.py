class GladosError(Exception):
    """Base exception with a safe, non-secret message."""


class ConfigError(GladosError):
    pass


class NetworkError(GladosError):
    pass


class AuthenticationError(GladosError):
    pass


class ProtocolError(GladosError):
    pass


class ApiRejectedError(GladosError):
    pass


class PushError(GladosError):
    pass
