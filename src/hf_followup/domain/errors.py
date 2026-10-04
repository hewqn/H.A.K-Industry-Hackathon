"""Safe errors shared by CLI, service, and HTTP adapters."""


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.status, self.retryable = code, message, status, retryable
