class ComfyOrchError(Exception):
    """Base error."""


class ValidationError(ComfyOrchError):
    pass


class ConnectionFailed(ComfyOrchError):
    pass


class QueueRejected(ComfyOrchError):
    pass


class ExecutionFailed(ComfyOrchError):
    pass


class CollectFailed(ComfyOrchError):
    pass
