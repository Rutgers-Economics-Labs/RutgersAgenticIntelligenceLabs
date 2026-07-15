class ExecutionError(Exception):
    pass


class PermissionDeniedError(ExecutionError):
    pass


class InvalidTransitionError(ExecutionError):
    pass


class BaselineMismatchError(ExecutionError):
    pass


class IntegrationError(ExecutionError):
    pass
